#!/usr/bin/env python3
"""Real production CLI install/update scripts with tiny offline Rust producers."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

p = argparse.ArgumentParser()
p.add_argument('--core', type=Path, required=True)
p.add_argument('--modules', type=Path, required=True)
p.add_argument('--desktop', type=Path, required=True)
p.add_argument('--extensions', type=Path, required=True)
p.add_argument('--core-binary', type=Path, help='Optional existing real Core executable; read-only inspect topology checks')
p.add_argument('--output', type=Path, required=True)
a = p.parse_args()
root = a.output.resolve()
root.mkdir(parents=True, exist_ok=False)
env = dict(os.environ, CARGO_NET_OFFLINE='true', HOME=str(root/'home'), PROTEUS_BUILD_SHARE='100', CARGO_BUILD_JOBS='2')
for key in list(env):
    if key.startswith('PROTEUS_') and key != 'PROTEUS_BUILD_SHARE':
        env.pop(key)
for key in ('CARGO_BUILD_TARGET', 'CARGO_TARGET_DIR'):
    env.pop(key, None)
Path(env['HOME']).mkdir()
hashes = {}

def write(path, value, executable=False):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value)
    if executable:
        path.chmod(0o755)

def head(repository, name, path):
    data = subprocess.check_output(['git','show','HEAD:'+name], cwd=repository)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    hashes[f'{repository.name}/{name}'] = hashlib.sha256(data).hexdigest()

def run(args, cwd=root, extra=None, check=True):
    result = subprocess.run(list(map(str,args)), cwd=cwd, env={**env,**(extra or {})}, text=True, capture_output=True, timeout=90)
    with (root/'commands.log').open('a') as log:
        log.write(f'$ cwd={cwd} {args}\n{result.stdout}{result.stderr}\nEXIT {result.returncode}\n')
    if check and result.returncode:
        raise RuntimeError(f'{args}: {result.stderr}')
    return result

def commit(path, message):
    if not (path/'.git').exists():
        run(['git','init','-q'],path)
    run(['git','add','.'],path)
    run(['git','-c','user.name=Local Fixture','-c','user.email=fixture@example.invalid','commit','-qm',message],path)
    return run(['git','rev-parse','HEAD'],path).stdout.strip()

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

desktop = root/'desktop'
for name in subprocess.check_output(['git','ls-files','scripts','repositories.json'],cwd=a.desktop,text=True).splitlines():
    head(a.desktop,name,desktop/name)
core = root/'core'
for name in ('install.sh','scripts/build_module.py','scripts/sources.py','repositories.json'):
    head(a.core,name,core/name)
for name in subprocess.check_output(['git','ls-files','configs'],cwd=a.core,text=True).splitlines():
    head(a.core,name,core/name)
write(core/'Cargo.toml','[workspace]\nmembers=["crates/proteus-core"]\nresolver="2"\n')
write(core/'crates/proteus-core/Cargo.toml','[package]\nname="proteus-core"\nversion="0.0.0"\nedition="2021"\n[[bin]]\nname="proteus"\npath="src/main.rs"\n')
write(core/'crates/proteus-core/src/main.rs','fn main(){println!("CORE-B");}\n')
# Production scripts remain unchanged. This fixture build script only delays an
# ordinary compilation until the second independent update has completed.
write(core/'crates/proteus-core/build.rs','''fn main() {
    println!("cargo:rerun-if-env-changed=FIXTURE_BUILD_BARRIER");
    if let Ok(dir) = std::env::var("FIXTURE_BUILD_BARRIER") {
        let dir = std::path::Path::new(&dir);
        std::fs::write(dir.join("entered"), "ready").unwrap();
        let start = std::time::Instant::now();
        while !dir.join("release").exists() {
            assert!(start.elapsed().as_secs() < 75, "fixture barrier timeout");
            std::thread::sleep(std::time::Duration::from_millis(20));
        }
    }
}
''')
write(core/'LICENSE','Synthetic MIT fixture\n')
write(core/'.gitignore','target/\n')
run(['cargo','generate-lockfile','--offline'],core)
core_commit = commit(core,'core B')

modules = root/'modules'
head(a.modules,'package.py',modules/'package.py')
head(a.modules,'LICENSE',modules/'LICENSE')
write(modules/'Cargo.toml','[workspace]\nmembers=["components/model-pack-module","components/code-mode-module"]\nresolver="2"\n')
for name, slot in [('model-pack','model'),('code-mode','tool')]:
    d = modules/'components'/f'{name}-module'
    write(d/'Cargo.toml',f'[package]\nname="proteus-{name}-module"\nversion="0.0.0"\nedition="2021"\n[package.metadata.proteus]\nid="{name}"\nimplementation="{slot}/{name}"\n')
    write(d/'src/main.rs',f'fn main(){{println!("MODULE-{name}");}}\n')
    write(d/'exports.json',json.dumps({slot:[name.replace('-','_')]}))
    (modules/slot/name).mkdir(parents=True)
run(['cargo','generate-lockfile','--offline'],modules)

# Fresh CLI install with all current tracked configs and actual package install.
install_env = {'PROTEUS_MODULES_SOURCE':str(modules),'PROTEUS_HOME':str(root/'cli-runtime'), 'PROTEUS_CONFIG_HOME':str(root/'cli-config'), 'PROTEUS_BIN_DIR':str(root/'cli-bin'), 'CARGO_TARGET_DIR':str(root/'installer-target')}
installed = run(['sh','install.sh'],core,install_env)
expected_profiles = sorted(x.name for x in (core/'configs').glob('*.config.toml'))
actual_profiles = sorted(x.name for x in (root/'cli-config/configs').glob('*.config.toml'))
missing_profiles = sorted(set(expected_profiles)-set(actual_profiles))
assert missing_profiles == ['code-mode.config.toml'], missing_profiles
assert (root/'cli-runtime/current/bin/proteus-code-mode-module').is_file()
module_result = run([root/'cli-runtime/current/bin/proteus-code-mode-module'])

# Positive control: identical tracked configs, real unchanged portable launcher.
# Native executable is a shell placeholder; no GUI/backend starts.
launcher_control = root/'launcher-control'
head(a.desktop,'scripts/portable/proteus-native',launcher_control/'proteus-native')
(launcher_control/'proteus-native').chmod(0o755)
head(a.desktop,'scripts/portable/system_proxy.py',launcher_control/'share/system_proxy.py')
head(a.desktop,'scripts/codex_executable.py',launcher_control/'share/codex_executable.py')
shutil.copytree(core/'configs',launcher_control/'share/configs')
write(launcher_control/'bin/proteus-native','#!/bin/sh\necho FIXTURE-NATIVE\n',True)
control_env = {'PROTEUS_CONFIG_HOME':str(root/'portable-config')}
control = run([launcher_control/'proteus-native','--version'],extra=control_env)
assert sha(root/'portable-config/configs/code-mode.config.toml') == sha(core/'configs/code-mode.config.toml')
# Updating an existing install also does not add the missing shipped profile.
second_install = run(['sh','install.sh'],core,install_env)
assert not (root/'cli-config/configs/code-mode.config.toml').exists()
real_core = None
if a.core_binary:
    inspect = [a.core_binary.resolve(),'--config','code-mode','inspect','topology','--format','json']
    missing = run(inspect,extra={'PROTEUS_CONFIG_HOME':str(root/'cli-config')},check=False)
    present = run(inspect,extra={'PROTEUS_CONFIG_HOME':str(root/'portable-config')})
    assert missing.returncode == 1 and "config name 'code-mode' was not found" in missing.stderr
    assert json.loads(present.stdout)['profile'] == 'code-mode'
    real_core = {'executable_sha256':sha(a.core_binary),'cli_profile_exit':missing.returncode,'cli_profile_error':missing.stderr.strip(),'portable_profile_exit':present.returncode,'resolved_portable_profile':'code-mode','scope':'inspect topology only; no worker/model invocation'}

# Minimal accepted current portable, then independent real Core/Extensions updates.
extensions = root/'extensions'
head(a.extensions,'package.py',extensions/'package.py')
write(extensions/'Cargo.toml','[workspace]\nmembers=["packages/demo"]\nresolver="2"\n')
write(extensions/'packages/demo/Cargo.toml','[package]\nname="extension-demo"\nversion="0.0.0"\nedition="2021"\n[[bin]]\nname="demo"\npath="src/main.rs"\n')
write(extensions/'packages/demo/src/main.rs','fn main(){println!("EXTENSION-B");}\n')
write(extensions/'packages/demo/extension.json',json.dumps({'id':'demo','protocol':1,'command':['bin/demo'],'required_features':[]}))
write(extensions/'packages/demo/LICENSE-GPL','Synthetic GPL fixture\n')
write(extensions/'LICENSE','Synthetic GPL fixture\n')
write(extensions/'.gitignore','target/\n')
run(['cargo','generate-lockfile','--offline'],extensions)
ext_commit = commit(extensions,'extension B')
live = desktop/'build/Proteus'
names = ('Proteus-desktop','Proteus-core','Proteus-modules','Proteus-desktop-extensions')
for relative in ('bin/proteus','bin/proteus-native','proteus-native','install-shortcut','bin/demo-module'):
    write(live/relative,'#!/bin/sh\necho BASE-A\n',True)
write(live/'share/extensions/demo/bin/demo','#!/bin/sh\necho EXTENSION-A\n',True)
write(live/'share/extensions/demo/extension.json',json.dumps({'id':'demo','protocol':1,'command':['bin/demo'],'required_features':[]}))
write(live/'share/modules/demo/module.json',json.dumps({'id':'demo','version':'0.0.0','command':['bin/demo-module'],'exports':{'tool':['demo']},'sha256':sha(live/'bin/demo-module')}))
write(live/'share/configs/config.toml','# base config\n')
write(live/'share/system_proxy.py','# fixture\n')
(live/'share/icons').mkdir()
for name in names:
    write(live/'share/licenses'/name/'LICENSE','Synthetic fixture\n')
record = {'schema_version':1,'version':'0.0.0','sources':{name:{'commit':'BASE-A','dirty':False} for name in names},'desktop_protocol':1,'desktop_features':[]}
write(live/'share/release-sources.json',json.dumps(record))
update_env = {'PROTEUS_HARNESS_SOURCE':str(core),'PROTEUS_EXTENSIONS_SOURCE':str(extensions),'CARGO_TARGET_DIR':str(root/'update-target')}
barrier = root/'barrier'
barrier.mkdir()
command = [sys.executable,str(desktop/'scripts/portable.py'),'--components','core','--no-archive']
with (root/'core-update.log').open('w') as log:
    background = subprocess.Popen(command,cwd=desktop,env={**env,**update_env,'FIXTURE_BUILD_BARRIER':str(barrier)},stdout=log,stderr=subprocess.STDOUT)
    try:
        started = time.monotonic()
        while not (barrier/'entered').exists():
            assert background.poll() is None, 'Core fixture failed before barrier'
            assert time.monotonic()-started < 45, 'Core barrier timeout'
            time.sleep(0.02)
        extension_update = run([sys.executable,desktop/'scripts/portable.py','--components','extensions','--no-archive'],desktop,{**update_env,'CARGO_TARGET_DIR':str(root/'extension-target')})
        after_extensions = run([live/'share/extensions/demo/bin/demo']).stdout.strip()
        assert after_extensions == 'EXTENSION-B'
        after_extensions_record = json.loads((live/'share/release-sources.json').read_text())
        assert after_extensions_record['sources']['Proteus-desktop-extensions']['commit'] == ext_commit
    finally:
        write(barrier/'release','go\n')
        core_status = background.wait(timeout=45)
assert core_status == 0
after_core_extension = run([live/'share/extensions/demo/bin/demo']).stdout.strip()
assert after_core_extension == 'EXTENSION-A'
assert run([live/'bin/proteus']).stdout.strip() == 'CORE-B'
final_record = json.loads((live/'share/release-sources.json').read_text())
assert final_record['sources']['Proteus-desktop-extensions']['commit'] == 'BASE-A'
assert final_record['sources']['Proteus-core']['commit'] == core_commit

# Sequential positive control: Extensions B then Core B retains both upgrades.
run([sys.executable,desktop/'scripts/portable.py','--components','extensions','--no-archive'],desktop,{**update_env,'CARGO_TARGET_DIR':str(root/'extension-target')})
run(command,desktop,update_env)
assert run([live/'share/extensions/demo/bin/demo']).stdout.strip() == 'EXTENSION-B'
assert run([live/'bin/proteus']).stdout.strip() == 'CORE-B'
sequential = json.loads((live/'share/release-sources.json').read_text())
assert sequential['sources']['Proteus-desktop-extensions']['commit'] == ext_commit
results = {
    'commits':{key:subprocess.check_output(['git','rev-parse','HEAD'],cwd=getattr(a,key),text=True).strip() for key in ('core','modules','desktop','extensions')},
    'script_sha256':hashes,
    'cli_profile_omission':{'install_exit':installed.returncode,'second_install_exit':second_install.returncode,'missing_shipped_profiles':missing_profiles,'module_executable_installed':True,'module_output':module_result.stdout.strip(),'portable_launcher_exit':control.returncode,'portable_launcher_copied_exact_profile':True},
    'real_core_named_profile_check':real_core,
    'concurrent_updates':{'extensions_exit':extension_update.returncode,'core_exit':core_status,'extension_after_extensions_success':after_extensions,'extension_after_core_success':after_core_extension,'extension_provenance_after_extensions':ext_commit,'extension_provenance_after_core':final_record['sources']['Proteus-desktop-extensions']['commit'],'final_core':'CORE-B','sequential_control':'CORE-B + EXTENSION-B'},
    'scope':'Unchanged production CLI/scripts, real offline Cargo/rustc/Git/copy/rename, tiny Core/Module/Extension crates; test-only Core build.rs pause enables deterministic overlap. No GUI, full Core runtime, live model or network providers exercised.'
}
(root/'results.json').write_text(json.dumps(results,indent=2)+'\n')
print(json.dumps(results,indent=2))
