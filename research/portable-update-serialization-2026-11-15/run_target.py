"""Execute only reviewed synthetic tests from an exact isolated source copy."""
import hashlib
import importlib
import json
from pathlib import Path
import sys
import unittest


target = Path(sys.argv[1]).resolve()
expected = json.loads(Path(sys.argv[2]).read_text())
mode = sys.argv[3]
if mode not in ('baseline', 'candidate'):
    raise ValueError(mode)
for name, digest in expected.items():
    if hashlib.sha256((target / name).read_bytes()).hexdigest() != digest:
        raise RuntimeError(f'Unreviewed source: {name}')
sys.path.insert(0, str(target))
tests = importlib.import_module('test_portable_serialization')
if Path(tests.__file__).resolve() != target / 'test_portable_serialization.py':
    raise RuntimeError('Wrong test module')
print(f'TEST_MODULE {tests.__file__}', flush=True)
if mode == 'baseline':
    suite = unittest.TestSuite([
        tests.PortableSerializationTests(
            'test_overlapping_default_base_updates_preserve_both_components'),
    ])
else:
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(tests.PortableSerializationTests)
if suite.countTestCases() != (1 if mode == 'baseline' else 6):
    raise RuntimeError('Unexpected test count')
result = unittest.TextTestRunner(verbosity=2).run(suite)
for name, digest in expected.items():
    if hashlib.sha256((target / name).read_bytes()).hexdigest() != digest:
        raise RuntimeError(f'Source changed during tests: {name}')
print(f'SUMMARY run={result.testsRun} failures={len(result.failures)} '
      f'errors={len(result.errors)} skipped={len(result.skipped)}', flush=True)
sys.exit(0 if result.wasSuccessful() else 1)
