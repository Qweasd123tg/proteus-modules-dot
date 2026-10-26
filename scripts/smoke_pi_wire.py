#!/usr/bin/env python3
"""Direct smoke of an already-built authored Pi example; no Core CLI or install.

Synthetic host frames exercise the real executable, not a complete Core agent.
No verifier, real tool, model, network callback, or cancellation race is exercised.
"""
from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
import queue
import subprocess
import sys
import threading

MODULE_ID = "planning.ready_steps"
MAX_FRAME_BYTES = 1_048_576
TIMEOUT = 10


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def binding() -> dict:
    return {"slot": "tool", "module_id": MODULE_ID, "contract_version": "v6",
            "composition": "ordered_many", "module_config": {}, "host_features": []}


def initialize(export: dict) -> dict:
    return {"protocol_version": "v3", "component_id": "authored-pi-smoke", "exports": [export]}


def frame(sequence: int, method: str, params: object) -> dict:
    return {"jsonrpc": "2.0", "id": f"h:7:{sequence}", "method": method, "params": params}


class Worker:
    def __init__(self, binary: Path):
        self.child = subprocess.Popen([str(binary)], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                      stderr=None, text=True, encoding="utf-8")
        self.output: queue.Queue = queue.Queue(maxsize=16)
        self.sequence = 0
        self.reader = threading.Thread(target=self.read, daemon=True)
        self.reader.start()

    def read(self) -> None:
        try:
            while True:
                line = self.child.stdout.readline(MAX_FRAME_BYTES + 1)
                if not line:
                    self.output.put((False, "unexpected EOF"), timeout=TIMEOUT)
                    return
                require(len(line.encode("utf-8")) <= MAX_FRAME_BYTES, "oversized response frame")
                require(line.endswith("\n"), "unterminated response frame")
                self.output.put((True, json.loads(line)), timeout=TIMEOUT)
        except (ValueError, OSError, queue.Full) as error:
            try:
                self.output.put((False, str(error)), timeout=1)
            except queue.Full:
                pass

    def request(self, method: str, params: object, *, error: bool = False) -> object:
        request = frame(self.sequence, method, params)
        self.sequence += 1
        self.child.stdin.write(json.dumps(request, separators=(",", ":")) + "\n")
        self.child.stdin.flush()
        try:
            readable, reply = self.output.get(timeout=TIMEOUT)
        except queue.Empty as timeout:
            raise ValueError("wire response timed out") from timeout
        require(readable, f"invalid wire output: {reply}")
        require(isinstance(reply, dict), "JSON-RPC response is not an object")
        require(reply.get("jsonrpc") == "2.0" and reply.get("id") == request["id"],
                f"unexpected callback, notification, or response identity: {reply}")
        require(("result" in reply) != ("error" in reply), f"ambiguous terminal response: {reply}")
        require("method" not in reply, "unexpected host callback")
        if error:
            detail = reply.get("error")
            require(isinstance(detail, dict) and type(detail.get("code")) is int
                    and isinstance(detail.get("message"), str) and bool(detail["message"]),
                    f"expected explicit JSON-RPC error, received {reply}")
            return detail
        require("error" not in reply, f"unexpected JSON-RPC error: {reply}")
        return reply["result"]

    def invoke(self, method: str, params: object, *, error: bool = False) -> object:
        invocation_id = f"h:7:{self.sequence}"
        reply = self.request(method, {
            "export": {"slot": "tool", "module_id": MODULE_ID},
            "lineage": {"root_invocation_id": invocation_id, "parent_invocation_id": None, "depth": 0},
            "params": params,
        }, error=error)
        if error:
            return reply
        require(isinstance(reply, dict) and set(reply) == {"result"}, "missing strict module result envelope")
        return reply["result"]

    def __enter__(self):
        return self

    def __exit__(self, kind, value, traceback):
        try:
            self.child.stdin.close()
            if kind is not None:
                self.child.kill()
            code = self.child.wait(timeout=TIMEOUT)
        except subprocess.TimeoutExpired:
            self.child.kill()
            self.child.wait()
            if kind is None:
                raise ValueError("module did not exit after stdin EOF")
        finally:
            self.reader.join(timeout=1)
            self.child.stdout.close()
        if kind is None:
            require(code == 0, f"module exited unsuccessfully: {code}")


def reject_initialize(binary: Path, export: dict, expected_error: str) -> None:
    result = subprocess.run([str(binary)], input=json.dumps(frame(0, "initialize", initialize(export))) + "\n",
                            text=True, encoding="utf-8", capture_output=True, timeout=TIMEOUT)
    require(result.returncode > 0, f"invalid initialization did not fail normally: {result.returncode}")
    require(not result.stdout.strip(), "invalid initialization unexpectedly acknowledged")
    require(expected_error in result.stderr, f"wrong initialization failure: {result.stderr}")


def run(binary: Path) -> list[str]:
    checks = []
    plan = {"nodes": [
        {"id": "first", "dependencies": [], "status": "succeeded"},
        {"id": "next", "dependencies": ["first"], "status": "pending"},
    ], "failure_policy": "all_settled"}
    invocation = {
        "call": {"id": "pi-smoke-call", "name": MODULE_ID, "args": plan,
                 "surface": "function", "raw_arguments": None},
        "cwd": str(Path.cwd()),
        "attribution": {"execution_id": "00000000-0000-4000-8000-000000000001", "agent": None},
        "skills": {"disabled": [], "packages": []},
    }
    with Worker(binary) as worker:
        manifest = worker.request("initialize", initialize(binding()))
        require(manifest["protocol_version"] == "v3" and manifest["component_id"] == "authored-pi-smoke",
                "wrong handshake")
        require(len(manifest["exports"]) == 1, "unexpected export count")
        export = manifest["exports"][0]
        require(all(export[key] == binding()[key] for key in
                    ("slot", "module_id", "contract_version", "composition")), "wrong export identity")
        checks.append("wire_v3_tool_v6_handshake")
        definitions = worker.invoke("list", None)
        require(len(definitions) == 1 and definitions[0]["spec"]["name"] == MODULE_ID, "wrong tool list")
        checks.append("tool_list")
        result = worker.invoke("invoke", invocation)
        require(result["ok"] is True and result["call_id"] == "pi-smoke-call", "wrong ToolResult")
        output = json.loads(result["output"])
        require(output["ready"] == ["next"] and output["advisory_only"] is True
                and output["status_source"] == "caller_supplied_unverified", "lost advisory provenance")
        checks.append("detached_invocation_advisory_result")
        invalid = copy.deepcopy(invocation)
        invalid["call"]["args"]["nodes"][1]["dependencies"] = ["missing"]
        require(worker.invoke("invoke", invalid)["ok"] is False, "dangling edge accepted")
        checks.append("invalid_graph_tool_result_error")
        invalid["call"]["raw_arguments"] = json.dumps(plan)
        require(worker.invoke("invoke", invalid)["ok"] is True, "raw arguments are not authoritative")
        checks.append("raw_arguments_authority")
        invalid["call"]["raw_arguments"] = "{not JSON}"
        worker.invoke("invoke", invalid, error=True)
        checks.append("malformed_raw_arguments_rejected")
        invalid = copy.deepcopy(invocation)
        invalid["call"]["args"]["failure_policy"] = "invented"
        worker.invoke("invoke", invalid, error=True)
        checks.append("invalid_policy_schema_rejected")
        invalid = copy.deepcopy(invocation)
        invalid["call"]["args"]["execute"] = True
        worker.invoke("invoke", invalid, error=True)
        checks.append("unknown_argument_rejected")
        invalid = copy.deepcopy(invocation)
        invalid["call"]["name"] = "not_exported"
        worker.invoke("invoke", invalid, error=True)
        checks.append("unknown_tool_rejected")
        worker.invoke("list", {}, error=True)
        checks.append("invalid_list_payload_rejected")
        worker.invoke("invoke", {"unexpected": True}, error=True)
        checks.append("invalid_invocation_rejected")
        require(worker.invoke("invoke", invocation) == result, "errors poisoned subsequent invocation")
        checks.append("repeat_after_errors_stable")
    invalid_export = binding()
    invalid_export["module_id"] = "not_exported"
    reject_initialize(binary, invalid_export, "unsupported export")
    checks.append("wrong_export_initialization_rejected")
    invalid_export = binding()
    invalid_export["module_config"] = {"execute": True}
    reject_initialize(binary, invalid_export, "unknown field")
    checks.append("wrong_config_initialization_rejected")
    return checks


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--module", required=True, type=Path)
    args = parser.parse_args()
    try:
        checks = run(args.module.resolve(strict=True))
        print(json.dumps({"schema_version": 1, "status": "passed", "checks_executed": checks}))
        return 0
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as error:
        print(json.dumps({"schema_version": 1, "status": "failed", "error": str(error)}))
        return 1


if __name__ == "__main__":
    sys.exit(main())
