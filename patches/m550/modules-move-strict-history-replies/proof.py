#!/usr/bin/env python3
"""Build the two old-SDK workers and verify exact canonical ReadRecords reply behavior."""
import argparse,hashlib,json,os,re,shutil,subprocess,sys,tarfile,tomllib
from pathlib import Path

D=Path(__file__).resolve().parent
MODULES='4cda80d9de0823c7b517a53790929c6b012607a64a76f431c04b582e829ebb3e'
CORE='daa6e425662389dbdcef1c555320a149dc719b3cb8ad88317858c7c44d9dd9eb'
PATCH='5c79bbc591f28fa228207449d8289848247471d69e397ee92b456c03fd7b229d'
REV='0c1b7572313230e5d123e95c722e1258a2e9ecd6'
PREFIX='Proteus-core-'+REV+'/'
PROJECT='components/session-storage-module/'
SDK_NAMES={'proteus-contracts','proteus-session-semantics','proteus-module-sdk','proteus-module-protocol','proteus-process-host'}
H=lambda b:hashlib.sha256(b).hexdigest()

def put(root,name,mode,raw):
 p=root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(raw);p.chmod(mode)

def stage(w,m,c,v):
 assert H(m.read_bytes())==MODULES and H(c.read_bytes())==CORE
 assert H((D/'source.patch').read_bytes())==PATCH
 with tarfile.open(m) as t:
  u=tomllib.loads(t.extractfile('Cargo.lock').read().decode())['package']
  mod={n.name:(n.mode,t.extractfile(n).read()) for n in t if n.isfile() and n.name.startswith((PROJECT,'storage/session-storage/'))}
 with tarfile.open(c) as t:
  sdk={n.name.removeprefix(PREFIX):(n.mode,t.extractfile(n).read()) for n in t if n.isfile() and n.name.startswith(tuple(PREFIX+'crates/'+x+'/' for x in SDK_NAMES))}
 assert len(mod)+len(sdk)==258
 lock=(D/'Cargo.lock').read_bytes()
 assert H(lock)=='bb66d10ddbb052c52105bebebafc9ae79f2c6698e66c94169055d440d1b920ea'
 index={(p['name'],p['version']):p for p in u}
 count=0
 for p in tomllib.loads(lock.decode())['package']:
  old=index[(p['name'],p['version'])]
  if 'checksum' in p:
   assert p['source']==old['source'] and p['checksum']==old['checksum']
   rec=v/f'{p["name"]}-{p["version"]}'/'.cargo-checksum.json'
   assert json.loads(rec.read_bytes())['package']==p['checksum']
   count+=1
  elif p['name'] in SDK_NAMES:
   assert old['source'].endswith('#'+REV)
 assert count==157
 for arm in ['baseline','candidate']:
  root=w/arm
  for n,(mode,b) in (mod|sdk).items():put(root,n,mode,b)
  put(root,'Cargo.toml',0o644,(D/'wrapper.toml').read_bytes())
  put(root,'Cargo.lock',0o644,lock)
  if arm=='candidate':
   for fl in (['--check'],[],['--reverse','--check'],['--reverse']):
    subprocess.run(['git','apply',*fl,str(D/'source.patch')],cwd=root,check=True)
   assert {(p.relative_to(root).as_posix(),p.read_bytes()) for p in (root/PROJECT).rglob('*') if p.is_file()}=={(n,b) for n,(_,b) in mod.items() if n.startswith(PROJECT)}
   subprocess.run(['git','apply',str(D/'source.patch')],cwd=root,check=True)
 print('exact archive preflight and inverse PASS',flush=True)

def main():
 a=argparse.ArgumentParser(description=__doc__)
 for n in ['modules','core','vendor','work','target']:
  a.add_argument('--'+n,required=True,type=Path)
 a.add_argument('--manifest',type=Path)
 a.add_argument('--small-manifest',type=Path)
 a.add_argument('--prepare-only',action='store_true')
 a.add_argument('--cargo',default='cargo');a.add_argument('--rustc',default='rustc')
 cfg=a.parse_args();w,t,v=(getattr(cfg,k).resolve() for k in ['work','target','vendor'])
 w.mkdir(parents=True,exist_ok=False)
 stage(w,cfg.modules,cfg.core,v)
 if cfg.prepare_only:return
 assert (cfg.manifest is None)==(cfg.small_manifest is None), 'provide both shared manifests or neither'
 assert subprocess.check_output([cfg.rustc,'--version'],text=True).startswith('rustc 1.95.0 ')
 t.mkdir(parents=True,exist_ok=False)
 e=dict(os.environ,CARGO_HOME=str(w/'cargo-home'),CARGO_TARGET_DIR=str(t),CARGO_INCREMENTAL='0',RUSTC=str(Path(shutil.which(cfg.rustc)).resolve()))
 cmd=[cfg.cargo,'--offline','--locked','--config','source.crates-io.replace-with="exact"','--config',
      'source.exact.directory='+json.dumps(str(v))]
 for mode,features in [('default',[]),('preserve_order',['--features','serde_json/preserve_order'])]:
  for arm in ('baseline','candidate'):
   root=w/arm
   # Same package name and relative source path can otherwise report a stale
   # executable across arms; clean these package outputs, not the shared SDK.
   subprocess.run(cmd+['clean','-p','proteus-session-storage-module'],cwd=root,env=e,check=True)
   build=subprocess.run(cmd+['test','-p','proteus-session-storage-module','--test','process','--no-run',
       '--message-format=json','-j2',*features],cwd=root,env=e,capture_output=True,check=True)
   (w/f'{arm}-{mode}-compile.jsonl').write_bytes(build.stdout)
   objects=[json.loads(x) for x in build.stdout.splitlines()]
   bin_,=[x for x in objects if x.get('target',{}).get('name')=='proteus-session-storage-module' and x.get('executable')]
   assert not bin_['fresh'] and Path(bin_['target']['src_path'])==root/PROJECT/'src/main.rs'
   artifact=w/f'{arm}-{mode}-worker';shutil.copy2(bin_['executable'],artifact)
   test,=[x['executable'] for x in objects if x.get('target',{}).get('name')=='process' and x.get('executable')]
   result=subprocess.check_output([test,'--test-threads=1'],text=True)
   assert '2 passed; 0 failed' in result
   (w/f'{arm}-{mode}-process.log').write_text(result)
   libs={x['target']['name']:f for x in objects if x['reason']=='compiler-artifact'
         for f in x['filenames'] if f.endswith('.rlib')}
   serde,=[x for x in objects if x.get('target',{}).get('name')=='serde_json']
   assert ('preserve_order' in serde['features'])==bool(features)
   if arm=='candidate':
    owner=w/f'owner-{mode}';owner.mkdir()
    shutil.copy2(D/'owner_meter.rs',owner/'main.rs')
    shutil.copy2(root/PROJECT/'src/display_reply.rs',owner/'display_reply.rs')
    search=[('dependency',t/'debug/deps')]
    search.extend(('native',p) for p in {f.parent for f in (t/'debug/build').glob('*/out/*.a')})
    rust=[cfg.rustc,'--edition=2024','-C','strip=symbols',*[v for kind,path in search for v in ('-L',f'{kind}={path}')]]
    rust += [x for k in ('anyhow','serde_json','ring','proteus_contracts','session_storage') for x in ('--extern',k+'='+libs[k])]
    subprocess.run(rust+[str(owner/'main.rs'),'-o',str(owner/'meter')],check=True)
    if mode=='default' and cfg.manifest is None:
     subprocess.run(rust+[str(D/'seed.rs'),'-o',str(w/'seed')],check=True)
 if cfg.manifest is None:
  fixtures=w/'fixtures'
  subprocess.run([str(w/'seed'),str(fixtures)],check=True)
  cfg.manifest=fixtures/'strict.json';cfg.small_manifest=fixtures/'small.json'
 f=w/'frames'
 for m in ('default','preserve_order'):
  out=subprocess.check_output([sys.executable,str(D/'worker_proof.py'),
    str(w/f'baseline-{m}-worker'),str(w/f'candidate-{m}-worker'),
    str(cfg.manifest),str(f),m,'--small-manifest',str(cfg.small_manifest),'--save-frame'])
  (w/f'actual-worker-{m}.json').write_bytes(out)
  out=subprocess.check_output([str(w/f'owner-{m}'/'meter'),str(f/f'{m}-strict-50k-frame.json'),str(cfg.manifest)])
  (w/f'owner-{m}.log').write_bytes(out)
 print('actual workers, legacy, negotiated fallback, unchanged page frames and owner A/B PASS',flush=True)

if __name__=='__main__':main()
