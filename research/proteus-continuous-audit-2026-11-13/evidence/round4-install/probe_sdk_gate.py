#!/usr/bin/env python3
"""Run unmodified Desktop release.sdk_gate against tiny real Cargo workspaces."""
import json, os, pathlib, shutil, subprocess, sys
from unittest.mock import patch
HERE=pathlib.Path(__file__).resolve().parent
DESKTOP=pathlib.Path('/workspace/shared/install-build-round4')
sys.path.insert(0,str(DESKTOP/'scripts'))
import release
root=HERE/'sdk-gate-fixture'
if root.exists(): shutil.rmtree(root)
root.mkdir()
(root/'Cargo.toml').write_text('[workspace]\nmembers=["protocol"]\nresolver="2"\n')
for path,name,binary,extra in [(root/'protocol','proteus-module-protocol','proteus-component-conformance','[features]\nconformance-cli=[]\n'), (root/'examples/modules/rust-tool','proteus-rust-tool-example','proteus-rust-tool-example','[workspace]\n')]:
    (path/'src').mkdir(parents=True)
    (path/'Cargo.toml').write_text(f'[package]\nname="{name}"\nversion="0.1.0"\nedition="2024"\n[[bin]]\nname="{binary}"\npath="src/main.rs"\n'+extra)
    (path/'src/main.rs').write_text('fn main() { println!("OLD"); }\n')
# Only fixture smoke is synthetic; builds and command selection are production.
(root/'examples/modules/rust-tool/smoke.py').write_text('''import argparse,json,pathlib,subprocess
p=argparse.ArgumentParser();p.add_argument('--module');p.add_argument('--conformance');a=p.parse_args()
result={k:subprocess.check_output([v],text=True).strip() for k,v in vars(a).items()}
pathlib.Path('smoke-observed.json').write_text(json.dumps(result));print('SMOKE',result)
''')
env=os.environ.copy();env.pop('CARGO_BUILD_TARGET',None);env.pop('CARGO_TARGET_DIR',None);env['CARGO_NET_OFFLINE']='true'
for path in (root,root/'examples/modules/rust-tool'):
    subprocess.run(['cargo','generate-lockfile','--offline'],cwd=path,env=env,check=True)
with patch.dict(os.environ,env,clear=True): release.sdk_gate(root)
for path in (root/'protocol/src/main.rs',root/'examples/modules/rust-tool/src/main.rs'):
    path.write_text('fn main() { println!("NEW"); }\n')
host=next(l.partition(': ')[2] for l in subprocess.check_output(['rustc','-vV'],text=True).splitlines() if l.startswith('host: '))
env['CARGO_BUILD_TARGET']=host
with patch.dict(os.environ,env,clear=True): release.sdk_gate(root)
observed=json.loads((root/'smoke-observed.json').read_text())
fresh={name:subprocess.check_output([root/'target'/host/'debug'/name],text=True).strip() for name in ('proteus-component-conformance','proteus-rust-tool-example')}
result={'host':host,'gate_success':True,'smoke_observed':observed,'newly_built_artifacts':fresh}
print(json.dumps(result,indent=2));(HERE/'sdk-gate-result.json').write_text(json.dumps(result,indent=2)+'\n')
assert set(observed.values())=={'OLD'} and set(fresh.values())=={'NEW'}
