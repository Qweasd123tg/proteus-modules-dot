#!/usr/bin/env python3
"""Verify canonical pending record byte accounting using the exact old SDK."""
import argparse,hashlib,json,os,re,subprocess,tarfile,tomllib
from pathlib import Path

D=Path(__file__).resolve().parent
MOD='47853afd9ae1bae7d14187d2d669b5e622bea186703a1b3aa6abaec719feaf24'
SDK='daa6e425662389dbdcef1c555320a149dc719b3cb8ad88317858c7c44d9dd9eb'
PATCH='437e4c010cd1890496ad9c0c2780f17ee6eb0dd5100e3b643b0420d8f6826795'
SOURCE='storage/session-storage/'
P=SOURCE+'src/snapshot.rs'
PIN0='c914c39ff273c35d70fb547b85b8db311a2d544b'
PIN1='2850cbf32aa8e88ab43303d5d4dc36771f8638b5'
REV='0c1b7572313230e5d123e95c722e1258a2e9ecd6'
ROOT='Proteus-core-'+REV+'/'
C=('proteus-contracts','proteus-session-semantics')
H=lambda b:hashlib.sha256(b).hexdigest()
G=lambda b:hashlib.sha1(f'blob {len(b)}\0'.encode()+b).hexdigest()
def put(root,path,b,m=0o644):
 p=root/path;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(b);p.chmod(m)
def stage(w,m,c,v):
 assert H(m.read_bytes())==MOD and H(c.read_bytes())==SDK and H((D/'source.patch').read_bytes())==PATCH
 with tarfile.open(m) as a:
  pkgs=tomllib.loads(a.extractfile('Cargo.lock').read().decode())['package']
  src={n.name:(n.mode,a.extractfile(n).read()) for n in a if n.isfile() and n.name.startswith(SOURCE)}
 with tarfile.open(c) as a:
  sdk={n.name.removeprefix(ROOT):(n.mode,a.extractfile(n).read()) for n in a if n.isfile() and n.name.startswith(tuple(ROOT+'crates/'+k+'/' for k in C))}
 assert len(sdk)+len(src)==184
 for p,(m,b) in sdk.items():put(w/'Core',p,b,m)
 index={(x['name'],x['version']):x for x in pkgs}
 lock=(D/'Cargo.lock').read_bytes()
 for x in tomllib.loads(lock.decode())['package']:
  y=index[(x['name'],x['version'])]
  if 'checksum' in x:
   assert (x['source'],x['checksum'])==(y['source'],y['checksum'])
   info=v/f'{x["name"]}-{x["version"]}'/'.cargo-checksum.json'
   assert json.loads(info.read_bytes())['package']==x['checksum']
  elif x['name'] in C:assert y['source'].endswith('#'+REV)
 for arm in ('baseline','candidate'):
  z=w/arm
  for path,(m,b) in src.items():put(z,path,b,m)
  assert G((z/P).read_bytes())==PIN0
  if arm=='candidate':
   for opts in (['--check'],[],['--reverse','--check'],['--reverse']):
    subprocess.run(['git','apply',*opts,str(D/'source.patch')],cwd=z,check=True)
   assert all((z/q).read_bytes()==b and (z/q).stat().st_mode&0o777==m for q,(m,b) in src.items())
   subprocess.run(['git','apply',str(D/'source.patch')],cwd=z,check=True)
   assert G((z/P).read_bytes())==PIN1
  put(z,'Cargo.toml',(D/'wrapper.toml').read_bytes());put(z,'Cargo.lock',lock)
  put(z,SOURCE+'src/tests/pending_proof.rs',(D/'pending-proof.rs').read_bytes())
  with (z/SOURCE/'src/tests/mod.rs').open('a') as f:f.write('\npub(crate) mod pending_proof;\n')
  v=(z/P).read_text();a='crate::codec::encoded_bytes(&record)?'
  assert v.count(a)==1
  (z/P).write_text(v.replace(a,'crate::tests::pending_proof::measure(&record)?'))
 print('full pins / inverse / registry preflight PASS',flush=True)

def strict_rows(text):
 assert 'test result: ok. 1 passed; 0 failed; 0 ignored;' in text
 a={}
 for kind,page,counts,decoded,hashed,fp,wire in re.findall(r'STRICT (Jsonl|Sqlite) (\d) ([-\d:,]+) (\d+) (\d+) ([0-9a-f]{64}) ([0-9a-f]{64})',text):
  key=f'{kind}-{page}'
  assert key not in a
  a[key]={'counted':[] if counts=='-' else [list(map(int,v.split(':'))) for v in counts.split(',')],
         'decoded':int(decoded),'fingerprint_bytes':int(hashed),'prefix_sha256':fp,'record_wire_sha256':wire}
 assert len(a)==6
 return a
def compare(g):
 for m,b in g.items():
  assert b['baseline']['binary_sha256']!=b['candidate']['binary_sha256']
  x,y=(b[a]['results'] for a in ('baseline','candidate'))
  for k in ('Jsonl','Sqlite'):
   for phase in (1,2,3):
    p,q=(a[f'{k}-{phase}'] for a in (x,y))
    assert {n:v for n,v in p.items() if n!='counted'}=={n:v for n,v in q.items() if n!='counted'}
    if phase==1:
     assert p['counted']==q['counted']
     assert p['counted'][1]==[2,37_389_295]
    elif phase==2:
     assert p['counted'][:1]==[[2,37_389_295]] and p['counted'][1:]==q['counted']==[[3,675]]
    else:assert p['counted']==[[3,675]] and q['counted']==[]
 return g

def main():
 p=argparse.ArgumentParser(description=__doc__)
 for k in ('modules','core','vendor','work','target'):p.add_argument('--'+k,type=Path,required=True)
 p.add_argument('--cargo',default='cargo');p.add_argument('--prepare-only',action='store_true')
 a=p.parse_args();w,t,v=(getattr(a,key).resolve() for key in ('work','target','vendor'))
 w.mkdir(parents=True,exist_ok=False)
 stage(w,a.modules,a.core,v)
 if a.prepare_only:return
 t.mkdir(parents=True,exist_ok=False)
 c=w/'fixture';c.mkdir()
 env=dict(os.environ,CARGO_HOME=str(w/'cargo-home'),CARGO_TARGET_DIR=str(t),CARGO_INCREMENTAL='0',
          CARGO_PROFILE_TEST_DEBUG='0',TMPDIR=str(c),PROTEUS_PENDING_CORPUS=str(c/'manifest.json'))
 cc=[a.cargo,'--offline','--locked','--config','source.crates-io.replace-with="exact"',
     '--config','source.exact.directory='+json.dumps(str(v))]
 out={}
 for mode,features in [('default',[]),('preserve_order',['--features','serde_json/preserve_order'])]:
  out[mode]={}
  for arm in ('baseline','candidate'):
   z=w/arm
   # Avoid same-name package executable reuse across separate checkouts.
   subprocess.run(cc+['clean','-p','session-storage'],cwd=z,env=env,check=True)
   native=subprocess.run(cc+['test','--no-run','--lib','--message-format=json','-j2',*features],cwd=z,env=env,capture_output=True,check=True)
   objects=[json.loads(v) for v in native.stdout.splitlines()]
   o,=[v for v in objects if v.get('target',{}).get('name')=='session_storage' and v.get('executable')]
   assert not o['fresh'] and Path(o['target']['src_path'])==z/SOURCE/'src/lib.rs'
   j,=[v for v in objects if v.get('target',{}).get('name')=='serde_json']
   assert ('preserve_order' in j['features'])==bool(features)
   exe=Path(o['executable'])
   def run(tag,data=None):
    e=env.copy()
    args=[str(exe),'--test-threads=1','--nocapture','--color','never']
    if data is not None:
     e['PROTEUS_PENDING_MODE']=data
     args+=['--ignored','large_strict_pending_count_same_corpus']
    text=subprocess.check_output(args,env=e,stderr=subprocess.STDOUT,text=True)
    (w/f'{arm}-{mode}-{tag}.log').write_text(text)
    return text
   if not (c/'manifest.json').is_file():run('seed','seed')
   v=run('suite')
   assert 'test result: ok. 105 passed; 0 failed; 2 ignored;' in v
   assert ('EDGE +1 count '+('1' if arm=='baseline' else '0')) in v
   out[mode][arm]=dict(binary_sha256=H(exe.read_bytes()),results=strict_rows(run('large','read')))
 print(json.dumps(compare(out),indent=2),flush=True)
if __name__=='__main__':main()
