#!/usr/bin/env python3
"""Authored Linux CI gate supervisor; sampled growth guard, not a quota/sandbox.

Only fixed reviewed workflow mappings may invoke this generic controller. No
live child is executed by its pure/mock tests. Escaped process groups remain
unproven: a direct child exit, EOF, or group signal is NOT tree settlement.
"""
import argparse
import hashlib
import json
import io
import os
from pathlib import Path
import selectors
import shutil
import signal
import stat
import uuid
import subprocess
import tarfile
import sys
import time

MIB = 1024 ** 2
RESERVE = 1024 ** 3
STOP_FREE = RESERVE + 128 * MIB
INITIAL_FREE = 8 * 1024 ** 3
MAX_FILE = 8 * MIB
MAX_ARTIFACTS = 32 * MIB
MAX_ENTRIES = 512
MAX_PATH_BYTES = 512
MAX_DEPTH = 16
MAX_PIPE = 4 * MIB
MAX_INPUTS = 16
DEADLINES = {"core-skills": 1800, "evidence-spans": 1500}


def save(path, value):
    data = (json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n").encode()
    if len(data) > MIB:
        raise ValueError("controller receipt exceeds 1 MiB")
    with path.open("xb") as stream:
        stream.write(data)


def inventory(root):
    """Bounded metadata walk of this explicit authored output leaf only."""
    if root.is_symlink():
        raise ValueError("artifact root must be a real directory")
    if not root.exists():
        return {}
    if not root.is_dir():
        raise ValueError("artifact root must be a real directory")
    entries, total, seen = {}, 0, 0
    todo = [(root, 0)]
    while todo:
        directory, depth = todo.pop()
        if depth > MAX_DEPTH:
            raise ValueError("artifact depth exceeds limit")
        with os.scandir(directory) as stream:
            for entry in stream:
                seen += 1
                if seen > MAX_ENTRIES:
                    raise ValueError("artifact entry count exceeds limit")
                st = entry.stat(follow_symlinks=False)
                path = Path(entry.path)
                if stat.S_ISDIR(st.st_mode):
                    todo.append((path, depth + 1))
                elif stat.S_ISREG(st.st_mode):
                    if st.st_size > MAX_FILE:
                        raise ValueError("artifact file exceeds limit")
                    total += st.st_size
                    if total > MAX_ARTIFACTS:
                        raise ValueError("artifact aggregate exceeds limit")
                    name = path.relative_to(root).as_posix()
                    if len(name.encode("utf-8")) > MAX_PATH_BYTES:
                        raise ValueError("artifact relative path exceeds limit")
                    entries[name] = {
                        "bytes": st.st_size, "mtime_ns": st.st_mtime_ns,
                        "device": st.st_dev, "inode": st.st_ino}
                else:
                    raise ValueError("artifact contains nonregular entry")
    return dict(sorted(entries.items()))


def bounded_read(path, limit):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as stream:
        before = os.fstat(stream.fileno())
        if not stat.S_ISREG(before.st_mode) or before.st_size > limit:
            raise ValueError("input is not a bounded regular file")
        data = stream.read(limit + 1)
        after = os.fstat(stream.fileno())
        if len(data) > limit or (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns):
            raise ValueError("file changed or exceeded bound while reading")
        return data


def snapshot(root, destination, retained=None):
    """Bounded regular-file tar payload; no extraction or global quiescence claim."""
    before = inventory(root)
    result, total = retained if retained is not None else {}, 0
    with destination.open("xb") as output, tarfile.open(fileobj=output, mode="w", format=tarfile.PAX_FORMAT) as archive:
        for name, metadata in before.items():
            data = bounded_read(root / name, MAX_FILE)
            if len(data) != metadata["bytes"]:
                raise ValueError("artifact changed during snapshot")
            total += len(data)
            if total > MAX_ARTIFACTS:
                raise ValueError("artifact aggregate exceeded during snapshot")
            entry = tarfile.TarInfo(name)
            entry.size = len(data)
            entry.mode = 0o600
            entry.mtime = 0
            archive.addfile(entry, io.BytesIO(data))
            result[name] = {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}
    if destination.stat().st_size > MAX_ARTIFACTS + 2 * MIB:
        raise ValueError("archive exceeds payload plus header bound")
    if inventory(root) != before:
        raise ValueError("artifact metadata changed during snapshot")
    return result


def input_hashes(paths):
    if len(paths) > MAX_INPUTS:
        raise ValueError("too many explicit controller inputs")
    return {str(path): hashlib.sha256(bounded_read(path, MIB)).hexdigest() for path in paths}


def stop(process):
    """R16 order: keep leader unreaped through group TERM/KILL, then wait."""
    result = {"all_descendant_termination": "unproven", "signals": []}
    if process.returncode is not None:
        result["direct_child"] = "already_reaped; numeric group not signaled"
        return result
    for sig in (signal.SIGTERM, signal.SIGKILL):
        item = {"signal": sig.name}
        try:
            os.killpg(process.pid, sig)
            item["result"] = "sent"
        except ProcessLookupError:
            item["result"] = "group_absent"
        except OSError as error:
            item["result"] = "signal_error"
            item["error"] = type(error).__name__
        result["signals"].append(item)
        if sig == signal.SIGTERM:
            time.sleep(0.25)
    try:
        process.wait(timeout=5)
        result["direct_child"] = "reaped"
    except (subprocess.TimeoutExpired, OSError) as error:
        result["direct_child"] = "unproven"
        result["wait_error"] = type(error).__name__
    return result


def supervise(process, artifact_root, output, timeout):
    """Bound decoded-independent raw pipes and time; do not block draining."""
    selector = None
    streams, counts = {}, {"stdout": 0, "stderr": 0}
    nonblocking = set()
    drain_errors = []
    truncated = set()
    start = time.monotonic()
    minimum = None
    samples = 0
    reason = None
    cleanup = None
    try:
        selector = selectors.DefaultSelector()
        minimum = shutil.disk_usage(output).free
        for name in counts:
            stream = getattr(process, name)
            os.set_blocking(stream.fileno(), False)
            nonblocking.add(name)
            selector.register(stream, selectors.EVENT_READ, name)
            streams[name] = (output / (name + ".bin")).open("xb")
        while True:
            free = shutil.disk_usage(output).free
            minimum = min(minimum, free)
            samples += 1
            if free < STOP_FREE:
                raise RuntimeError("stopped_disk_guard")
            if time.monotonic() - start >= timeout:
                raise RuntimeError("stopped_deadline")
            inventory(artifact_root)
            if not selector.get_map() and process.poll() is not None:
                break
            for key, _ in selector.select(0.1):
                try:
                    data = os.read(key.fileobj.fileno(), 65536)
                except BlockingIOError:
                    continue
                if not data:
                    selector.unregister(key.fileobj)
                    continue
                remaining = MAX_PIPE - counts[key.data]
                streams[key.data].write(data[:remaining])
                counts[key.data] += min(len(data), remaining)
                if len(data) > remaining:
                    truncated.add(key.data)
                    raise RuntimeError("stopped_pipe_limit")
        if process.returncode != 0:
            reason = "failed_command"
    except BaseException as error:
        reason = str(error)[:300] if isinstance(error, (RuntimeError, ValueError)) else type(error).__name__
        cleanup = stop(process)
        # At most four nonblocking reads per confirmed pipe; never communicate().
        for name in sorted(nonblocking):
            if name not in streams:
                continue
            for _ in range(4):
                try:
                    data = os.read(getattr(process, name).fileno(), 65536)
                    if not data:
                        break
                    remaining = MAX_PIPE - counts[name]
                    streams[name].write(data[:remaining])
                    counts[name] += min(len(data), remaining)
                    if len(data) > remaining:
                        truncated.add(name)
                        break
                except BlockingIOError:
                    break
                except OSError as error:
                    drain_errors.append(type(error).__name__)
                    break
    finally:
        try:
            if selector is not None:
                selector.close()
        except OSError as error:
            drain_errors.append(type(error).__name__)
            reason = reason or "selector_close_error"
        for stream in streams.values():
            try:
                stream.close()
            except OSError as error:
                drain_errors.append(type(error).__name__)
                reason = reason or "capture_close_error"
        for name in counts:
            try:
                getattr(process, name).close()
            except OSError:
                reason = reason or "pipe_close_error"
    return {"status": "passed" if reason is None else "failed", "reason": reason,
            "returncode": process.returncode, "captured_bytes": counts,
            "truncated_pipes": sorted(truncated), "drain_errors": drain_errors,
            "drain_scope": "at most four reads per confirmed nonblocking pipe; unread bytes may remain on failure",
            "minimum_observed_free_bytes": minimum, "sample_count": samples,
            "elapsed_seconds": time.monotonic() - start,
            "cleanup": cleanup, "all_descendant_termination": "unproven"}


def device(path):
    parent = path
    while not parent.exists():
        if parent == parent.parent:
            raise ValueError("no existing filesystem ancestor")
        parent = parent.parent
    return parent.stat().st_dev


def archive_identity(path):
    size = path.stat().st_size
    if size > MAX_ARTIFACTS + 2 * MIB:
        raise ValueError("archive exceeds retained bound")
    digest = hashlib.sha256()
    read_bytes = 0
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(65536), b""):
            read_bytes += len(block)
            if read_bytes > MAX_ARTIFACTS + 2 * MIB:
                raise ValueError("archive grew beyond retained bound")
            digest.update(block)
    if read_bytes != size:
        raise ValueError("archive changed while hashing")
    return {"bytes": size, "sha256": digest.hexdigest()}


def execute(profile, cwd, output, artifact_root, inputs, command, target=None):
    if not command or len(command) > 32 or sum(len(x.encode()) for x in command) > 16384:
        raise ValueError("command exceeds supported explicit argument bounds")
    if sys.platform != "linux":
        raise ValueError("Linux CI only; no alternate backend")
    if output.exists() or output.is_symlink() or artifact_root.exists() or artifact_root.is_symlink():
        raise ValueError("output and child artifact leaves must both be fresh")
    if output == artifact_root or output in artifact_root.parents or artifact_root in output.parents:
        raise ValueError("output and child artifact leaves must be disjoint")
    volumes = [cwd, output, artifact_root] + ([target] if target is not None else [])
    if len({device(path) for path in volumes}) != 1:
        raise ValueError("workspace, target and evidence must share the monitored filesystem")
    initial = shutil.disk_usage(cwd).free
    if initial < INITIAL_FREE:
        raise ValueError("initial free space below 8 GiB; nothing spawned or deleted")
    before = input_hashes(inputs)
    output.mkdir(parents=True, exist_ok=False)
    invocation = {"schema_version": 1, "invocation_id": uuid.uuid4().hex,
                  "profile": profile, "fresh_owned_output": str(output),
                  "fresh_child_leaf": str(artifact_root)}
    save(output / "invocation.json", invocation)
    result = {"schema_version": 1, "profile": profile, "command": command,
              "invocation_id": invocation["invocation_id"],
              "initial_free_bytes": initial, "reserve_bytes": RESERVE,
              "same_filesystem_checked": [str(path) for path in volumes],
              "stop_free_bytes": STOP_FREE, "artifact_limit_bytes": MAX_ARTIFACTS,
              "pipe_limit_bytes_each": MAX_PIPE, "deadline_seconds": DEADLINES[profile],
              "source_before": before, "all_descendant_termination": "unproven",
              "guard_kind": "sampled disk/output growth monitor, not a quota or sandbox",
              "cleanup_policy": "only owned unreaped process group; Core component groups may escape"}
    process = None
    try:
        process = subprocess.Popen(command, cwd=cwd, stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE, start_new_session=True)
        result.update(supervise(process, artifact_root, output, DEADLINES[profile]))
    except BaseException as error:
        result.update(status="failed", reason=type(error).__name__)
        if process is not None:
            result["cleanup"] = stop(process)
    result["snapshot_files"] = {}
    try:
        after = input_hashes(inputs)
        result["source_after"] = after
        if after != before:
            result.update(status="failed", source_error="controller_inputs_changed")
    except BaseException as error:
        result["status"] = "failed"
        result["source_error"] = type(error).__name__ + ": " + str(error)[:300]
    try:
        if shutil.disk_usage(output).free < STOP_FREE:
            raise ValueError("insufficient snapshot headroom")
        if not artifact_root.is_dir():
            raise ValueError("child artifact leaf missing")
        snapshot(artifact_root, output / "artifacts.tar", result["snapshot_files"])
        result["snapshot_status"] = "bounded_tar; not global quiescence proof"
    except BaseException as error:
        result["snapshot_status"] = "failed_or_partial"
        result["snapshot_error"] = type(error).__name__ + ": " + str(error)[:300]
        result["status"] = "failed"
        result["omitted_evidence"] = "Any source entry absent from snapshot_files was not retained; inventory may be incomplete. No original gate completion inferred."
    if (output / "artifacts.tar").is_file():
        try:
            result["archive"] = archive_identity(output / "artifacts.tar")
        except BaseException as error:
            result["status"] = "failed"
            result["archive_error"] = type(error).__name__ + ": " + str(error)[:300]
    result["semantic_scope"] = "Underlying gate exit and supervisor status are separate; partial artifacts never establish gate acceptance."
    try:
        save(output / "result.json", result)
    except BaseException as error:
        result["status"] = "failed"
        result["receipt_error"] = type(error).__name__
        fallback = {"schema_version": 1, "invocation_id": invocation["invocation_id"],
                    "status": "failed", "primary_reason": result.get("reason"),
                    "receipt_error": type(error).__name__,
                    "scope": "partial evidence; result.json may be absent or incomplete; no acceptance"}
        try:
            save(output / "incomplete-result.json", fallback)
        except BaseException as fallback_error:
            result["fallback_receipt_error"] = type(fallback_error).__name__
            print("resource-envelope: final receipts unavailable; failed partial evidence", file=sys.stderr)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", required=True, choices=DEADLINES)
    parser.add_argument("--cwd", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--artifacts", type=Path, required=True)
    parser.add_argument("--target", type=Path, required=True)
    parser.add_argument("--input", action="append", type=Path, default=[])
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if not command:
        parser.error("an explicit authored command is required")
    result = execute(args.profile, args.cwd.resolve(strict=True), args.output.absolute(),
                     args.artifacts.absolute(), [p.resolve(strict=True) for p in args.input], command, args.target.absolute())
    print(json.dumps({"status": result["status"], "descendant_termination": "unproven"}))
    raise SystemExit(0 if result["status"] == "passed" else 1)


if __name__ == "__main__":
    main()
