"""Controller-only mocked tests. These do NOT execute Core, a tracer, or kill a process."""
import importlib.util
import json
from pathlib import Path
import signal
import subprocess
import sys
import unittest
from unittest.mock import Mock, patch

SPEC = importlib.util.spec_from_file_location("cache_controller", Path(__file__).with_name("run_cache_probe.py"))
runner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runner)
OUTPUT = Path(sys.argv.pop(1)).resolve()
OUTPUT.mkdir(parents=False, exist_ok=False)


class ControllerTests(unittest.TestCase):
    def new_run(self, case):
        output = OUTPUT / case
        output.mkdir()
        return runner.Run(Path("/nonexecuted-authored-fixture"), output, True), output

    def test_timeout_kills_new_owned_group_and_retains_partial_receipt(self):
        run, output = self.new_run("timeout")
        process = Mock(pid=424242, returncode=-9)
        process.communicate.side_effect = [subprocess.TimeoutExpired(["mock"],120), ("partial stdout", "partial stderr")]
        with patch.object(runner.subprocess,"Popen",return_value=process) as popen, patch.object(runner.os,"killpg") as kill:
            with self.assertRaisesRegex(RuntimeError,"owned group killed"):
                run.execute("timeout",["only"],trace=True)
            self.assertTrue(popen.call_args.kwargs["start_new_session"])
            kill.assert_called_once_with(424242,signal.SIGKILL)
        receipt=json.loads((output / "timeout.process.json").read_text())
        self.assertTrue(receipt["timed_out"])
        self.assertEqual((output / "timeout.stdout.json").read_text(),"partial stdout")

    def test_ptrace_denial_stops_tracing_and_cleans_owned_group(self):
        run, output = self.new_run("denied")
        process = Mock(pid=424243,returncode=1)
        process.communicate.return_value=("","strace: ptrace(PTRACE_TRACEME): Operation not permitted\n")
        with patch.object(runner.subprocess,"Popen",return_value=process), patch.object(runner.os,"killpg") as kill:
            self.assertIsNone(run.execute("denied",["only"],trace=True))
            kill.assert_called_once_with(424243,signal.SIGKILL)
        self.assertFalse(run.tracing)
        self.assertEqual(run.checks[-1]["status"],"trace_unavailable")
        self.assertTrue((output / "denied.stderr.txt").is_file())

    def test_missing_tracer_records_unavailability_without_retry(self):
        run, output = self.new_run("missing")
        with patch.object(runner.subprocess,"Popen",side_effect=FileNotFoundError("mock missing tracer")) as popen:
            self.assertIsNone(run.execute("missing",["only"],trace=True))
            popen.assert_called_once()
        self.assertFalse(run.tracing)
        self.assertEqual(json.loads((output / "missing.process.json").read_text())["status"],"trace_unavailable")

    def test_fixture_failure_is_not_relabelled_tracer_unavailability(self):
        run, _ = self.new_run("semantic-failure")
        process=Mock(pid=424244,returncode=1)
        process.communicate.return_value=("","Error: only API wrong count\n")
        with patch.object(runner.subprocess,"Popen",return_value=process), patch.object(runner.os,"killpg") as kill:
            with self.assertRaisesRegex(RuntimeError,"failed rc=1"):
                run.execute("semantic-failure",["only"],trace=True)
            kill.assert_called_once_with(424244,signal.SIGKILL)
        self.assertTrue(run.tracing)

    def test_trace_file_limit_signal_kills_group_without_unavailable_reclassification(self):
        run, output = self.new_run("trace-file-limit")
        process=Mock(pid=424245,returncode=-signal.SIGXFSZ)
        process.communicate.return_value=("partial","trace file size limit exceeded")
        with patch.object(runner.subprocess,"Popen",return_value=process), patch.object(runner.os,"killpg") as kill:
            with self.assertRaisesRegex(RuntimeError,"failed rc="):
                run.execute("trace-file-limit",["only"],trace=True)
            kill.assert_called_once_with(424245,signal.SIGKILL)
        self.assertTrue(run.tracing)
        self.assertEqual(json.loads((output / "trace-file-limit.process.json").read_text())["returncode"],-signal.SIGXFSZ)

    def test_second_drain_timeout_preserves_partial_output_and_bounded_wait(self):
        run, output = self.new_run("second-drain-timeout")
        process=Mock(pid=424246,returncode=-9)
        process.communicate.side_effect=[subprocess.TimeoutExpired(["mock"],120),
            subprocess.TimeoutExpired(["mock"],10,output=b"partial bytes",stderr=b"partial error")]
        process.wait.return_value=-9
        with patch.object(runner.subprocess,"Popen",return_value=process), patch.object(runner.os,"killpg") as kill:
            with self.assertRaisesRegex(RuntimeError,"owned group killed"):
                run.execute("second-drain-timeout",["only"],trace=True)
            kill.assert_called_once_with(424246,signal.SIGKILL)
        process.wait.assert_called_once_with(timeout=5)
        receipt=json.loads((output / "second-drain-timeout.process.json").read_text())
        self.assertTrue(receipt["drain_timed_out"])
        self.assertEqual((output / "second-drain-timeout.stdout.json").read_text(),"partial bytes")


if __name__=="__main__":unittest.main()
