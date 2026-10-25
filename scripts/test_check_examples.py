#!/usr/bin/env python3
"""Runner regression tests. Uses no Rust toolchain and executes no module binary."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

SPEC = importlib.util.spec_from_file_location("check_examples", Path(__file__).with_name("check_examples.py"))
checks = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = checks
SPEC.loader.exec_module(checks)


class RunnerTests(unittest.TestCase):
    def test_outcomes_are_not_skip_to_pass(self):
        self.assertEqual(checks.outcome([]), ("incomplete", 2))
        self.assertEqual(checks.outcome([{"status": "not_run"}]), ("incomplete", 2))
        self.assertEqual(checks.outcome([{"status": "passed"}, {"status": "not_run"}]), ("incomplete", 2))
        self.assertEqual(checks.outcome([{"status": "failed"}, {"status": "not_run"}]), ("failed", 1))
        self.assertEqual(checks.outcome([{"status": "passed"}]), ("passed", 0))

    def test_tests_need_actual_execution_and_required_wire(self):
        passed = "test wire_case ... ok\ntest result: ok. 1 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out;\n"
        self.assertEqual(checks.test_evidence(passed, "wire_case")["passed"], 1)
        for output in ("", "test result: ok. 0 passed; 0 failed; 0 ignored;",
                       "test result: ok. 1 passed; 0 failed; 1 ignored;",
                       "test result: FAILED. 0 passed; 1 failed; 0 ignored;"):
            with self.subTest(output=output), self.assertRaises(ValueError):
                checks.test_evidence(output, None)
        with self.assertRaises(ValueError):
            checks.test_evidence(passed, "different_wire")

    def create_example(self, root):
        example = checks.EXAMPLES[1]
        folder = root / "examples" / example.folder
        folder.mkdir(parents=True)
        (folder / "Cargo.toml").write_text(
            f'[package]\nname = "{example.binary}"\n[workspace]\n[dependencies]\n'
            f'proteus-module-sdk = {{git = "{checks.SDK_GIT}", rev = "{checks.SDK_REV}"}}\n')
        (folder / "Cargo.lock").write_text(
            f'version = 4\n[[package]]\nname = "proteus-module-sdk"\nsource = "{checks.SDK_SOURCE}"\n')
        return example, folder

    def test_exact_source_and_lock_pin_required(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            example, folder = self.create_example(root)
            self.assertEqual(len(checks.preflight(root, example)["lock_sha256"]), 64)
            lock = folder / "Cargo.lock"
            lock.write_text(lock.read_text().replace(checks.SDK_REV, "0" * 40))
            with self.assertRaises(ValueError):
                checks.preflight(root, example)

    def test_manifest_override_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            example, folder = self.create_example(root)
            manifest = folder / "Cargo.toml"
            manifest.write_text(manifest.read_text() + '[patch.crates-io]\nanyhow = { path = "foreign" }\n')
            with self.assertRaises(ValueError):
                checks.preflight(root, example)

    def test_compiler_reported_binary_not_target_path_guess(self):
        with tempfile.TemporaryDirectory() as directory:
            binary = Path(directory) / "custom-output"
            binary.write_bytes(b"not executable; inspected only")
            artifact = {"reason": "compiler-artifact", "target": {"name": "module", "kind": ["bin"]},
                        "executable": str(binary)}
            self.assertEqual(checks.build_binary(json.dumps(artifact), "module"), binary)
            with self.assertRaises(ValueError):
                checks.build_binary(json.dumps(artifact), "different-module")
            with self.assertRaises(ValueError):
                checks.build_binary("finished but no artifact", "module")

    def test_smoke_requires_all_executed_checks(self):
        report = {"schema_version": 1, "status": "passed", "checks_executed": [str(n) for n in range(14)]}
        self.assertEqual(checks.smoke_evidence(json.dumps(report))["count"], 14)
        report["checks_executed"] = []
        with self.assertRaises(ValueError):
            checks.smoke_evidence(json.dumps(report))
        with self.assertRaises(ValueError):
            checks.smoke_evidence('prefix "status": "passed"')

    def test_source_hash_includes_code_test_and_config_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "src").mkdir()
            (root / "tests").mkdir()
            (root / "src" / "main.rs").write_text("// fixture")
            (root / "tests" / "fixture.json").write_text("{}")
            (root / "module-config.json").write_text("{}")
            before = checks.source_evidence(root)
            self.assertEqual(len(before["source_files"]), 3)
            (root / "module-config.json").write_text('{"changed": true}')
            self.assertNotEqual(before["source_sha256"], checks.source_evidence(root)["source_sha256"])

    def test_command_failure_recorded_and_paths_normalized(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            runner = checks.Runner(root, root / "validation" / "results.json", 1)
            process = mock.Mock(returncode=7)
            process.communicate.return_value = (f"failure inside {root}/examples/pi-ready-steps", None)
            with mock.patch.object(checks.subprocess, "Popen", return_value=process) as launch:
                result, _ = runner.command("example", "test", ["fixed", "--arg"], root)
            self.assertEqual(result["status"], "failed")
            self.assertEqual(runner.finish(), 1)
            call = launch.call_args
            self.assertEqual(call.args[0], ["fixed", "--arg"])
            self.assertNotIn("shell", call.kwargs)
            self.assertNotIn(str(root), runner.report.read_text())
            self.assertNotIn(str(root), (runner.log_dir / "example-test.log").read_text())

    def test_missing_command_is_failure_not_pass(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            runner = checks.Runner(root, root / "validation" / "results.json", 1)
            with mock.patch.object(checks.subprocess, "Popen", side_effect=FileNotFoundError("missing")):
                result, _ = runner.command("example", "test", ["not-installed"], root)
            self.assertEqual(result["status"], "failed")
            self.assertIsNone(result["returncode"])

    def test_timeout_is_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            runner = checks.Runner(root, root / "validation" / "results.json", 1)
            process = mock.Mock(pid=12345, returncode=-9)
            process.communicate.side_effect = [subprocess.TimeoutExpired(["fixed"], 1), ("partial", None)]
            with mock.patch.object(checks.subprocess, "Popen", return_value=process), \
                    mock.patch.object(checks.os, "killpg", create=True):
                result, _ = runner.command("example", "test", ["fixed"], root)
            self.assertEqual(result["status"], "failed")
            self.assertEqual(result["reason"], "timeout")

    def test_cleanup_handles_already_exited_group(self):
        process = mock.Mock(pid=12345)
        process.communicate.return_value = ("partial", None)
        with mock.patch.object(checks.os, "killpg", side_effect=ProcessLookupError(), create=True):
            output, warning = checks.stop_command(process)
        self.assertEqual(output, "partial")
        self.assertIsNone(warning)
        process.communicate.assert_called_once_with(timeout=5)

    def test_cleanup_pipe_and_reap_are_bounded(self):
        process = mock.Mock(pid=12345)
        process.communicate.side_effect = subprocess.TimeoutExpired(["fixed"], 5, output=b"partial")
        process.wait.side_effect = subprocess.TimeoutExpired(["fixed"], 1)
        with mock.patch.object(checks.os, "killpg", create=True):
            output, warning = checks.stop_command(process)
        self.assertEqual(output, "partial")
        self.assertIn("pipe deadline", warning)
        self.assertIn("reap deadline", warning)
        process.stdout.close.assert_called_once()
        process.wait.assert_called_once_with(timeout=1)


if __name__ == "__main__":
    unittest.main()
