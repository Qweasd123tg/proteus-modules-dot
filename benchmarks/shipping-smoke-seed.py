"""Private ordinary-shipping seed/readiness transport, source-only draft.
All launches must be inside the separately owned hard-supervised worker.
"""
import json
import os
import subprocess
import time
from pathlib import Path


class SeedState:
    def __init__(self, capture, semantics, run_id, each):
        self.c, self.s, self.base, self.each = capture, semantics, run_id, each
        self.session = self.stream = self.thread = None
        self.snapshot = self.pending = self.config = None
        self.turns, self.event_ids = [], set()
        self.seq, self.ordinal, self.active = -1, -1, False
        self.current = None
        self.controls, self.acks = {}, set()
        self.shutdown = False

    def begin(self, ordinal):
        self.c.require(not self.active and ordinal == len(self.turns), "seed send order")
        self.ordinal, self.active = ordinal, True
        self.current = {"run_id": self.base + ":" + str(ordinal), "turn_id": None,
                        "thread_id": None, "output": None, "finished": None,
                        "turn_output": None, "snapshot": None, "settled": False,
                        "accepted": 0, "echoes": 0, "running": False}

    def identity(self, value):
        self.c.require(value["session_id"] == self.session
                       and value["thread_id"] == self.current["thread_id"]
                       and value["turn_id"] == self.current["turn_id"], "seed lineage")

    def consume(self, stamp, row):
        need = self.c.require
        if row["type"] == "response":
            need(row["ok"] is True and row.get("error") is None, "seed response error")
            if row["id"] == self.base + ":config":
                need(self.config is None and not self.active, "duplicate config")
                self.config = row["output"]
            elif row["id"] in self.controls:
                need(row["id"] not in self.acks and stamp >= self.controls[row["id"]]
                     and row.get("output") is None, "control acknowledgment")
                self.acks.add(row["id"])
            else:
                need(self.active and row["id"] == self.current["run_id"]
                     and self.current["output"] is None
                     and isinstance(row["output"], dict)
                     and row["output"].get("queued") is not True, "seed unsolicited/queued response")
                self.current["output"] = row["output"]
            return
        need(row["type"] == "event", "seed outer type")
        event, kind = row["event"], row["event"]["type"]
        if kind == "session_snapshot":
            snap = event["snapshot"]
            if self.session is None:
                self.session = self.c.uid(snap["session_id"])
                self.stream = self.c.uid(snap["stream_id"])
                need(snap["execution"]["active"] is None, "initial busy session")
            need(snap["session_id"] == self.session and snap["stream_id"] == self.stream,
                 "snapshot identity")
            if self.active:
                last = snap["execution"]["last"]
                need(snap["execution"]["active"] is None and last is not None
                     and last["run_id"] == self.current["run_id"] and last["status"] == "success"
                     and last["error"] is None and self.current["snapshot"] is None,
                     "unexpected seed mid-turn/duplicate snapshot")
                self.current["snapshot"] = snap
            else:
                need(self.snapshot is None, "unexpected idle snapshot")
            self.snapshot = snap
        elif kind == "pending_requests_updated":
            snap = event["snapshot"]
            need(not snap["approvals"] and not snap["user_inputs"]
                 and not snap["queued_user_messages"], "seed pending work")
            if self.session is not None:
                need(snap["session_id"] == self.session and snap["stream_id"] == self.stream,
                     "pending identity")
            self.pending = snap
        elif kind == "runtime":
            env = event["envelope"]
            need(env["schema_version"] == 2 and env["event_id"] not in self.event_ids
                 and env["seq"] > self.seq, "runtime sequence")
            self.c.uid(env["event_id"])
            self.event_ids.add(env["event_id"])
            self.seq = env["seq"]
            body = env["event"]
            need(isinstance(body, dict) and len(body) == 1, "runtime enum")
            name, value = next(iter(body.items()))
            if name == "TurnStarted":
                need(self.active and self.current["turn_id"] is None, "extra turn")
                self.current["turn_id"] = self.c.uid(value["turn_id"])
                self.current["thread_id"] = self.c.uid(value["thread_id"])
                need(self.thread is None or self.thread == value["thread_id"], "thread changed")
                self.thread = value["thread_id"]
                self.identity(value)
                self.identity(env)
            elif name == "AssistantMessageCompleted":
                need(self.active and self.current["turn_id"] is not None, "early assistant")
                self.identity(env)
                expected = self.s.assistant(self.ordinal)
                need(value == {"message_id": expected["id"], "phase": "final_answer",
                               "text": "seed accepted"}, "seed accepted message")
                self.current["accepted"] += 1
                need(self.current["accepted"] == 1, "duplicate completion")
            elif name == "TurnFinished":
                need(self.active and self.current["finished"] is None, "duplicate finish")
                self.identity(env)
                self.current["finished"] = value["output"]
            elif name == "Error":
                raise RuntimeError("seed runtime error")
            elif env["turn_id"] is not None:
                need(self.active, "late runtime turn event")
                self.identity(env)
        elif kind == "execution_updated":
            active, last = event["execution"]["active"], event["execution"]["last"]
            if active is not None:
                need(self.active and active["run_id"] == self.current["run_id"]
                     and active["status"] == "running" and active["error"] is None
                     and active["options"] == {"intent": None, "permission_mode": "normal"},
                     "seed active execution")
                self.current["running"] = True
            elif self.active:
                need(last is not None and last["run_id"] == self.current["run_id"]
                     and last["status"] == "success" and last["error"] is None,
                     "seed settlement")
                self.current["settled"] = True
            else:
                need(self.snapshot is not None and self.s.same(event["execution"],
                     self.snapshot["execution"]), "foreign/late idle execution state")
        elif kind == "user_message_submitted":
            need(self.active and event["text"] == "A" * self.each and not event["images"],
                 "seed input echo")
            self.current["echoes"] += 1
            need(self.current["echoes"] == 1, "duplicate input echo")
        elif kind == "turn_output":
            need(self.active and self.current["turn_output"] is None, "duplicate turn output")
            self.current["turn_output"] = event["output"]
        elif kind == "profile_reload_status":
            need(event["error"] is None, "profile error")
        elif kind == "shutdown":
            ident = self.base + ":shutdown"
            need(ident in self.controls and stamp >= self.controls[ident]
                 and not self.shutdown, "unsolicited shutdown")
            self.shutdown = True
        else:
            need(kind in ("session_activity_updated", "session_catalog_updated"),
                 "unreviewed seed event: " + kind)

    def ready(self):
        return self.snapshot is not None and self.pending is not None and self.config is not None

    def complete(self):
        c = self.current
        return (c is not None and c["output"] is not None and c["finished"] is not None
                and c["turn_output"] is not None and c["snapshot"] is not None and c["settled"])

    def finish(self):
        c = self.current
        self.c.require(self.complete() and c["running"] and c["accepted"] == c["echoes"] == 1,
                       "incomplete seed lifecycle")
        self.c.require(c["output"] == c["finished"] == c["turn_output"]
                       and c["output"]["text"] == "seed accepted", "terminal divergence")
        self.identity(c["output"]["metadata"])
        self.turns.append({**{key: c[key] for key in ("run_id", "turn_id", "thread_id", "output")},
                           "config_identity": self.s.config_identity(self.config)})
        self.active = False


def serve(capture, semantics, spec, destination, inspect_only=False):
    root = Path(destination)
    root.mkdir(mode=0o700, parents=False, exist_ok=False)
    c = capture
    state = SeedState(c, semantics, spec["run_id"], spec["payload_bytes"] // 16)
    deadline = time.monotonic() + spec["seconds"]
    cleanup_deadline = None
    process = output = None
    receipt = {"status": "ATTEMPTED", "inspect_only": inspect_only}
    try:
        c.enable_subreaper()
        argv = [spec["binary"], "--config", spec["config"], "--cwd", spec["workspace"]]
        argv += ["--resume-session", spec["session_dir"]] if inspect_only else ["--new-session"]
        argv += ["server", "stdio"]
        process = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE, env=spec["env"], start_new_session=True)
        output = c.Output(process, root)
        os.set_blocking(process.stdin.fileno(), False)
        receipt["identity"] = c.process_identity(process.pid)
        c.require(c.sha("/proc/" + str(process.pid) + "/exe") == spec["binary_sha256"],
                  "seed executable identity")
        c.write_request(process, {"type": "config_summary", "id": spec["run_id"] + ":config"}, deadline)
        def wait(predicate):
            while not predicate():
                c.require(time.monotonic() < deadline - 15 and process.poll() is None,
                          "seed/readiness deadline or exit")
                output.drain(state)
                time.sleep(0.001)
        wait(state.ready)
        c.require(state.pending["session_id"] == state.session
                  and state.pending["stream_id"] == state.stream, "startup witnesses disagree")
        if inspect_only:
            c.require(state.session == spec["session_id"], "resumed wrong session")
        else:
            c.require(state.snapshot["transcript"] == [], "fresh session contains history")
            evidence_root = Path(spec["evidence_root"]).resolve()
            session_path = Path(state.config["session_dir"]).resolve()
            session_relative = str(session_path.relative_to(evidence_root))
            c.require(session_relative.startswith("config/"), "session outside owned config root")
            cache_paths = [session_relative + "/.read-" + name + ".sqlite" + suffix
                           for name in ("view", "summary") for suffix in ("", "-wal", "-shm")]
            discovery = {"schema": "shipping-smoke-session-discovery-v1",
                         "session_id": state.session, "session_relative": session_relative,
                         "cache_paths": cache_paths,
                         "source_anchors": {
                             "read_cache": "82d39fe3c7faa0395bfc2e81041309fb0395be74",
                             "read_model": "14422a6dd7d5cc3253cad79ffe20b3e76d09c741",
                             "catalog_cache": "3aaa03c29398428514db91f3cb788a7af4b9af9e"}}
            discovery_raw = c.canonical(discovery) + b"\n"
            c.require(len(discovery_raw) <= 16384, "discovery receipt cap")
            with (evidence_root / "session-discovery.json").open("xb") as out:
                out.write(discovery_raw)
                out.flush()
                os.fsync(out.fileno())
            for ordinal in range(16):
                output.drain(state)
                state.begin(ordinal)
                request = {"type": "send", "id": state.current["run_id"],
                           "text": "A" * state.each}
                raw = c.canonical(request) + b"\n"
                c.require(len(raw) <= c.LINE_LIMIT, "encoded seed request too large")
                c.write_request(process, request, deadline)
                wait(state.complete)
                state.finish()
        cleanup_deadline = min(deadline, time.monotonic() + 15)
        ident = spec["run_id"] + ":shutdown"
        state.controls[ident] = time.monotonic_ns()
        c.write_request(process, {"type": "shutdown", "id": ident}, cleanup_deadline)
        process.stdin.close()
        c.require(process.wait(timeout=max(0, cleanup_deadline - time.monotonic())) == 0,
                  "seed shutdown exit")
        receipt["status"] = "TRANSPORT_PENDING_FINAL_DRAIN"
    except Exception as error:
        receipt.update(status="FAILED_CENSORED", error=str(error)[:2048])
    finally:
        if cleanup_deadline is None:
            cleanup_deadline = min(deadline, time.monotonic() + 15)
        errors = []
        if process is not None:
            try:
                if process.poll() is None:
                    c.kill_group(process)
                    process.wait(timeout=max(0, cleanup_deadline - time.monotonic()))
                receipt["adopted_workers_stopped"] = c.reap_adopted(cleanup_deadline)
                if receipt["adopted_workers_stopped"]:
                    errors.append("unexpected owned descendants required forced termination")
            except Exception as error:
                errors.append(str(error)[:1024])
        if output is not None:
            try:
                output.close(cleanup_deadline)
                output.drain(state)
                c.require(state.acks == set(state.controls) and state.shutdown,
                          "incomplete shutdown witnesses")
                if not inspect_only:
                    c.require(len(state.turns) == 16 and not state.active, "seed inventory incomplete")
                c.require(time.monotonic() <= cleanup_deadline, "cleanup deadline")
                if receipt["status"] == "TRANSPORT_PENDING_FINAL_DRAIN":
                    receipt["status"] = "PENDING_CANONICAL_VERIFICATION"
            except Exception as error:
                errors.append(str(error)[:1024])
            receipt["raw_capture"] = {"bytes": output.total, "retained_bytes": output.retained,
                                      "max_line": output.max_line, "stdout_frames": output.frames,
                                      "overflow_chunks": output.overflow, "reader_errors": output.errors}
        receipt["input_frames"] = getattr(process, "shipping_input_frames", [])
        if errors:
            receipt.update(status="FAILED_CENSORED", cleanup_errors=errors)
        receipt.update(session_id=state.session, turns=state.turns,
                       snapshot=state.snapshot, config_summary=state.config)
        raw = c.canonical(receipt) + b"\n"
        c.require(len(raw) <= 4 * 1024 * 1024, "seed receipt budget")
        (root / "receipt.json").write_bytes(raw)
    return receipt
