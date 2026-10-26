#!/usr/bin/env python3
"""Fixed authored-package Cargo operation with a sampled disk stop margin.

This follows the coordinated builder's 1 GiB reserve +128 MiB stop margin.
It does not delete data or claim an OS filesystem quota/descendant sandbox.
"""
import argparse
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import time

PACKAGE = Path(__file__).resolve().parent.parent
RESERVE = 1024 ** 3
STOP_FREE = RESERVE + 128 * 1024 ** 2


def stop(process):
    result = {"signals": [], "all_descendant_termination": "unproven"}
    if process.returncode is not None:
        # poll()/wait() has already reaped this identity. Do not signal a numeric
        # group ID that could now have been recycled for an unrelated process.
        result["direct_child"] = "already_reaped; no further group signal"
        return result
    # Keep the direct child unreaped through both group signals. A leader can
    # exit on TERM while a same-group compiler continues to allocate; returning
    # after an early wait would leave that descendant alive and allow PID reuse.
    for sig in (signal.SIGTERM, signal.SIGKILL):
        attempt = {"signal": sig.name}
        try:
            os.killpg(process.pid, sig)
            attempt["result"] = "sent"
        except ProcessLookupError:
            attempt["result"] = "group_absent"
        except OSError as error:
            attempt["result"] = "signal_error"
            attempt["error"] = repr(error)
        result["signals"].append(attempt)
        if sig == signal.SIGTERM:
            time.sleep(0.25)  # Bounded grace; no poll/wait before final group signal.
    try:
        process.wait(timeout=5)
        result["direct_child"] = "reaped"
    except subprocess.TimeoutExpired:
        result["direct_child"] = "cleanup_timeout; termination unproven"
    except OSError as error:
        result["direct_child"] = "cleanup_error; termination unproven"
        result["wait_error"] = repr(error)
    return result


def execute(command, output, timeout):
    output.mkdir(exist_ok=False)
    initial = shutil.disk_usage(output).free
    result = {"status": "pending", "command": command, "reserve_bytes": RESERVE,
              "stop_threshold_bytes": STOP_FREE, "initial_free_bytes": initial,
              "samples": [], "cleanup": "No data deleted; sampled guard is not an OS quota."}
    started = time.monotonic()
    process = None
    try:
        if initial <= STOP_FREE:
            result["status"] = "blocked_initial_disk_headroom"
            return result
        with (output / "stdout.txt").open("w") as stdout, (output / "stderr.txt").open("w") as stderr:
            process = subprocess.Popen(command, cwd=PACKAGE, stdout=stdout, stderr=stderr, start_new_session=True)
            while process.poll() is None:
                elapsed = time.monotonic() - started
                free = shutil.disk_usage(output).free
                result["samples"].append({"elapsed_seconds": elapsed, "free_bytes": free})
                reason = "stopped_disk_guard" if free < STOP_FREE else "stopped_timeout" if elapsed >= timeout else None
                if reason:
                    result["status"] = reason
                    result["process_cleanup"] = stop(process)
                    break
                time.sleep(0.1)
            result["returncode"] = process.returncode
            if result["status"] == "pending":
                result["status"] = "passed" if process.returncode == 0 else "failed_command"
        return result
    except BaseException as error:
        result["status"] = "failed_controller"
        result["error"] = repr(error)
        if process is not None:
            result["process_cleanup"] = stop(process)
        raise
    finally:
        result["elapsed_seconds"] = time.monotonic() - started
        result["final_free_bytes"] = shutil.disk_usage(output).free
        result["minimum_observed_free_bytes"] = min([initial, result["final_free_bytes"],
                                                      *(sample["free_bytes"] for sample in result["samples"])])
        (output / "result.json").write_text(json.dumps(result, indent=2) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("fetch", "build"))
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    command = (["cargo", "fetch", "--locked"] if args.operation == "fetch" else
               ["cargo", "build", "--locked", "--offline", "-j2", "--bin", "proteus-typed-frontmatter-comparison"])
    result = execute(command, args.output, 300 if args.operation == "fetch" else 600)
    print(json.dumps({key: value for key, value in result.items() if key != "samples"}, indent=2))
    raise SystemExit(0 if result["status"] == "passed" else 1)


if __name__ == "__main__":
    main()
