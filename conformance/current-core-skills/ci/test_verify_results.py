#!/usr/bin/env python3
"""Pure authored gate controls, not evidence that Core was executed."""
import copy
import importlib.util
import json
from pathlib import Path
import sys
import unittest

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("verifier", HERE / "verify_results.py")
v = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v)


class Controls(unittest.TestCase):
    def setUp(self):
        self.expected = json.loads((HERE.parent / "scenarios.json").read_text())
        self.report = {"schema_version": 1, "core_commit": self.expected["core_commit"],
                       "checks": [{"name": n, "status": "passed", "evidence": {}}
                                  for n in self.expected["checks"]]}
        self.stderr = "\n".join("SKILLS_CORE_CHECK " + json.dumps(
            {"name": n, "status": "passed"}) for n in self.expected["checks"])
        self.before = {"harness": {"source": "sha"}, "portable_module": {"source": "sha"}}
        self.after = copy.deepcopy(self.before)

    def run_gate(self):
        return v.verify(self.report, self.stderr, self.expected, self.before, self.after)

    def test_valid_complete_control(self):
        self.assertEqual(self.run_gate()["core_checks"], 11)

    def test_omitted_check(self):
        self.report["checks"].pop()
        with self.assertRaisesRegex(ValueError, "exact ordered 11"):
            self.run_gate()

    def test_duplicate_check(self):
        self.report["checks"][-1] = self.report["checks"][0]
        with self.assertRaisesRegex(ValueError, "exact ordered 11"):
            self.run_gate()

    def test_nonpassing_check(self):
        self.report["checks"][0]["status"] = "skipped"
        with self.assertRaisesRegex(ValueError, "did not pass"):
            self.run_gate()

    def test_boolean_schema_version(self):
        self.report["schema_version"] = True
        with self.assertRaisesRegex(ValueError, "report version"):
            self.run_gate()

    def test_float_schema_version(self):
        self.report["schema_version"] = 1.0
        with self.assertRaisesRegex(ValueError, "report version"):
            self.run_gate()

    def test_nonfinite_json(self):
        for constant in ("NaN", "Infinity", "-Infinity"):
            with self.subTest(constant=constant):
                with self.assertRaisesRegex(ValueError, "non-finite JSON constant"):
                    v.decode('{"value":' + constant + '}')

    def test_wrong_core_pin(self):
        self.report["core_commit"] = "wrong"
        with self.assertRaisesRegex(ValueError, "Core pin"):
            self.run_gate()

    def test_missing_completion_marker(self):
        self.stderr = "\n".join(self.stderr.splitlines()[:-1])
        with self.assertRaisesRegex(ValueError, "completion markers"):
            self.run_gate()

    def test_changed_source(self):
        self.after["portable_module"]["source"] = "changed"
        with self.assertRaisesRegex(ValueError, "source hashes changed"):
            self.run_gate()

    def test_duplicate_json_key(self):
        with self.assertRaisesRegex(ValueError, "duplicate JSON key: status"):
            v.decode('{"status":"failed","status":"passed"}')


if __name__ == "__main__":
    result = unittest.TextTestRunner(verbosity=2).run(
        unittest.defaultTestLoader.loadTestsFromTestCase(Controls))
    raise SystemExit(0 if result.wasSuccessful() and result.testsRun == 11 and not result.skipped else 1)
