#!/usr/bin/env python3
"""Mocked Cargo controller controls; never launches Cargo or Rust code."""
import importlib.util
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

sys.dont_write_bytecode = True
spec = importlib.util.spec_from_file_location("guard", Path(__file__).with_name("guarded_cargo.py"))
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)


class Controls(unittest.TestCase):
    def run_guard(self, free, clock, process, signal_error=None):
        with tempfile.TemporaryDirectory() as root, \
                patch.object(guard.shutil, "disk_usage", side_effect=lambda _: SimpleNamespace(free=next(free))), \
                patch.object(guard.time, "monotonic", side_effect=lambda: next(clock)), \
                patch.object(guard.time, "sleep"), \
                patch.object(guard.subprocess, "Popen", return_value=process) as spawn, \
                patch.object(guard.os, "killpg", side_effect=signal_error) as kill:
            result = guard.execute(["authored-mock-only"], Path(root) / "new", timeout=5)
            return result, spawn.call_count, kill.call_args_list

    def test_initial_low_disk_prevents_spawn(self):
        result, count, signals = self.run_guard(iter([guard.STOP_FREE, guard.STOP_FREE]), iter([0, 1]), Mock())
        self.assertEqual(result["status"], "blocked_initial_disk_headroom")
        self.assertEqual((count, signals), (0, []))

    def test_complete_command(self):
        process = Mock(pid=123, returncode=0)
        process.poll.return_value = 0
        result, count, signals = self.run_guard(iter([guard.STOP_FREE + 1] * 2), iter([0, 1]), process)
        self.assertEqual(result["status"], "passed")
        self.assertEqual((count, signals), (1, []))

    def test_disk_drop_stops_only_owned_group(self):
        process = Mock(pid=123, returncode=None)
        process.poll.return_value = None
        result, count, signals = self.run_guard(iter([guard.STOP_FREE + 1, guard.STOP_FREE - 1, guard.STOP_FREE - 1]), iter([0, 1, 2]), process)
        self.assertEqual(result["status"], "stopped_disk_guard")
        self.assertEqual(count, 1)
        self.assertEqual(signals[0].args, (123, signal.SIGTERM))
        process.wait.assert_called_once_with(timeout=5)

    def test_deadline_stops_owned_group(self):
        process = Mock(pid=123, returncode=None)
        process.poll.return_value = None
        result, _, signals = self.run_guard(iter([guard.STOP_FREE + 1] * 3), iter([0, 6, 7]), process)
        self.assertEqual(result["status"], "stopped_timeout")
        self.assertEqual(signals[0].args, (123, signal.SIGTERM))

    def test_leader_exits_on_term_but_group_kill_precedes_reap(self):
        process = Mock(pid=123, returncode=None)
        order = []
        def signal_group(pid, sig):
            self.assertEqual(pid, 123)
            order.append(sig.name)
            process.wait.assert_not_called()
            process.poll.assert_not_called()
            # TERM may have exited the real leader; retain its unreaped identity.
        def reap(timeout):
            self.assertEqual(timeout, 5)
            order.append("reap")
            process.returncode = -15
        process.wait.side_effect = reap
        with patch.object(guard.os, "killpg", side_effect=signal_group), \
                patch.object(guard.time, "sleep") as grace:
            result = guard.stop(process)
        self.assertEqual(order, ["SIGTERM", "SIGKILL", "reap"])
        grace.assert_called_once_with(0.25)
        self.assertEqual(result["direct_child"], "reaped")
        self.assertEqual(result["all_descendant_termination"], "unproven")

    def test_signal_denial_preserves_guard_reason(self):
        process = Mock(pid=123, returncode=None)
        process.poll.return_value = None
        result, _, signals = self.run_guard(
            iter([guard.STOP_FREE + 1, guard.STOP_FREE - 1, guard.STOP_FREE - 1]),
            iter([0, 1, 2]), process, PermissionError("authored denial"))
        self.assertEqual(result["status"], "stopped_disk_guard")
        self.assertEqual([call.args[1] for call in signals], [signal.SIGTERM, signal.SIGKILL])
        self.assertEqual([row["result"] for row in result["process_cleanup"]["signals"]], ["signal_error"] * 2)
        self.assertTrue(all("authored denial" in row["error"] for row in result["process_cleanup"]["signals"]))

    def test_already_reaped_identity_is_not_signaled_again(self):
        process = Mock(pid=123, returncode=0)
        with patch.object(guard.os, "killpg") as kill:
            result = guard.stop(process)
        kill.assert_not_called()
        process.wait.assert_not_called()
        self.assertEqual(result["direct_child"], "already_reaped; no further group signal")


if __name__ == "__main__":
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Controls))
    raise SystemExit(0 if result.wasSuccessful() and result.testsRun == 7 and not result.skipped else 1)
