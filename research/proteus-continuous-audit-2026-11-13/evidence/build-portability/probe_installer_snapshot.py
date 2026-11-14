#!/usr/bin/env python3
"""Unchanged install.sh + real Cargo/process-host; fixture binary and module producer."""
import argparse, hashlib, json, os, selectors, shutil, subprocess, time
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--core',type=Path,default=Path('/workspace/shared/proteus-review-20261112/core'));p.add_argument('--output',type=Path,default=Path(__file__).parent/'fixture');args=p.parse_args()
core=args.core.resolve(); root=args.output.resolve(); root.mkdir(parents=True,exist_ok=False)
project=root/'core'; (project/'src').mkdir(parents=True);(project/'scripts').mkdir()
installer=subprocess.check_output(['git','show','HEAD:install.sh'],cwd=core);(project/'install.sh').write_bytes(installer)
shutil.copytree(core/'configs',project/'configs')
(project/'Cargo.toml').write_text(f'''[package]\nname="proteus-core"\nversion="0.0.0"\nedition="2024"\n[[bin]]\nname="proteus"\npath="src/main.rs"\n[dependencies]\nproteus-process-host={{path={json.dumps(str(core/'crates/proteus-process-host'))}}}\nserde_json="1"\n''')
host_source='''use std::{io::{self, BufRead, Write},time::Duration};
use proteus_process_host::{ProcessHost,ProcessSpec,NewlineJsonFraming};
use serde_json::json;
const RELEASE: &str = "RELEASE_MARKER";
fn main() {
 if std::env::args().any(|arg| arg == "--version") {println!("{RELEASE}");return;}
 let host = ProcessHost::new(ProcessSpec::new("proteus-model-pack-module"), NewlineJsonFraming::default());
 println!("{}",json!({"event":"started","host":RELEASE,"pid":std::process::id(),"path":std::env::var("PATH").unwrap()}));io::stdout().flush().unwrap();
 for line in io::stdin().lock().lines() {
  let line = line.unwrap(); if line == "quit" { break; }
  if line == "reset" {host.reset();}
  match host.request("release",json!({}),Duration::from_secs(3)) {
   Ok(value)=>println!("{}",json!({"host":RELEASE,"worker":value,"command":line})),
   Err(error)=>println!("{}",json!({"host":RELEASE,"error":format!("{error:#}"),"command":line})),
  };io::stdout().flush().unwrap();
 }
}
'''
bundler='''import json,sys
from pathlib import Path
root=Path(__file__).resolve().parent.parent
bundle=Path(sys.argv[sys.argv.index('--bundle')+1]);(bundle/'bin').mkdir()
release=(root/'release.txt').read_text().strip()
worker=bundle/'bin/proteus-model-pack-module'
worker.write_text('#!/usr/bin/env python3\\nimport json,sys\\nRELEASE='+repr(release)+'\\nfor line in sys.stdin:\\n message=json.loads(line)\\n if "id" in message: print(json.dumps({"jsonrpc":"2.0","id":message["id"],"result":RELEASE}),flush=True)\\n')
worker.chmod(0o755)
'''
(project/'scripts/build_module.py').write_text(bundler)
env={**os.environ,'CARGO_TARGET_DIR':str(root/'target'),'CARGO_NET_OFFLINE':'true','PROTEUS_HOME':str(root/'installed/runtime'),'PROTEUS_BIN_DIR':str(root/'installed/bin'),'PROTEUS_CONFIG_HOME':str(root/'installed/config'),'HOME':str(root/'home')}
Path(env['HOME']).mkdir(); env.pop('CARGO_BUILD_TARGET',None);env.pop('PROTEUS_CONFIG_PATH',None)
log=root/'commands.log'
def run(command,environment=env):
 r=subprocess.run(command,cwd=project,env=environment,text=True,capture_output=True)
 with log.open('a') as f:f.write('$ '+' '.join(map(str,command))+'\n'+r.stdout+r.stderr+'\nEXIT '+str(r.returncode)+'\n')
 return r
fragment1=project/'configs/fragments/openai-chatgpt.toml';fragment2=project/'configs/fragments/codex-runtime.toml';original1=fragment1.read_text();original2=fragment2.read_text()
def source(release):
 (project/'src/main.rs').write_text(host_source.replace('RELEASE_MARKER',release));(project/'release.txt').write_text(release)
 fragment1.write_text(original1+'\n# audit release '+release+'\n');fragment2.write_text(original2+'\n# audit release '+release+'\n')
def readline(proc):
 selector=selectors.DefaultSelector();selector.register(proc.stdout,selectors.EVENT_READ)
 if not selector.select(10): raise AssertionError('host did not respond')
 return json.loads(proc.stdout.readline())
def ask(proc,command):
 proc.stdin.write(command+'\n');proc.stdin.flush();return readline(proc)
source('A');assert run(['cargo','generate-lockfile','--offline']).returncode==0
assert run(['sh','install.sh']).returncode==0
wrapper=root/'installed/bin/proteus';old_snapshot=(root/'installed/runtime/current').resolve()
processes=[]
def start(command,environment):
 proc=subprocess.Popen(command,cwd=project,env=environment,text=True,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE);processes.append(proc);return proc,readline(proc)
try:
 running,started=start([str(wrapper)],env);initial=ask(running,'request');assert initial['host']==initial['worker']=='A'
 # Positive control uses the exact selected snapshot, not the mutable current link.
 pinned_env={**env,'PATH':str(old_snapshot/'bin')+os.pathsep+env['PATH']}
 pinned,pinned_started=start([str(old_snapshot/'proteus')],pinned_env);assert ask(pinned,'request')['worker']=='A'
 source('B');update=run(['sh','install.sh']);assert update.returncode==0
 continued=ask(running,'request');assert continued['worker']=='A'
 restarted=ask(running,'reset');assert restarted['host']=='A' and restarted['worker']=='B'
 pinned_restarted=ask(pinned,'reset');assert pinned_restarted['host']==pinned_restarted['worker']=='A'
 fresh,fresh_started=start([str(wrapper)],env);fresh_result=ask(fresh,'request');assert fresh_result['host']==fresh_result['worker']=='B'
 # Real filesystem failure, no cp/subprocess mocks: existing readable fragment is read-only.
 current_before_failure=(root/'installed/runtime/current').resolve();dest1=root/'installed/config/configs/fragments/openai-chatgpt.toml';dest2=root/'installed/config/configs/fragments/codex-runtime.toml'
 assert dest1.read_text().endswith('# audit release B\n') and dest2.read_text().endswith('# audit release B\n')
 dest2.chmod(0o444);source('C');failed=run(['sh','install.sh']);assert failed.returncode!=0
 current_after_failure=(root/'installed/runtime/current').resolve();version=run([str(wrapper),'--version']).stdout.strip()
 assert current_after_failure!=current_before_failure and version=='C';assert dest1.read_text().endswith('# audit release C\n');assert dest2.read_text().endswith('# audit release B\n')
 dest2.chmod(0o644)
 report={'core_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=core,text=True).strip(),'installer_sha256':hashlib.sha256(installer).hexdigest(),'scope':'Pristine production install.sh and proteus-process-host. Actual Cargo/rustc, shell, filesystem and process I/O. Minimal Rust host and Python worker substitute full Core/module packaging. No full Core, model, desktop UI or production profile invocation.','live_snapshot':{'started':started,'initial':initial,'continued_existing_worker_after_B':continued,'restarted_worker_after_B':restarted,'pinned_snapshot_control_after_B':pinned_restarted,'fresh_wrapper_after_B':fresh_result},'config_failure':{'install_status':failed.returncode,'stderr':failed.stderr,'snapshot_before':str(current_before_failure),'snapshot_after':str(current_after_failure),'wrapper_release_after_failed_install':version,'first_managed_fragment_release':'C','second_managed_fragment_release':'B','previous_snapshot_retained':current_before_failure.exists()},'fixture':str(root)}
 (root.parent/'results.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
finally:
 for proc in processes:
  if proc.poll() is None:
   proc.stdin.write('quit\n');proc.stdin.flush()
   try:proc.wait(timeout=10)
   except subprocess.TimeoutExpired:proc.kill();proc.wait()
