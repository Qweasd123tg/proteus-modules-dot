"""Pinned CAS runtime gate contract; no lock regeneration or user database."""
import hashlib
import os
from pathlib import Path
import sys

LOCK_SHA='2b319cbe3ec46e35906574563eef2af4623e16d946665d03574480704dcbd2ea'
TARGET_COUNTS={'actual_modules':4,'bounds':5,'evidence_contract':21,'raw_arguments':7,'storage':17,'wire':7,'workflow':8}


def source_identity(workspace):
    result={};total=0;roots=[workspace,workspace.parent/'evidence-spans']
    for root in roots:
        paths=sorted(root.rglob('*'))
        if not root.is_dir() or len(paths)>256: raise ValueError('source inventory missing or too large')
        for p in paths:
            if p.is_symlink():raise ValueError('source symlink')
            if not p.is_file():continue
            data=p.read_bytes();total+=len(data)
            if len(data)>1024*1024 or total>4*1024*1024:raise ValueError('source byte bound')
            result[p.relative_to(workspace.parent).as_posix()]=hashlib.sha256(data).hexdigest()
    workflow=workspace.parents[1]/'.github/workflows/check-correction-memory.yml'
    result['@workflow/check-correction-memory.yml']=hashlib.sha256(workflow.read_bytes()).hexdigest()
    if result['correction-memory/Cargo.lock']!=LOCK_SHA:raise ValueError('reviewed lock identity changed')
    return result


def binaries():
    target=Path(os.environ['CARGO_TARGET_DIR'])/'debug'
    return {'module':target/'proteus-example-correction-memory','example':target/'examples/correction_workflow'}


def binary_identity():
    result={}
    for name,path in binaries().items():
        if path.is_symlink() or not path.is_file() or not 0<path.stat().st_size<=128*1024*1024:raise ValueError('binary bound/type')
        data=path.read_bytes();result[name]={'path':str(path),'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()}
    return result


def plan(workspace):
    ci=workspace/'ci';m=str(workspace/'Cargo.toml')
    fixed=['--locked','--offline','--manifest-path',m]
    return [
      ('toolchain',['rustup','toolchain','install','1.95.0','--profile','minimal','--component','rustfmt','--no-self-update']),
      ('rustc',['rustc','+1.95.0','-Vv']),('cargo',['cargo','+1.95.0','-V']),
      ('envelope-controls',[sys.executable,'-B','-I',str(ci/'test_envelope.py')]),
      ('validator-controls',[sys.executable,'-B','-I',str(ci/'test_runtime.py')]),
      ('live-controls',[sys.executable,'-B','-I',str(ci/'live_controls.py'),'validation/correction-memory/live']),
      ('format',['cargo','+1.95.0','fmt','--check','--manifest-path',m]),
      ('fetch',['cargo','+1.95.0','fetch','--locked','--manifest-path',m]),
      ('metadata',['cargo','+1.95.0','metadata',*fixed,'--format-version','1']),
      ('build',['cargo','+1.95.0','build',*fixed,'--all-targets']),
      *[('test-'+name,['cargo','+1.95.0','test',*fixed,'--test',name,'--','--test-threads=1']) for name in TARGET_COUNTS],
      ('example',[str(binaries()['example'])])]
