#!/usr/bin/env python3
"""First hosted phase only: resolve fixed dependencies, retain lock; never build."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tomllib

workspace = Path('examples/correction-memory')
artifacts = Path('validation/cas-lock-resolution')
commands = []


def save(path, value): path.write_text(json.dumps(value, sort_keys=True, indent=2)+'\n')

def identities():
    return {p.as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for root in (workspace, Path('examples/evidence-spans')) for p in sorted(root.rglob('*'))
        if p.is_file() and p != workspace/'Cargo.lock'}

def run(label, argv):
    commands.append({'label': label, 'argv': argv, 'returncode': None});save(artifacts/'commands.json', commands)
    with (artifacts/(label+'.stdout')).open('xb') as out, (artifacts/(label+'.stderr')).open('xb') as err:
        result = subprocess.run(argv, stdin=subprocess.DEVNULL, stdout=out, stderr=err)
    commands[-1]['returncode'] = result.returncode;save(artifacts/'commands.json', commands)
    if result.returncode: raise RuntimeError('stage failed: '+label)

def main():
    artifacts.mkdir(parents=True, exist_ok=False)
    if (workspace/'Cargo.lock').exists(): raise RuntimeError('resolution phase requires absent CAS lock')
    before=identities();save(artifacts/'source-before.json', before)
    try:
        run('toolchain', ['rustup', 'toolchain', 'install', '1.95.0', '--profile', 'minimal', '--no-self-update'])
        run('rustc', ['rustc', '+1.95.0', '-Vv'])
        run('controller-controls', [sys.executable, '-B', '-I', str(workspace/'ci/test_envelope.py')])
        run('generate-lockfile', ['cargo', '+1.95.0', 'generate-lockfile', '--manifest-path', str(workspace/'Cargo.toml')])
        lock=workspace/'Cargo.lock';shutil.copyfile(lock,artifacts/'Cargo.lock')
        packages=tomllib.loads(lock.read_text())['package']
        indexed={p['name']:p for p in packages}
        assert indexed['rusqlite']['version']=='0.33.0'
        assert indexed['ring']['version']=='0.17.14'
        assert indexed['libsqlite3-sys']['version']=='0.31.0'
        for p in packages:
            if p['name'].startswith('proteus-') and 'source' in p:
                assert p['source'].endswith('#3f36a003b4f3fde2242fc80f7aedac00dd127d1d')
        run('metadata', ['cargo', '+1.95.0', 'metadata', '--locked', '--offline', '--no-deps', '--format-version', '1', '--manifest-path', str(workspace/'Cargo.toml')])
        save(artifacts/'lock-summary.json', {'status':'resolved_not_reviewed_not_compiled','sha256':hashlib.sha256(lock.read_bytes()).hexdigest(),
            'packages':packages,'compile_or_test_performed':False})
    finally:
        after=identities();save(artifacts/'source-after.json', after)
        if after != before: raise RuntimeError('non-lock source changed')

if __name__=='__main__': main()
