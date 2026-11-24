#!/usr/bin/env python3
"""Replay using extracted Modules M350, a pinned source checkout of Core, and a Cargo vendor."""
import argparse, hashlib, json, os, re, shutil, subprocess, tempfile, tomllib
from pathlib import Path
D=Path(__file__).resolve().parent
H=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
CLI=argparse.ArgumentParser(description=__doc__)
for n in ("modules","core","vendor"):CLI.add_argument("--"+n,required=True,type=Path)
CLI.add_argument("--cargo",default="cargo")
CLI.add_argument("--work",required=True,type=Path)
CLI.add_argument("--prepare-only",action="store_true")
args=CLI.parse_args()
r=args.work.resolve();r.mkdir(parents=True,exist_ok=True);m=args.modules.resolve();c=args.core.resolve()
hook=Path("hook/codex-context-preparation")
assert H(m/'Cargo.lock')=='0b4717cd37ba4b5848068f64c52e863000d8d7ea6d90464f4a134689e45bef54'
sources=json.loads((D/'sources.json').read_bytes());assert H(D/'source.patch')==sources['patch']['sha256']
def tree_match(t,j):
 exp=json.loads((D/j).read_text())
 actual={p.relative_to(t).as_posix():H(p) for p in t.rglob('*') if p.is_file()}
 assert actual==exp, f'{j}: wrong source tree'
tree_match(m/hook,'hook-baseline.json')
tree_match(c/'crates/proteus-contracts','contracts-baseline.json')
deps={ (x['name'],x['version'],x.get('checksum')) for x in tomllib.loads((m/'Cargo.lock').read_text())['package'] }
env=os.environ.copy();env['CARGO_HOME']=str(r/'home');env['CARGO_TARGET_DIR']=str(r/'target')
def cargo(root,*args_):
 return subprocess.run([args.cargo,'--offline','--config','source.crates-io.replace-with="verified"','--config','source.verified.directory='+json.dumps(str(args.vendor.resolve())),*args_],cwd=root,env=env,check=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True).stdout
out={}
for arm in ('before','after'):
 root=r/arm
 if root.exists():raise SystemExit(f'Use a fresh work directory ({root} exists)')
 root.mkdir();shutil.copytree(m/hook,root/hook)
 for p,pin in sources['paths'].items():assert H(root/p)==pin['before']['sha256']
 if arm=='after':
  for opts in (['--check'],[]):
   subprocess.run(['git','apply',*opts,str(D/'source.patch')],cwd=root,check=True)
  for p,pin in sources['paths'].items():assert H(root/p)==pin['after']['sha256']
 shutil.copy(D/'hook-proof.rs',root/hook/'src/hook-proof.rs')
 with (root/hook/'src/tests.rs').open('a') as f:f.write('\ninclude!("hook-proof.rs");\n')
 (root/'Cargo.toml').write_text('[workspace]\nresolver="2"\nmembers=["hook/codex-context-preparation"]\n[workspace.dependencies]\nproteus-contracts={path='+json.dumps(str(c/'crates/proteus-contracts'))+'}\n')
 # The external workspace is replaced by a local path; all actual registry resolutions
 # must nevertheless equal authenticated names/versions/checksums from product lock.
 cargo(root,'generate-lockfile')
 pkgs=tomllib.loads((root/'Cargo.lock').read_text())['package']
 assert all((x['name'],x['version'],x['checksum']) in deps for x in pkgs if 'source' in x)
 if args.prepare_only:continue
 text=cargo(root,'test','--locked','--release','--lib','-p','codex-context-preparation','--','--test-threads=1','--nocapture')
 (r/(arm+'-tests.log')).write_text(text)
 assert re.search(r'test result: ok\. 54 passed; 0 failed;',text),text
 out[arm]={n:list(map(int,[count,bytes_,peak])) for n,count,bytes_,peak in re.findall(r'WIRE (\d+) (\d+) (\d+) (\d+)',text)}
 assert out[arm].keys()=={'0','32','128'}
if not args.prepare_only:
 for n in ('32','128'):
  a,b=out['before'][n],out['after'][n]
  assert a[0]>b[0] and min(a[1]-b[1],a[2]-b[2])>=int(n)*8192,(a,b)
 print(json.dumps(out,indent=2))
