#!/usr/bin/env python3
"""Real Cargo + unchanged install/build_module/sources/package scripts, tiny crates."""
import argparse,hashlib,json,os,shutil,subprocess
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--core',type=Path,default=Path('/workspace/shared/proteus-review-20261112/core'));p.add_argument('--modules',type=Path,default=Path('/workspace/shared/proteus-review-20261112/modules'));p.add_argument('--output',type=Path,default=Path(__file__).parent/'relative-fixture');a=p.parse_args()
root=a.output.resolve();root.mkdir(parents=True,exist_ok=False);core=root/'core';modules=root/'modules';(core/'src').mkdir(parents=True);(core/'scripts').mkdir();component=modules/'components/model-pack-module';(component/'src').mkdir(parents=True);(modules/'model/model-pack').mkdir(parents=True)
sources={}
for source_root,destination,names in [(a.core,core,['install.sh','scripts/build_module.py','scripts/sources.py','repositories.json']),(a.modules,modules,['package.py','LICENSE'])]:
 for name in names:
  data=subprocess.check_output(['git','show','HEAD:'+name],cwd=source_root);(destination/name).write_bytes(data);sources[str(destination.relative_to(root)/name)]=hashlib.sha256(data).hexdigest()
shutil.copytree(a.core/'configs',core/'configs')
(core/'Cargo.toml').write_text('[package]\nname="proteus-core"\nversion="0.0.0"\nedition="2021"\n[[bin]]\nname="proteus"\npath="src/main.rs"\n')
(core/'src/main.rs').write_text('fn main(){println!("fixture-core");}\n')
(modules/'Cargo.toml').write_text('[workspace]\nmembers=["components/model-pack-module"]\nresolver="2"\n')
(component/'Cargo.toml').write_text('[package]\nname="proteus-model-pack-module"\nversion="0.0.0"\nedition="2021"\n[package.metadata.proteus]\nid="model-pack"\nimplementation="model/model-pack"\n')
(component/'src/main.rs').write_text('fn main(){println!("fixture-module");}\n');(component/'exports.json').write_text('{"model":["*"]}\n')
env={**os.environ,'CARGO_TARGET_DIR':str(root/'target'),'CARGO_NET_OFFLINE':'true','PROTEUS_MODULES_SOURCE':str(modules),'HOME':str(root/'home')};env.pop('CARGO_BUILD_TARGET',None);env.pop('PROTEUS_CONFIG_PATH',None);Path(env['HOME']).mkdir()
def run(command,cwd=core,environment=env):
 r=subprocess.run(command,cwd=cwd,env=environment,text=True,capture_output=True)
 with (root/'commands.log').open('a') as f:f.write('$ (cd '+str(cwd)+') '+' '.join(map(str,command))+'\n'+r.stdout+r.stderr+'\nEXIT '+str(r.returncode)+'\n')
 return r
for cwd in [core,modules]: assert run(['cargo','generate-lockfile','--offline'],cwd).returncode==0
# Direct documented bundler call, with ordinary relative destination.
direct=run(['python3','scripts/build_module.py','--profile','release','--bundle','direct-bundle']);assert direct.returncode==0
assert not (core/'direct-bundle').exists();assert (modules/'direct-bundle/bin/proteus-model-pack-module').is_file()
# Relative installation root: host publishes in cwd, module package publishes in Modules cwd.
relative_env={**env,'PROTEUS_HOME':'relative-runtime','PROTEUS_BIN_DIR':str(root/'relative-bin'),'PROTEUS_CONFIG_HOME':str(root/'relative-config')}
relative=run(['sh','install.sh'],environment=relative_env);assert relative.returncode==0
relative_snapshot=(core/'relative-runtime/current').resolve();assert (relative_snapshot/'proteus').is_file();assert not (relative_snapshot/'bin/proteus-model-pack-module').exists()
misplaced=list((modules/'relative-runtime/releases').glob('*/bin/proteus-model-pack-module'));assert len(misplaced)==1
relative_host=run([str(root/'relative-bin/proteus')],environment=relative_env);relative_module=run([str(root/'relative-bin/proteus-model-pack-module')],environment=relative_env)
assert relative_host.returncode==0;assert relative_module.returncode!=0
# Absolute destination control, same scripts, source roots and target cache.
absolute_env={**env,'PROTEUS_HOME':str(root/'absolute-runtime'),'PROTEUS_BIN_DIR':str(root/'absolute-bin'),'PROTEUS_CONFIG_HOME':str(root/'absolute-config')}
absolute=run(['sh','install.sh'],environment=absolute_env);assert absolute.returncode==0
absolute_module=run([str(root/'absolute-bin/proteus-model-pack-module')],environment=absolute_env);assert absolute_module.returncode==0 and absolute_module.stdout.strip()=='fixture-module'
report={'core_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=a.core,text=True).strip(),'modules_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=a.modules,text=True).strip(),'source_sha256':sources,'direct_bundle':{'status':direct.returncode,'expected_root':str(core/'direct-bundle'),'expected_root_exists':False,'actual_root':str(modules/'direct-bundle')},'relative_install':{'status':relative.returncode,'published_snapshot':str(relative_snapshot),'host_status':relative_host.returncode,'module_status':relative_module.returncode,'module_stderr':relative_module.stderr,'module_in_published_snapshot':False,'misplaced_module':str(misplaced[0])},'absolute_install_control':{'status':absolute.returncode,'module_status':absolute_module.returncode,'module_output':absolute_module.stdout.strip()},'scope':'Pristine production scripts and real offline Cargo/rustc. Tiny Core/module crates substitute heavy application builds. No package producer mocks or source resolver mocks; actual module manifest/hash/install logic.'}
(root.parent/'relative-results.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
