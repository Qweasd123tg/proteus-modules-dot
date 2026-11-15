"""Run exact reviewed command-construction tests from one isolated copy."""
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
        raise RuntimeError(f'Unreviewed file: {name}')
sys.path.insert(0, str(target))
tests = importlib.import_module('test_build_module_paths')
if Path(tests.__file__).resolve() != target / 'test_build_module_paths.py':
    raise RuntimeError('Wrong test module')
print(f'TEST_MODULE {tests.__file__}', flush=True)
if mode == 'baseline':
    suite = unittest.TestSuite([tests.BuildModulePathTests(
        'test_relative_bundle_and_target_dir_use_callers_directory')])
else:
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(tests.BuildModulePathTests)
if suite.countTestCases() != (1 if mode == 'baseline' else 5):
    raise RuntimeError('Unexpected test count')
result = unittest.TextTestRunner(verbosity=2).run(suite)
for name, digest in expected.items():
    if hashlib.sha256((target / name).read_bytes()).hexdigest() != digest:
        raise RuntimeError(f'Changed source: {name}')
print(f'SUMMARY run={result.testsRun} failures={len(result.failures)} '
      f'errors={len(result.errors)} skipped={len(result.skipped)}', flush=True)
sys.exit(0 if result.wasSuccessful() else 1)
