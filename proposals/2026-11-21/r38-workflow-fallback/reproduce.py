#!/usr/bin/env python3
"""Verify a clean pinned tree, unit suite and differential. Input checkout is read only."""
from argparse import ArgumentParser
from pathlib import Path
from tempfile import TemporaryDirectory
from subprocess import run
import shutil

here = Path(__file__).resolve().parent
base = '9469e3b12529d08b1f4a76882693e2065e842c51'
p = ArgumentParser()
p.add_argument('repository', type=Path)
p.add_argument('--cached-rustc', type=Path, help='rustc args file, one per line, for locally built locked dependencies')
args = p.parse_args()
with TemporaryDirectory(prefix='workflow-fallback-') as tmp:
    root = Path(tmp)
    archive = root / 'tree.tar'
    with archive.open('wb') as f:
        run(['git','-C',args.repository.resolve(),'archive',base],stdout=f,check=True)
    run(['tar','xf',archive],cwd=root,check=True)
    crate=root/'workflow/coding-workflow'
    test=crate/'tests'
    versions=test/'versions'
    versions.mkdir(parents=True)
    source=crate/'src/output_text.rs'
    shutil.copyfile(source,versions/'before.rs')
    run(['git','apply','--check',here/'candidate.patch'],cwd=root,check=True)
    run(['git','apply',here/'candidate.patch'],cwd=root,check=True)
    shutil.copyfile(source,versions/'after.rs')
    shutil.copyfile(here/'probe.rs',test/'fallback_probe.rs')
    if args.cached_rustc:
        flags=args.cached_rustc.read_text().splitlines()
        for file,name,opt in [(crate/'src/lib.rs','coding_workflow',[]),(test/'fallback_probe.rs','fallback_probe',['-O'])]:
            run(['rustc','--edition=2024','--test','--crate-name',name,*flags,*opt,file,'-o',root/name],cwd=root,check=True)
            run([root/name,'--test-threads=1','--nocapture'],cwd=root,check=True)
    else:
        run(['cargo','test','--locked','-p','coding-workflow','--lib','--','--test-threads=1'],cwd=root,check=True)
        run(['cargo','test','--release','--locked','-p','coding-workflow','--test','fallback_probe','--',
             '--test-threads=1','--nocapture'],cwd=root,check=True)
