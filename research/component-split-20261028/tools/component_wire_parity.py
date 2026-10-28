#!/usr/bin/env python3
"""Bounded, model-free plan-component differential probe (Python stdlib/POSIX).

Only explicitly supplied executables are launched, without a shell. This is not
a sandbox or a Core policy/approval gate. No callbacks are serviced. Both files
must be built from the same patched Modules tree, pinned to SDK 1f533a13.
Wire source: Core 1f533a13 contracts/process_module.rs, process_slots.rs and
module-sdk/runtime.rs; plan semantics: Modules 56571639 tool/plan-tool/src/lib.rs.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import selectors
import signal
import subprocess
import tempfile
import time


MODULES_REV = "56571639c804443dbca58e054fff8631ecb8b312"
SDK_REV = "1f533a13f20a93bf164f7c8a169553b0b219bb51"
COMPONENT_ID = "plan-wire-parity"
LIMITS = {"total_seconds": 120, "request_seconds": 5, "frame_bytes": 1048576,
          "stdout_bytes": 4194304, "stderr_bytes": 131072, "frames": 64,
          "request_bytes": 65536, "cleanup_seconds": 2}


class ProbeFailure(Exception):
    """A failed assertion, invalid frame or resource bound violation."""


class ProbeTimeout(ProbeFailure):
    """A deadline elapsed; distinct from a target assertion failure."""


def require(condition, message):
    if not condition:
        raise ProbeFailure(message)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def strict_json(raw):
    def pairs(entries):
        result = {}
        for key, value in entries:
            require(key not in result, "duplicate JSON object key")
            result[key] = value
        return result

    def nonfinite(_value):
        raise ProbeFailure("non-finite JSON number")

    def finite_float(value):
        parsed = float(value)
        require(math.isfinite(parsed), "non-finite JSON number")
        return parsed

    try:
        return json.loads(raw.decode("utf-8"), object_pairs_hook=pairs,
                          parse_constant=nonfinite, parse_float=finite_float)
    except (UnicodeError, ValueError, RecursionError) as error:
        raise ProbeFailure("malformed UTF-8 JSON frame") from error


class Worker:
    """One owned session; nonblocking stdin/stdout/stderr share finite budgets."""

    def __init__(self, command, cwd, deadline, limits=None):
        require(os.name == "posix", "this bounded process-group runner requires POSIX")
        if time.monotonic() >= deadline:
            raise ProbeTimeout("whole-suite deadline already elapsed")
        self.limits = dict(LIMITS if limits is None else limits)
        self.deadline = deadline
        self.selector = selectors.DefaultSelector()
        self.buffer = bytearray()
        self.stderr = bytearray()
        self.frames = []
        self.stdout_bytes = 0
        self.frame_count = 0
        self.request_count = 0
        self.closed = False
        self.stdin_closed = False
        self.stdout_eof = False
        self.stderr_eof = False
        # Deliberately omit credentials, user config, proxies and model settings.
        env = {"PATH": os.defpath, "HOME": str(cwd), "TMPDIR": str(cwd),
               "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8", "RUST_BACKTRACE": "0"}
        try:
            self.process = subprocess.Popen(command, cwd=cwd, env=env,
                                            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                            stderr=subprocess.PIPE, bufsize=0,
                                            start_new_session=True, close_fds=True)
        except BaseException:
            self.selector.close()
            raise
        try:
            for stream, name in ((self.process.stdin, "stdin"),
                                 (self.process.stdout, "stdout"),
                                 (self.process.stderr, "stderr")):
                os.set_blocking(stream.fileno(), False)
                if name != "stdin":
                    self.selector.register(stream, selectors.EVENT_READ, name)
        except BaseException:
            self.close()
            raise

    def _until(self):
        return min(self.deadline, time.monotonic() + self.limits["request_seconds"])

    def _read(self, stream, name):
        try:
            chunk = os.read(stream.fileno(), 8192)
        except BlockingIOError:
            return
        if not chunk:
            self.selector.unregister(stream)
            if name == "stdout":
                self.stdout_eof = True
                require(not self.buffer, "stdout ended with an unterminated frame")
            else:
                self.stderr_eof = True
            return
        if name == "stderr":
            require(len(self.stderr) + len(chunk) <= self.limits["stderr_bytes"],
                    "stderr byte budget exceeded")
            self.stderr.extend(chunk)
            return
        self.stdout_bytes += len(chunk)
        require(self.stdout_bytes <= self.limits["stdout_bytes"],
                "stdout byte budget exceeded")
        self.buffer.extend(chunk)
        while b"\n" in self.buffer:
            end = self.buffer.index(10)
            require(end + 1 <= self.limits["frame_bytes"], "frame byte budget exceeded")
            raw = bytes(self.buffer[:end])
            del self.buffer[:end + 1]
            self.frame_count += 1
            require(self.frame_count <= self.limits["frames"], "frame count budget exceeded")
            require(bool(raw.strip()), "blank stdout frame")
            self.frames.append(strict_json(raw))
        require(len(self.buffer) < self.limits["frame_bytes"],
                "unterminated frame byte budget exceeded")

    def _pump(self, until, pending=None):
        remaining = until - time.monotonic()
        if remaining <= 0:
            raise ProbeTimeout("request/startup or whole-suite deadline elapsed")
        for key, _mask in self.selector.select(min(remaining, 0.05)):
            if key.data == "stdin":
                try:
                    sent = os.write(key.fd, pending)
                except BlockingIOError:
                    continue
                except BrokenPipeError as error:
                    raise ProbeFailure("child closed stdin before request was written") from error
                pending = pending[sent:]
                if not pending:
                    self.selector.unregister(key.fileobj)
            else:
                self._read(key.fileobj, key.data)
        return pending

    def send(self, request):
        require(not self.stdin_closed, "stdin already closed")
        require(not self.frames, "unsolicited/duplicate response before next request")
        pending = canonical(request) + b"\n"
        require(len(pending) <= self.limits["request_bytes"], "request byte budget exceeded")
        self.request_count += 1
        require(self.request_count <= self.limits["frames"], "request count budget exceeded")
        self.selector.register(self.process.stdin, selectors.EVENT_WRITE, "stdin")
        until = self._until()
        self.response_deadline = until
        while pending:
            pending = self._pump(until, pending)

    def response(self, request_id):
        until = self.response_deadline
        while not self.frames:
            require(not self.stdout_eof, "child exited without the expected response")
            self._pump(until)
        frame = self.frames.pop(0)
        require(isinstance(frame, dict), "JSON-RPC response must be an object")
        require("method" not in frame, "host callback or notification is forbidden")
        require(frame.get("jsonrpc") == "2.0" and frame.get("id") == request_id,
                "JSON-RPC version/response identity mismatch")
        result = "result" in frame
        require(set(frame) == {"jsonrpc", "id", "result" if result else "error"},
                "malformed JSON-RPC response envelope")
        if not result:
            error = frame["error"]
            require(isinstance(error, dict) and {"code", "message"} <= set(error)
                    and set(error) <= {"code", "message", "data"}
                    and type(error["code"]) is int and isinstance(error["message"], str),
                    "malformed JSON-RPC error envelope")
        return frame

    def exchange(self, request):
        self.send(request)
        return self.response(request["id"])

    def finish(self, rejected=False):
        """SDK shutdown is stdin EOF, not an invented shutdown method."""
        # A negative fixture must exit on the invalid request itself. Closing
        # stdin first could make an EOF-only failure look like valid rejection.
        if not rejected and not self.stdin_closed:
            self.process.stdin.close()
            self.stdin_closed = True
        until = self.response_deadline if rejected else self._until()
        while not (self.stdout_eof and self.stderr_eof):
            self._pump(until)
        require(not self.frames, "unsolicited response/callback during shutdown or rejection")
        remaining = until - time.monotonic()
        if remaining <= 0:
            raise ProbeTimeout("child exit deadline elapsed")
        try:
            code = self.process.wait(timeout=remaining)
        except subprocess.TimeoutExpired as error:
            raise ProbeTimeout("child exit deadline elapsed") from error
        require(code == 1 if rejected else code == 0,
                f"unexpected exit status {code} (rejected={rejected})")
        if rejected:
            require(bool(self.stderr), "rejection lacked a diagnostic on stderr")
        return code

    def metrics(self):
        return {"frames": self.frame_count, "stdout_bytes": self.stdout_bytes,
                "stderr_bytes": len(self.stderr), "requests": self.request_count,
                "stderr_sha256": hashlib.sha256(self.stderr).hexdigest(),
                "stderr_tail": bytes(self.stderr[-2048:]).decode("utf-8", errors="replace")}

    def close(self):
        if self.closed:
            return
        self.closed = True
        # Signal only this child's newly created session/process group. Never
        # search names/PIDs or signal a shared caller process group. Escalate even
        # after leader exit so descendants cannot keep inherited pipes open.
        process = self.process
        try:
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            try:
                process.wait(timeout=self.limits["cleanup_seconds"] / 2)
            except subprocess.TimeoutExpired:
                pass
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            try:
                process.wait(timeout=self.limits["cleanup_seconds"] / 2)
            except subprocess.TimeoutExpired as error:
                raise ProbeFailure("owned child could not be reaped after SIGKILL") from error
        finally:
            self.selector.close()
            for stream in (process.stdin, process.stdout, process.stderr):
                stream.close()


def initialize(config=None):
    return {"jsonrpc": "2.0", "id": "h:1:0", "method": "initialize", "params": {
        "protocol_version": "v3", "component_id": COMPONENT_ID, "exports": [{
            "slot": "tool", "module_id": "plan_tool", "contract_version": "v6",
            "composition": "ordered_many", "module_config": {} if config is None else config,
            "host_features": []}]}}


def manifest():
    return {"protocol_version": "v3", "component_id": COMPONENT_ID, "exports": [{
        "slot": "tool", "module_id": "plan_tool", "contract_version": "v6",
        "composition": "ordered_many", "module_features": [], "config_schema": {"fields": []}}]}


def invocation(sequence, method, params):
    wire_id = f"h:1:{sequence}"
    return {"jsonrpc": "2.0", "id": wire_id, "method": method, "params": {
        "export": {"slot": "tool", "module_id": "plan_tool"}, "lineage": {
            "root_invocation_id": wire_id, "parent_invocation_id": None, "depth": 0},
        "params": params}}


def tool_input(label, args, cwd, name="update_plan", raw=None):
    return {"call": {"id": "call-" + label, "name": name, "args": args,
                     "surface": "function", "raw_arguments": raw}, "cwd": str(cwd),
            "attribution": {"execution_id": "00000000-0000-4000-8000-000000000001",
                            "agent": None}, "skills": {"disabled": [], "packages": []}}


def cases(cwd):
    """No generated/random/model inputs; keep semantic oddities of the baseline."""
    rows = [("list-first", "list", None, "list"),
            ("list-repeat", "list", None, "list"),
            ("list-non-null", "list", {}, "rpc-error")]
    args_cases = [
        ("three-statuses", {"explanation": "Starting — проверка", "plan": [
            {"step": "Read", "status": "completed"},
            {"step": "Fix", "status": "in_progress"},
            {"step": "Check", "status": "pending"}]}, "ok"),
        ("empty", {"plan": []}, "ok"),
        ("blank-multiple-active", {"plan": [
            {"step": "", "status": "in_progress"},
            {"step": " ", "status": "in_progress"}]}, "ok"),
        ("long", {"plan": [{"step": f"Step {n}", "status": "pending"}
                             for n in range(21)]}, "ok"),
        ("bad-status", {"plan": [{"step": "x", "status": "done"}]}, "tool-error"),
        ("unknown-step-field", {"plan": [{"step": "x", "status": "pending", "x": 1}]},
         "tool-error"),
        ("unknown-args-field", {"plan": [], "x": 1}, "tool-error"),
        ("missing-plan", {}, "tool-error"),
        ("null-args", None, "tool-error"),
    ]
    for label, args, expected in args_cases:
        rows.append((label, "invoke", tool_input(label, args, cwd), expected))
    for label, raw in (("raw-contradictory", '{"plan":[{"status":"wrong"}]}'),
                       ("raw-malformed", "{not JSON")):
        rows.append((label, "invoke", tool_input(label, {"plan": []}, cwd, raw=raw), "ok"))
    for label, name in (("unknown-name", "missing"), ("case-name", "Update_Plan"),
                        ("space-name", " update_plan")):
        rows.append((label, "invoke", tool_input(label, {"plan": []}, cwd, name), "rpc-error"))
    for key in ("attribution", "skills"):
        label = "missing-" + key
        value = tool_input(label, {"plan": []}, cwd)
        del value[key]
        rows.append((label, "invoke", value, "rpc-error"))
    rows.append(("wrong-method", "not_a_tool_method", None, "rpc-error"))
    result = [(label, invocation(index, method, params), expected)
              for index, (label, method, params, expected) in enumerate(rows, 1)]
    for field in ("slot", "module_id"):
        request = invocation(len(result) + 1, "list", None)
        request["params"]["export"][field] = "not_requested"
        result.append(("wrong-target-" + field, request, "rpc-error"))
    return result


def validate_outcome(request, response, expected):
    if expected == "rpc-error":
        require("error" in response and response["error"]["code"] == -32000,
                "expected terminal RPC error -32000")
        require(bool(response["error"]["message"]), "empty terminal error message")
        return
    require("result" in response, "expected successful JSON-RPC response")
    wrapped = response["result"]
    require(isinstance(wrapped, dict) and set(wrapped) == {"result"},
            "canonical method response envelope changed")
    value = wrapped["result"]
    if expected == "list":
        require(isinstance(value, list) and len(value) == 1,
                "expected exactly one tool definition (no dedup/filtering)")
        definition = value[0]
        require(isinstance(definition, dict)
                and set(definition) == {"spec", "model_visible", "user_command"}
                and definition["model_visible"] is True and definition["user_command"] is None,
                "tool visibility or canonical definition changed")
        spec = definition["spec"]
        require(isinstance(spec, dict) and spec.get("name") == "update_plan"
                and spec.get("supports_parallel_tool_calls") is False
                and spec.get("safety") == "ReadOnly", "plan tool identity/capability changed")
        return
    require(isinstance(value, dict) and set(value) == {
        "call_id", "ok", "output", "content", "error", "metadata"},
        "canonical ToolResult fields changed")
    call = request["params"]["params"]["call"]
    require(value["call_id"] == call["id"], "ToolResult call identity mismatch")
    if expected == "ok":
        args = call["args"]
        expected_result = {"call_id": call["id"], "ok": True, "output": "Plan updated",
                           "content": [], "error": None, "metadata": {
                               "plan": args["plan"], "explanation": args.get("explanation"),
                               **{status: sum(step["status"] == status for step in args["plan"])
                                  for status in ("completed", "in_progress", "pending")}}}
        require(canonical(value) == canonical(expected_result), "plan success semantics changed")
    else:
        require(value["ok"] is False and value["output"] == "" and value["content"] == []
                and value["metadata"] == {} and isinstance(value["error"], str)
                and value["error"].startswith("plan entries must be "),
                "expected baseline failed-tool result, not a transport error")


def rejection_cases():
    result = []
    for label, field, value in (("bad-slot", "slot", "not_a_slot"),
                                ("bad-module-id", "module_id", "not_a_module"),
                                ("bad-contract", "contract_version", "v5"),
                                ("bad-composition", "composition", "select_one"),
                                ("bad-config", "module_config", None)):
        request = initialize()
        request["params"]["exports"][0][field] = value
        result.append((label, False, request))
    request = initialize()
    request["params"]["protocol_version"] = "v2"
    result.append(("bad-wire-version", False, request))
    request = initialize()
    request["id"] = "h:1:1"
    result.append(("bad-initialize-id", False, request))
    for label, wire_id in (("wrong-generation", "h:2:1"),
                            ("wrong-direction", "m:1:1"),
                            ("zero-sequence", "h:1:0")):
        request = invocation(1, "list", None)
        request["id"] = wire_id
        request["params"]["lineage"]["root_invocation_id"] = wire_id
        result.append((label, True, request))
    request = invocation(1, "list", None)
    request["params"]["lineage"]["root_invocation_id"] = "h:1:2"
    result.append(("wrong-lineage", True, request))
    return result


def run_suite(commands, cwd, report, limits=None):
    limits = dict(LIMITS if limits is None else limits)
    start = time.monotonic()
    deadline = start + limits["total_seconds"]
    plans = [("default-config", {}, None), ("opaque-config", {"opaque": {"value": 3}}, None)]
    plans += [(name, None, (needs_init, request))
              for name, needs_init, request in rejection_cases()]
    report.update({"status": "running", "limits": limits, "sdk_revision": SDK_REV,
                   "modules_baseline": MODULES_REV, "scope": "wire parity only; not Core conformance, policy/approval, OS sandbox or RAM benchmark",
                   "scenarios": [{"name": name, "status": "never-run"} for name, _, _ in plans]})
    try:
        for (name, config, rejection), row in zip(plans, report["scenarios"]):
            row.update({"status": "running", "workers": {
                "reference": {"status": "never-run"}, "candidate": {"status": "never-run"}}})
            transcripts = {}
            for label in ("reference", "candidate"):
                worker = Worker(commands[label], cwd, deadline, limits)
                row["workers"][label] = {"status": "running"}
                transcript = []
                try:
                    if rejection is None or rejection[0]:
                        response = worker.exchange(initialize(config))
                        require(canonical(response) == canonical({"jsonrpc": "2.0", "id": "h:1:0",
                                                                 "result": manifest()}),
                                "manifest identity/schema/features mismatch")
                        transcript.append(("initialize", response))
                    if rejection is None:
                        first_list = None
                        for case_name, request, expected in cases(cwd):
                            response = worker.exchange(request)
                            validate_outcome(request, response, expected)
                            if expected == "list":
                                if first_list is None:
                                    first_list = response["result"]
                                else:
                                    require(canonical(first_list) == canonical(response["result"]),
                                            "list changed across repeated calls")
                            transcript.append((case_name, response))
                        worker.finish()
                    else:
                        worker.send(rejection[1])
                        worker.finish(rejected=True)
                    transcripts[label] = transcript
                    row["workers"][label]["status"] = "passed"
                finally:
                    row["workers"][label].update(worker.metrics())
                    worker.close()
            row["responses"] = [{"name": case_name, "reference_sha256": digest(reference),
                                 "candidate_sha256": digest(candidate)}
                                for (case_name, reference), (_, candidate) in
                                zip(transcripts["reference"], transcripts["candidate"])]
            for response in row["responses"]:
                require(response["reference_sha256"] == response["candidate_sha256"],
                        f"wire transcript mismatch in {name}/{response['name']}")
            require(canonical(transcripts["reference"]) == canonical(transcripts["candidate"]),
                    f"wire transcript length/order mismatch in {name}")
            row.update({"status": "passed", "response_count": len(transcripts["reference"]),
                        "transcript_sha256": digest(transcripts["reference"])})
        report["status"] = "passed"
    except (ProbeFailure, OSError, ValueError) as error:
        status = "timeout" if isinstance(error, ProbeTimeout) else "failed"
        report.update({"status": status, "error": str(error)[:2048]})
        for row in report["scenarios"]:
            if row["status"] == "running":
                row["status"] = status
                for worker in row.get("workers", {}).values():
                    if worker["status"] == "running":
                        worker["status"] = status
        raise
    finally:
        report["elapsed_seconds"] = round(time.monotonic() - start, 3)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference", required=True, type=Path)
    parser.add_argument("--candidate", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    report = {"status": "never-run"}
    try:
        commands = {}
        for label in ("reference", "candidate"):
            binary = getattr(args, label).resolve(strict=True)
            require(binary.is_file() and os.access(binary, os.X_OK),
                    f"{label} is not an executable file")
            commands[label] = [str(binary)]
        require(commands["reference"] != commands["candidate"], "comparison requires distinct files")
        require(not os.path.samefile(commands["reference"][0], commands["candidate"][0]),
                "comparison requires distinct file identities")
        with tempfile.TemporaryDirectory(prefix="plan-wire-parity-") as cwd:
            run_suite(commands, Path(cwd), report)
    except (ProbeFailure, OSError, ValueError) as error:
        if report["status"] == "never-run":
            report["error"] = str(error)[:2048]
        print(f"plan wire parity: {report['status']}: {error}")
        return 1
    finally:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False) + "\n",
                               encoding="utf-8")
    print("plan wire parity: passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
