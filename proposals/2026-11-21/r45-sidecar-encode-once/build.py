#!/usr/bin/env python3
"""Build only the storage crate and its genuine module main with one test-only probe."""
import argparse, io, json, os, struct, subprocess, tarfile
from pathlib import Path
PIN='9469e3b12529d08b1f4a76882693e2065e842c51'
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--candidate', action='store_true', help='apply the production patch before adding the same measurement probe')
p.add_argument('--cpu-clock',action='store_true',help='also sample the Linux request thread CPU clock (benchmark only)')
p.add_argument('--fingerprint', help='bin fingerprint directory suffix if the target has multiple prior builds')
for key in ['repo','target','out']: p.add_argument(key,type=Path)
a=p.parse_args(); repo=a.repo.resolve(); target=a.target.resolve(); out=a.out.resolve(); out.mkdir(parents=True,exist_ok=True)
files=['storage/session-storage/src','components/session-storage-module/src']
data=subprocess.check_output(['git','-C',repo,'archive',PIN,*files])
with tarfile.open(fileobj=io.BytesIO(data)) as tf: tf.extractall(out,filter='data')
if a.candidate: subprocess.run(['git','apply',str((Path(__file__).parent/'candidate.patch').resolve())],cwd=out,check=True)
exec((Path(__file__).parent/'instrument.py').read_text())
fp=target/'debug/.fingerprint'; deps=target/'debug/deps'
def recipe(name,file):
    return json.loads((fp/name/file).read_text())
def externs(recipe,override=None):
    result=[]
    for _,name,_,val in recipe['deps']:
        if override and name in override:
            lib=override[name]
        else:
            valhex=struct.pack('<Q',val).hex()
            ids=[p.parent.name.rsplit('-',1)[1] for p in fp.glob('*/lib-'+name) if p.read_text().strip()==valhex]
            assert len(ids)==1,(name,ids)
            lib=deps/f'lib{name}-{ids[0]}.rlib'
        assert lib.is_file(),lib
        result+=['--extern',f'{name}={lib}']
    return result
# Both compile recipes come from the same locked workspace storage worker, using matching dependency fingerprints.
recipes=[f for f in fp.glob('proteus-session-storage-module-*/bin-proteus-session-storage-module.json')
         if a.fingerprint is None or f.parent.name.endswith('-'+a.fingerprint)]
assert len(recipes)==1, 'Expected one worker fingerprint; select with --fingerprint: '+str([f.parent.name for f in recipes])
binrecipe=recipe(recipes[0].parent.name,recipes[0].name)
storeval=next(struct.pack('<Q',v).hex() for _,n,_,v in binrecipe['deps'] if n=='session_storage')
storemark=next(p for p in fp.glob('*/lib-session_storage') if p.read_text().strip()==storeval)
storerecipe=recipe(storemark.parent.name,'lib-session_storage.json')
common=['rustc','--edition=2024','-C','opt-level=3','-C','debuginfo=0','-C','link-arg=-fuse-ld=lld','-L',f'dependency={deps}']
store=out/'libsession_storage.rlib'; exe=out/'module'
clock_dep=[]
if a.cpu_clock:
    libs=list(deps.glob('liblibc-*.rlib'));assert len(libs)==1,libs
    clock_dep=['--extern',f'libc={libs[0]}']
subprocess.run(common+clock_dep+['--crate-name','session_storage','--crate-type','rlib',out/'storage/session-storage/src/lib.rs','-o',store]+externs(storerecipe),check=True)
native=[]
for folder in (target/'debug/build').glob('*/out'):
    if list(folder.glob('*.a')): native+=['-L',f'native={folder}']
env=dict(os.environ,CARGO_PKG_NAME='proteus-session-storage-module',CARGO_PKG_VERSION='0.1.0-alpha.3')
subprocess.run(common+['-C','strip=symbols',out/'components/session-storage-module/src/main.rs','-o',exe]+externs(binrecipe,{'session_storage':store})+native,env=env,check=True)
