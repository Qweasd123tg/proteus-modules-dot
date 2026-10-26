"""Pure/mock lifecycle and byte-bound controls; never launches a process."""
import sys
sys.dont_write_bytecode = True
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import subprocess
import types
import unittest
from unittest.mock import Mock, patch
from controller import Worker, MAX_FRAME, MAX_STDOUT, MAX_STDERR


def fake_worker():
    worker = Worker.__new__(Worker)
    worker.stdout_sink = Mock()
    worker.stderr_sink = Mock()
    worker.closed = False
    worker.buffer = bytearray()
    worker.stderr = bytearray()
    worker.total_stdout = 0
    worker.deadline = 10**20
    worker.selector = Mock()
    worker.nonblocking = {"stdin", "stdout", "stderr"}
    worker.child = Mock()
    worker.child.returncode = None
    worker.child.poll.return_value = None
    return worker


class ControllerTests(unittest.TestCase):
    def test_spawn_failure_closes_selector_without_pipe_reads(self):
        selector = Mock()
        with patch("controller.selectors.DefaultSelector", return_value=selector), \
             patch("controller.subprocess.Popen", side_effect=OSError("spawn failure")), \
             patch("controller.os.read") as read:
            with self.assertRaisesRegex(OSError, "spawn failure"):
                Worker(["/unused"], "/unused", {}, 10**20)
        selector.close.assert_called_once()
        read.assert_not_called()

    def test_deadline_refuses_before_select(self):
        worker = fake_worker()
        worker.deadline = -1
        with self.assertRaises(TimeoutError):
            worker._events(-1)
        worker.selector.select.assert_not_called()

    def test_stdout_remaining_budget_bounds_os_read_and_retains_overflow(self):
        worker = fake_worker()
        worker.total_stdout = MAX_STDOUT - 1
        stream = Mock()
        stream.fileno.return_value = 42
        worker.selector.select.return_value = [(types.SimpleNamespace(data="stdout", fileobj=stream), None)]
        with patch("controller.os.read", return_value=b"xx") as read:
            with self.assertRaisesRegex(ValueError, "byte cap"):
                worker._events(10**20)
        read.assert_called_once_with(42, 2)
        worker.stdout_sink.assert_called_once_with(b"xx")

    def test_stderr_remaining_budget_bounds_os_read_and_retains_overflow(self):
        worker = fake_worker()
        worker.stderr = bytearray(b"x" * (MAX_STDERR - 1))
        stream = Mock()
        stream.fileno.return_value = 42
        worker.selector.select.return_value = [(types.SimpleNamespace(data="stderr", fileobj=stream), None)]
        with patch("controller.os.read", return_value=b"xx") as read:
            with self.assertRaisesRegex(ValueError, "byte cap"):
                worker._events(10**20)
        read.assert_called_once_with(42, 2)
        worker.stderr_sink.assert_called_once_with(b"xx")

    def test_frame_cap_refuses_before_json_parse(self):
        worker = fake_worker()
        worker.buffer = bytearray(b"x" * (MAX_FRAME - 1))
        worker.selector.select.return_value = [(types.SimpleNamespace(data="stdout", fileobj=Mock()), None)]
        with patch("controller.os.read", return_value=b"xx"):
            with self.assertRaisesRegex(ValueError, "byte cap"):
                worker._events(10**20)

    def test_cleanup_escalates_only_owned_child_and_reaps(self):
        worker = fake_worker()
        def wait(timeout):
            self.assertEqual(timeout, 2)
            if worker.child.kill.call_count:
                worker.child.returncode = -9
                return -9
            raise subprocess.TimeoutExpired("owned", timeout)
        worker.child.wait.side_effect = wait
        with patch("controller.os.read", return_value=b""):
            report = worker.stop(False)
        self.assertTrue(report["reaped"])
        worker.child.terminate.assert_called_once()
        worker.child.kill.assert_called_once()
        self.assertEqual(worker.child.wait.call_count, 2)

    def test_cleanup_timeout_stays_unsettled(self):
        worker = fake_worker()
        worker.child.wait.side_effect = subprocess.TimeoutExpired("owned", 2)
        with patch("controller.os.read", return_value=b""):
            report = worker.stop(False)
        self.assertFalse(report["reaped"])
        self.assertIn("TimeoutExpired", report["error"])

    def test_close_and_signal_errors_do_not_skip_final_kill_wait(self):
        worker = fake_worker()
        worker.child.stdin.close.side_effect = OSError("close failure")
        worker.child.terminate.side_effect = PermissionError("signal failure")
        def wait(timeout):
            if worker.child.kill.call_count:
                worker.child.returncode = -9
                return -9
            raise subprocess.TimeoutExpired("owned", timeout)
        worker.child.wait.side_effect = wait
        with patch("controller.os.read", return_value=b""):
            report = worker.stop(False)
        self.assertTrue(report["reaped"])
        self.assertIn("close failure", report["error"])
        self.assertIn("signal failure", report["error"])
        worker.child.kill.assert_called_once()

    def test_setup_failure_skips_unconfirmed_blocking_reads(self):
        child = Mock()
        child.returncode = None
        child.poll.return_value = None
        child.wait.side_effect = subprocess.TimeoutExpired("owned", 2)
        with patch("controller.subprocess.Popen", return_value=child), \
             patch("controller.os.set_blocking", side_effect=[None, OSError("setup failure")]), \
             patch("controller.os.read") as read:
            with self.assertRaisesRegex(RuntimeError, "setup failure"):
                Worker(["/unused"], "/unused", {}, 10**20)
        read.assert_not_called()
        child.kill.assert_called_once()


if __name__ == "__main__":
    unittest.main()
