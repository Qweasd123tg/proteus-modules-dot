#!/usr/bin/env python3
"""Two sequential owned Node children: pure controls then known SDK; no Core/providers."""
import sys
if not __debug__ or not sys.flags.isolated or not sys.flags.no_site:
    raise RuntimeError("use unoptimized python3 -I -B -S")
sys.dont_write_bytecode = True

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import selectors
import time

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from controller import Worker, MAX_FRAME
from oracle import payload_request, check_response, check_pure, check_initialize, require
from strict_json import loads

PACKAGE = ROOT.parent
# Explicit caller-provisioned trusted runtime and SDK paths; never auto-download.
NODE = None
SDK = None
NODE_SHA256 = None
SDK_SHA256 = {
    "worker.mjs": "f7dd6ad7cc49823f97974f3e2c5ffbd9b3228927e5940224f49ced5639ba2dd4",
    "hooks.mjs": "1a0347377f8b05b3a7a00804453150ede421eb5b45b8485a093d8d64067b2a0e",
    "ports.mjs": "cba7d129152f3a15ce3e1d96cdc6645407e4262d1b12b872fcc8081d69a69bff",
    "command.mjs": "b1448479b537280bd2f9bae060bbe7c2328e144945cd140f0a31a2857639eee9",
    "validation.mjs": "14dd7139012f84140edff1804c2d5325d0b0c0168471c7a3d9e221b141e4149c",
}
PACKAGE_FILES = ['CONTROL_INVENTORY.json', 'EVIDENCE_SUMMARY.json', 'PACKAGE_MAP.json', 'README.md', 'SDK_CASE_PROPOSAL.json', 'guard.mjs', 'sdk-fixture.mjs', 'test-guard.mjs', 'optional-sdk/README.md', 'optional-sdk/controller.py', 'optional-sdk/oracle.py', 'optional-sdk/probe.py', 'optional-sdk/strict_json.py', 'optional-sdk/test_controller.py', 'optional-sdk/test_oracle.py']
RESERVE = 1 << 30
ACTIVE_SECONDS = 30
MAX_STDIN = 32 * 1024
MAX_ARTIFACT = 256 * 1024


def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def free_bytes():
    stat = os.statvfs(ROOT)
    return stat.f_bavail * stat.f_frsize


def verify_manifest(root, names, expected_manifest):
    require(digest(root / "CODE.sha256") == expected_manifest, "reviewed source manifest hash mismatch")
    declared = {}
    for line in (root / "CODE.sha256").read_text().splitlines():
        expected, name = line.split("  ", 1)
        require(name in names and name not in declared, "source manifest inventory mismatch")
        require(not (root / name).is_symlink(), "source symlink refused")
        require(digest(root / name) == expected, "source file mismatch: " + name)
        declared[name] = expected
    require(set(declared) == set(names), "source manifest incomplete")
    return declared


def inputs():
    rows = {}
    require(digest(NODE) == NODE_SHA256, "Node binary hash mismatch")
    rows["node_binary"] = NODE_SHA256
    for name, expected in SDK_SHA256.items():
        member = SDK / name
        require(not member.is_symlink() and member.is_file(), "SDK member must be a non-symlink regular file: " + name)
        require(digest(member) == expected, "SDK hash mismatch: " + name)
        rows["sdk/" + name] = expected
    for name in PACKAGE_FILES:
        require(not (PACKAGE / name).is_symlink(), "source symlink refused")
        rows["package/" + name] = digest(PACKAGE / name)
    rows["package/CODE.sha256"] = digest(PACKAGE / "CODE.sha256")
    return rows


class Artifacts:
    def __init__(self, path):
        path.mkdir()  # Atomic fresh leaf; never reuse output.
        self.path = path
        self.used = 0
        self.offsets = {}

    def append(self, name, raw):
        require(free_bytes() >= RESERVE + 1024 * 1024, "disk reserve stop")
        require(self.used + len(raw) <= MAX_ARTIFACT, "aggregate artifact byte cap")
        with (self.path / name).open("ab") as target:
            target.write(raw)
        self.used += len(raw)
        self.offsets[name] = self.offsets.get(name, 0) + len(raw)

    def json(self, name, value):
        require(not (self.path / name).exists(), "artifact must not be overwritten")
        raw = (json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()
        require(len(raw) <= 64 * 1024, "JSON artifact too large")
        self.append(name, raw)


def frame_bytes(value):
    raw = (json.dumps(value, separators=(",", ":"), ensure_ascii=False, allow_nan=False) + "\n").encode()
    require(len(raw) <= 4096, "request frame cap")
    return raw


def receive(worker, deadline):
    while b"\n" not in worker.buffer:
        require(not worker.stdout_eof, "stdout closed before expected response")
        worker._events(deadline)
    end = worker.buffer.index(b"\n") + 1
    require(end <= MAX_FRAME, "response frame byte cap")
    response = bytes(worker.buffer[:end])
    del worker.buffer[:end]
    require(not worker.buffer, "unexpected extra response bytes")
    return response


def exchange(worker, artifacts, request):
    require(free_bytes() >= RESERVE + 1024 * 1024, "disk reserve stop")
    require(not worker.buffer, "unexpected buffered frame before request")
    raw = frame_bytes(request)
    require(artifacts.offsets.get("sdk.stdin.raw", 0) + len(raw) <= MAX_STDIN, "stdin byte cap")
    deadline = min(worker.deadline, time.monotonic() + 3)
    sent = 0
    worker.selector.register(worker.child.stdin, selectors.EVENT_WRITE, "stdin")
    try:
        while sent < len(raw):
            if worker._events(deadline):
                try:
                    count = os.write(worker.child.stdin.fileno(), raw[sent:])
                except BlockingIOError:
                    continue
                require(count > 0, "stdin write made no progress")
                artifacts.append("sdk.stdin.raw", raw[sent:sent + count])
                sent += count
    finally:
        worker.selector.unregister(worker.child.stdin)
    return raw, receive(worker, deadline)


def clean(report):
    return (report is not None and report["reaped"] and report["returncode"] == 0
            and not report["error"] and not report["terminated"] and not report["killed"])


def main():
    global NODE, SDK, NODE_SHA256
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-reviewed", action="store_true")
    parser.add_argument("--output", required=True)
    parser.add_argument("--source-manifest-sha256", required=True)
    parser.add_argument("--node", type=Path, required=True)
    parser.add_argument("--node-sha256", required=True)
    parser.add_argument("--sdk-dir", type=Path, required=True)
    args = parser.parse_args()
    require(os.name == "posix", "optional probe requires POSIX pipe/selector semantics")
    require(args.node.is_absolute() and args.sdk_dir.is_absolute(), "runtime/SDK paths must be absolute")
    require(re.fullmatch(r"[0-9a-f]{64}", args.node_sha256) is not None, "expected Node SHA256 required")
    NODE = args.node.resolve(strict=True)
    SDK = args.sdk_dir.resolve(strict=True)
    NODE_SHA256 = args.node_sha256
    require(NODE.is_file() and SDK.is_dir(), "runtime/SDK path type mismatch")
    require(args.run_reviewed, "explicit reviewed-run flag required; not an authorization verifier")
    require(re.fullmatch(r"results-[a-z0-9-]+", args.output) is not None, "invalid output leaf")
    require(free_bytes() >= RESERVE + 2 * 1024 * 1024, "insufficient preflight reserve")
    verify_manifest(PACKAGE, PACKAGE_FILES, args.source_manifest_sha256)
    before = inputs()
    corpus = loads((PACKAGE / "SDK_CASE_PROPOSAL.json").read_text())
    inventory = loads((PACKAGE / "CONTROL_INVENTORY.json").read_text())
    require(type(corpus["schema_version"]) is int and corpus["schema_version"] == 1, "case schema")
    require(type(inventory["schema_version"]) is int and inventory["schema_version"] == 1, "control schema")
    names = inventory["required_controls"]
    require(len(names) == 38 and len(set(names)) == 38, "exact pure inventory")
    cases = corpus["cases"]
    require(len(cases) == 13 and len({case["name"] for case in cases}) == 13, "exact SDK case inventory")
    require([case["wire_id"] for case in cases] == [f"h:7:{i}" for i in range(1, 14)], "ordinary exact IDs")
    artifacts = Artifacts(ROOT / args.output)
    artifacts.json("inputs-before.json", before)
    for phase in ("pure", "sdk"):
        for suffix in ("stdin.raw", "stdout.raw", "stderr.raw"):
            artifacts.append(phase + "." + suffix, b"")
    worker = None
    started = time.monotonic()
    deadline = started + ACTIVE_SECONDS
    observations, exchanges, cleanups = [], [], []
    pure_result = None
    failure = None
    phase = "pure"
    environment = {"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8", "TZ": "UTC"}
    try:
        worker = Worker([str(NODE), str(PACKAGE / "test-guard.mjs")], str(PACKAGE), environment,
                        min(deadline, time.monotonic() + 10),
                        lambda raw: artifacts.append("pure.stdout.raw", raw),
                        lambda raw: artifacts.append("pure.stderr.raw", raw))
        pure_result = check_pure(receive(worker, worker.deadline), names)
        cleanup = worker.stop(True)
        cleanups.append({"phase": phase, **cleanup})
        worker = None
        require(clean(cleanup), "pure child not cleanly reaped; SDK phase forbidden")
        require(artifacts.offsets["pure.stderr.raw"] == 0, "unexpected pure stderr; SDK phase forbidden")
        require(time.monotonic() < deadline, "total active deadline before SDK phase")
        require(free_bytes() >= RESERVE + 1024 * 1024, "disk reserve before SDK phase")
        phase = "sdk"
        worker = Worker([str(NODE), str(SDK / "worker.mjs")], str(PACKAGE), environment, deadline,
                        lambda raw: artifacts.append("sdk.stdout.raw", raw),
                        lambda raw: artifacts.append("sdk.stderr.raw", raw))
        exports = [{"slot": "hook", "module_id": row["module_id"], "contract_version": "v6",
                    "composition": "ordered_many", "module_config": {
                        "entry": str(PACKAGE / "sdk-fixture.mjs"), "settings": row["settings"]},
                    "host_features": []} for row in corpus["exports"]]
        request = {"jsonrpc": "2.0", "id": "h:7:0", "method": "initialize", "params": {
            "protocol_version": "v3", "component_id": "authored.argument-guard", "exports": exports}}
        sent, received = exchange(worker, artifacts, request)
        check_initialize(received, corpus)
        exchanges.append({"name": "initialize", "request_sha256": hashlib.sha256(sent).hexdigest(),
                          "response_sha256": hashlib.sha256(received).hexdigest()})
        for case in cases:
            sent, received = exchange(worker, artifacts, payload_request(case, str(PACKAGE)))
            observations.append(check_response(case, sent, received))
            exchanges.append({"name": case["name"], "request_sha256": hashlib.sha256(sent).hexdigest(),
                              "response_sha256": hashlib.sha256(received).hexdigest()})
    except BaseException as error:
        failure = f"{type(error).__name__}: {error}"[:2048]
    finally:
        if worker is not None:
            cleanups.append({"phase": phase, **worker.stop(failure is None)})
    try:
        after = inputs()
    except BaseException as error:
        after = {"hash_check_error": f"{type(error).__name__}: {error}"[:2048]}
        failure = failure or "post-run input hash check failed"
    artifacts.json("inputs-after.json", after)
    if before != after:
        failure = failure or "input hashes changed"
    if len(cleanups) != 2 or not all(clean(row) for row in cleanups):
        failure = failure or "two clean direct-child exits not established"
    if artifacts.offsets["pure.stderr.raw"] or artifacts.offsets["sdk.stderr.raw"]:
        failure = failure or "unexpected stderr"
    if pure_result is None or len(observations) != 13 or len(exchanges) != 14:
        failure = failure or "required controls or SDK observations incomplete"
    report = {"schema_version": 1, "status": "passed" if failure is None else "failed", "failure": failure,
              "scope": "38 pure guard controls then 13 authored SDK hooks+initialize; no Core/policy execution",
              "runtime_seconds": time.monotonic() - started, "pure_result": pure_result,
              "observations": observations, "exchanges": exchanges, "cleanups": cleanups,
              "raw_bytes": artifacts.offsets.copy(), "inputs_unchanged": before == after,
              "provider_or_tool_effects_executed": False}
    artifacts.json("result.json", report)
    manifest = {p.name: {"sha256": digest(p), "bytes": p.stat().st_size}
                for p in sorted(artifacts.path.iterdir()) if p.is_file()}
    artifacts.json("artifact-manifest.json", manifest)
    print(json.dumps({"status": report["status"], "pure_controls": len((pure_result or {}).get("controls", [])),
                      "sdk_invocations": len(observations), "rpc_exchanges": len(exchanges), "output_leaf": args.output}))
    return 0 if failure is None else 1


if __name__ == "__main__":
    raise SystemExit(main())
