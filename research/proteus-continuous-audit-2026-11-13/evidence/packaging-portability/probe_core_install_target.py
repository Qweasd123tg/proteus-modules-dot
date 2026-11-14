#!/usr/bin/env python3
"""Run pristine Core install.sh with a tiny real Cargo binary and stub module bundler."""
import argparse, hashlib, json, os, shutil, subprocess
from pathlib import Path

p=argparse.ArgumentParser()
p.add_argument('--core',type=Path,default=Path('/workspace/shared/proteus-review-20261112/core'))
p.add_argument('--output',type=Path,default=Path(__file__).parent/'core-install-fixture')
a=p.parse_args(); root=a.output.resolve(); root.mkdir(parents=True,exist_ok=False)
project=root/'core'; (project/'src').mkdir(parents=True); (project/'scripts').mkdir()
script=subprocess.check_output(['git','show','HEAD:install.sh'],cwd=a.core)
(project/'install.sh').write_bytes(script)
shutil.copytree(a.core/'configs',project/'configs')
(project/'Cargo.toml').write_text('''[package]
name = "proteus-core"
version = "0.0.0"
edition = "2021"
[[bin]]
name = "proteus"
path = "src/main.rs"
''')
# Only module building is replaced; installer build/copy/snapshot/publish/wrapper
# and config installation all run unchanged. This avoids building unrelated modules.
(project/'scripts/build_module.py').write_text('''import sys
from pathlib import Path
bundle=Path(sys.argv[sys.argv.index('--bundle')+1]); (bundle/'bin').mkdir()
module=bundle/'bin/proteus-model-pack-module'; module.write_text('#!/bin/sh\\nprintf module-stub\\n'); module.chmod(0o755)
''')
env={**os.environ,'CARGO_TARGET_DIR':str(root/'target'),'PROTEUS_BIN_DIR':str(root/'installed/bin'),'PROTEUS_HOME':str(root/'installed/home'),'PROTEUS_CONFIG_HOME':str(root/'installed/config'),'CARGO_NET_OFFLINE':'true'}
env.pop('CARGO_BUILD_TARGET',None)
host=subprocess.check_output(['rustc','-vV'],env=env,text=True).split('host: ',1)[1].splitlines()[0]
def run(args,environment):
 result=subprocess.run(args,cwd=project,env=environment,text=True,capture_output=True)
 with (root/'commands.log').open('a') as log: log.write('$ '+ ' '.join(map(str,args))+'\n'+result.stdout+result.stderr+'\nEXIT '+str(result.returncode)+'\n')
 return result
source=project/'src/main.rs';source.write_text('fn main() { println!("OLD"); }\n')
assert run(['cargo','generate-lockfile','--offline'],env).returncode==0
assert run(['sh','install.sh'],env).returncode==0
wrapper=root/'installed/bin/proteus'; initial=run([str(wrapper)],env).stdout.strip();assert initial=='OLD'
source.write_text('fn main() { println!("NEW"); }\n')
targeted={**env,'CARGO_BUILD_TARGET':host}
install=run(['sh','install.sh'],targeted);assert install.returncode==0
fresh=root/'target'/host/'release/proteus'
fresh_output=run([str(fresh)],targeted).stdout.strip()
installed_output=run([str(wrapper)],targeted).stdout.strip()
assert fresh_output=='NEW';assert installed_output=='OLD'
# Cold control: targeted build has no legacy output to silently pick up.
cold={**targeted,'CARGO_TARGET_DIR':str(root/'target-cold'),'PROTEUS_HOME':str(root/'cold-home'),'PROTEUS_BIN_DIR':str(root/'cold-bin'),'PROTEUS_CONFIG_HOME':str(root/'cold-config')}
cold_run=run(['sh','install.sh'],cold)
assert cold_run.returncode!=0
assert (root/'target-cold'/host/'release/proteus').is_file()
assert not (root/'cold-home/current').exists()
report={'core_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=a.core,text=True).strip(),'script_sha256':hashlib.sha256(script).hexdigest(),'host':host,'initial_wrapper_output':initial,'warm_install_status':install.returncode,'fresh_targeted_binary_output':fresh_output,'installed_wrapper_output':installed_output,'current_snapshot':str((root/'installed/home/current').resolve()),'cold_install_status':cold_run.returncode,'cold_stderr':cold_run.stderr,'cold_published_snapshot':(root/'cold-home/current').exists(),'scope':'Unmodified production install.sh; actual offline Cargo/rustc/subprocess. Tiny binary fixture, stubbed build_module.py; no Core runtime or full Modules build.'}
(root.parent/'core-install-results.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
