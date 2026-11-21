#!/usr/bin/env python3
"""A/B on Linux. Fresh checkout applies the patch; Cargo release by default.
--cache: optional read-only Cargo debug target for a mostly optimized direct rustc build.
"""
import argparse, json, os, shutil, struct, subprocess, tempfile
from pathlib import Path
P=Path(__file__).resolve().parent
SHA='9469e3b12529d08b1f4a76882693e2065e842c51'
def run(*a,**kw):return subprocess.run(list(map(str,a)),check=True,**kw)
def make(root, package, out, count, cache):
    # Do not instrument any timed binary. Counting binary records the actual
    # updates in both copies, in a separate invocation, with identical inputs.
    d=package/'examples'/'r38_probe'; d.mkdir(parents=True,exist_ok=True)
    for arm in ('stock','candidate'):
        original=(root/f'{arm}.rs').read_text()
        line='rolling = rolling.wrapping_shl(1).wrapping_add(GEAR[*byte as usize]);'
        assert original.count(line)==1
        if count:original=original.replace(line, 'crate::LOOKUPS.set(crate::LOOKUPS.get()+1); '+line)
        (d/f'{arm}.rs').write_text(original)
    shutil.copy(package/'src/io.rs',d/'io.rs')
    shutil.copy(P/'probe.rs',d/'main.rs')
    if cache:
        deps=cache/'debug/deps'; fproot=cache/'debug/.fingerprint'
        fp=sorted(fproot.glob('session-storage-*/test-lib-session_storage.json'))[0]
        recipe=json.loads(fp.read_text()); args=['rustc','--edition=2024','-C','opt-level=3','-C','debuginfo=0','-C','link-arg=-fuse-ld=lld','-L',f'dependency={deps}']
        for _,name,_,val in recipe['deps']:
            if name not in ('anyhow','ring','tempfile','serde','serde_json','uuid'):continue
            hexd=struct.pack('<Q',val).hex()
            found=[p for p in fproot.glob('*/lib-'+name) if p.read_text().strip()==hexd]
            assert len(found)==1,(name,found)
            suffix=found[0].parent.name.rsplit('-',1)[1]
            lib=deps/f'lib{name}-{suffix}.rlib'
            assert lib.is_file();args+=['--extern',f'{name}={lib}']
        for folder in (cache/'debug/build').glob('*/out'):
            if list(folder.glob('*.a')):args+=['-L',f'native={folder}']
        if count:args+=['--cfg','gear_count']
        exe=root/'probe'
        run(*args,d/'main.rs','-o',exe)
        with out.open('w') as f: run(exe,stdout=f)
    else:
        env=dict(os.environ)
        # Only the example's last compilation needs the instrumentation cfg.
        cmd=['cargo','rustc','--locked','--release','-p','session-storage','--example','r38_probe','--message-format=json']
        if count:cmd+=['--','--cfg','gear_count']
        result=run(*cmd,cwd=package,env=env,stdout=subprocess.PIPE,text=True)
        executables=[json.loads(line).get('executable') for line in result.stdout.splitlines() if line]
        exe=next(x for x in reversed(executables) if x)
        with out.open('w') as f:run(exe,stdout=f)
parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('repo',type=Path);parser.add_argument('output',type=Path);parser.add_argument('--cache',type=Path)
a=parser.parse_args();repo=a.repo.resolve();output=a.output.resolve();output.mkdir(exist_ok=True,parents=True)
with tempfile.TemporaryDirectory() as tmp:
    root=Path(tmp); tree=root/'repo'; run('git','clone','--quiet','--shared','--no-checkout',repo,tree)
    run('git','checkout','-q','--detach',SHA,cwd=tree);package=tree/'storage/session-storage';s=package/'src/blob_codec.rs'
    shutil.copy(s,root/'stock.rs');run('git','apply','--check',P/'source.patch',cwd=tree);run('git','apply',P/'source.patch',cwd=tree);shutil.copy(s,root/'candidate.rs')
    for name,count in [('work',True),('timing',False)]:make(root,package,output/f'{name}.csv',count,a.cache.resolve() if a.cache else None)
