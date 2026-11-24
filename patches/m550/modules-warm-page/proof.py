#!/usr/bin/env python3
"""Independently rebuild and verify warm canonical-page projection optimization."""
from pathlib import Path
import argparse, hashlib, json, os, re, statistics, subprocess, tarfile, tomllib

D=Path(__file__).resolve().parent
M='a04006ac24402104fc7366d6c41fd2090c7a8add508f28e0980522e0f98e70d1'
C='daa6e425662389dbdcef1c555320a149dc719b3cb8ad88317858c7c44d9dd9eb'
CORE='Proteus-core-0c1b7572313230e5d123e95c722e1258a2e9ecd6/'
PATCH='1b44c741a22d10bb5590d54e9988730f04e9a914fa0cd5d4ad9fcf78690752ad'
STORAGE='storage/session-storage/'
def h(data):return hashlib.sha256(data).hexdigest()
def oh(data):return hashlib.sha1(f'blob {len(data)}\0'.encode()+data).hexdigest()
def put(dst,data,mode=0o644):
 dst.parent.mkdir(exist_ok=True,parents=True);dst.write_bytes(data);dst.chmod(mode)
def read_archives(mod,core):
 assert h(mod.read_bytes())==M and h(core.read_bytes())==C
 with tarfile.open(mod) as f:
  pkgs=tomllib.loads(f.extractfile('Cargo.lock').read().decode())['package']
  before={n.name:(n.mode,f.extractfile(n).read()) for n in f if n.name.startswith(STORAGE) and n.isfile()}
 with tarfile.open(core) as f:
  sdk={n.name.removeprefix(CORE):(n.mode,f.extractfile(n).read()) for n in f if n.isfile() and n.name.startswith(tuple(CORE+'crates/'+c+'/' for c in ['proteus-contracts','proteus-session-semantics']))}
 assert len(before)+len(sdk)==184
 return before,sdk,pkgs
def checks(lock,up,vendor):
 pkgs={(p['name'],p['version']):p for p in up}
 for p in tomllib.loads(lock.decode())['package']:
  q=pkgs[(p['name'],p['version'])]
  if 'source' in p:
   assert p['source']==q['source'] and p['checksum']==q['checksum']
   attestation=vendor/f'{p["name"]}-{p["version"]}'/'.cargo-checksum.json'
   assert json.loads(attestation.read_bytes())['package']==p['checksum']
  elif p['name'] in ['proteus-contracts','proteus-session-semantics']:
   assert q['source'].endswith('#0c1b7572313230e5d123e95c722e1258a2e9ecd6')
  else:assert p['name']=='session-storage'
def capture(build_log,exe,logfile):
 p=subprocess.run([str(exe),'--test-threads=1','--nocapture','--color','never'],capture_output=True,text=True)
 logfile.write_text(p.stdout+p.stderr);p.check_returncode()
 assert re.search(r'test result: ok\. 101 passed; 0 failed; 2 ignored;',p.stdout)
 rows={}
 for match in re.finditer(r'WARM (\w+) (\d+) (\w+) ((?:\d+ ){5}\d+)',p.stdout):
  kind,n,tag,v=match.groups()
  rows[f'{kind}-{n}-{tag}']=list(map(int,v.split()))[:5]
 assert len(rows)==12,rows
 return dict(binary_sha256=h(exe.read_bytes()),log_sha256=h(logfile.read_bytes()),compile_log_sha256=h(build_log.read_bytes()),rows=rows)
def paired_capture(exe,work,mode,logfile):
 f=work/'fixture.json'
 env=dict(os.environ,TMPDIR=str(work),PROTEUS_PAGE_METER_MODE=mode,PROTEUS_PAGE_METER_MANIFEST=str(f))
 p=subprocess.run([str(exe),'--ignored','--test-threads=1','--nocapture','--color','never',
                  'warm_page_same_corpus_allocator'],capture_output=True,text=True,env=env)
 logfile.write_text(p.stdout+p.stderr);p.check_returncode()
 assert re.search(r'test result: ok\. 1 passed; 0 failed; 0 ignored;',p.stdout)
 if mode=='seed':return
 return paired_rows(p.stdout)
def paired_rows(out):
 cases={}
 for m in re.finditer(r'PAIRED (\w+) (\d+) (\w+) ((?:\d+ ){5})([0-9a-f]{64})',out):
  k,n,role,data,h=m.groups()
  cases.setdefault(f'{k}-{n}-{role}',[]).append([*map(int,data.split()),h])
 assert len(cases)==12 and all(len(v)==7 for v in cases.values())
 return cases
def compare(o):
 receipt={}
 for mode,pair in o.items():
  assert pair['baseline']['binary_sha256']!=pair['candidate']['binary_sha256'],(mode,'same binary')
  result={}
  for label,a in pair['baseline']['same_corpus'].items():
   b=pair['candidate']['same_corpus'][label]
   # Actual storage validation work and normalized response wire bytes must
   # be equal on all paired reads of the same pinned durable corpus.
   assert {tuple(x[3:]) for x in a+b}=={tuple(a[0][3:])},(mode,label,'read/response drift',a,b)
   x,y=([int(statistics.median(z[i] for z in arm)) for i in range(3)] for arm in (a,b))
   n=int(label.split('-')[1])
   if n==0:
    assert abs(x[0]-y[0])<=1 and abs(x[1]-y[1])<=2048 and x[2]==y[2],(mode,label,'history-only control',x,y)
   else:
    assert x[0]>y[0] and x[1]>y[1],(mode,label,'allocation reduction',x,y)
    if n>=128:
     assert x[1]-y[1]>=n*64 and x[2]-y[2]>=n*64,(mode,label,'rich-case allocation reduction',x,y)
   result[label]=dict(baseline=x,candidate=y,storage_reads=a[0][3:5],record_wire_sha256=a[0][5])
  receipt[mode]=result
 return receipt
def main():
 cli=argparse.ArgumentParser(description=__doc__)
 for n in ('modules','core','vendor','work','target'):
  cli.add_argument('--'+n,type=Path,required=True)
 cli.add_argument('--cargo',default='cargo')
 cli.add_argument('--prepare-only',action='store_true')
 args=cli.parse_args()
 W,V,T=(getattr(args,n).resolve() for n in ('work','vendor','target'))
 W.mkdir(parents=True,exist_ok=False)
 src,sdk,u=read_archives(args.modules,args.core)
 lock=(D/'Cargo.lock').read_bytes();checks(lock,u,V)
 assert h((D/'source.patch').read_bytes())==PATCH
 rel=STORAGE+'src/snapshot.rs'
 for p,(m,b) in sdk.items():put(W/'Core'/p,b,m)
 for arm in ('baseline','candidate'):
  root=W/arm
  for p,(m,b) in src.items():put(root/p,b,m)
  assert oh((root/rel).read_bytes())=='c5b3e04616cca767364d508efc5e9a2f7015de37'
  if arm=='candidate':
   for opt in (['--check'],[],['--reverse','--check']):
    subprocess.run(['git','apply',*opt,str(D/'source.patch')],cwd=root,check=True)
   assert oh((root/rel).read_bytes())=='c914c39ff273c35d70fb547b85b8db311a2d544b'
  put(root/'Cargo.toml',(D/'wrapper.toml').read_bytes());put(root/'Cargo.lock',lock)
  put(root/STORAGE/'src/tests/warm_page_proof.rs',(D/'warm-page-proof.rs').read_bytes())
  with (root/STORAGE/'src/tests/mod.rs').open('a') as f:f.write('\nmod warm_page_proof;\n')
 if args.prepare_only:return
 assert not T.exists(),'use an independent, initially absent build target to avoid stale donor artifacts'
 T.mkdir(parents=True)
 home=W/'cargo-home';home.mkdir()
 env=dict(os.environ,CARGO_HOME=str(home),CARGO_INCREMENTAL='0',CARGO_TARGET_DIR=str(T),LC_ALL='C')
 prefix=[args.cargo,'--offline','--locked','--config','source.crates-io.replace-with="exact"','--config','source.exact.directory='+json.dumps(str(V))]
 out={}
 fixture=W/'fixture';fixture.mkdir()
 for mode,features in [('default',[]),('preserve_order',['--features','serde_json/preserve_order'])]:
  out[mode]={}
  for arm in ('baseline','candidate'):
   build_log=W/f'{arm}-{mode}-compile.jsonl'
   # Cargo may reuse a local package with the same name/relative path after
   # moving between source roots in one target. Preserve dependencies, but
   # explicitly clear this package's artifacts before every measurement.
   subprocess.run(prefix+['clean','--release','-p','session-storage'],cwd=W/arm,env=env,check=True,stdout=subprocess.DEVNULL)
   with build_log.open('wb') as stdout,(W/f'{arm}-{mode}-compile.stderr').open('wb') as stderr:
    subprocess.run(prefix+['test','--release','--lib','--no-run','--message-format=json','-j2',*features],cwd=W/arm,env=env,stdout=stdout,stderr=stderr,check=True)
   units=[json.loads(l) for l in build_log.read_bytes().splitlines()]
   exe,=[u for u in units if u['reason']=='compiler-artifact' and u['target']['name']=='session_storage' and u['executable']]
   assert Path(exe['target']['src_path'])==(W/arm/STORAGE/'src/lib.rs')
   assert not exe['fresh']
   sj,=[u for u in units if u['reason']=='compiler-artifact' and u['target']['name']=='serde_json']
   assert ('preserve_order' in sj['features'])==bool(features)
   p=Path(exe['executable'])
   out[mode][arm]=capture(build_log,p,W/f'{arm}-{mode}-tests.log')
   if not (fixture/'fixture.json').exists():
    paired_capture(p,fixture,'seed',W/'same-corpus-seed.log')
   out[mode][arm]['same_corpus']=paired_capture(p,fixture,'read',W/f'{arm}-{mode}-paired.log')
 print(json.dumps(dict(result=compare(out),exact_runs=out),indent=2))
if __name__=='__main__':main()
