"""Run only the reviewed synthetic target from a verified isolated copy."""
import hashlib
import importlib
import json
from pathlib import Path
import sys
import unittest


target = Path(sys.argv[1]).resolve()
expected = json.loads(Path(sys.argv[2]).read_text())
for name, digest in expected.items():
    path = target / name
    actual = hashlib.sha256(path.read_bytes()).hexdigest()
    if actual != digest:
        raise RuntimeError(f'Unreviewed source: {path}')
sys.path.insert(0, str(target))
modules = {}
for name in ('adapters', 'binary_identity_test'):
    module = importlib.import_module(name)
    actual = Path(module.__file__).resolve()
    if actual != target / f'{name}.py':
        raise RuntimeError(f'Unexpected module: {actual}')
    modules[name] = module
    print(f'IMPORT {name}: {actual}', flush=True)
suite = unittest.defaultTestLoader.loadTestsFromTestCase(
    modules['binary_identity_test'].PreparedBinaryIdentity,
)
if suite.countTestCases() != 4:
    raise RuntimeError('Unexpected test count')
result = unittest.TextTestRunner(verbosity=2).run(suite)
for name, digest in expected.items():
    if hashlib.sha256((target / name).read_bytes()).hexdigest() != digest:
        raise RuntimeError(f'Source changed during tests: {name}')
print(f'SUMMARY run={result.testsRun} failures={len(result.failures)} '
      f'errors={len(result.errors)} skipped={len(result.skipped)}', flush=True)
sys.exit(0 if result.wasSuccessful() else 1)
