#!/usr/bin/env python3
"""Hosted synthetic checks for the qualification controller, never application code."""
import argparse
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parent


def alive_group(pid):
    try:
        os.killpg(pid, 0)
        return True
    except ProcessLookupError:
        return False


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    if args.root.exists() or args.report.exists():
        raise SystemExit("Absent fixture and report paths required")
    args.root.mkdir(parents=True)
    results = []
    expected = {
        "normal": None,
        "timeout": "TimeoutError",
        "output": "ValueError: Command output-byte bound exceeded",
        "orphan-pipe": "TimeoutError",
        "orphan-closed": "RuntimeError: Command left descendants",
        "signal": "InterruptedError",
    }
    report = {"schema": 1, "status": "running", "fixtures": results}
    try:
        for name, error in expected.items():
            evidence = args.root / (name + "-evidence")
            command = [sys.executable, str(ROOT / "run_qualification.py"),
                       "--work-dir", str(args.root / (name + "-work")),
                       "--evidence-dir", str(evidence), "--fixture", name]
            started = time.monotonic()
            proc = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                    start_new_session=True)
            try:
                if name == "signal":
                    deadline = started + 10
                    while time.monotonic() < deadline:
                        path = evidence / "result.json"
                        try:
                            state = json.loads(path.read_text())
                        except (OSError, json.JSONDecodeError):
                            state = {}
                        if state.get("commands") and "pid" in state["commands"][-1]:
                            break
                        if proc.poll() is not None:
                            raise AssertionError("Signal fixture exited before its child started")
                        time.sleep(0.05)
                    else:
                        raise AssertionError("Signal fixture did not reach its child")
                    proc.send_signal(signal.SIGTERM)
                code = proc.wait(timeout=15)
                raw = (evidence / "result.json").read_bytes()
                if len(raw) > 1024 * 1024:
                    raise AssertionError("Fixture evidence exceeded 1 MiB")
                state = json.loads(raw)
                if error is None:
                    assert code == 0 and state["status"] == "success", state
                else:
                    assert code != 0 and state["status"] == "failure", state
                    assert error in state["error"], state
                assert len(state["commands"]) == 1, state
                pid = state["commands"][0]["pid"]
                deadline = time.monotonic() + 5
                while alive_group(pid) and time.monotonic() < deadline:
                    time.sleep(0.05)
                assert not alive_group(pid), f"Fixture process group survived: {name}, {pid}"
                results.append({"name": name, "status": "passed", "exit_code": code,
                                "expected_failure": error, "group_gone": True,
                                "evidence": state})
            finally:
                # Fixture controller could have failed before its own cleanup.
                try:
                    leftover = json.loads((evidence / "result.json").read_text())
                    for row in leftover.get("commands", []):
                        if "pid" in row:
                            try:
                                os.killpg(row["pid"], signal.SIGKILL)
                            except ProcessLookupError:
                                pass
                except (OSError, json.JSONDecodeError):
                    pass
                try:
                    os.killpg(proc.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                if proc.poll() is None:
                    proc.wait(timeout=5)
        report["status"] = "success"
        print("PASS: 6 controller fixtures, including orphaned descendants and SIGTERM cleanup")
    except BaseException as exc:
        report["status"] = "failure"
        report["error"] = f"{type(exc).__name__}: {exc}"
        raise
    finally:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        data = (json.dumps(report, indent=2, sort_keys=True) + "\n").encode()
        if len(data) > 2 * 1024 * 1024:
            raise ValueError("Controller self-test evidence exceeds 2 MiB")
        args.report.write_bytes(data)


if __name__ == "__main__":
    main()
