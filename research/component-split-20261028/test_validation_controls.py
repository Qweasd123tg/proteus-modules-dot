"""Controller-only synthetic checks; never invoke Cargo, Git or product code."""
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

spec = importlib.util.spec_from_file_location("controller", Path(__file__).with_name("run_validation.py"))
controller = importlib.util.module_from_spec(spec)
spec.loader.exec_module(controller)


class Controls(unittest.TestCase):
    def test_selected_graph_accepts_internal_contracts(self):
        graph = controller.parse_graph("0::proteus-plan-module v0.1.0 (/tmp/plan)::\n1::proteus-contracts v0.1.0 (https://example.invalid#abc)::default\n", "proteus-plan-module")
        self.assertEqual(graph["packages"], ["proteus-contracts", "proteus-plan-module"])

    def test_graph_rejects_unparsed_trailer(self):
        with self.assertRaisesRegex(ValueError, "unrecognized"):
            controller.parse_graph("0::proteus-plan-module v0.1.0::\nopaque trailer\n", "proteus-plan-module")

    def test_graph_rejects_wrong_root(self):
        with self.assertRaisesRegex(ValueError, "root"):
            controller.parse_graph("0::proteus-reference-module v0.1.0::\n", "proteus-plan-module")

    def test_graph_rejects_aggregate_or_core_in_plan(self):
        for package in ("proteus-reference-module", "proteus-core", "proteus-native", "model-pack"):
            with self.subTest(package=package), self.assertRaisesRegex(ValueError, "forbidden"):
                controller.parse_graph(f"0::proteus-plan-module v0.1.0::\n1::{package} v0.1.0::\n", "proteus-plan-module")

    def test_core_runtime_also_forbidden_in_reference(self):
        with self.assertRaisesRegex(ValueError, "forbidden"):
            controller.parse_graph("0::proteus-reference-module v0.1.0::\n1::proteus-core v0.1.0::\n", "proteus-reference-module")

    def test_required_format_failure_does_not_gate_independent_compile(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            validation = controller.Validation(root / "work", root / "evidence")
            validation.stage("source", lambda: None)
            validation.stage("format", lambda: (_ for _ in ()).throw(ValueError("format defect")), ("source",))
            validation.stage("plan_tests", lambda: "compile diagnostics collected", ("source",))
            self.assertEqual(validation.report["stages"]["format"]["status"], "fail")
            self.assertEqual(validation.report["stages"]["plan_tests"]["status"], "pass")
            self.assertTrue(any(s["status"] != "pass" for s in validation.report["stages"].values()))

    def test_prerequisite_failure_is_never_pass(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            validation = controller.Validation(root / "work", root / "evidence")
            call = mock.Mock()
            validation.stage("wire_parity", call, ("artifact_identity_before",))
            call.assert_not_called()
            self.assertEqual(validation.report["stages"]["wire_parity"]["status"], "not_run")

    def test_fresh_work_rejects_existing_directory_before_commands(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            validation = controller.Validation(root, root / "evidence")
            with mock.patch.object(validation, "command") as command:
                with self.assertRaisesRegex(ValueError, "already exists"):
                    validation.prepare()
                command.assert_not_called()

    def test_owned_child_separate_logs_failure_no_retry(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            validation = controller.Validation(root, root / "evidence")
            with self.assertRaisesRegex(RuntimeError, "exited 7"):
                validation.command("control", [sys.executable, "-c", "import sys;print('out');print('err',file=sys.stderr);sys.exit(7)"], timeout=3)
            self.assertEqual(len(validation.report["commands"]), 1)
            record = validation.report["commands"][0]
            self.assertEqual(record["status"], "fail")
            self.assertEqual(Path(record["stdout"]["path"]).read_text(), "out\n")
            self.assertEqual(Path(record["stderr"]["path"]).read_text(), "err\n")

    def test_owned_child_timeout_fails_once(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            validation = controller.Validation(root, root / "evidence")
            with self.assertRaises(TimeoutError):
                validation.command("control", [sys.executable, "-c", "import time;time.sleep(3)"], timeout=0.1)
            self.assertEqual(len(validation.report["commands"]), 1)
            self.assertEqual(validation.report["commands"][0]["status"], "fail")

    def test_owned_child_output_budget_fails_closed(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            validation = controller.Validation(root, root / "evidence")
            with mock.patch.object(controller, "MAX_LOG_BYTES", 64), self.assertRaisesRegex(RuntimeError, "output budget"):
                validation.command("control", [sys.executable, "-c", "print('x'*1000)"], timeout=3)
            self.assertEqual(validation.report["commands"][0]["status"], "fail")

    def test_exhausted_total_budget_never_spawns(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            validation = controller.Validation(root, root / "evidence")
            validation.deadline = 0
            with mock.patch.object(controller.subprocess, "Popen") as popen, self.assertRaises(TimeoutError):
                validation.command("control", ["must-not-execute"])
            popen.assert_not_called()

    def test_cleanup_failure_preserves_partial_logs(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            validation = controller.Validation(root, root / "evidence")
            with mock.patch.object(controller, "terminate_group", side_effect=RuntimeError("cleanup defect")), self.assertRaisesRegex(RuntimeError, "cleanup defect"):
                validation.command("control", [sys.executable, "-c", "print('partial')"], timeout=3)
            record = validation.report["commands"][0]
            self.assertEqual(record["status"], "fail")
            self.assertIn("cleanup defect", record["cleanup_error"])
            self.assertEqual(Path(record["stdout"]["path"]).read_text(), "partial\n")

    def test_release_binds_exact_cargo_artifact_and_rejects_test(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            validation = controller.Validation(root / "work", root / "evidence")
            executable = validation.work / "target/release/proteus-plan-module"
            executable.parent.mkdir(parents=True)
            executable.write_bytes(b"synthetic binary fixture")
            message = {"reason": "compiler-artifact", "package_id": "synthetic-exact-package-id",
                       "target": {"kind": ["bin"], "name": "proteus-plan-module", "src_path": str(validation.module / "components/plan-module/src/main.rs")},
                       "profile": {"test": False}, "fresh": False, "executable": str(executable)}
            def invoke():
                return validation.release("plan_release", "proteus-plan-module", "plan-module", 30)
            def transcript():
                return json.dumps(message) + "\n" + json.dumps({"reason": "build-finished", "success": True}) + "\n"
            with mock.patch.object(validation, "cargo", side_effect=["synthetic-exact-package-id\n", transcript()]):
                self.assertEqual(invoke()["artifact"]["sha256"], controller.sha256(executable))
            false_finished = json.dumps(message) + "\n" + json.dumps({"reason": "build-finished", "success": 1}) + "\n"
            with mock.patch.object(validation, "cargo", side_effect=["synthetic-exact-package-id\n", false_finished]), self.assertRaisesRegex(ValueError, "successful selected binary"):
                invoke()
            for key, value in (("package_id", "wrong"), ("profile", {"test": True}), ("executable", str(root / "not-selected"))):
                previous = message[key]
                message[key] = value
                with self.subTest(key=key), mock.patch.object(validation, "cargo", side_effect=["synthetic-exact-package-id\n", transcript()]), self.assertRaises(ValueError):
                    invoke()
                message[key] = previous


if __name__ == "__main__":
    unittest.main()
