"""Fixed CI command and source identities shared by producer and verifier."""
import hashlib
import os
from pathlib import Path
import sys


def source_identity(workspace):
    result = {}; total = 0
    paths = sorted(workspace.rglob('*'))
    if len(paths)>256: raise ValueError('source entry bound')
    workflow = workspace.parents[1]/'.github/workflows/check-usage-attribution.yml'
    paths.append(workflow)
    for p in paths:
        if p.is_symlink(): raise ValueError('source symlink')
        if not p.is_file(): continue
        data = p.read_bytes(); total += len(data)
        if len(data)>1024*1024 or total>2*1024*1024: raise ValueError('source byte bound')
        key = p.relative_to(workspace).as_posix() if p != workflow else '@workflow/check-usage-attribution.yml'
        result[key] = hashlib.sha256(data).hexdigest()
    return result


def binary_path(): return Path(os.environ['CARGO_TARGET_DIR'])/'debug/usage-attribution-stdin'

def binary_identity():
    path = binary_path()
    if path.is_symlink() or not path.is_file() or not 0 < path.stat().st_size <= 64*1024*1024:
        raise ValueError('binary not bounded regular file')
    data = path.read_bytes()
    return {'path': str(path), 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}


def plan(workspace):
    ci=workspace/'ci'; manifest=str(workspace/'Cargo.toml'); binary=str(binary_path())
    return [
      ('toolchain', ['rustup','toolchain','install','1.95.0','--profile','minimal','--component','rustfmt']),
      ('rustc',['rustc','+1.95.0','-Vv']),('cargo',['cargo','+1.95.0','-V']),
      ('envelope-controls',[sys.executable,'-B','-I',str(ci/'test_envelope.py')]),
      ('validator-controls',[sys.executable,'-B','-I',str(ci/'test_verify.py')]),
      ('live-controls',[sys.executable,'-B','-I',str(ci/'live_controls.py'),'validation/usage-attribution/live']),
      ('format',['cargo','+1.95.0','fmt','--check','--manifest-path',manifest]),
      ('fetch',['cargo','+1.95.0','fetch','--locked','--manifest-path',manifest]),
      *[(target,['cargo','+1.95.0','test','--locked','--offline','--manifest-path',manifest,'--test',target,'--','--test-threads=1']) for target in ('projection','stdio')],
      ('fixture',[binary]),('null',[binary]),('invalid',[binary])]
