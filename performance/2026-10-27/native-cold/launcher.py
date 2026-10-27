#!/usr/bin/env python3
"""Linux-only bounded GNU-time launcher. Imported by hosted controller only."""
import json
import os
from pathlib import Path
import resource
import selectors
import signal
import subprocess
import time

OUTPUT_CAP = 32 * 1024 * 1024
CHILD_SECONDS = 60


def child_limits():
    # Forces the same fork/exec path for measurement and calibration.
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    resource.setrlimit(resource.RLIMIT_CPU, (60, 60))


def launch(command, env, deadline, timeout=CHILD_SECONDS):
    if time.monotonic() >= deadline:
        raise TimeoutError("whole-run deadline")
    output = {"stdout": bytearray(), "stderr": bytearray()}
    fd = os.memfd_create("native-gnu-time", flags=0)
    process = None
    usage = None
    reaped = False
    completed = False
    started = time.monotonic_ns()
    end = min(deadline, time.monotonic() + timeout)
    try:
        process = subprocess.Popen(
            ["/usr/bin/time", "-f", "%x %M", "-o", f"/proc/self/fd/{fd}", "--", *map(str, command)],
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            env=env, start_new_session=True, pass_fds=(fd,), preexec_fn=child_limits,
        )
        with selectors.DefaultSelector() as selector:
            for name in output:
                pipe = getattr(process, name)
                os.set_blocking(pipe.fileno(), False)
                selector.register(pipe, selectors.EVENT_READ, name)
            while selector.get_map() or not reaped:
                if time.monotonic() >= end:
                    raise TimeoutError("owned child exceeded deadline")
                for key, _ in selector.select(min(0.05, max(0, end-time.monotonic()))):
                    chunk = os.read(key.fd, 65536)
                    if not chunk:
                        selector.unregister(key.fileobj)
                        key.fileobj.close()
                        continue
                    if sum(map(len, output.values())) + len(chunk) > OUTPUT_CAP:
                        raise ValueError("combined stdout/stderr exceeded 32 MiB")
                    output[key.data].extend(chunk)
                if not reaped:
                    pid, status, usage = os.wait4(process.pid, os.WNOHANG)
                    if pid:
                        reaped = True
                        process.returncode = os.waitstatus_to_exitcode(status)
        elapsed = time.monotonic_ns() - started
        os.lseek(fd, 0, os.SEEK_SET)
        timing = os.read(fd, 4097)
        if len(timing) > 4096:
            raise ValueError("GNU-time output oversized")
        # GNU time can prepend signal diagnostics. Successful SUT must emit exactly two numbers.
        fields = timing.decode("ascii").strip().split()
        if process.returncode != 0 or len(fields) != 2 or fields[0] != "0":
            raise RuntimeError(f"child rc={process.returncode}; time={timing!r}; stderr={bytes(output['stderr'])[-2000:]!r}")
        rss = int(fields[1])
        if rss < 0:
            raise ValueError("negative RSS")
        completed = True
        return {
            "stdout": bytes(output["stdout"]), "stderr": bytes(output["stderr"]),
            "sut_peak_rss_kib": rss,
            "outer_wait4_maxrss_kib_DIAGNOSTIC_ONLY": usage.ru_maxrss,
            "process_wall_ns": elapsed,
        }
    finally:
        if process is not None and not completed:
            # The time leader may exit while its child still holds inherited pipes.
            # Kill the owned group on every exceptional exit, reaped leader or not.
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            if not reaped:
                try:
                    _, status, _ = os.wait4(process.pid, 0)
                    process.returncode = os.waitstatus_to_exitcode(status)
                except ChildProcessError:
                    pass
        if process is not None:
            for name in output:
                pipe = getattr(process, name)
                if pipe is not None:
                    pipe.close()
        os.close(fd)


def json_child(command, env, deadline):
    result = launch(command, env, deadline)
    raw = result.pop("stdout")
    stderr = result.pop("stderr")
    if stderr:
        raise ValueError(f"unexpected child stderr: {stderr[-2000:]!r}")
    result["value"] = json.loads(raw)
    return result


def controls(binary, env, deadline, rows=None):
    if rows is None:
        rows = []
    # Keep touched high-parent bytes LIVE over the identical launch() path.
    for repeat in range(3):
        for high in [False, True]:
            parent = bytearray(192 * 1024 * 1024) if high else bytearray()
            for index in range(0, len(parent), 4096):
                parent[index] = 1
            for allocation in [0, 32, 128]:
                row = json_child([binary, str(allocation)], env, deadline)
                if row.pop("value") != {"allocated_mib": allocation}:
                    raise ValueError("allocation control lied")
                rows.append(dict(row, repeat=repeat, high_parent=high,
                                 child_allocation_mib=allocation, parent_bytes=len(parent)))
            # Explicit use makes lifetime intent independent of interpreter optimization.
            if parent and parent[0] != 1:
                raise AssertionError("parent allocation")
            del parent
    for repeat in range(3):
        selected = [row for row in rows if row["repeat"] == repeat]
        for allocation in [0, 32, 128]:
            pair = [row for row in selected if row["child_allocation_mib"] == allocation]
            if abs(pair[0]["sut_peak_rss_kib"] - pair[1]["sut_peak_rss_kib"]) > 8*1024:
                raise AssertionError("SUT RSS depends on parent allocation")
        for high in [False, True]:
            sample = {row["child_allocation_mib"]: row for row in selected if row["high_parent"] == high}
            low = sample[0]["sut_peak_rss_kib"]
            for allocation in [32, 128]:
                delta = sample[allocation]["sut_peak_rss_kib"] - low
                if not (allocation*1024 - 8*1024 <= delta <= allocation*1024 + 8*1024):
                    raise AssertionError("GNU-time missed known child allocation")
        zero = [row for row in selected if row["child_allocation_mib"] == 0]
        high_diagnostic = next(row for row in zero if row["high_parent"])["outer_wait4_maxrss_kib_DIAGNOSTIC_ONLY"]
        low_diagnostic = next(row for row in zero if not row["high_parent"])["outer_wait4_maxrss_kib_DIAGNOSTIC_ONLY"]
        if high_diagnostic - low_diagnostic < 160*1024:
            raise AssertionError("high-parent diagnostic delta was not exercised")
    return rows
