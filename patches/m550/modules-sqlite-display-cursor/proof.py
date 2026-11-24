#!/usr/bin/env python3
"""Rebuild and verify the transaction-bound SQLite display scan."""
import argparse,hashlib,json,os,re,subprocess,tarfile,tomllib
from pathlib import Path

D=Path(__file__).resolve().parent
S='storage/session-storage/'
MODULES='c60d90058dc93f99890c20788a07e19969703ea2a2cb14d39e0b239c164412dd'
CORE='daa6e425662389dbdcef1c555320a149dc719b3cb8ad88317858c7c44d9dd9eb'
PATCH='c3b7cb4a3b8e90695e8b5795d22fc892f99766e6c8e5794d1cbd3699b23a9125'
PREFIX='Proteus-core-0c1b7572313230e5d123e95c722e1258a2e9ecd6/'
PINS={'storage/session-storage/src/backend/mod.rs': ('83b4441fa64cc8a89fa68718cae70135da979ed4', '373f53920d5baf77b0f6a175a37368f402e28a9c'), 'storage/session-storage/src/backend/sqlite.rs': ('130338b251e7879c9bb106d569e95dacd90bf521', '9bc837d9627411aadb60933911b342e1b983a4bc'), 'storage/session-storage/src/service/display.rs': ('8ab82f2f0f058a57e1c535e23ddd339d5da75106', '8a37ca10bb60c1083512afbc1dec6cb526715b10')}
H=lambda b:hashlib.sha256(b).hexdigest()
G=lambda b:hashlib.sha1(f'blob {len(b)}\0'.encode()+b).hexdigest()
def saved(root, path, data, mode=0o644):
 p=root/path;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(data);p.chmod(mode)
def verification_inputs(w,modules,core,vendor):
 assert H(modules.read_bytes())==MODULES
 assert H(core.read_bytes())==CORE
 assert H((D/'source.patch').read_bytes())==PATCH
 with tarfile.open(modules) as f:
  full=tomllib.loads(f.extractfile('Cargo.lock').read().decode())
  records={m.name:(m.mode,f.extractfile(m).read()) for m in f if m.isfile() and m.name.startswith(S)}
 with tarfile.open(core) as f:
  sdks={m.name.removeprefix(PREFIX):(m.mode,f.extractfile(m).read()) for m in f if m.isfile() and m.name.startswith(tuple(PREFIX+'crates/'+c+'/' for c in ['proteus-contracts','proteus-session-semantics']))}
 assert len(records)+len(sdks)==184
 for p,(mode,b) in sdks.items():saved(w/'Core',p,b,mode)
 locked=(D/'Cargo.lock').read_bytes()
 index={(p['name'],p['version']):p for p in full['package']}
 for q in tomllib.loads(locked.decode())['package']:
  p=index[(q['name'],q['version'])]
  if 'checksum' in q:
   assert p['checksum']==q['checksum'] and p['source']==q['source']
   attestation=vendor/f'{q["name"]}-{q["version"]}'/'.cargo-checksum.json'
   assert json.loads(attestation.read_bytes())['package']==q['checksum']
  elif q['name']!='session-storage':
   assert q['name'] in ('proteus-contracts','proteus-session-semantics')
   assert p['source'].endswith('#0c1b7572313230e5d123e95c722e1258a2e9ecd6')
 for arm in ['baseline','candidate']:
  root=w/arm
  for p,(mode,b) in records.items():saved(root,p,b,mode)
  for path,(old,new) in PINS.items():assert G((root/path).read_bytes())==old
  if arm=='candidate':
   for flags in (['--check'],[],['--reverse','--check']):
    subprocess.run(['git','apply',*flags,str(D/'source.patch')],cwd=root,check=True)
   for path,(old,new) in PINS.items():assert G((root/path).read_bytes())==new
  saved(root,'Cargo.lock',locked)
  saved(root,'Cargo.toml',(D/'wrapper.toml').read_bytes())
  saved(root,S+'src/tests/stage_proof.rs',(D/'service-proof.rs').read_bytes())
  with (root/S/'src/tests/mod.rs').open('a') as m:m.write('\npub(crate) mod stage_proof;\n')
  a=root/S/'src/backend/sqlite.rs'
  changes=[('    let mut rows = stmt.query(params![i64::try_from(after)?, i64::try_from(end)?])?;',
           '    #[cfg(test)]\n    crate::tests::stage_proof::row_query(false);'),
          ('    Ok(record)\n}\n\n#[cfg(test)]',
           '    #[cfg(test)]\n    crate::tests::stage_proof::row_decoded(sequence);')]
  if arm=='candidate':
   changes.append(('        let mut rows = stmt.query([i64::try_from(self.end)?])?;',
                  '        #[cfg(test)]\n        crate::tests::stage_proof::row_query(true);'))
  text=a.read_text()
  for before,insert in changes:
   assert text.count(before)==1,(arm,before)
   text=text.replace(before,insert+'\n'+before)
  a.write_text(text)
def read_native(log):
 p=log.read_text()
 assert re.search(r'test result: ok\. 1 passed; 0 failed; 0 ignored;',p)
 modes={}
 for m in re.finditer(r'DISPLAY (Jsonl|Sqlite) 4 ((?:\d+ ){6})([0-9a-f]{64}) (\d+) ([0-9a-f]{64})',p):
  name,nums,wire,hashed,src=m.groups()
  v=list(map(int,nums.split()))
  assert v[1:3]==[50_000,200] and v[0]<32*1024*1024
  modes[name]=dict(state_bytes=v[0],records=v[1],pages=v[2],staged_wire_bytes=v[3],
                   seek_replays=v[4],ordered_replays=v[5],record_wire_sha256=wire,
                   canonical_fingerprint_bytes=int(hashed),snapshot_prefix=src)
 cap={m[0]:list(map(int,m[1:])) for m in re.findall(r'CAP (Jsonl|Sqlite) 5 (\d+) (\d+) (\d+) (\d+)',p)}
 assert modes.keys()==cap.keys()=={'Jsonl','Sqlite'} and all(v[0]==50_000 for v in cap.values())
 return dict(display=modes,over_cap_fallback=cap)
def compare(out):
 for mode,pair in out.items():
  a,b=pair['baseline'],pair['candidate']
  assert a['exe_sha256']!=b['exe_sha256'],(mode,'reused binary')
  want=(('seek_replays','ordered_replays'),(50001,0),(0,1))
  for kind,x in a['results']['display'].items():
   y=b['results']['display'][kind]
   assert all(x[k]==y[k] for k in x if k not in want[0]),(mode,kind,'wire/source/page changed')
   ca,cb=(arm['results']['over_cap_fallback'][kind] for arm in (a,b))
   assert ca[:2]==cb[:2]
   xx=tuple(x[k] for k in want[0]);yy=tuple(y[k] for k in want[0])
   if kind=='Sqlite':
    assert (xx,yy)==want[1:] and tuple(ca[2:])==xx and tuple(cb[2:])==yy
   else:
    assert xx==yy==(0,0) and ca==cb
def main():
 c=argparse.ArgumentParser(description=__doc__)
 for p in ['modules','core','vendor','work','target']:c.add_argument('--'+p,required=True,type=Path)
 c.add_argument('--cargo',default='cargo');c.add_argument('--prepare-only',action='store_true')
 a=c.parse_args();w,v,t=(getattr(a,m).resolve() for m in ('work','vendor','target'))
 w.mkdir(parents=True,exist_ok=False)
 verification_inputs(w,a.modules,a.core,v)
 if a.prepare_only:return
 t.mkdir(parents=True,exist_ok=False)
 corpus=w/'corpus';corpus.mkdir()
 env=dict(os.environ,CARGO_HOME=str(w/'cargo-home'),CARGO_TARGET_DIR=str(t),CARGO_INCREMENTAL='0',
          CARGO_PROFILE_TEST_DEBUG='0',TMPDIR=str(corpus),PROTEUS_STAGE_CORPUS=str(corpus/'fixtures.json'))
 cmd=[a.cargo,'--offline','--locked','--config','source.crates-io.replace-with="exact"',
      '--config','source.exact.directory='+json.dumps(str(v))]
 out={}
 for mode,features in [('default',[]),('preserve_order',['--features','serde_json/preserve_order'])]:
  out[mode]={}
  for arm in ('baseline','candidate'):
   root=w/arm
   # Do not reuse the executable of a same-named module in another source root.
   subprocess.run(cmd+['clean','-p','session-storage'],cwd=root,env=env,check=True)
   p=subprocess.run(cmd+['test','--no-run','--lib','--message-format=json','-j2',*features],cwd=root,env=env,check=True,capture_output=True)
   (w/f'{arm}-{mode}-compile.jsonl').write_bytes(p.stdout)
   units=[json.loads(l) for l in p.stdout.splitlines()]
   e,=[u for u in units if u['reason']=='compiler-artifact' and u['target']['name']=='session_storage' and u['executable']]
   assert not e['fresh'] and Path(e['target']['src_path'])==root/S/'src/lib.rs'
   s,=[u for u in units if u['reason']=='compiler-artifact' and u['target']['name']=='serde_json']
   assert ('preserve_order' in s['features'])==bool(features)
   exe=Path(e['executable'])
   def run(log,runmode=None):
    args=[str(exe),'--test-threads=1','--nocapture','--color','never']
    e=env.copy()
    if runmode is not None:
     args+=['--ignored','sqlite_display_scan_large_corpus']
     e['PROTEUS_STAGE_MODE']=runmode
    with log.open('wb') as f:subprocess.run(args,stdout=f,stderr=subprocess.STDOUT,env=e,check=True)
    return log
   if not (corpus/'fixtures.json').exists():run(w/'seed.log','seed')
   h=run(w/f'{arm}-{mode}-tests.log')
   assert re.search(r'test result: ok\. 103 passed; 0 failed; 2 ignored;',h.read_text())
   large=run(w/f'{arm}-{mode}-large.log','read')
   out[mode][arm]=dict(exe_sha256=H(exe.read_bytes()),results=read_native(large))
 compare(out)
 print(json.dumps(out,indent=2))
if __name__=='__main__':main()
