#!/usr/bin/env python3
"""Synthetic helper-log controls, never parser/runtime evidence."""
import importlib.util
from pathlib import Path
import sys
import unittest

sys.dont_write_bytecode = True
spec = importlib.util.spec_from_file_location("logs", Path(__file__).with_name("verify_helper_logs.py"))
logs = importlib.util.module_from_spec(spec)
spec.loader.exec_module(logs)


class Controls(unittest.TestCase):
    def setUp(self):
        self.required = ["test_alpha", "test_beta"]
        self.text = "test_alpha (__main__.Controls.test_alpha) ... ok\ntest_beta (__main__.Controls.test_beta) ... ok\n\nRan 2 tests in 0.001s\n\nOK\n"

    def test_exact_positive(self):
        self.assertEqual(logs.verify(self.text, self.required)["passed"], 2)

    def test_renamed_case_same_total(self):
        text = self.text.replace("test_beta", "test_replacement")
        with self.assertRaisesRegex(ValueError, "exact named cases"):
            logs.verify(text, self.required)

    def test_skipped_line(self):
        text = self.text.replace("test_beta) ... ok", "test_beta) ... skipped 'reason'")
        with self.assertRaisesRegex(ValueError, "exact passing case"):
            logs.verify(text, self.required)

    def test_wrong_summary(self):
        with self.assertRaisesRegex(ValueError, "single summary"):
            logs.verify(self.text.replace("Ran 2 tests", "Ran 3 tests"), self.required)


if __name__ == "__main__":
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Controls))
    raise SystemExit(0 if result.wasSuccessful() and result.testsRun == 4 and not result.skipped else 1)
