#!/usr/bin/env python3
"""Run only these tiny authored Python child strings; no Core coverage claim."""
import importlib.util
from pathlib import Path
import subprocess
import sys
import unittest

sys.dont_write_bytecode = True
spec = importlib.util.spec_from_file_location("runner", Path(__file__).with_name("process_capture.py"))
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


class Controls(unittest.TestCase):
    def child(self, code):
        return subprocess.Popen([sys.executable, "-I", "-B", "-c", code],
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                start_new_session=True)

    def test_complete_stdout_stderr(self):
        child = self.child("import sys; print('output'); print('diagnostic', file=sys.stderr)")
        out, err, error = runner.capture(child, timeout=5, max_bytes=64)
        self.assertIsNone(error)
        self.assertEqual((out, err, child.returncode), ("output\n", "diagnostic\n", 0))

    def test_capture_overflow_kills_and_reaps_controller(self):
        child = self.child("import sys,time; sys.stdout.write('x'*1000); sys.stdout.flush(); time.sleep(10)")
        out, _, error = runner.capture(child, timeout=5, max_bytes=64)
        self.assertEqual(len(out), 64)
        self.assertIn("stdout exceeds 64-byte capture limit", error)
        self.assertIsNotNone(child.returncode)

    def test_deadline_kills_and_reaps_controller(self):
        child = self.child("import time; time.sleep(10)")
        _, _, error = runner.capture(child, timeout=0.1, max_bytes=64)
        self.assertIn("0.1-second probe timeout", error)
        self.assertIsNotNone(child.returncode)

    def test_non_utf8_is_not_silently_accepted(self):
        child = self.child("import os; os.write(1,b'\\xff')")
        _, _, error = runner.capture(child, timeout=5, max_bytes=64)
        self.assertIn("stdout is not UTF-8", error)
        self.assertEqual(child.returncode, 0)


if __name__ == "__main__":
    result = unittest.TextTestRunner(verbosity=2).run(
        unittest.defaultTestLoader.loadTestsFromTestCase(Controls))
    raise SystemExit(0 if result.wasSuccessful() and result.testsRun == 4 and not result.skipped else 1)
