#!/usr/bin/env python3
"""Build the two old-SDK workers and verify warm CompareSnapshots behavior using the exact old SDK."""
import argparse,hashlib,json,os,re,shutil,subprocess,sys,tarfile,tomllib
from pathlib import Path

D=Path(__file__).resolve().parent
MODULES='68ce421bb78b4cee606f123ba7edffdeda1a073d79e21f41aa74dca83fb82529'
CORE='daa6e425662389dbdcef1c555320a149dc719b3cb8ad88317858c7c44d9dd9eb'
PATCH='c015146791266dad89db3b5469016aa68712e6190873b7f1b5c6ef0abf5ef73e'
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
   assert {(p.relative_to(root).as_posix(),p.read_bytes(),p.stat().st_mode&0o777) for stem in (PROJECT, 'storage/session-storage/') for p in (root/stem).rglob('*') if p.is_file()}=={(n,b,m) for n,(m,b) in mod.items()}
   subprocess.run(['git','apply',str(D/'source.patch')],cwd=root,check=True)
  with (root/'storage/session-storage/src/tests/usage.rs').open('ab') as f:
   f.write((D/'compare-sidecar.rs').read_bytes())
 print('exact archive pins, inverse, and vendor preflight PASS',flush=True)

def main():
 a=argparse.ArgumentParser(description=__doc__)
 for n in ['modules','core','vendor','work','target']:
  a.add_argument('--'+n,required=True,type=Path)
 a.add_argument('--prepare-only',action='store_true')
 a.add_argument('--cargo',default='cargo');a.add_argument('--rustc',default='rustc')
 cfg=a.parse_args();w,t,v=(getattr(cfg,k).resolve() for k in ['work','target','vendor'])
 w.mkdir(parents=True,exist_ok=False)
 stage(w,cfg.modules,cfg.core,v)
 if cfg.prepare_only:return
 assert subprocess.check_output([cfg.rustc,'--version'],text=True).startswith('rustc 1.95.0 ')
 t.mkdir(parents=True,exist_ok=False)
 c=w/'fixture';c.mkdir()
 e=dict(os.environ,CARGO_HOME=str(w/'cargo-home'),CARGO_TARGET_DIR=str(t),
        CARGO_INCREMENTAL='0',CARGO_PROFILE_TEST_DEBUG='0',
        RUSTC=str(Path(shutil.which(cfg.rustc)).resolve()),
        TMPDIR=str(c),PROTEUS_WARM_COMPARE_CORPUS=str(c/'manifest.json'))
 cmd=[cfg.cargo,'--offline','--locked','--config','source.crates-io.replace-with="exact"','--config',
      'source.exact.directory='+json.dumps(str(v))]
 def run_native(binary,args,mode=None):
  env=e.copy()
  if mode is not None:
   env['PROTEUS_WARM_COMPARE_MODE']=mode
   env['PROTEUS_WARM_COMPARE_SERIAL_CORRUPTION']='1'
  return subprocess.check_output([binary,*args],env=env,text=True,stderr=subprocess.STDOUT)
 def checkout(args,z,m,arm,tag):
  build=subprocess.run(cmd+['test',*args,'--no-run','--message-format=json','-j2',*m],cwd=z,env=e,capture_output=True,check=True)
  (w/f'{arm}-{tag}-compile.jsonl').write_bytes(build.stdout)
  return [json.loads(x) for x in build.stdout.splitlines()]
 for mode,features in [('default',[]),('preserve_order',['--features','serde_json/preserve_order'])]:
  for arm in ('baseline','candidate'):
   z=w/arm
   subprocess.run(cmd+['clean','-p','session-storage','-p','proteus-session-storage-module'],cwd=z,env=e,check=True)
   objects=checkout(['-p','session-storage','--lib'],z,features,arm,mode+'-storage')
   test,=[x for x in objects if x.get('target',{}).get('name')=='session_storage' and x.get('executable')]
   assert not test['fresh'] and Path(test['target']['src_path'])==z/'storage/session-storage/src/lib.rs'
   serde,=[x for x in objects if x.get('target',{}).get('name')=='serde_json']
   assert ('preserve_order' in serde['features'])==bool(features)
   exe=test['executable']
   if not Path(e['PROTEUS_WARM_COMPARE_CORPUS']).exists():
    txt=run_native(exe,['--ignored','--exact','tests::usage::warm_compare_probe::compare_warm_rich_prefix'],'seed')
    assert '1 passed; 0 failed' in txt
    (w/'seed.log').write_text(txt)
   txt=run_native(exe,['--test-threads=1'])
   assert '100 passed; 0 failed; 2 ignored' in txt
   (w/f'{arm}-{mode}-suite.log').write_text(txt)
   txt=run_native(exe,['--ignored','--exact','tests::usage::warm_compare_probe::compare_warm_rich_prefix','--nocapture'],'read')
   assert '1 passed; 0 failed' in txt
   (w/f'{arm}-{mode}-meter.log').write_text(txt)
   objects=checkout(['-p','proteus-session-storage-module','--test','process'],z,features,arm,mode+'-worker')
   exe,=[x for x in objects if x.get('target',{}).get('name')=='proteus-session-storage-module' and x.get('executable')]
   assert not exe['fresh'] and Path(exe['target']['src_path'])==z/PROJECT/'src/main.rs'
   shutil.copy2(exe['executable'],w/f'{arm}-{mode}-worker')
   tested,=[x['executable'] for x in objects if x.get('target',{}).get('name')=='process' and x.get('executable')]
   txt=run_native(tested,['--test-threads=1'])
   assert '2 passed; 0 failed' in txt
   (w/f'{arm}-{mode}-process.log').write_text(txt)
  txt=subprocess.check_output([sys.executable,str(D/'worker_proof.py'),
    str(w/f'baseline-{mode}-worker'),str(w/f'candidate-{mode}-worker'),
    e['PROTEUS_WARM_COMPARE_CORPUS'],str(w/'frames'),mode],text=True)
  (w/f'actual-worker-{mode}.json').write_text(txt)
 print('both layouts: native storage suites, scoped meter and legacy worker stdio PASS',flush=True)

if __name__=='__main__':main()
