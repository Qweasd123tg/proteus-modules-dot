#!/usr/bin/env python3
"""Run only explicit authored binaries with an empty HOME and fresh workspace.

This is a bounded-time trusted-process smoke, not an OS sandbox. Core launches
component-owned process groups; killing this controller's group on failure does
not prove all descendants terminated. Every timeout is a failed run.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import selectors
import signal
import subprocess
import time


def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def save(path, value):
    path.write_text(json.dumps(value, indent=2) + "\n")


def capture(process, timeout=90, max_bytes=2 * 1024 * 1024):
    """Bound each pipe independently, including descendants holding a pipe open."""
    buffers = {"stdout": bytearray(), "stderr": bytearray()}
    deadline = time.monotonic() + timeout
    selector = selectors.DefaultSelector()
    for name in buffers:
        stream = getattr(process, name)
        os.set_blocking(stream.fileno(), False)
        selector.register(stream, selectors.EVENT_READ, name)
    error = None
    try:
        while selector.get_map() or process.poll() is None:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise RuntimeError(f"{timeout}-second probe timeout")
            for key, _ in selector.select(min(remaining, 0.1)):
                data = os.read(key.fileobj.fileno(), 65536)
                if not data:
                    selector.unregister(key.fileobj)
                    continue
                buffer = buffers[key.data]
                available = max_bytes - len(buffer)
                buffer.extend(data[:available])
                if len(data) > available:
                    raise RuntimeError(f"{key.data} exceeds {max_bytes}-byte capture limit")
        process.wait(timeout=max(0.01, deadline - time.monotonic()))
    except BaseException as failure:
        error = repr(failure)
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            error += "; controller reap exceeded 5 seconds"
        error += "; controller group kill attempted; component-owned descendant cleanup unproven"
    finally:
        selector.close()
        process.stdout.close()
        process.stderr.close()
    decoded = []
    for name in ("stdout", "stderr"):
        try:
            decoded.append(bytes(buffers[name]).decode("utf-8"))
        except UnicodeDecodeError:
            error = (error + "; " if error else "") + f"{name} is not UTF-8"
            decoded.append(bytes(buffers[name]).decode("utf-8", errors="replace"))
    return decoded[0], decoded[1], error



def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--probe", type=Path, required=True)
    parser.add_argument("--module", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    probe, module = (path.resolve(strict=True) for path in (args.probe, args.module))
    for executable in (probe, module):
        if not executable.is_file() or not os.access(executable, os.X_OK):
            parser.error(f"not an executable file: {executable}")
    if shutil.disk_usage(args.output.parent).free < 1024 ** 3:
        raise RuntimeError("less than 1 GiB free; no cleanup attempted")
    args.output.mkdir(exist_ok=False)
    output = args.output.resolve(strict=True)
    workspace, home, temp = (output / name for name in ("workspace", "home", "tmp"))
    for directory in (workspace, home, temp):
        directory.mkdir()
    before = {"probe": digest(probe), "portable_module": digest(module)}
    save(output / "inputs.json", {"binary_sha256": before, "timeout_seconds": 90, "capture_limit_bytes_per_pipe": 2097152,
         "started_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
         "launch": "trusted; cleared environment and empty HOME are not an OS sandbox"})
    env = {"PATH": os.defpath, "HOME": str(home), "XDG_CONFIG_HOME": str(home),
           "TMPDIR": str(temp), "PROTEUS_PORTABLE_SKILLS_BINARY": str(module),
           "PROTEUS_SKILLS_PROBE_WORKSPACE": str(workspace)}
    started = time.monotonic()
    process = None
    try:
        process = subprocess.Popen([str(probe)], cwd=workspace, env=env,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   start_new_session=True)
        stdout, stderr, capture_error = capture(process)
        (output / "stdout.json").write_text(stdout)
        (output / "stderr.txt").write_text(stderr)
        if capture_error:
            raise RuntimeError(capture_error)
        if process.returncode:
            raise RuntimeError(f"probe failed with {process.returncode}")
        if before != {"probe": digest(probe), "portable_module": digest(module)}:
            raise RuntimeError("binary changed during run")
        if list(home.iterdir()):
            raise RuntimeError("probe changed the empty HOME")
        # Authored fixture inputs are intentionally created/changed, not an empty-workspace claim.
        files = sorted(path for path in workspace.rglob("*") if path.is_file())
        expected_paths = {"root-a/review/SKILL.md", "root-b/review/SKILL.md",
                          "large-body/review/SKILL.md"}
        expected_paths.update(f"catalog-cap/skill-{index}/SKILL.md" for index in range(16))
        if {str(path.relative_to(workspace)) for path in files} != expected_paths:
            raise RuntimeError("workspace file set differs from 19 authored fixtures")
        save(output / "fixture-files.json", {
            str(path.relative_to(workspace)): {"bytes": path.stat().st_size, "sha256": digest(path)}
            for path in files})
        save(output / "process.json", {"status": "passed", "returncode": process.returncode,
             "elapsed_seconds": time.monotonic() - started, "binaries_unchanged": True,
             "home_empty": True, "authored_fixture_files": 19})
    except BaseException as error:
        save(output / "process.json", {"status": "failed", "error": repr(error),
             "returncode": process.returncode if process else None,
             "elapsed_seconds": time.monotonic() - started})
        raise


if __name__ == "__main__":
    main()
