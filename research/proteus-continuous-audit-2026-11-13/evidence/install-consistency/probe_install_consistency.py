#!/usr/bin/env python3
"""Isolated real CLI/Cargo probes; production Python scripts copied from Git HEAD."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

p = argparse.ArgumentParser()
p.add_argument('--desktop', type=Path, default=Path('/workspace/shared/install-build-round4'))
p.add_argument('--modules', type=Path, default=Path('/workspace/shared/proteus-review-20261112/modules'))
p.add_argument('--output', type=Path, required=True)
a = p.parse_args()
ROOT = a.output.resolve()
ROOT.mkdir(parents=True, exist_ok=False)
env = dict(os.environ, CARGO_NET_OFFLINE='true', CARGO_TARGET_DIR=str(ROOT/'target'), HOME=str(ROOT/'home'), PROTEUS_BUILD_SHARE='100')
for name in ('CARGO_BUILD_TARGET', 'PROTEUS_HARNESS_SOURCE', 'PROTEUS_MODULES_SOURCE', 'PROTEUS_EXTENSIONS_SOURCE'):
    env.pop(name, None)
Path(env['HOME']).mkdir()
source_hashes = {}

def run(command, cwd=ROOT, *, check=True, extra=None):
    result = subprocess.run([str(x) for x in command], cwd=cwd, env={**env, **(extra or {})}, text=True, capture_output=True)
    with (ROOT/'commands.log').open('a') as log:
        log.write(f'$ cwd={cwd} {command}\n{result.stdout}{result.stderr}\nEXIT {result.returncode}\n')
    if check and result.returncode:
        raise RuntimeError(f'{command}: {result.stderr}')
    return result

def write(path, text, executable=False):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    if executable:
        path.chmod(0o755)

def copy_head(repo, name, destination):
    data = subprocess.check_output(['git', 'show', 'HEAD:'+name], cwd=repo)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(data)
    source_hashes[f'{repo.name}/{name}'] = hashlib.sha256(data).hexdigest()

def git_commit(path, message):
    if not (path/'.git').exists():
        run(['git','init','-q'], path)
    run(['git','add','.'], path)
    run(['git','-c','user.name=Synthetic Fixture','-c','user.email=fixture@example.invalid','commit','-qm',message], path)
    return run(['git','rev-parse','HEAD'], path).stdout.strip()

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

desktop = ROOT/'desktop'
for name in subprocess.check_output(['git','ls-files','scripts','repositories.json'],cwd=a.desktop,text=True).splitlines():
    copy_head(a.desktop,name,desktop/name)

core = ROOT/'core'
write(core/'Cargo.toml', '[workspace]\nmembers=["crates/proteus-core"]\nresolver="2"\n')
write(core/'crates/proteus-core/Cargo.toml','[package]\nname="proteus-core"\nversion="0.0.0"\nedition="2021"\n[[bin]]\nname="proteus"\npath="src/main.rs"\n')
write(core/'crates/proteus-core/src/main.rs','fn main(){println!("CORE-B");}\n')
write(core/'configs/config.toml','# new fixture config\n')
run(['cargo','generate-lockfile','--offline'],core)
git_commit(core,'fixture core without license to trigger packaging failure')

names = ('Proteus-desktop','Proteus-core','Proteus-modules','Proteus-desktop-extensions')
def base(path, *, core_link=None):
    for relative in ('bin/proteus','bin/proteus-native','proteus-native','install-shortcut','bin/proteus-demo-module','share/extensions/demo/worker'):
        write(path/relative, '#!/bin/sh\necho BASE-A\n', True)
    if core_link:
        (path/'bin/proteus').unlink()
        (path/'bin/proteus').symlink_to(core_link)
    for relative in ('share/icons','share/licenses'):
        (path/relative).mkdir(parents=True,exist_ok=True)
    for name in names:
        write(path/'share/licenses'/name/'LICENSE','synthetic notice\n')
    write(path/'share/configs/config.toml','# fixture config\n')
    write(path/'share/system_proxy.py','# fixture\n')
    write(path/'share/extensions/demo/extension.json',json.dumps({'protocol':1,'command':['worker']}))
    write(path/'share/modules/demo/module.json',json.dumps({'id':'demo','version':'0.0.0','command':['bin/proteus-demo-module'],'exports':{'tool':['demo']},'sha256':sha(path/'bin/proteus-demo-module')}))
    record = {'schema_version':1,'version':'0.0.0','sources':{name:{'commit':'fixture-source-A','dirty':False} for name in names},'desktop_protocol':1,'desktop_features':[], 'binary_sha256':{file.name:sha(file) for file in (path/'bin').iterdir()}}
    write(path/'share/release-sources.json',json.dumps(record,indent=2)+'\n')
    return record

def portable(base_path, *args, check=True):
    return run([sys.executable,desktop/'scripts/portable.py','--base',base_path,'--no-archive',*args],desktop,check=check,extra={'PROTEUS_HARNESS_SOURCE':str(core)})

# Two bases accepted by the real validator differ only in whether Core is a symlink.
# Real Cargo/producer runs; actual missing license fails after copying the built binary.
live = desktop/'build/Proteus'
base(live)
live_before = sha(live/'bin/proteus')
linked_target = ROOT/'shared-core'
write(linked_target,'#!/bin/sh\necho BASE-A\n',True)
linked = ROOT/'linked-base'
base(linked,core_link=linked_target)
linked_before = sha(linked_target)
linked_record_before = (linked/'share/release-sources.json').read_bytes()
failed_linked = portable(linked,'--components','core',check=False)
assert failed_linked.returncode != 0 and 'has no license file' in failed_linked.stderr
assert sha(linked_target) != linked_before
assert run([linked/'bin/proteus']).stdout.strip() == 'CORE-B'
assert sha(live/'bin/proteus') == live_before
assert (linked/'share/release-sources.json').read_bytes() == linked_record_before
plain = ROOT/'plain-base'
base(plain)
plain_before = sha(plain/'bin/proteus')
failed_plain = portable(plain,'--components','core',check=False)
assert failed_plain.returncode != 0 and 'has no license file' in failed_plain.stderr
assert sha(plain/'bin/proteus') == plain_before
symlink_result = {'failed_update_exit':failed_linked.returncode,'error':failed_linked.stderr.splitlines()[-1], 'external_base_before':'BASE-A','external_base_after':run([linked/'bin/proteus']).stdout.strip(),'external_base_metadata_unchanged':True,'output_installation_unchanged':True,'regular_file_control_exit':failed_plain.returncode,'regular_file_control_unchanged':True,'symlink_preserved_in_base':(linked/'bin/proteus').is_symlink()}

# Successful selected update also modifies an external base despite publishing elsewhere.
write(core/'LICENSE','synthetic MIT fixture\n')
git_commit(core,'valid core notices')
success_target = ROOT/'shared-success-core'
write(success_target,'#!/bin/sh\necho BASE-A\n',True)
success_base = ROOT/'success-linked-base'
base(success_base,core_link=success_target)
success = portable(success_base,'--components','core')
assert run([success_base/'bin/proteus']).stdout.strip() == 'CORE-B'
assert run([live/'bin/proteus']).stdout.strip() == 'CORE-B'
assert (live/'bin/proteus').is_symlink()
symlink_result.update(successful_update_exit=success.returncode, successful_update_also_modified_external_base=True, published_binary_still_symlink_to_shared_source=True)

# Independent package CLI upgrade, with a real committed source A -> B and Cargo artifact.
modules = ROOT/'modules'
copy_head(a.modules,'package.py',modules/'package.py')
write(modules/'LICENSE','synthetic notice\n')
write(modules/'Cargo.toml','[workspace]\nmembers=["components/demo"]\nresolver="2"\n')
write(modules/'components/demo/Cargo.toml','[package]\nname="proteus-demo-module"\nversion="0.0.0"\nedition="2021"\n[package.metadata.proteus]\nid="demo"\nimplementation="tool/demo"\n')
write(modules/'components/demo/exports.json','{"tool":["demo"]}\n')
write(modules/'components/demo/src/main.rs','fn main(){println!("MODULE-A");}\n')
write(modules/'.gitignore','dist/\n')
(modules/'tool/demo').mkdir(parents=True)
run(['cargo','generate-lockfile','--offline'],modules)
commit_a = git_commit(modules,'module A')
module_base = ROOT/'module-base'
record_a = base(module_base)
run([sys.executable,'package.py','--package','demo','--install',module_base],modules)
digest_a = sha(module_base/'bin/proteus-demo-module')
record_a['sources']['Proteus-modules'] = {'commit':commit_a,'dirty':False}
record_a['binary_sha256']['proteus-demo-module'] = digest_a
write(module_base/'share/release-sources.json',json.dumps(record_a,indent=2)+'\n')
initial_record_bytes = (module_base/'share/release-sources.json').read_bytes()
write(modules/'components/demo/src/main.rs','fn main(){println!("MODULE-B");}\n')
commit_b = git_commit(modules,'module B')
run([sys.executable,'package.py','--package','demo','--install',module_base],modules)
digest_b = sha(module_base/'bin/proteus-demo-module')
assert digest_b != digest_a
assert run([module_base/'bin/proteus-demo-module']).stdout.strip() == 'MODULE-B'
module_metadata = json.loads((module_base/'share/modules/demo/module.json').read_text())
assert module_metadata['sha256'] == digest_b
assert (module_base/'share/release-sources.json').read_bytes() == initial_record_bytes
reused = portable(module_base,'--reuse-binaries')
reused_record = json.loads((live/'share/release-sources.json').read_text())
assert run([live/'bin/proteus-demo-module']).stdout.strip() == 'MODULE-B'
assert reused_record['binary_sha256']['proteus-demo-module'] == digest_a
assert reused_record['sources']['Proteus-modules']['commit'] == commit_a
provenance_result = {'module_source_A':commit_a,'module_source_B':commit_b,'binary_A_sha256':digest_a,'binary_B_sha256':digest_b,'actual_module_after_install':'MODULE-B','module_metadata_sha256':module_metadata['sha256'],'top_level_record_unchanged_after_install':True,'reuse_cli_exit':reused.returncode,'reused_binary':'MODULE-B','reused_record_binary_sha256':reused_record['binary_sha256']['proteus-demo-module'],'reused_record_modules_source':reused_record['sources']['Proteus-modules']['commit']}

# A later selected Core update refreshes all binary hashes but retains the false module source.
partial = portable(module_base,'--components','core')
partial_record = json.loads((live/'share/release-sources.json').read_text())
assert partial_record['binary_sha256']['proteus-demo-module'] == digest_b
assert partial_record['sources']['Proteus-modules']['commit'] == commit_a
provenance_result.update(later_core_update_exit=partial.returncode,later_core_update_hash_repaired=True,later_core_update_still_claims_module_source_A=True)

result = {'upstream_commits':{name:subprocess.check_output(['git','rev-parse','HEAD'],cwd=repo,text=True).strip() for name,repo in [('Desktop',a.desktop),('Modules',a.modules)]},'production_source_sha256':source_hashes,'symlink_stage':symlink_result,'package_provenance':provenance_result,'scope':'Production packaging scripts unchanged, actual CLI subprocesses, real offline Cargo/rustc and filesystem. Tiny synthetic binaries/layouts replace full applications. No subprocess/build/rename mocks; no real accounts/services.'}
write(ROOT/'results.json',json.dumps(result,indent=2)+'\n')
print(json.dumps(result,indent=2))
