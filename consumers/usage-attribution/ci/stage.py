#!/usr/bin/env python3
"""Fixed commands; outer envelope owns deadline/growth handling. No upstream suite."""
import importlib.util
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

workspace = Path('consumers/usage-attribution')
artifacts = Path('validation/usage-attribution')
ci = workspace/'ci'
spec = importlib.util.spec_from_file_location('contract', ci/'contract.py')
c = importlib.util.module_from_spec(spec); spec.loader.exec_module(c)
commands = []


def save(path, value): path.write_text(json.dumps(value, indent=2, sort_keys=True)+'\n')


def run(label, argv, data=None, expected=0):
    with (artifacts/(label+'.stdout')).open('xb') as out, (artifacts/(label+'.stderr')).open('xb') as err:
        commands.append({'label': label, 'argv': argv, 'returncode': None})
        save(artifacts/'commands.json', commands)
        result = subprocess.run(argv, input=data, stdin=subprocess.DEVNULL if data is None else None, stdout=out, stderr=err)
        commands[-1]['returncode'] = result.returncode; save(artifacts/'commands.json', commands)
        if result.returncode != expected: raise RuntimeError('stage failed: '+label)


def main():
    artifacts.mkdir(parents=True, exist_ok=False)
    save(artifacts/'source-before.json', c.source_identity(workspace))
    try:
        for label, argv in c.plan(workspace):
            data=None
            if label == 'fixture':
                save(artifacts/'binary.json', c.binary_identity())
                data=(workspace/'fixtures/mixed-snapshot.json').read_bytes()
            elif label == 'null': data=b'null'
            elif label == 'invalid': data=b'{"private":"DO_NOT_ECHO"}'
            run(label, argv, data, expected=2 if label == 'invalid' else 0)
        save(artifacts/'binary-after.json', c.binary_identity())
    finally:
        save(artifacts/'source-after.json', c.source_identity(workspace))
    subprocess.run([sys.executable, '-B', '-I', str(ci/'verify.py'), str(workspace), str(artifacts)], check=True)

if __name__ == '__main__': main()
