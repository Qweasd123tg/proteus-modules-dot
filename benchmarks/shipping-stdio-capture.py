"""Private shipping stdio capture adapter; not a qualification or benchmark runner.
Caller must authenticate full source/build/seed/config receipts and own its worker.
capture() returns PENDING_CANONICAL_VERIFICATION, never benchmark PASS.
No top-level product execution. Do not import/execute before separate authorization.
"""
import ctypes
import hashlib
import json
import os
import queue
import select
import signal
import socket
import statistics
import struct
import subprocess
import threading
import time
import uuid
from pathlib import Path

TASK = "Run the fixed benchmark probe calls, then finish."
ANSWER = "benchmark complete"
MID = "22222222-2222-4222-8222-222222222221"
PART = "22222222-2222-4222-8222-222222222222"
LINE_LIMIT = 8 * 1024 * 1024
TOTAL_LIMIT = 96 * 1024 * 1024
PLAN_LIMIT = 8 * 1024 * 1024
RECEIPT_LIMIT = 24 * 1024 * 1024
CLEANUP_SECONDS = 15
READY_SECONDS = 30
TURN_SECONDS = 30
HOLD_SECONDS = 5
PLATEAU_NS = 500_000_000
INTERVAL_NS = 5_000_000


def require(value, message):
    if not value:
        raise RuntimeError(message)


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")


def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1048576), b""):
            h.update(block)
    return h.hexdigest()


def uid(value):
    require(isinstance(value, str) and str(uuid.UUID(value)) == value, "invalid UUID")
    return value


def process_identity(pid):
    fields = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()
    return {"pid": pid, "start_ticks": int(fields[19]), "ppid": int(fields[1])}


def descendant(pid, root):
    seen = set()
    while pid > 1 and pid not in seen:
        if pid == root:
            return True
        seen.add(pid)
        pid = process_identity(pid)["ppid"]
    return False


def write_request(process, value, outer_deadline=None):
    data = canonical(value) + b"\n"
    if not hasattr(process, "shipping_input_frames"):
        process.shipping_input_frames = []
    frame = {"type": value.get("type"), "id": value.get("id"),
             "encoded_bytes": len(data), "sha256": hashlib.sha256(data).hexdigest(),
             "written_bytes": 0, "complete": False}
    require(len(process.shipping_input_frames) < 128, "input frame inventory cap")
    process.shipping_input_frames.append(frame)
    require(len(data) <= LINE_LIMIT, "input line limit")
    deadline = time.monotonic() + 1
    if outer_deadline is not None:
        deadline = min(deadline, outer_deadline)
    while data:
        require(time.monotonic() < deadline, "stdin write timeout")
        if select.select([], [process.stdin], [], 0.05)[1]:
            try:
                count = os.write(process.stdin.fileno(), data)
                require(count > 0, "stdin zero-length write")
                frame["written_bytes"] += count
                data = data[count:]
            except BlockingIOError:
                pass
    frame["complete"] = True
    return frame


def kill_group(process):
    try:
        if process.returncode is None:  # unreaped direct child reserves this group identity
            os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass


def enable_subreaper():
    require(hasattr(os, "pidfd_open") and hasattr(signal, "pidfd_send_signal"),
            "Python/Linux pidfd support required")
    libc = ctypes.CDLL(None, use_errno=True)
    require(libc.prctl(36, 1, 0, 0, 0) == 0, "PR_SET_CHILD_SUBREAPER failed")


def reap_adopted(deadline):
    # This dedicated controller creates only one benchmark child at a time.
    # Core workers have separate groups; after their host exits, subreaper
    # adoption gives this controller owned children, not reusable cached PIDs.
    stopped = []
    while True:
        children, vanished_thread = set(), False
        for task in Path("/proc/self/task").iterdir():
            try:
                children.update(int(pid) for pid in (task / "children").read_text().split())
            except FileNotFoundError:
                vanished_thread = True  # rescan instead of claiming cleanup complete
        if not children and not vanished_thread:
            return stopped
        require(time.monotonic() < deadline, "owned descendants did not terminate")
        for pid in children:
            try:
                if os.waitpid(pid, os.WNOHANG)[0]:
                    continue
                fd = os.pidfd_open(pid)
                try:
                    signal.pidfd_send_signal(fd, signal.SIGKILL)
                finally:
                    os.close(fd)
                if pid not in stopped:
                    stopped.append(pid)
                os.waitpid(pid, os.WNOHANG)
            except (ProcessLookupError, ChildProcessError):
                pass
        time.sleep(0.005)


def proc_snapshot(root):
    """Per-PID starttime identity; failed/disappeared reads are not zeros."""
    scan_started_ns = time.monotonic_ns()
    pending, seen, values, missed = [root], set(), [], []
    while pending and len(seen) < 64:
        pid = pending.pop()
        if pid in seen:
            continue
        seen.add(pid)
        try:
            base = Path("/proc") / str(pid)
            stat = (base / "stat").read_text().rsplit(")", 1)[1].split()
            # stat[0] is field 3. CPU ticks include this process, not descendants.
            item = {"pid": pid, "start_ticks": int(stat[19]),
                    "cpu_ticks": int(stat[11]) + int(stat[12]),
                    "scope": "host" if pid == root else "worker"}
            for task in (base / "task").iterdir():
                try:
                    pending.extend(int(p) for p in (task / "children").read_text().split())
                except OSError:
                    missed.append({"pid": pid, "error": "thread_children_unavailable"})
            try:
                fields = {line.split(":")[0]: int(line.split()[1]) * 1024
                          for line in (base / "smaps_rollup").read_text().splitlines()
                          if line.startswith(("Rss:", "Pss:"))}
                item.update(rss_bytes=fields["Rss"], pss_bytes=fields["Pss"])
            except (OSError, KeyError, ValueError) as error:
                item["memory_unavailable"] = type(error).__name__
            # Reject PID reuse during the multi-file read.
            after = (base / "stat").read_text().rsplit(")", 1)[1].split()
            require(int(after[19]) == item["start_ticks"], "PID reused while sampling")
            values.append(item)
        except (OSError, ValueError, RuntimeError) as error:
            missed.append({"pid": pid, "error": type(error).__name__})
    return {"scan_start_ns": scan_started_ns, "scan_end_ns": time.monotonic_ns(),
            "pids": values, "missed": missed,
            "truncated": bool(pending)}



class Output:
    """Continuously drain both pipes. Queue and raw evidence are bounded."""
    def __init__(self, process, root):
        self.messages = queue.Queue(maxsize=128)
        self.errors = []
        self.total = 0
        self.retained = 0
        self.max_line = 0
        self.frames = []
        self.overflow = []
        self.lock = threading.Lock()
        self.threads = []
        for label, stream in (("stdout", process.stdout), ("stderr", process.stderr)):
            thread = threading.Thread(target=self.read, args=(label, stream, root), daemon=True)
            thread.start()
            self.threads.append(thread)

    def read(self, label, stream, root):
        try:
            with (root / (label + ".raw")).open("xb") as out:
                while True:
                    line = stream.readline(LINE_LIMIT + 1)
                    if not line:
                        break
                    observed = time.monotonic_ns()
                    with self.lock:
                        self.total += len(line)
                        self.max_line = max(self.max_line, len(line))
                        available = max(0, TOTAL_LIMIT - self.retained)
                        retained = min(len(line), available)
                        self.retained += retained
                        complete_line = line.endswith(b"\n") and len(line) <= LINE_LIMIT
                        frame = {"stream": label, "observed_chunk_bytes": len(line),
                                 "observed_chunk_sha256": hashlib.sha256(line).hexdigest(),
                                 "retained_chunk_bytes": retained,
                                 "complete_line_observed": complete_line}
                        frame_count_ok = label != "stdout" or len(self.frames) < 16384
                        if label == "stdout" and complete_line and frame_count_ok:
                            self.frames.append({"encoded_bytes": len(line),
                                                "sha256": frame["observed_chunk_sha256"]})
                        if retained != len(line) or len(line) > LINE_LIMIT or not frame_count_ok:
                            self.overflow.append(frame)
                    # Preserve the bounded failure prefix before reporting overflow.
                    out.write(line[:retained])
                    require(retained == len(line) and len(line) <= LINE_LIMIT and frame_count_ok,
                            "output byte/frame budget; explicit failure prefix retained")
                    if label == "stdout":
                        require(line.endswith(b"\n"), "unterminated stdout JSONL")
                        self.messages.put_nowait((observed, json.loads(line)))
                out.flush()
                os.fsync(out.fileno())
        except Exception as error:
            self.errors.append(f"{label}: {type(error).__name__}: {error}")

    def drain(self, state):
        require(not self.errors, "; ".join(self.errors))
        while True:
            try:
                stamp, item = self.messages.get_nowait()
            except queue.Empty:
                return
            state.consume(stamp, item)

    def close(self, deadline):
        for thread in self.threads:
            thread.join(timeout=max(0, deadline - time.monotonic()))
        require(not any(t.is_alive() for t in self.threads), "inherited pipe remains open")
        require(not self.errors, "; ".join(self.errors))


class State:
    def __init__(self, plan):
        self.plan = plan
        self.sent = False
        self.released = plan["mode"] == "latency"
        self.release_before_ns = None
        self.control_requests = {}
        self.control_acks = set()
        self.shutdown_seen = False
        self.initial = None
        self.pending = None
        self.config = False
        self.active_seen = False
        self.last_success = False
        self.turn = None
        self.thread = None
        self.accepted = 0
        self.echoes = 0
        self.finished = None
        self.output = None
        self.turn_output = None
        self.end_ns = None
        self.final_snapshot = None
        self.event_ids = set()
        self.runtime_seq = -1
        self.trace = []

    def identity(self, value):
        require(value["session_id"] == self.plan["session_id"], "session mismatch")
        require(value["thread_id"] == self.thread, "thread mismatch")
        require(value["turn_id"] == self.turn, "turn mismatch")

    def terminal_allowed(self, stamp):
        return (self.released and (self.plan["mode"] == "latency"
                or (self.release_before_ns is not None and stamp >= self.release_before_ns)))

    def control_request(self, process, kind, deadline):
        ident = self.plan["run_id"] + ":" + kind
        require(ident not in self.control_requests, "duplicate control request")
        # Before-write timestamp is conservative: it does not claim acknowledgment.
        before_write = time.monotonic_ns()
        request = {"type": kind, "id": ident}
        if kind == "cancel":
            request["target_id"] = self.plan["run_id"]
        write_request(process, request, deadline)
        self.control_requests[ident] = before_write

    def consume(self, stamp, row):
        self.trace.append({"observed_ns": stamp, "type": row.get("type")})
        require(len(self.trace) <= 16384, "event count limit")
        if row["type"] == "response":
            require(row["ok"] is True and row.get("error") is None, "request failed")
            if row["id"] == self.plan["run_id"] + ":config":
                require(not self.config and not self.sent, "duplicate/late config")
                require(hashlib.sha256(canonical(row["output"])).hexdigest()
                        == self.plan["config_summary_sha256"], "config summary mismatch")
                self.config = True
            elif row["id"] == self.plan["run_id"]:
                require(self.sent and self.terminal_allowed(stamp) and self.output is None,
                        "premature or duplicate send response")
                require(isinstance(row["output"], dict)
                        and row["output"].get("queued") is not True, "queued send")
                self.output, self.end_ns = row["output"], stamp
            else:
                ident = row["id"]
                require(ident in self.control_requests and ident not in self.control_acks
                        and stamp >= self.control_requests[ident]
                        and row.get("output") is None, "unsolicited/duplicate control response")
                self.control_acks.add(ident)
            return
        require(row["type"] == "event", "unknown output type")
        event = row["event"]
        kind = event["type"]
        if kind == "pending_requests_updated":
            value = event["snapshot"]
            require(value["session_id"] == self.plan["session_id"], "pending session")
            uid(value["stream_id"])
            require(not value["approvals"] and not value["user_inputs"]
                    and not value["queued_user_messages"], "pending work exists")
            if self.pending is not None:
                require(value["stream_id"] == self.pending["stream_id"]
                        and value["seq"] >= self.pending["seq"], "pending stream changed")
            self.pending = value
        elif kind == "session_snapshot":
            value = event["snapshot"]
            require(value["session_id"] == self.plan["session_id"], "snapshot session")
            uid(value["stream_id"])
            if self.initial is None:
                require(not self.sent and value["execution"]["active"] is None, "initial busy")
                require(value["transcript"] == self.plan["seed_transcript"]
                        and value["history"] == self.plan["seed_history_cursor"],
                        "seed display witness changed")
                # An idle resumed view has no observed turn yet; do not invent one.
                if value["root_thread_id"] is not None:
                    uid(value["root_thread_id"])
                self.initial = value
            else:
                last = value["execution"]["last"]
                require(self.sent and self.terminal_allowed(stamp) and value["execution"]["active"] is None
                        and last["run_id"] == self.plan["run_id"]
                        and last["status"] == "success" and last["error"] is None,
                        "unexpected mid-turn snapshot")
                require(value["stream_id"] == self.initial["stream_id"]
                        and value["seq"] > self.initial["seq"], "snapshot stream changed")
                require(self.final_snapshot is None, "extra final snapshot")
                self.final_snapshot = value
        elif kind == "execution_updated":
            active, last = event["execution"]["active"], event["execution"]["last"]
            if active is not None:
                require(self.sent and active["run_id"] == self.plan["run_id"]
                        and active["status"] == "running" and active["error"] is None,
                        "foreign/canceled active run")
                require(active["options"] == self.plan["run_options"], "run options changed")
                self.active_seen = True
            elif self.sent:
                require(self.terminal_allowed(stamp) and last is not None
                        and last["run_id"] == self.plan["run_id"]
                        and last["status"] == "success" and last["error"] is None,
                        "run did not settle successfully")
                self.last_success = True
            else:
                require(self.initial is not None and canonical(event["execution"]) ==
                        canonical(self.initial["execution"]), "foreign idle execution state")
        elif kind == "runtime":
            value = event["envelope"]
            require(value["schema_version"] == 2, "runtime schema")
            ident = uid(value["event_id"])
            require(ident not in self.event_ids and value["seq"] > self.runtime_seq,
                    "duplicate/unordered runtime event")
            require(isinstance(value["timestamp_ms"], int), "event timestamp")
            self.event_ids.add(ident)
            self.runtime_seq = value["seq"]
            body = value["event"]
            require(isinstance(body, dict) and len(body) == 1, "runtime enum shape")
            name, payload = next(iter(body.items()))
            if name == "TurnStarted":
                require(self.sent and self.turn is None, "extra root turn")
                self.turn = uid(payload["turn_id"])
                self.thread = uid(payload["thread_id"])
                require(self.initial is not None
                        and (self.initial["root_thread_id"] is None
                             or self.thread == self.initial["root_thread_id"]),
                        "turn differs from authenticated measured startup thread")
                self.identity(payload)
                self.identity(value)
            elif name == "AssistantMessageCompleted":
                require(self.sent and self.turn is not None, "completion before turn")
                self.identity(value)
                require(payload == {"message_id": MID, "phase": "final_answer", "text": ANSWER},
                        "wrong accepted message")
                self.accepted += 1
                require(self.accepted == 1, "extra accepted message")
            elif name == "TurnFinished":
                require(self.terminal_allowed(stamp) and self.finished is None, "premature terminal")
                self.identity(value)
                self.finished = payload["output"]
            elif name == "Error":
                raise RuntimeError("runtime error: " + payload["message"])
            elif value["turn_id"] is not None:
                require(self.sent, "turn event before measured send")
                self.identity(value)
        elif kind == "user_message_submitted":
            require(self.sent and event["text"] == TASK and not event["images"], "input echo")
            self.echoes += 1
            require(self.echoes == 1, "extra input echo")
        elif kind == "turn_output":
            require(self.sent and self.terminal_allowed(stamp) and self.turn_output is None,
                    "premature/duplicate turn output")
            self.turn_output = event["output"]
        elif kind in ("event_stream_lagged", "error", "approval_requested",
                      "user_input_requested", "modules_reloaded"):
            raise RuntimeError("unexpected app event: " + kind)
        elif kind == "profile_reload_status":
            require(event["error"] is None, "profile reload failure")
        elif kind == "shutdown":
            ident = self.plan["run_id"] + ":shutdown"
            require(ident in self.control_requests and not self.shutdown_seen
                    and stamp >= self.control_requests[ident], "unsolicited/duplicate shutdown event")
            self.shutdown_seen = True
        elif kind not in ("session_activity_updated", "session_catalog_updated"):
            raise RuntimeError("unreviewed app event: " + kind)

    def ready(self):
        return self.initial is not None and self.pending is not None and self.config

    def settled(self):
        return (self.output is not None and self.finished is not None
                and self.turn_output is not None and self.last_success
                and self.final_snapshot is not None)

    def verify_transport(self):
        require(self.active_seen and self.turn is not None and self.accepted == 1
                and self.echoes == 1 and self.settled(), "incomplete lifecycle")
        require(self.output == self.finished == self.turn_output, "terminal witnesses differ")
        require(self.output["text"] == ANSWER, "final text")
        self.identity(self.output["metadata"])
        require(self.final_snapshot["root_thread_id"] == self.thread,
                "final root thread")


def plateau_summary(samples, root_identity, begin, end):
    rows = []
    for sample in samples:
        if begin <= sample["scan_start_ns"] <= sample["scan_end_ns"] <= end:
            host = [p for p in sample["pids"] if p["pid"] == root_identity["pid"]
                    and p["start_ticks"] == root_identity["start_ticks"]]
            if len(host) == 1 and "rss_bytes" in host[0] and "pss_bytes" in host[0]:
                rows.append((sample, host[0]))
    require(len(rows) >= 10, "insufficient contained host scans")
    starts = [r[0]["scan_start_ns"] for r in rows]
    require(starts[-1] - starts[0] >= 250_000_000, "insufficient plateau span")
    boundaries = [begin] + starts + [end]
    require(max(b-a for a, b in zip(boundaries, boundaries[1:])) <= 100_000_000,
            "plateau coverage gap")
    return {"statistical_unit": "one fresh process", "valid_scans": len(rows),
            "median_rss_bytes": statistics.median(r[1]["rss_bytes"] for r in rows),
            "median_pss_bytes": statistics.median(r[1]["pss_bytes"] for r in rows),
            "sampled_rss_max": max(r[1]["rss_bytes"] for r in rows),
            "sampled_pss_max": max(r[1]["pss_bytes"] for r in rows),
            "scan_duty_ns": sum(r[0]["scan_end_ns"] - r[0]["scan_start_ns"] for r in rows),
            "plateau_ns": end - begin, "not_exact_peak": True}


def capture(plan, destination):
    """One sample only, inside a dedicated wrapper-owned subprocess/subreaper.
    No build/seed/replay commands or arbitrary callback execution are accepted.
    The wrapper must bind final canonical verification before pair acceptance.
    """
    require(plan["schema"] == "authenticated-shipping-sample-v1", "plan schema")
    require(plan["mode"] in ("latency", "resource"), "pass mode")
    require(plan["payload_bytes"] in (4096, 1048576), "payload size")
    require(plan["qualification_status"] == "EXACT_FINAL_COMPOSITION_PASS"
            and plan["root_authorization_receipt_sha256"], "execution hold")
    require(plan["max_encoded_witness_bytes"] <= LINE_LIMIT
            and plan["wire_bounds_receipt_sha256"], "encoded bound not sealed")
    require("LD_PRELOAD" not in plan["env"], "allocator instrumentation forbidden")
    uid(plan["session_id"])
    plan_bytes = canonical(plan) + b"\n"
    require(len(plan_bytes) <= PLAN_LIMIT, "plan evidence budget")
    root = Path(destination).resolve()
    root.mkdir(mode=0o700, parents=False, exist_ok=False)
    with (root / "plan.json").open("xb") as out:
        out.write(plan_bytes)
    receipt = {"status": "ATTEMPTED", "plan_sha256": hashlib.sha256(plan_bytes).hexdigest(),
               "stage": "admission", "run_id": plan["run_id"],
               "deadlines_seconds": {"ready": READY_SECONDS, "turn": TURN_SECONDS,
                                     "hold": HOLD_SECONDS, "cleanup": CLEANUP_SECONDS}}
    process = output = listener = channel = None
    state = State(plan)
    samples = []
    cleanup_errors = []
    cleanup_deadline = None
    try:
        inventory = {str(Path(item["path"]).resolve()): item["sha256"]
                     for item in plan["input_files"]}
        require(len(inventory) == len(plan["input_files"]), "duplicate input path")
        require(str(Path(plan["config"]).resolve()) in inventory, "config missing from inventory")
        require(not Path(plan["config"]).resolve().is_relative_to(root), "config/output overlap")
        for item in plan["input_files"]:
            require(sha(item["path"]) == item["sha256"], "input hash mismatch")
        require(sha(plan["binary"]) == plan["binary_sha256"], "shipping binary hash")
        profile = json.loads(Path(plan["config"]).read_bytes())
        fixture = profile["module_config"]["model"]["release-probe"]
        require(fixture["mode"] == plan["mode"] and fixture["phase"] == "measure"
                and fixture["nonce"] == plan["nonce"]
                and fixture["payload_bytes"] == plan["payload_bytes"], "fixture/profile mismatch")
        if plan["mode"] == "resource":
            require(fixture["hold_socket"] == str(root / "hold.sock"), "socket ownership")
            listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            listener.bind(fixture["hold_socket"])
            os.chmod(fixture["hold_socket"], 0o600)
            listener.listen(1)
            listener.setblocking(False)
        else:
            require(fixture["hold_socket"] is None, "latency control channel forbidden")
        enable_subreaper()
        command = [plan["binary"], "--config", plan["config"], "--cwd", plan["workspace"],
                   "--resume-session", plan["session_dir"], "server", "stdio"]
        receipt["stage"] = "startup"
        process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE, env=plan["env"], start_new_session=True)
        output = Output(process, root)
        os.set_blocking(process.stdin.fileno(), False)
        identity = process_identity(process.pid)
        require(sha(f"/proc/{process.pid}/exe") == plan["binary_sha256"], "loaded executable")
        receipt["host_identity"] = identity
        write_request(process, {"type": "config_summary", "id": plan["run_id"] + ":config"})
        deadline = time.monotonic() + READY_SECONDS
        while not state.ready():
            require(time.monotonic() < deadline and process.poll() is None, "startup timeout/exit")
            output.drain(state)
            time.sleep(0.001)
        require(state.initial["stream_id"] == state.pending["stream_id"], "live stream mismatch")
        if plan["mode"] == "resource":
            receipt["pre_turn"] = proc_snapshot(process.pid)
        receipt["stage"] = "turn"
        state.sent = True
        start_ns = time.monotonic_ns()
        receipt["send_before_write_ns"] = start_ns
        write_request(process, {"type": "send", "id": plan["run_id"], "text": TASK})
        receipt["send_flushed_ns"] = time.monotonic_ns()
        deadline = time.monotonic() + TURN_SECONDS
        hold_deadline = time.monotonic() + HOLD_SECONDS
        packet = None
        control = bytearray()
        plateau_begin = plateau_end = next_scan = None
        while not state.settled():
            require(time.monotonic() < deadline and process.poll() is None, "turn timeout/exit")
            output.drain(state)
            if plan["mode"] == "resource" and not state.released:
                require(time.monotonic() < hold_deadline, "hold checkpoint timeout")
                if channel is None:
                    try:
                        channel, _ = listener.accept()
                        channel.setblocking(False)
                        peer, user, _ = struct.unpack("3i", channel.getsockopt(
                            socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
                        require(user == os.getuid() and descendant(peer, process.pid), "foreign provider")
                        receipt["provider_identity"] = process_identity(peer)
                    except BlockingIOError:
                        pass
                if channel is not None and packet is None:
                    try:
                        data = channel.recv(4097 - len(control))
                        require(data and len(control) + len(data) <= 4096, "hold frame/EOF")
                        control.extend(data)
                        if b"\n" in control:
                            require(control.endswith(b"\n") and control.count(b"\n") == 1,
                                    "multiple hold records")
                            packet = json.loads(control)
                            require(set(packet) == {"kind", "nonce", "invocation_id", "session_id",
                                "thread_id", "turn_id", "message_id", "part_id", "request_sha256"},
                                "hold fields")
                            require(packet["kind"] == "hold_ready" and packet["nonce"] == plan["nonce"]
                                    and packet["message_id"] == MID and packet["part_id"] == PART,
                                    "hold identity")
                            digest, invocation = packet["request_sha256"], packet["invocation_id"]
                            require(isinstance(digest, str) and len(digest) == 64
                                    and all(c in "0123456789abcdef" for c in digest),
                                    "request digest shape")
                            require(isinstance(invocation, str), "invocation ID type")
                            parts = invocation.split(":")
                            require(len(parts) == 3 and parts[0] == "h"
                                    and all(p.isascii() and p.isdecimal() and str(int(p)) == p
                                            for p in parts[1:])
                                    and int(parts[2]) > 0, "invocation ID shape")
                            receipt["hold_ready"] = packet
                    except BlockingIOError:
                        pass
                if packet is not None and state.accepted == 1 and state.active_seen:
                    state.identity(packet)
                    require(process_identity(receipt["provider_identity"]["pid"])["start_ticks"]
                            == receipt["provider_identity"]["start_ticks"], "provider PID reused")
                    now = time.monotonic_ns()
                    if plateau_begin is None:
                        plateau_begin, plateau_end, next_scan = now, now + PLATEAU_NS, now
                    if now >= plateau_end:
                        receipt["plateau"] = plateau_summary(samples, identity, plateau_begin, plateau_end)
                        release = canonical({"kind": "release", "nonce": plan["nonce"]}) + b"\n"
                        output.drain(state)
                        state.release_before_ns = time.monotonic_ns()
                        receipt["release_before_write_ns"] = state.release_before_ns
                        channel.settimeout(1)
                        channel.sendall(release)
                        state.released = True
                        receipt["release_flushed_ns"] = time.monotonic_ns()
                    elif now >= next_scan:
                        sample = proc_snapshot(process.pid)
                        samples.append(sample)
                        require(len(samples) <= 128, "resource scan count budget")
                        # No burst catch-up if smaps reads overrun the target interval.
                        next_scan = max(now + INTERVAL_NS, time.monotonic_ns() + 1)
            time.sleep(0.001)
        receipt["stage"] = "transport_verification"
        state.verify_transport()
        require(process_identity(process.pid)["start_ticks"] == identity["start_ticks"], "host PID reused")
        receipt["latency_ns"] = state.end_ns - start_ns if plan["mode"] == "latency" else None
        receipt["resource_pass_is_not_latency"] = plan["mode"] == "resource"
        receipt["turn_id"] = state.turn
        receipt["thread_id"] = state.thread
        # Full output/snapshot remain in stdout.raw; do not duplicate MiB payloads in receipt.
        receipt["output_sha256"] = hashlib.sha256(canonical(state.output)).hexdigest()
        receipt["final_snapshot_sha256"] = hashlib.sha256(canonical(state.final_snapshot)).hexdigest()
        receipt["stage"] = "shutdown"
        cleanup_deadline = time.monotonic() + CLEANUP_SECONDS
        receipt["cleanup_started_ns"] = time.monotonic_ns()
        state.control_request(process, "shutdown", cleanup_deadline)
        process.stdin.close()
        require(process.wait(timeout=min(5, max(0, cleanup_deadline - time.monotonic()))) == 0,
                "nonzero shipping exit")
        # Reader joining and final lifecycle checks occur after descendant cleanup in finally.
        receipt["status"] = "TRANSPORT_PENDING_FINAL_DRAIN"
    except Exception as error:
        receipt["status"] = "FAILED_CENSORED"
        receipt["error"] = f"{type(error).__name__}: {error}"[:2048]
        receipt["failed_at_ns"] = time.monotonic_ns()
        receipt["latency_ns"] = None
    finally:
        if cleanup_deadline is None:
            cleanup_deadline = time.monotonic() + CLEANUP_SECONDS
            receipt["cleanup_started_ns"] = time.monotonic_ns()
        if process is not None:
            if process.poll() is None:
                # Best effort release/cancel within the same global deadline.
                if channel is not None and not state.released:
                    try:
                        remaining = cleanup_deadline - time.monotonic()
                        require(remaining > 0, "cleanup deadline before release")
                        channel.settimeout(min(0.2, remaining))
                        channel.sendall(canonical({"kind": "release", "nonce": plan["nonce"]}) + b"\n")
                    except Exception as error:
                        cleanup_errors.append("release: " + str(error)[:1024])
                try:
                    if plan["run_id"] + ":cancel" not in state.control_requests:
                        state.control_request(process, "cancel", cleanup_deadline)
                    if plan["run_id"] + ":shutdown" not in state.control_requests:
                        state.control_request(process, "shutdown", cleanup_deadline)
                    process.wait(timeout=min(2, max(0, cleanup_deadline - time.monotonic())))
                except Exception as error:
                    cleanup_errors.append("graceful stop: " + str(error)[:1024])
                    kill_group(process)
                    try:
                        process.wait(timeout=min(2, max(0, cleanup_deadline - time.monotonic())))
                    except Exception as error:
                        cleanup_errors.append("kill wait: " + str(error)[:1024])
            try:
                receipt["adopted_workers_stopped"] = reap_adopted(cleanup_deadline)
                if receipt["adopted_workers_stopped"]:
                    cleanup_errors.append("unexpected owned descendants required forced termination")
            except Exception as error:
                cleanup_errors.append("adopted workers: " + str(error)[:1024])
            if output is not None:
                try:
                    # No reader can enqueue another row after this successful join.
                    output.close(cleanup_deadline)
                    output.drain(state)
                    if receipt["status"] == "TRANSPORT_PENDING_FINAL_DRAIN":
                        state.verify_transport()
                        require(state.shutdown_seen, "missing shutdown event")
                        require(state.control_acks == set(state.control_requests),
                                "missing control acknowledgment")
                        for item in plan["input_files"]:
                            require(sha(item["path"]) == item["sha256"], "input changed during sample")
                        receipt["status"] = "PENDING_CANONICAL_VERIFICATION"
                except Exception as error:
                    cleanup_errors.append("final drain/verification: " + str(error)[:1024])
        for stream in (channel, listener):
            if stream is not None:
                stream.close()
        receipt["cleanup_finished_ns"] = time.monotonic_ns()
        if time.monotonic() > cleanup_deadline:
            cleanup_errors.append("global cleanup deadline exceeded")
        if cleanup_errors or receipt["status"] == "TRANSPORT_PENDING_FINAL_DRAIN":
            receipt["status"] = "FAILED_CENSORED"
            receipt["cleanup_errors"] = cleanup_errors
            receipt["latency_ns"] = None
        if output is not None:
            receipt["raw_capture"] = {"observed_bytes": output.total,
                                      "retained_bytes": output.retained,
                                      "max_line_bytes": output.max_line,
                                      "stdout_frames": output.frames,
                                      "overflow_chunks": output.overflow,
                                      "reader_errors": output.errors}
        receipt["input_frames"] = getattr(process, "shipping_input_frames", [])
        receipt["initial_root_thread_id"] = (state.initial["root_thread_id"]
                                             if state.initial is not None else None)
        receipt["samples"] = samples
        receipt["event_trace"] = state.trace
        receipt["finished_at_ns"] = time.monotonic_ns()
        encoded = canonical(receipt) + b"\n"
        # Bounded failure evidence is never silently turned into a successful receipt.
        # Retain the prefix and complete-record hash if a pathological receipt exceeds its cap.
        if len(encoded) > RECEIPT_LIMIT:
            with (root / "attempt.overflow-prefix.raw").open("xb") as out:
                out.write(encoded[:RECEIPT_LIMIT - 4096])
            receipt = {"status": "FAILED_CENSORED", "stage": "receipt_budget",
                       "run_id": plan["run_id"], "latency_ns": None,
                       "complete_receipt_bytes": len(encoded),
                       "complete_receipt_sha256": hashlib.sha256(encoded).hexdigest(),
                       "evidence_truncated": True, "raw_stdout_stderr_and_plan_retained": True,
                       "reason": "Receipt cap exceeded; comparison is invalid, never a usable sample."}
            encoded = canonical(receipt) + b"\n"
        with (root / "attempt.json").open("xb") as out:
            out.write(encoded)
            out.flush()
            os.fsync(out.fileno())
    return receipt
