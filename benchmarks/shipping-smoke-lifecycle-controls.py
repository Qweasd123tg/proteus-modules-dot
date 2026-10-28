"""Private lifecycle-only controls; no top-level execution and no product commands.
run() may be invoked only by the separately authorized dedicated hosted launcher.
It reuses the hash-admitted capture and evidence supervisor; it is not a smoke runner.
"""
import hashlib
import json
import math
import os
import signal
import time
import types
from pathlib import Path

MIB = 1024 * 1024
MAX_SYNTHETIC_BYTES = 8 * MIB
MAX_RETAINED_FILES = 128
RAW_STAGE_BYTES = MIB
RUN_MAX_SECONDS = 300
MIN_REMAINING_SECONDS = 120
FIRST_LINE = b'{"type":"event","event":{"type":"session_activity_updated"}}\n'
LATE_LINE = b'{"type":"event","event":{"type":"error"}}\n'
LATE_STDERR = b"synthetic inherited-pipe child exit=7\n"


def need(value, reason):
    if not value:
        raise RuntimeError(reason)


def stage_end(deadline, now, allowance):
    """Pure bound: stage and cleanup share the caller's one absolute deadline."""
    need(type(deadline) in (int, float) and math.isfinite(deadline)
         and type(now) in (int, float) and math.isfinite(now)
         and type(allowance) is int and allowance > 5, "stage time types")
    end = min(deadline, now + allowance)
    need(end > now + 5, "insufficient remaining lifecycle stage budget")
    return end


def guard_ok(guard):
    return (isinstance(guard, dict)
            and guard.get("status") == "SUPERVISED_STAGE_COMPLETE"
            and guard.get("owned_cleanup_complete") is True)


def expected_blocked(guard, child_pid):
    """An expected timeout is a passing control, never a passing product stage."""
    return (isinstance(guard, dict) and guard.get("status") == "FAILED_CENSORED"
            and guard.get("owned_cleanup_complete") is True
            and "outer absolute operation deadline" in (guard.get("reason") or "")
            and type(child_pid) is int and child_pid > 1
            and child_pid in guard.get("forced_owned_pids", []))


def lifecycle_status(controls_ok, cleanup_known, retention_complete, package_ok):
    need(all(type(item) is bool for item in
             (controls_ok, cleanup_known, retention_complete, package_ok)), "status flag types")
    return ("LIFECYCLE_CONTROLS_COMPLETE"
            if controls_ok and cleanup_known and retention_complete and package_ok
            else "FAILED_CENSORED")


def _setup(supervisor, work, evidence):
    work, evidence = Path(work), Path(evidence)
    need(work.is_absolute() and evidence.is_absolute()
         and len(str(work).encode()) <= 512 and len(str(evidence).encode()) <= 512
         and not work.is_relative_to(evidence) and not evidence.is_relative_to(work),
         "fresh absolute disjoint lifecycle roots")
    need(not work.exists() and not evidence.exists()
         and work.parent.is_dir() and evidence.parent.is_dir(), "lifecycle roots already exist")
    work.mkdir(mode=0o700)
    evidence.mkdir(mode=0o700)
    raw = work / "raw"
    raw.mkdir(mode=0o700)
    for name in ("positive", "blocked", "pipe"):
        (raw / name).mkdir(mode=0o700)
    supervisor.quota_scan(raw, {"other": 1})
    return {"created": True, "scope": "SYNTHETIC_LIFECYCLE_ONLY"}


def _positive(supervisor, raw):
    receipt = supervisor.write_json(Path(raw) / "positive" / "raw.json",
        {"kind": "synthetic-positive", "payload": "preserve this exact control evidence"}, 4096)
    return {"kind": "positive-return", "raw_receipt": receipt}


def _read_pipe(fd, limit, deadline):
    os.set_blocking(fd, False)
    data = bytearray()
    while True:
        need(time.monotonic() < deadline, "synthetic pipe deadline")
        try:
            chunk = os.read(fd, limit + 1 - len(data))
        except BlockingIOError:
            time.sleep(0.005)
            continue
        if not chunk:
            return bytes(data)
        data.extend(chunk)
        need(len(data) <= limit, "synthetic pipe cap")
        if data.endswith(b"\n"):
            return bytes(data)


def _wait_child(pid, deadline):
    while True:
        need(time.monotonic() < deadline, "synthetic child wait deadline")
        done, status = os.waitpid(pid, os.WNOHANG)
        if done:
            return status
        time.sleep(0.005)


def _blocked(capture, supervisor, raw, deadline):
    """The worker and a separate-session child both wait for the real outer deadline."""
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
    readfd, writefd = os.pipe()
    child = os.fork()
    if child == 0:
        try:
            os.close(readfd)
            os.setsid()
            signal.signal(signal.SIGTERM, signal.SIG_IGN)
            ident = capture.process_identity(os.getpid())
            supervisor.write_json(Path(raw) / "blocked" / "child.json",
                dict(ident, kind="synthetic-blocked-descendant",
                     sid=os.getsid(0), pgid=os.getpgrp()), 4096)
            os.write(writefd, b"READY\n")
            os.close(writefd)
            while True:
                signal.pause()
        except BaseException:
            os._exit(70)
    os.close(writefd)
    try:
        need(_read_pipe(readfd, 64, deadline) == b"READY\n", "blocked child not ready")
    finally:
        os.close(readfd)
    ident = capture.process_identity(os.getpid())
    supervisor.write_json(Path(raw) / "blocked" / "worker.json",
        dict(ident, kind="synthetic-blocked-worker", child=child,
             sid=os.getsid(0), pgid=os.getpgrp()), 4096)
    while True:
        signal.pause()


def _blocked_trial(capture, supervisor, raw, deadline):
    """No inner monitor deadline race; the outer monitored worker stays live longer."""
    return supervisor._hard(capture, _blocked,
                            (capture, supervisor, raw, deadline - 5), deadline)


def _small_json(supervisor, root, relative):
    fd = supervisor._open_source(root, relative)
    try:
        before = os.fstat(fd)
        need(before.st_size <= 4096, "synthetic marker cap")
        raw = os.read(fd, 4097)
        need(len(raw) == before.st_size and supervisor.stamp(before)
             == supervisor.stamp(os.fstat(fd)), "synthetic marker changed")
        return supervisor._strict_json(raw)
    finally:
        os.close(fd)


def _verify_blocked(capture, supervisor, raw, guard):
    child = _small_json(supervisor, raw, "blocked/child.json")
    worker = _small_json(supervisor, raw, "blocked/worker.json")
    need(child["kind"] == "synthetic-blocked-descendant"
         and worker["kind"] == "synthetic-blocked-worker"
         and child["pid"] == worker["child"] and child["ppid"] == worker["pid"]
         and child["pid"] != worker["pid"]
         and child["sid"] == child["pgid"] == child["pid"]
         and worker["sid"] == worker["pgid"] == worker["pid"],
         "separate-group descendant witness mismatch")
    need(expected_blocked(guard, child["pid"]), "blocked deadline/cleanup control failed")
    try:
        current = capture.process_identity(child["pid"])
    except FileNotFoundError:
        original_live = False
    else:
        original_live = current["start_ticks"] == child["start_ticks"]
    need(not original_live, "original synthetic descendant still live")
    return {"control": "blocked_worker_separate_group_descendant", "observed": True,
            "worker_identity": worker, "descendant_identity": child,
            "original_descendant_identity_no_longer_live": True,
            "pid_reuse_forced": False, "outer_cleanup_complete": True}


def _late_pipe(capture, supervisor, raw, deadline):
    """A writer exits; its child holds both pipes, then supplies a late error and exit 7."""
    capture.enable_subreaper()
    out_r, out_w = os.pipe()
    err_r, err_w = os.pipe()
    announce_r, announce_w = os.pipe()
    release_r, release_w = os.pipe()
    writer = os.fork()
    if writer == 0:
        try:
            for fd in (out_r, err_r, announce_r, release_w):
                os.close(fd)
            os.write(out_w, FIRST_LINE)
            child = os.fork()
            if child == 0:
                try:
                    os.close(announce_w)
                    os.setsid()
                    need(os.read(release_r, 1) == b"R", "synthetic release missing")
                    os.close(release_r)
                    time.sleep(0.05)
                    os.write(out_w, LATE_LINE)
                    os.write(err_w, LATE_STDERR)
                    os._exit(7)
                except BaseException:
                    os._exit(71)
            os.close(release_r)
            os.write(announce_w, (str(child) + "\n").encode("ascii"))
            for fd in (announce_w, out_w, err_w):
                os.close(fd)
            os._exit(0)
        except BaseException:
            os._exit(72)
    for fd in (out_w, err_w, announce_w, release_r):
        os.close(fd)
    process = types.SimpleNamespace(stdout=os.fdopen(out_r, "rb", buffering=0),
                                    stderr=os.fdopen(err_r, "rb", buffering=0))
    output = None
    try:
        announced = _read_pipe(announce_r, 64, deadline)
        need(announced.endswith(b"\n") and announced[:-1].isdigit(), "synthetic child identity")
        child = int(announced[:-1])
        output = capture.Output(process, Path(raw) / "pipe")
        state = capture.State({"mode": "resource", "run_id": "synthetic-lifecycle-pipe",
                               "session_id": "11111111-1111-4111-8111-111111111111"})
        writer_status = _wait_child(writer, deadline)
        need(os.WIFEXITED(writer_status) and os.WEXITSTATUS(writer_status) == 0,
             "synthetic writer did not exit cleanly")
        child_identity = capture.process_identity(child)
        need(child_identity["ppid"] == os.getpid(), "inherited-pipe child not adopted")
        while not state.trace:
            need(time.monotonic() < deadline, "initial pipe event deadline")
            output.drain(state)
            time.sleep(0.005)
        need(len(state.trace) == 1, "unexpected initial pipe events")
        os.write(release_w, b"R")
        os.close(release_w)
        release_w = None
        output.close(deadline)
        rejection = None
        try:
            output.drain(state)
        except RuntimeError as error:
            rejection = str(error)
        need(rejection == "unexpected app event: error"
             and len(state.trace) == 2, "late final-drain error not rejected")
        child_status = _wait_child(child, deadline)
        need(os.WIFEXITED(child_status) and os.WEXITSTATUS(child_status) == 7,
             "late child nonzero exit witness missing")
        need(capture.reap_adopted(deadline) == [], "unexpected forced cleanup in late-pipe control")
        expected = {"pipe/stdout.raw": FIRST_LINE + LATE_LINE,
                    "pipe/stderr.raw": LATE_STDERR}
        receipts = {}
        for relative, content in expected.items():
            info = (Path(raw) / relative).lstat()
            need(info.st_size == len(content), "late raw capture size differs")
            digest = supervisor._hash_member(raw, relative, info, deadline)
            need(digest == hashlib.sha256(content).hexdigest(), "late raw capture differs")
            receipts[relative] = {"bytes": len(content), "sha256": digest}
        need(output.total == sum(len(value) for value in expected.values())
             and not output.errors, "late raw capture accounting")
        return {"control": "inherited_pipes_late_error_nonzero_exit", "observed": True,
                "writer_wait_status": writer_status, "child_wait_status": child_status,
                "child_identity": child_identity, "reader_join_complete": True,
                "late_error_rejected": rejection, "raw_capture": receipts}
    finally:
        os.close(announce_r)
        if release_w is not None:
            os.close(release_w)
        for stream in (process.stdout, process.stderr):
            stream.close()


def _record(supervisor, raw, controls, errors, guards, deadline):
    value = {"schema": 1, "mode": "synthetic-lifecycle-only", "controls": controls,
             "errors": errors, "raw_stage_guards": guards,
             "shipping_product_build_replay": "NOT_RUN"}
    supervisor.write_json(Path(raw) / "control-results.json", value, 65536)
    rows, inventory_errors = supervisor.inventory(raw, deadline)
    size = sum(info.st_size for _, info in rows)
    need(not inventory_errors and size <= RAW_STAGE_BYTES and len(rows) <= 64,
         "synthetic source inventory bound")
    return {"raw_source_bytes": size, "raw_source_files": len(rows)}


def run(capture, supervisor, work, evidence, deadline):
    """Five-argument lifecycle-only callable. Dedicated single-thread owner required.
    Caller authenticates this source plus capture/supervisor and independently enforces
    the 300 s wall. No Core, fixture model, build, replay, test runner or CI is invoked.
    """
    started = time.monotonic()
    need(type(deadline) in (int, float) and math.isfinite(deadline)
         and started + MIN_REMAINING_SECONDS <= deadline <= started + RUN_MAX_SECONDS,
         "lifecycle absolute deadline must leave 120..300 seconds")
    work, evidence = Path(work), Path(evidence)
    controls, errors, guards = [], [], []
    created, cleanup_known = False, True
    raw = work / "raw"
    source_inventory = {"raw_source_bytes": None, "raw_source_files": None}
    retained = package = None

    def hard(name, operation, args, end, monitor=True):
        nonlocal cleanup_known
        try:
            guard = supervisor._hard(capture, operation, args, end,
                                     root=raw if monitor else None,
                                     caps={"other": 1} if monitor else None)
        except BaseException:
            cleanup_known = False  # No returned ownership receipt, no dependent I/O.
            raise
        guards.append({"name": name, "guard": guard})
        cleanup_known = cleanup_known and guard.get("owned_cleanup_complete") is True
        return guard

    def guarded(name, operation, args, allowance, monitor=True):
        end = stage_end(deadline, time.monotonic(), allowance)
        return hard(name, operation, args, end, monitor)

    try:
        guard = guarded("fresh-roots", _setup, (supervisor, work, evidence), 10, False)
        cleanup_known = cleanup_known and guard.get("owned_cleanup_complete") is True
        need(guard_ok(guard) and guard["value"] == {
            "created": True, "scope": "SYNTHETIC_LIFECYCLE_ONLY"}, "lifecycle setup failed")
        created = True

        guard = guarded("positive-return", _positive, (supervisor, raw), 10)
        cleanup_known = cleanup_known and guard.get("owned_cleanup_complete") is True
        need(guard_ok(guard) and guard["value"]["kind"] == "positive-return",
             "positive supervised control failed")
        controls.append({"control": "positive_supervisor_return", "observed": True,
                         "raw_receipt": guard["value"]["raw_receipt"]})

        blocked_outer_end = stage_end(deadline, time.monotonic(), 22)
        # The outer monitor runs until 5 s after the inner absolute deadline.
        # Its independent quota/disk guard cannot race the inner deadline classification.
        guard = hard("blocked-controller", _blocked_trial,
                     (capture, supervisor, raw, blocked_outer_end - 10), blocked_outer_end)
        need(guard_ok(guard), "blocked control outer supervision failed")
        blocked_guard = guard["value"]
        guards.append({"name": "blocked-worker-observation", "guard": blocked_guard})
        cleanup_known = cleanup_known and blocked_guard.get("owned_cleanup_complete") is True
        need(cleanup_known, "blocked control cleanup uncertain")
        checked = guarded("blocked-witness", _verify_blocked,
                          (capture, supervisor, raw, blocked_guard), 10)
        cleanup_known = cleanup_known and checked.get("owned_cleanup_complete") is True
        need(guard_ok(checked), "blocked control witnesses failed")
        controls.append(checked["value"])

        pipe_end = stage_end(deadline, time.monotonic(), 15)
        guard = hard("inherited-pipe", _late_pipe,
                     (capture, supervisor, raw, pipe_end - 5), pipe_end)
        cleanup_known = cleanup_known and guard.get("owned_cleanup_complete") is True
        need(guard_ok(guard), "late-pipe control failed")
        controls.append(guard["value"])
    except BaseException as error:
        errors.append(type(error).__name__ + ": " + str(error)[:2048])

    controls_ok = (not errors and [row.get("control") for row in controls] == [
        "positive_supervisor_return", "blocked_worker_separate_group_descendant",
        "inherited_pipes_late_error_nonzero_exit"]
        and all(row.get("observed") is True for row in controls))
    if created and cleanup_known:
        try:
            end = stage_end(deadline, time.monotonic(), 10)
            guard = hard("raw-control-record", _record,
                         (supervisor, raw, controls, errors, guards, end - 5), end)
            cleanup_known = cleanup_known and guard.get("owned_cleanup_complete") is True
            need(guard_ok(guard), "lifecycle raw control record failed")
            source_inventory = guard["value"]
            ledger = supervisor.new_ledger()
            retain_end = stage_end(deadline, time.monotonic(), 35)
            try:
                retained = supervisor.retain(raw, evidence / "shared", {"other": 48},
                    supervisor.TOTAL - supervisor.FINAL_BYTES, ledger=ledger, capture=capture,
                    deadline=retain_end, bucket="shared", cache_paths=())
            except BaseException:
                cleanup_known = False
                raise
            cleanup_known = cleanup_known and retained["supervision"].get("owned_cleanup_complete") is True
            need(cleanup_known, "lifecycle retention cleanup uncertain")
            status = {"status": "LIFECYCLE_CONTROLS_COMPLETE" if controls_ok else "FAILED_CENSORED",
                      "scope": "SYNTHETIC_LIFECYCLE_ONLY", "controls": controls, "errors": errors,
                      "shipping_product_build_replay": "NOT_RUN", "stages": guards,
                      "performance_claim": None}
            package_end = stage_end(deadline, time.monotonic(), 50)
            try:
                package = supervisor.package(capture, evidence, Path(str(evidence) + ".tar.gz"),
                                             status, ledger, package_end)
            except BaseException:
                cleanup_known = False
                raise
            cleanup_known = cleanup_known and package["supervision"].get("owned_cleanup_complete") is True
        except BaseException as error:
            errors.append("evidence: " + type(error).__name__ + ": " + str(error)[:2048])
    else:
        errors.append("raw preservation/package not attempted: roots or owned cleanup uncertain")

    retention_ok = isinstance(retained, dict) and retained.get("status") == "COMPLETE_PRIMARY_EVIDENCE"
    package_ok = (isinstance(package, dict) and package.get("status") == "PACKAGE_COMPLETE"
                  and guard_ok(package.get("supervision"))
                  and package.get("candidate_feasibility_status") == "FAILED_CENSORED"
                  and type(package.get("compressed_bytes")) is int
                  and type(package.get("uncompressed_bytes_including_result")) is int
                  and type(package.get("all_retained_file_entries_including_package")) is int
                  and package["uncompressed_bytes_including_result"] <= MAX_SYNTHETIC_BYTES
                  and package["all_retained_file_entries_including_package"] <= MAX_RETAINED_FILES
                  and type(source_inventory.get("raw_source_bytes")) is int
                  and source_inventory["raw_source_bytes"]
                      + package["uncompressed_bytes_including_result"]
                      + package["compressed_bytes"] <= MAX_SYNTHETIC_BYTES)
    status = lifecycle_status(controls_ok and not errors, cleanup_known, retention_ok, package_ok)
    return {"schema": 1, "status": status, "scope": "SYNTHETIC_LIFECYCLE_ONLY",
            "controls": controls, "errors": errors, "owned_cleanup_complete": cleanup_known,
            "source_inventory": source_inventory, "retention": retained,
            "evidence_package": package, "seconds": time.monotonic() - started,
            "absolute_deadline": deadline, "raw_evidence_preserved": created,
            "limits": {"wall_seconds": RUN_MAX_SECONDS, "synthetic_bytes": MAX_SYNTHETIC_BYTES,
                       "retained_files": MAX_RETAINED_FILES, "disk_floor_bytes": 2 * 1024**3},
            "shipping_product_build_replay": "NOT_RUN",
            "unestablished": ["real PID reuse", "full disk", "blocked filesystem",
                              "durability under machine loss", "runtime fixture non-start"],
            "performance_claim": None}
