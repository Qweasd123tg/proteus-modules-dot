"""Private Linux source-only hard supervisor and capped evidence tail.
No invocation at import time; runtime authorization remains in entry.py.
Retained byte/file caps are exact. Workspace polling can overshoot transiently.
"""
import gzip
import hashlib
import json
import os
import selectors
import shutil
import signal
import stat
import subprocess
import time
import uuid
from pathlib import Path

MIB = 1024 * 1024
TOTAL = 512 * MIB
COMPRESSED = 256 * MIB
MAX_FILES = 4096
RAW_FILES = 4080
META_BYTES = 8 * MIB
FINAL_BYTES = 24 * MIB
TERMINAL_BYTES = MIB
TERMINAL_FILES = 1
ARCHIVE_BYTES = COMPRESSED - TERMINAL_BYTES - 65536
CAPS = {
    "small": {"journal": 8, "seed": 4, "sample": 4, "events": 2, "replay": 4, "other": 2},
    "large": {"journal": 96, "seed": 40, "sample": 24, "events": 8, "replay": 4, "other": 4},
}
BUCKETS = {"shared": 48*MIB, "smoke-01": 24*MIB, "smoke-02": 24*MIB,
           "smoke-03": 176*MIB, "smoke-04": 176*MIB}
CACHE_NAMES = {".read-" + kind + ".sqlite" + tail
               for kind in ("view", "summary") for tail in ("", "-wal", "-shm")}


def require(value, reason):
    if not value:
        raise RuntimeError(reason)


def encode(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def stamp(info):
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def safe_relative(value):
    require(isinstance(value, str) and 0 < len(value.encode("utf-8")) <= 512,
            "relative path byte budget")
    parts = value.split("/")
    require(not value.startswith("/") and all(part not in ("", ".", "..") for part in parts),
            "unsafe relative path")
    return parts


def write_all(fd, raw):
    while raw:
        count = os.write(fd, raw)
        require(count > 0, "short write")
        raw = raw[count:]


def write_json(path, value, cap=4*MIB):
    raw = encode(value) + b"\n"
    require(len(raw) <= cap, "JSON receipt budget")
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        write_all(fd, raw)
    finally:
        os.close(fd)
    return {"path": str(path), "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}


def inventory(root, deadline=None):
    """Bound enumeration even when the source contains too many entries.
    An incomplete inventory is explicit failure, not a complete selected subset.
    """
    root = Path(root)
    rows, errors, seen = [], [], 0
    pending = [root]
    try:
        info = root.lstat()
        require(stat.S_ISDIR(info.st_mode) and info.st_uid == os.geteuid(),
                "unowned or non-directory evidence root")
        while pending:
            if deadline is not None:
                require(time.monotonic() < deadline, "inventory deadline")
            directory = pending.pop()
            children = []
            with os.scandir(directory) as it:
                for item in it:
                    seen += 1
                    require(seen <= 8192, "directory entry ceiling; inventory incomplete")
                    children.append(item.name)
            for name in sorted(children):
                path = directory / name
                relative = str(path.relative_to(root))
                safe_relative(relative)
                info = path.lstat()
                require(info.st_uid == os.geteuid(), "unowned evidence")
                if stat.S_ISDIR(info.st_mode):
                    pending.append(path)
                elif stat.S_ISREG(info.st_mode):
                    if len(rows) == MAX_FILES:
                        raise RuntimeError("source file ceiling; inventory incomplete")
                    rows.append((path, info))
                elif stat.S_ISSOCK(info.st_mode) and relative == "sample/hold.sock":
                    continue  # Only the exact owned control endpoint, never a raw file.
                else:
                    raise RuntimeError("symlink or nonregular evidence: " + relative)
    except BaseException as error:
        errors.append(type(error).__name__ + ": " + str(error)[:1024])
    rows.sort(key=lambda item: str(item[0].relative_to(root)))
    return rows, errors


def files(root):
    rows, errors = inventory(root)
    require(not errors, "; ".join(errors))
    return rows


def category(relative, cache_paths=()):
    parts = relative.parts
    name = relative.name
    # Authoritative identities take precedence even over an erroneous cache list.
    if name == "journal.jsonl" or "blobs" in parts:
        return "journal"
    if str(relative) in cache_paths:
        require(name in CACHE_NAMES, "cache exemption is not an exact derived name")
        return "derived_cache"
    if name == "events.jsonl":
        return "events"
    if parts and parts[0] == "sample":
        return "sample"
    if parts and parts[0] in ("seed", "readiness") and name in ("stdout.raw", "stderr.raw"):
        return "seed"
    if parts and parts[0] == "replay":
        return "replay"
    return "other"


CACHE_ANCHORS = {"read_cache": "82d39fe3c7faa0395bfc2e81041309fb0395be74",
                 "read_model": "14422a6dd7d5cc3253cad79ffe20b3e76d09c741",
                 "catalog_cache": "3aaa03c29398428514db91f3cb788a7af4b9af9e"}


def cache_policy(value):
    require(isinstance(value, dict) and set(value) ==
            {"schema", "session_id", "session_relative", "cache_paths", "source_anchors"},
            "cache discovery schema fields")
    require(value["schema"] == "shipping-smoke-session-discovery-v1"
            and value["source_anchors"] == CACHE_ANCHORS, "cache discovery source binding")
    session = value["session_id"]
    require(isinstance(session, str) and str(uuid.UUID(session)) == session, "cache session UUID")
    relative = value["session_relative"]
    safe_relative(relative)
    require(relative.startswith("config/"), "cache session outside config")
    expected = sorted(relative+"/"+name for name in CACHE_NAMES)
    require(isinstance(value["cache_paths"], list) and sorted(value["cache_paths"]) == expected,
            "cache paths differ from exact session inventory")
    return session, relative, tuple(expected)


def _strict_json(raw):
    def pairs(values):
        result = {}
        for key, value in values:
            require(key not in result, "duplicate evidence key")
            result[key] = value
        return result
    def invalid(value):
        raise RuntimeError("nonfinite JSON constant: " + value)
    return json.loads(raw, object_pairs_hook=pairs, parse_constant=invalid)


def _discover_cache_paths(root):
    """Only a source-pinned early discovery AND first durable journal line can exempt.
    A missing/torn/racing marker conservatively exempts nothing. Full cache content
    hashes are still required by retention, outside the active-request interval.
    """
    marker = journal = None
    try:
        marker = _open_source(root, "session-discovery.json")
        before = os.fstat(marker)
        require(before.st_size <= 16384, "cache discovery cap")
        raw = b""
        while len(raw) < before.st_size:
            block = os.read(marker, min(4096, before.st_size-len(raw)))
            require(block, "cache discovery shortened")
            raw += block
        require(stamp(os.fstat(marker)) == stamp(before), "cache discovery changed")
        session, relative, paths = cache_policy(_strict_json(raw))
        journal = _open_source(root, relative+"/journal.jsonl")
        first = bytearray()
        while b"\n" not in first and len(first) <= 8*MIB:
            block = os.read(journal, min(65536, 8*MIB+1-len(first)))
            require(block, "first journal line not durable yet")
            first.extend(block)
        require(b"\n" in first and first.index(10) <= 8*MIB, "first journal line cap")
        row = _strict_json(bytes(first).split(b"\n", 1)[0])
        require(isinstance(row, dict) and row.get("session_id") == session
                and type(row.get("session_seq")) is int and row["session_seq"] == 1,
                "cache discovery journal attribution")
        return paths
    except BaseException:
        return ()
    finally:
        if marker is not None:
            os.close(marker)
        if journal is not None:
            os.close(journal)


def quota_scan(root, caps):
    totals = {key: 0 for key in caps}
    cache_paths = () if set(caps) == {"other"} else _discover_cache_paths(root)
    cached = 0
    for path, info in files(root):
        kind = "other" if set(caps) == {"other"} else category(path.relative_to(root), cache_paths)
        if kind == "derived_cache":
            cached += info.st_size
        else:
            totals[kind] += info.st_size
            require(totals[kind] <= caps[kind]*MIB, "category overflow: " + kind)
    require(shutil.disk_usage(root).free >= 2*1024**3, "disk floor below 2 GiB")
    return {"retained_categories": totals, "provisional_derived_cache_bytes": cached,
            "exact_cache_discovery_authenticated": bool(cache_paths),
            "cache_full_hashes_required_at_retention": True, "workspace_polling_not_atomic_quota": True}


def _pipe_send(fd, value, deadline, cap=65536):
    raw = encode(value) + b"\n"
    require(len(raw) <= cap, "control pipe frame cap")
    os.set_blocking(fd, False)
    while raw:
        require(time.monotonic() < deadline, "control pipe deadline")
        try:
            count = os.write(fd, raw)
            raw = raw[count:]
        except BlockingIOError:
            time.sleep(0.005)


def _cleanup_owned(deadline):
    """Dedicated single-thread controller only. Bounded kernel /proc child inventory.
    No evidence or ordinary filesystem reads occur in this outer deadline path.
    """
    stopped = []
    while True:
        require(time.monotonic() < deadline, "owned cleanup absolute deadline")
        fd = os.open("/proc/self/task/"+str(os.getpid())+"/children", os.O_RDONLY | os.O_NONBLOCK)
        try:
            raw = os.read(fd, 65537)
        finally:
            os.close(fd)
        require(len(raw) <= 65536, "owned child inventory exceeds bounded cleanup; uncertain")
        children = raw.split()
        require(len(children) <= 4096, "owned process count exceeds bounded cleanup; uncertain")
        if not children:
            return stopped
        for token in children:
            require(time.monotonic() < deadline, "owned cleanup absolute deadline")
            require(token.isdigit(), "invalid kernel child identity")
            pid = int(token)
            try:
                done, _ = os.waitpid(pid, os.WNOHANG)
                if done:
                    continue
                # A direct unreaped child reserves its PID even if pidfd_open fails.
                try:
                    handle = os.pidfd_open(pid)
                except OSError:
                    os.kill(pid, signal.SIGKILL)
                else:
                    try:
                        signal.pidfd_send_signal(handle, signal.SIGKILL)
                    finally:
                        os.close(handle)
                if pid not in stopped:
                    require(len(stopped) < 4096, "cleanup PID receipt ceiling; uncertain")
                    stopped.append(pid)
                os.waitpid(pid, os.WNOHANG)
            except (ProcessLookupError, ChildProcessError):
                pass
        time.sleep(min(0.005, max(0, deadline-time.monotonic())))


def pipe_capacity(result_path, requested):
    require(type(requested) is int and 65536 <= requested <= 4*MIB+65536, "result pipe cap")
    require(result_path is not None or requested == 65536, "large pipe requires persisted result")
    return requested


def _hard(capture, operation, arguments, deadline, root=None, caps=None, result_path=None,
          result_summary=None, result_pipe_cap=65536):
    """Parent does no evidence walks, stat, copy, hash or archive I/O.
    Worker and independent quota monitor may block; pidfds and the absolute parent
    deadline remain live. The dedicated parent owns no unrelated child processes.
    """
    require(deadline > time.monotonic()+5, "no time for operation and owned cleanup")
    result_pipe_cap = pipe_capacity(result_path, result_pipe_cap)
    require(result_summary is None or callable(result_summary), "result summary callback")
    capture.enable_subreaper()
    readfd, writefd = os.pipe()
    os.set_blocking(readfd, False)
    monitor_read = monitor_write = None
    pids, handles, statuses = [], {}, {}
    selector = selectors.DefaultSelector()
    buffers = {"worker": bytearray(), "monitor": bytearray()}
    response, quota, failure, exited_at = None, None, None, None
    started = time.monotonic()
    stopped, cleanup_complete = [], False
    try:
        worker = os.fork()
        if worker == 0:
            os.close(readfd)
            try:
                os.setsid()
                value = operation(*arguments)
                written = None
                if result_path is not None:
                    written = write_json(result_path, {"status": "WORKER_RETURNED", "value": value})
                if result_summary is not None:
                    value = result_summary(value)
                _pipe_send(writefd, {"status": "WORKER_RETURNED", "value": value,
                                    "result_receipt": written}, deadline-5, result_pipe_cap)
                os._exit(0)
            except BaseException as error:
                message = type(error).__name__ + ": " + str(error)[:2048]
                try:
                    if result_path is not None:
                        try:
                            write_json(result_path, {"status": "FAILED_CENSORED", "error": message})
                        except BaseException:
                            pass  # Preserve any partial result; the bounded pipe still reports failure.
                    _pipe_send(writefd, {"status": "FAILED_CENSORED", "error": message}, deadline-5)
                finally:
                    os._exit(1)
        pids.append(worker)  # Recorded before pidfd_open: failure cannot orphan the child.
        handles[worker] = os.pidfd_open(worker)
        os.close(writefd)
        writefd = None
        selector.register(readfd, selectors.EVENT_READ, "worker")
        if root is not None:
            monitor_read, monitor_write = os.pipe()
            os.set_blocking(monitor_read, False)
            monitor = os.fork()
            if monitor == 0:
                os.close(monitor_read)
                os.close(readfd)
                try:
                    os.setsid()
                    while time.monotonic() < deadline-5:
                        scan_started = time.monotonic()
                        try:
                            receipt = quota_scan(root, caps)
                            message = {"status": "QUOTA_OK", "scan_started": scan_started, "quota": receipt}
                        except BaseException as error:
                            message = {"status": "FAILED_CENSORED",
                                       "error": type(error).__name__ + ": " + str(error)[:2048]}
                        _pipe_send(monitor_write, message, deadline-5, 8192)
                        if message["status"] != "QUOTA_OK":
                            os._exit(1)
                        time.sleep(0.05)
                    os._exit(1)
                except BaseException:
                    os._exit(1)
            pids.append(monitor)
            handles[monitor] = os.pidfd_open(monitor)
            os.close(monitor_write)
            monitor_write = None
            selector.register(monitor_read, selectors.EVENT_READ, "monitor")
        else:
            monitor = None
        while True:
            require(time.monotonic() < deadline-5, "outer absolute operation deadline")
            for key, _ in selector.select(min(0.05, max(0, deadline-5-time.monotonic()))):
                label = key.data
                chunk = os.read(key.fd, 65536)
                if not chunk:
                    selector.unregister(key.fd)
                    continue
                buffer = buffers[label]
                buffer.extend(chunk)
                require(len(buffer) <= (result_pipe_cap if label == "worker" else 65536),
                        "control pipe buffer overflow")
                while b"\n" in buffer:
                    line, _, tail = buffer.partition(b"\n")
                    buffer[:] = tail
                    value = json.loads(line)
                    if label == "worker":
                        require(response is None, "duplicate worker response")
                        response = value
                    else:
                        require(value["status"] == "QUOTA_OK", value.get("error", "quota monitor failure"))
                        quota = value
            for pid in pids:
                if pid not in statuses:
                    done, status = os.waitpid(pid, os.WNOHANG)
                    if done:
                        statuses[pid] = status
                        if pid == worker:
                            exited_at = time.monotonic()
            require(monitor is None or monitor not in statuses, "quota monitor exited")
            if worker in statuses and response is not None:
                require(statuses[worker] == 0 and response["status"] == "WORKER_RETURNED",
                        response.get("error", "worker failed"))
                if monitor is None or (quota is not None and quota["scan_started"] >= exited_at):
                    break
            if worker in statuses and statuses[worker] != 0:
                raise RuntimeError(response.get("error", "worker failed") if response else "worker failed without receipt")
            if worker in statuses and response is None and not any(
                    key.data == "worker" for key in selector.get_map().values()):
                raise RuntimeError("worker exited without complete control response")
    except BaseException as error:
        failure = type(error).__name__ + ": " + str(error)[:2048]
    finally:
        # Direct children remain unreaped identities if pidfd_open itself failed.
        for pid in pids:
            if pid not in statuses:
                try:
                    if pid in handles:
                        signal.pidfd_send_signal(handles[pid], signal.SIGKILL)
                    else:
                        os.kill(pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
        cleanup_end = min(deadline, time.monotonic()+5)
        try:
            stopped = _cleanup_owned(cleanup_end)
            cleanup_complete = True
            if any(pid not in pids for pid in stopped):
                failure = failure or "owned descendants remained after operation"
        except BaseException as error:
            failure = failure or "owned cleanup uncertain: " + str(error)[:2048]
        for fd in handles.values():
            os.close(fd)
        selector.close()
        for fd in (readfd, writefd, monitor_read, monitor_write):
            if fd is not None:
                os.close(fd)
    if time.monotonic() > deadline:
        failure = failure or "outer absolute deadline expired during cleanup"
    return {"status": "FAILED_CENSORED" if failure else "SUPERVISED_STAGE_COMPLETE",
            "reason": failure, "value": response.get("value") if response else None,
            "result_receipt": response.get("result_receipt") if response else None,
            "worker_wait_status": statuses.get(pids[0]) if pids else None,
            "quota": quota, "forced_owned_pids": stopped, "owned_cleanup_complete": cleanup_complete,
            "seconds": time.monotonic()-started, "absolute_deadline": deadline}


def supervise(capture, operation, arguments, root, caps, seconds, result_path,
              result_summary=None, result_pipe_cap=65536):
    return _hard(capture, operation, arguments, time.monotonic()+seconds,
                 root=root, caps=caps, result_path=result_path,
                 result_summary=result_summary, result_pipe_cap=result_pipe_cap)


def command(argv, cwd, env, root, seconds, cap):
    """Separated raw stdout and diagnostics, bounded incremental writes.
    Parent supervisor supplies the independent hard deadline and adoption cleanup.
    """
    root = Path(root)
    root.mkdir(mode=0o700, parents=False, exist_ok=False)
    child = subprocess.Popen(argv, cwd=cwd, env=env, stdin=subprocess.DEVNULL,
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
    deadline, total = time.monotonic() + seconds, 0
    selector = selectors.DefaultSelector()
    streams = {}
    receipt = {"argv": argv, "status": "ATTEMPTED", "observed_bytes": 0,
               "failure_prefix": False, "unretained_observed_bytes": 0}
    try:
        for name, pipe in (("stdout", child.stdout), ("stderr", child.stderr)):
            os.set_blocking(pipe.fileno(), False)
            out = (root / (name + ".raw")).open("xb")
            streams[pipe] = out
            selector.register(pipe, selectors.EVENT_READ)
        while selector.get_map() or child.poll() is None:
            require(time.monotonic() < deadline, "command deadline")
            for key, _ in selector.select(0.05):
                chunk = os.read(key.fileobj.fileno(), 65536)
                if not chunk:
                    selector.unregister(key.fileobj)
                    continue
                available = cap - total
                receipt["observed_bytes"] += len(chunk)
                receipt["unretained_observed_bytes"] += max(0, len(chunk)-available)
                receipt["failure_prefix"] = receipt["failure_prefix"] or len(chunk) > available
                streams[key.fileobj].write(chunk[:available])
                total += min(len(chunk), available)
                require(len(chunk) <= available, "command output cap")
        receipt["exit_code"] = child.wait(timeout=max(0, deadline-time.monotonic()))
        require(receipt["exit_code"] == 0, "command nonzero exit")
        receipt["status"] = "COMMAND_COMPLETE"
    except BaseException as error:
        receipt["status"] = "FAILED_CENSORED"
        receipt["error"] = type(error).__name__ + ": " + str(error)[:2048]
        raise
    finally:
        if child.poll() is None:
            try:
                os.killpg(child.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        for pipe, out in streams.items():
            out.close()
            pipe.close()
        selector.close()
        receipt["retained_bytes"] = total
        write_json(root / "command.json", receipt, 65536)
    return receipt


def new_ledger():
    """One object for shared and every procedure. Reservations are not extra raw quota."""
    return {"schema": 1, "payload_bytes": 0, "control_bytes": 0, "raw_files": 0,
            "control_files": 0, "claimed": [], "failed": False, "uncertain": False,
            "bucket_receipts": {}, "limits": {"uncompressed": TOTAL, "files": MAX_FILES,
            "compressed": COMPRESSED, "failure_control_reserve": 64*MIB}}


def allocation(ledger, bucket, caps, remaining_global):
    """Pure admission/accounting helper; reserve metadata before copying."""
    require(bucket in BUCKETS and bucket not in ledger["claimed"], "unknown or repeated evidence bucket")
    expected_caps = {"other": 48} if bucket == "shared" else CAPS["small" if bucket in ("smoke-01", "smoke-02") else "large"]
    require(caps == expected_caps and all(type(value) is int for value in caps.values()),
            "bucket category allocation mismatch")
    require(type(remaining_global) is int and META_BYTES <= remaining_global <= TOTAL,
            "global reserve exhausted or invalid")
    require(0 <= ledger["raw_files"] <= RAW_FILES, "global raw-file ledger")
    require(0 <= ledger["control_files"] <= 10, "global metadata ledger")
    allowance = min(BUCKETS[bucket], remaining_global-META_BYTES)
    require(ledger["payload_bytes"]+ledger["control_bytes"]+allowance+META_BYTES+FINAL_BYTES <= TOTAL,
            "global bytes including final reserve")
    return {"data": allowance, "metadata": META_BYTES, "raw_files": RAW_FILES-ledger["raw_files"],
            "control_files": 2, "bucket": bucket}



def copy_allowance(source_bytes, category_limit, category_used, data_limit, data_used):
    values = (source_bytes, category_limit, category_used, data_limit, data_used)
    require(all(type(value) is int and value >= 0 for value in values), "copy counts")
    require(category_used <= category_limit and data_used <= data_limit, "copy budget exceeded")
    return min(source_bytes, category_limit-category_used, data_limit-data_used)


def prefix_flags(source_bytes, read_bytes, retained_bytes, stable, cache, error):
    """Pure classification: observed size is not a full-content hash witness."""
    require(all(type(value) is int and value >= 0
                for value in (source_bytes, read_bytes, retained_bytes)), "prefix count shape")
    require(retained_bytes <= read_bytes <= source_bytes, "prefix counts")
    require(type(stable) is bool and type(cache) is bool, "prefix flags")
    full = stable and read_bytes == source_bytes and error is None
    return {"source_full_hash_verified": full,
            "complete_raw_retained": full and not cache and retained_bytes == source_bytes,
            "derived_cache_excluded": full and cache,
            "failure_prefix": not cache and (not full or retained_bytes != source_bytes)}


def final_status(procedure_status, ledger_failed, package_complete, cleanup_complete):
    return ("FEASIBILITY_SMOKE_COMPLETE"
            if procedure_status == "FEASIBILITY_SMOKE_COMPLETE" and not ledger_failed
            and package_complete and cleanup_complete else "FAILED_CENSORED")

def _open_source(root, relative):
    parts = safe_relative(relative)
    directory = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        require(os.fstat(directory).st_uid == os.geteuid(), "unowned source root")
        for part in parts[:-1]:
            following = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory)
            info = os.fstat(following)
            require(info.st_uid == os.geteuid(), "unowned source directory")
            os.close(directory)
            directory = following
        fd = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid():
            os.close(fd)
            raise RuntimeError("unowned or nonregular source")
        return fd
    finally:
        os.close(directory)


def _copy_file(root, relative, before, target, amount, deadline, cache=False):
    """Read only retained bytes; do not read the oversized remainder to invent a hash."""
    read = copied = 0
    source = output = None
    digest = hashlib.sha256()
    failure = None
    created = False
    full = False
    try:
        source = _open_source(root, relative)
        require(stamp(os.fstat(source)) == stamp(before), "source replaced before retention")
        if not cache:
            target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            output = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            created = True  # Empty regular files are preserved too.
        while read < amount:
            require(time.monotonic() < deadline, "retention copy deadline")
            block = os.read(source, min(65536, amount-read))
            require(block, "source shortened during retention")
            read += len(block)
            if output is not None:
                require(shutil.disk_usage(target.parent).free >= 2*1024**3+len(block),
                        "retention disk floor below 2 GiB")
                # Count exactly each successful write, including a partial-error prefix.
                pending = block
                while pending:
                    count = os.write(output, pending)
                    require(count > 0, "short evidence write")
                    digest.update(pending[:count])
                    copied += count
                    pending = pending[count:]
            else:
                digest.update(block)
        require(stamp(os.fstat(source)) == stamp(before), "source changed during retention")
        full = read == before.st_size
    except BaseException as error:
        failure = type(error).__name__ + ": " + str(error)[:1024]
    finally:
        if output is not None:
            os.close(output)
        if source is not None:
            os.close(source)
    flags = prefix_flags(before.st_size, read, copied, full, cache, failure)
    return {"source_bytes_observed": before.st_size, "source_sha256": digest.hexdigest() if flags["source_full_hash_verified"] else None,
            **flags, "retained_bytes": copied,
            "retained_sha256": digest.hexdigest() if not cache else None,
            "created_file": created, "read_bytes": read, "error": failure,
            "device": before.st_dev, "inode": before.st_ino,
            "mtime_ns": before.st_mtime_ns, "ctime_ns": before.st_ctime_ns}


def _retain_worker(root, destination, caps, grant, deadline, cache_paths, expected_files):
    root, dest = Path(root), Path(destination)
    dest.mkdir(mode=0o700, parents=False, exist_ok=False)
    raw_root = dest / "raw"
    raw_root.mkdir(mode=0o700)
    authenticated = () if set(caps) == {"other"} else _discover_cache_paths(root)
    policy_mismatch = bool(cache_paths) and set(cache_paths) != set(authenticated)
    cache_paths = () if policy_mismatch else authenticated
    require(len(cache_paths) <= 6 and len(set(cache_paths)) == len(cache_paths), "cache inventory")
    for relative in cache_paths:
        safe_relative(relative)
        require(Path(relative).name in CACHE_NAMES and category(Path(relative)) != "journal",
                "authoritative file cannot be a cache")
    require(len({str(Path(p).parent) for p in cache_paths}) <= 1, "cache roots differ")
    require(isinstance(expected_files, dict) and len(expected_files) <= 16, "expected receipt count")
    for relative, expected in expected_files.items():
        safe_relative(relative)
        require(isinstance(expected, dict) and set(expected) == {"bytes", "sha256"}
                and type(expected["bytes"]) is int and 0 <= expected["bytes"] <= 4*MIB
                and isinstance(expected["sha256"], str) and len(expected["sha256"]) == 64
                and all(c in "0123456789abcdef" for c in expected["sha256"]), "expected receipt shape")
    used = {key: 0 for key in caps}
    data = count = metadata = cache_read = 0
    rows, errors = inventory(root, deadline)
    if policy_mismatch:
        errors.append("supplied cache exemption not authenticated; no caches excluded")
    observed_names = {str(path.relative_to(root)) for path, _ in rows}
    for relative in sorted(set(expected_files)-observed_names):
        errors.append("expected guarded result is absent: "+relative)
    complete = not errors
    fd = os.open(dest / "retention-ledger.jsonl",
                 os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    def log(value):
        nonlocal metadata
        raw = encode(value)+b"\n"
        require(shutil.disk_usage(dest).free >= 2*1024**3+len(raw), "retention ledger disk floor")
        require(len(raw) <= 2048 and metadata+len(raw) <= META_BYTES-65536,
                "retention ledger reserve exhausted")
        write_all(fd, raw)
        metadata += len(raw)
    try:
        log({"schema": 1, "status": "RETENTION_STARTED", "source": str(root),
             "inventory_complete": not errors, "inventory_errors": errors,
             "original_source_not_deleted": True, "raw_slot_grant": grant["raw_files"]})
        for index, (path, before) in enumerate(rows):
            require(time.monotonic() < deadline, "retention deadline")
            relative = str(path.relative_to(root))
            kind = "other" if set(caps) == {"other"} else category(Path(relative), cache_paths)
            cache = kind == "derived_cache"
            amount = (copy_allowance(before.st_size, caps[kind]*MIB, used[kind], grant["data"], data)
                      if not cache else min(before.st_size, max(0, 128*MIB-cache_read)))
            slot = cache or count < grant["raw_files"]
            log({"index": index, "path": relative, "category": kind, "state": "COPY_PLANNED",
                 "source_bytes_observed": before.st_size, "planned_read_bytes": amount if slot else 0,
                 "destination": "raw/"+relative if not cache and slot else None})
            if not slot:
                receipt = {"source_bytes_observed": before.st_size, "source_sha256": None,
                           "retained_bytes": 0, "complete_raw_retained": False,
                           "source_full_hash_verified": False, "created_file": False,
                           "derived_cache_excluded": False, "failure_prefix": True,
                           "error": "global file ledger exhausted; original source retained",
                           "read_bytes": 0}
            else:
                receipt = _copy_file(root, relative, before, raw_root / relative, amount, deadline, cache)
            if relative in expected_files:
                expected = expected_files[relative]
                matched = (receipt["complete_raw_retained"] and receipt["source_full_hash_verified"]
                           and receipt["source_bytes_observed"] == expected["bytes"]
                           and receipt["source_sha256"] == expected["sha256"])
                receipt["expected_receipt_matches"] = matched
                receipt["expected_sha256"] = expected["sha256"]
                receipt["expected_bytes"] = expected["bytes"]
                if not matched:
                    receipt["error"] = receipt["error"] or "guarded result differs from retained evidence"
            count += int(receipt["created_file"])
            if cache:
                cache_read += receipt["read_bytes"]
            else:
                used[kind] += receipt["retained_bytes"]
                data += receipt["retained_bytes"]
            good = receipt["derived_cache_excluded"] if cache else receipt["complete_raw_retained"]
            complete = complete and good and receipt["error"] is None
            log({"index": index, "state": "COPY_FINISHED", **receipt})
        status = "COMPLETE_PRIMARY_EVIDENCE" if complete else "FAILED_CENSORED"
        summary = {"status": status, "not_full_session_archive": True,
                   "original_source_not_deleted": True, "inventory_complete": not errors,
                   "inventory_errors": errors, "enumerated_files": len(rows),
                   "retained_bytes": data, "retained_raw_files": count,
                   "categories": used, "excluded_cache_read_bytes": cache_read,
                   "ledger": "retention-ledger.jsonl"}
        # Self-inclusive byte count stabilizes in a bounded number of digit changes.
        summary["retained_bytes_including_manifest"] = 0
        summary["metadata_bytes"] = 0
        for _ in range(8):
            raw = encode(summary)+b"\n"
            new = metadata+len(raw)
            if summary["metadata_bytes"] == new:
                break
            summary["metadata_bytes"] = new
            summary["retained_bytes_including_manifest"] = data+new
        raw = encode(summary)+b"\n"
        require(metadata+len(raw) == summary["metadata_bytes"] <= META_BYTES,
                "retention manifest reserve")
        write_json(dest / "retention.json", summary, 65536)
        summary["retained_files_including_manifest"] = count+2
        return summary
    finally:
        os.close(fd)


def retain(root, destination, caps, remaining_global, *, ledger, capture, deadline,
           bucket, cache_paths=(), expected_files=None):
    """Hard-supervised immutable snapshot, deterministic prefixes on failure.
    Exact cache paths are authenticated from the source-bound discovery plus journal.
    An optional caller list must match it; absent/invalid discovery excludes nothing.
    """
    grant = allocation(ledger, bucket, caps, remaining_global)
    ledger["claimed"].append(bucket)
    guard = _hard(capture, _retain_worker,
                  (root, destination, caps, grant, deadline-5, tuple(cache_paths),
                   {} if expected_files is None else expected_files), deadline)
    result = guard["value"]
    verified = guard["status"] == "SUPERVISED_STAGE_COMPLETE" and isinstance(result, dict)
    if verified:
        ledger["payload_bytes"] += result["retained_bytes"]
        ledger["control_bytes"] += result["metadata_bytes"]
        ledger["raw_files"] += result["retained_raw_files"]
        ledger["control_files"] += 2
        result = dict(result, supervision=guard)
    else:
        # The killed writer cannot report actual prefix lengths. Charge its entire
        # grant pessimistically, preserve it, and never call unknown bytes complete.
        ledger["payload_bytes"] += grant["data"]
        ledger["control_bytes"] += grant["metadata"]
        ledger["raw_files"] += grant["raw_files"]
        ledger["control_files"] += 2
        ledger["uncertain"] = True
        result = {"status": "FAILED_CENSORED", "retained_bytes_including_manifest":
                  grant["data"]+grant["metadata"], "bytes_are_upper_bound": True,
                  "actual_retained_bytes": None, "partial_destination": str(destination),
                  "reason": "retention interrupted; partial raw files and ledger preserved",
                  "supervision": guard}
    ledger["failed"] = ledger["failed"] or result["status"] != "COMPLETE_PRIMARY_EVIDENCE"
    ledger["bucket_receipts"][bucket] = {key: result.get(key) for key in
        ("status", "retained_bytes_including_manifest", "bytes_are_upper_bound", "actual_retained_bytes")}
    return result

def _hash_member(root, relative, before, deadline):
    fd = _open_source(root, relative)
    value, size = hashlib.sha256(), 0
    try:
        require(stamp(os.fstat(fd)) == stamp(before), "package source replaced")
        while size < before.st_size:
            require(time.monotonic() < deadline, "package hashing deadline")
            block = os.read(fd, min(65536, before.st_size-size))
            require(block, "package source shortened")
            value.update(block)
            size += len(block)
        require(stamp(os.fstat(fd)) == stamp(before), "package source changed")
        return value.hexdigest()
    finally:
        os.close(fd)


class _CappedSink:
    def __init__(self, fd, deadline, root):
        self.fd, self.deadline, self.root = fd, deadline, root
        self.bytes, self.hash = 0, hashlib.sha256()

    def write(self, raw):
        require(time.monotonic() < self.deadline, "compressed package deadline")
        require(self.bytes+len(raw) <= ARCHIVE_BYTES, "compressed package ceiling including terminal/container reserve")
        require(shutil.disk_usage(self.root).free >= 2*1024**3+len(raw),
                "package disk floor below 2 GiB")
        pending = memoryview(raw)
        while pending:
            count = os.write(self.fd, pending)
            require(count > 0, "short package write")
            self.hash.update(pending[:count])
            self.bytes += count
            pending = pending[count:]
        return len(raw)

    def flush(self):
        pass  # No additional data or unbounded fsync in the parent.

    def tell(self):
        return self.bytes


class _MemberReader:
    def __init__(self, fd, size, deadline):
        self.fd, self.remaining, self.deadline = fd, size, deadline
        self.hash = hashlib.sha256()

    def read(self, amount):
        require(time.monotonic() < self.deadline, "archive member read deadline")
        require(type(amount) is int and 0 <= amount <= 1024*1024, "archive read request")
        wanted = min(amount, self.remaining)
        chunks, total = [], 0
        while total < wanted:
            chunk = os.read(self.fd, min(65536, wanted-total))
            require(chunk, "archive member shortened")
            chunks.append(chunk)
            self.hash.update(chunk)
            total += len(chunk)
            self.remaining -= len(chunk)
        return b"".join(chunks)


def _package_worker(evidence, archive, status, ledger, deadline):
    """Bound all hashing, compression, final receipts and failure handling in this worker.
    A timeout leaves .partial, raw files and the started ledgers untouched.
    """
    import tarfile
    evidence, archive = Path(evidence), Path(archive)
    partial = Path(str(archive)+".partial")
    require(not archive.is_relative_to(evidence) and not evidence.is_relative_to(archive),
            "compressed package must be outside uncompressed evidence")
    raw_status = dict(status, status="EVIDENCE_FINALIZATION_PENDING",
                      procedure_status=status.get("status"), evidence_ledger=ledger,
                      acceptance_requires="PACKAGE_COMPLETE receipt and successful outer cleanup")
    write_json(evidence / "final.json", raw_status, 4*MIB)
    rows, errors = inventory(evidence, deadline)
    source_total = sum(info.st_size for _, info in rows)
    require(not errors and source_total <= TOTAL-4*MIB-65536-TERMINAL_BYTES
            and len(rows)+4+TERMINAL_FILES <= MAX_FILES, "final inventory or metadata reserve exhausted")
    members = []
    for path, info in rows:
        relative = str(path.relative_to(evidence))
        members.append({"path": relative, "bytes": info.st_size,
                        "sha256": _hash_member(evidence, relative, info, deadline)})
    manifest = {"schema": 1, "files": members, "uncompressed_member_bytes": source_total,
                "self_excluded": "package-inventory.json",
                "result_excluded": "package-result.json", "not_full_session_archive": True}
    inventory_raw = encode(manifest)+b"\n"
    require(len(inventory_raw) <= 4*MIB, "package inventory reserve")
    write_json(evidence / "package-inventory.json", manifest, 4*MIB)
    manifest_path = evidence / "package-inventory.json"
    rows.append((manifest_path, manifest_path.lstat()))
    members.append({"path": "package-inventory.json", "bytes": len(inventory_raw),
                    "sha256": hashlib.sha256(inventory_raw).hexdigest()})
    rows.sort(key=lambda item: str(item[0].relative_to(evidence)))
    wanted = {row["path"]: row for row in members}
    compressed, error, complete = 0, None, False
    created_partial = linked_archive = removed_partial = False
    sink = None
    fd = None
    try:
        fd = os.open(partial, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        created_partial = True
        sink = _CappedSink(fd, deadline, partial.parent)
        with gzip.GzipFile(filename="", mode="wb", fileobj=sink, mtime=0, compresslevel=6) as gz:
            with tarfile.open(fileobj=gz, mode="w|", format=tarfile.PAX_FORMAT) as tar:
                for path, before in rows:
                    relative = str(path.relative_to(evidence))
                    source = _open_source(evidence, relative)
                    try:
                        require(stamp(os.fstat(source)) == stamp(before), "archive source replaced")
                        reader = _MemberReader(source, before.st_size, deadline)
                        info = tarfile.TarInfo(relative)
                        info.size, info.mode, info.mtime = before.st_size, 0o600, 0
                        info.uid = info.gid = 0
                        info.uname = info.gname = ""
                        tar.addfile(info, reader)
                        require(reader.remaining == 0 and reader.hash.hexdigest() == wanted[relative]["sha256"]
                                and stamp(os.fstat(source)) == stamp(before), "archive source changed")
                    finally:
                        os.close(source)
        os.close(fd)
        fd = None
        require(time.monotonic() < deadline, "package completion deadline")
        # Rename only a complete, size-capped package; no raw evidence is removed.
        os.link(partial, archive, follow_symlinks=False)  # Exclusive: never overwrite an existing archive.
        linked_archive = True
        os.unlink(partial)  # The identical complete inode remains at archive.
        removed_partial = True
        complete = True
    except BaseException as failure:
        error = type(failure).__name__ + ": " + str(failure)[:2048]
    finally:
        if fd is not None:
            os.close(fd)
    if sink is not None:
        compressed = sink.bytes
    aliases = ([str(partial)] if created_partial and not removed_partial else []) + (
               [str(archive)] if linked_archive else [])
    result = {"status": "PACKAGE_COMPLETE" if complete else "FAILED_CENSORED",
              "archive": str(archive) if complete else (str(partial) if created_partial else None),
              "archive_aliases": aliases, "aliases_share_one_compressed_inode": len(aliases) == 2,
              "terminal_acceptance": "PENDING_OUTER_TERMINAL_AUTHORITY",
              "compressed_bytes": compressed, "compressed_cap_bytes": COMPRESSED,
              "gzip_cap_bytes": ARCHIVE_BYTES, "outer_container_reserved_bytes": 65536,
              "compressed_storage_scope": "Separate from 512 MiB uncompressed evidence; partial included.",
              "compressed_sha256": sink.hash.hexdigest() if sink else None,
              "compressed_hash_is_complete_archive": complete,
              "error": error, "raw_evidence_preserved": True,
              "uncompressed_bytes_including_result": 0,
              "uncompressed_files_including_result": len(rows)+1,
              "all_retained_file_entries_including_package": len(rows)+1+len(aliases),
              "terminal_control_reserved_bytes": TERMINAL_BYTES,
              "terminal_control_reserved_files": TERMINAL_FILES,
              "uncompressed_bytes_plus_terminal_reserve": 0,
              "all_retained_file_entries_plus_terminal_reserve": len(rows)+1+len(aliases)+TERMINAL_FILES}
    for _ in range(8):
        raw = encode(result)+b"\n"
        count = source_total+len(inventory_raw)+len(raw)
        if result["uncompressed_bytes_including_result"] == count:
            break
        result["uncompressed_bytes_including_result"] = count
        result["uncompressed_bytes_plus_terminal_reserve"] = count+TERMINAL_BYTES
    raw = encode(result)+b"\n"
    require(len(raw) <= 65536 and source_total+len(inventory_raw)+len(raw)
            == result["uncompressed_bytes_including_result"] <= TOTAL,
            "final exact uncompressed cap")
    require(result["uncompressed_bytes_plus_terminal_reserve"] <= TOTAL, "outer terminal byte reserve")
    require(result["all_retained_file_entries_plus_terminal_reserve"] <= MAX_FILES, "final exact file cap")
    write_json(evidence / "package-result.json", result, 65536)
    result["candidate_feasibility_status"] = final_status(status.get("status"), ledger["failed"], complete, True)
    result["feasibility_status"] = "PENDING_OUTER_TERMINAL_AUTHORITY" if complete else "FAILED_CENSORED"
    return result


def package(capture, evidence, archive, status, ledger, deadline):
    """A failed/incomplete package never authorizes deletion or success."""
    require("final" not in ledger["claimed"], "finalization cannot be retried")
    ledger["claimed"].append("final")
    guard = _hard(capture, _package_worker,
                  (evidence, archive, status, ledger, deadline-5), deadline)
    value = guard["value"]
    if guard["status"] != "SUPERVISED_STAGE_COMPLETE" or not isinstance(value, dict):
        ledger["failed"] = True
        return {"status": "FAILED_CENSORED", "feasibility_status": "FAILED_CENSORED",
                "reason": "finalization interrupted; raw evidence and any partial package preserved",
                "supervision": guard, "partial_archive": str(archive)+".partial",
                "partial_archive_may_be_absent": True,
                "compressed_bytes": None, "compressed_bytes_upper_bound": ARCHIVE_BYTES,
                "compressed_cap_bytes": COMPRESSED, "gzip_cap_bytes": ARCHIVE_BYTES,
                "outer_container_reserved_bytes": 65536,
                "compressed_storage_scope": "Separate from uncompressed evidence; interrupted prefix retained."}
    value["candidate_feasibility_status"] = final_status(status.get("status"), ledger["failed"],
        value.get("status") == "PACKAGE_COMPLETE", guard["status"] == "SUPERVISED_STAGE_COMPLETE"
        and guard["owned_cleanup_complete"])
    value["feasibility_status"] = ("PENDING_OUTER_TERMINAL_AUTHORITY"
        if value["candidate_feasibility_status"] == "FEASIBILITY_SMOKE_COMPLETE" else "FAILED_CENSORED")
    return dict(value, supervision=guard)


def expected_stage_files(shared, stages):
    """Pure path mapping of guarded source-stage result receipts into shared evidence."""
    root = Path(shared)
    require(root.is_absolute() and isinstance(stages, list), "shared receipt root/stages")
    expected = {}
    for stage in stages:
        receipt = stage.get("result_receipt")
        if receipt is None:
            continue
        require(isinstance(receipt, dict) and set(receipt) == {"path", "bytes", "sha256"},
                "guarded stage receipt fields")
        path = Path(receipt["path"])
        try:
            relative = str(path.relative_to(root))
        except ValueError:
            raise RuntimeError("guarded shared result is outside the shared root")
        safe_relative(relative)
        require(relative not in expected and len(expected) < 16, "duplicate/too many shared receipts")
        expected[relative] = {"bytes": receipt["bytes"], "sha256": receipt["sha256"]}
    return expected


def finalize(capture, shared, evidence, status, ledger, deadline):
    """Final absolute deadline belongs to the attempt's reserved control budget.
    Shared diagnostics remain under work until this point; no direct final writes.
    """
    require(deadline > time.monotonic()+45, "insufficient reserved finalization window")
    shared_deadline = min(deadline-40, time.monotonic()+45)
    remaining = TOTAL-ledger["payload_bytes"]-ledger["control_bytes"]-FINAL_BYTES
    expected = expected_stage_files(shared, status.get("stages", []))
    retained = retain(shared, Path(evidence)/"shared", {"other": 48}, remaining,
                      ledger=ledger, capture=capture, deadline=shared_deadline, bucket="shared",
                      expected_files=expected)
    status = dict(status, shared_retention=retained)
    if retained["status"] != "COMPLETE_PRIMARY_EVIDENCE":
        status["status"] = "FAILED_CENSORED"
    result = package(capture, evidence, Path(str(evidence)+".tar.gz"), status, ledger, deadline)
    status["status"] = result.get("feasibility_status", "FAILED_CENSORED")
    status["evidence_package"] = result
    status["performance_claim"] = None
    return status
