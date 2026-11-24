#!/usr/bin/env python3
"""Exact stdout replay of the real native session-storage worker."""
import argparse
import base64
import contextlib
import hashlib
import json
import os
from pathlib import Path
import select
import struct
import subprocess
import time
import uuid
import zlib

MIB = 1024 * 1024
DEFAULT_LIMIT = 8 * MIB
MAX_FRAME = 128 * MIB
MAX_BLOB = 64 * MIB
IMAGE_LIMIT = 5 * MIB
LIMIT_ENV = "PROTEUS_MODULE_MAX_FRAME_BYTES"
SESSION_ID = "90234567-89ab-4cde-8f01-123456789abc"
OTHER_SESSION = "40234567-89ab-4cde-8f01-123456789abc"
MISSING = hashlib.sha256(b"absent blob").hexdigest()


def ensure(condition, message):
    if not condition:
        raise RuntimeError(message)


def serialized(obj):
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":")).encode() + b"\n"


def digest(data):
    return hashlib.sha256(data).hexdigest()


class Worker:
    def __init__(self, binary, backend, cap=None):
        env = {"PATH": "/usr/bin:/bin", "LC_ALL": "C.UTF-8"}
        if cap is not None:
            env[LIMIT_ENV] = str(cap)
        self.child = subprocess.Popen(
            [str(binary)], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, env=env, bufsize=0,
        )
        self.backend = backend
        self.buffer = bytearray()
        self.sequence = 0
        self.send({"jsonrpc": "2.0", "id": "h:1:0", "method": "initialize", "params": {
            "protocol_version": "v3", "component_id": "storage-test", "exports": [{
                "slot": "session_storage", "module_id": backend, "contract_version": "v2",
                "composition": "select_one", "module_config": {}, "host_features": [],
            }],
        }})
        self.manifest = self.line()
        result = json.loads(self.manifest).get("result")
        ensure(result and result["exports"][0]["module_id"] == backend, "worker initialize failed")

    def send(self, obj):
        # FileIO can make partial writes for large pipe buffers.
        with memoryview(serialized(obj)) as frame:
            sent = 0
            while sent < len(frame):
                sent += self.child.stdin.write(frame[sent:])

    def invoke(self, request, method="execute", sequence=None):
        self.sequence += 1
        number = self.sequence if sequence is None else sequence
        rid = f"h:1:{number}"
        self.send({"jsonrpc": "2.0", "id": rid, "method": method, "params": {
            "export": {"slot": "session_storage", "module_id": self.backend},
            "lineage": {"root_invocation_id": rid, "parent_invocation_id": None, "depth": 0},
            "params": request,
        }})
        return rid

    def line(self, timeout=30):
        deadline = time.monotonic() + timeout
        start = 0
        fd = self.child.stdout.fileno()
        while True:
            end = self.buffer.find(b"\n", start)
            if end >= 0:
                raw = bytes(self.buffer[:end + 1])
                del self.buffer[:end + 1]
                return raw
            start = len(self.buffer)
            ready, _, _ = select.select([fd], [], [], max(0, deadline - time.monotonic()))
            ensure(ready, "worker stdout timed out")
            batch = os.read(fd, 128 * 1024)
            ensure(batch, f"worker stdout EOF after {len(self.buffer)} buffered bytes")
            self.buffer.extend(batch)
            ensure(len(self.buffer) <= MAX_FRAME, "worker emitted too much stdout")

    def execute(self, request, method="execute", sequence=None):
        rid = self.invoke(request, method, sequence)
        raw = self.line()
        parsed = json.loads(raw)
        ensure(parsed["id"] == rid, f"unexpected response id {parsed['id']!r}; expected {rid!r}")
        return raw, parsed

    def close(self):
        if self.child.poll() is None:
            self.child.stdin.close()
            try:
                self.child.wait(5)
            except subprocess.TimeoutExpired:
                self.child.kill()
                self.child.wait(5)
        for f in (self.child.stdin, self.child.stdout, self.child.stderr):
            f.close()

    @contextlib.contextmanager
    @staticmethod
    def open(binary, backend, cap=None):
        worker = Worker(binary, backend, cap)
        try:
            yield worker
        finally:
            worker.close()


def result(reply, variant):
    payload = reply.get("result")
    if not isinstance(payload, dict) or payload.get("result") != variant:
        raise RuntimeError(f"expected {variant}: {str(reply)[:700]}")
    return payload


def make_png(size):
    def chunk(kind, content):
        check = zlib.crc32(kind + content)
        return struct.pack(">I", len(content)) + kind + content + struct.pack(">I", check)
    prefix = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
    suffix = chunk(b"IDAT", zlib.compress(b"\x00\x7f\x1b\xfe")) + chunk(b"IEND", b"")
    extra = size - len(prefix) - len(suffix) - 12
    ensure(extra > 0, "image fixture too small")
    return prefix + chunk(b"prOo", payload_bytes(extra, b"png")) + suffix


def payload_bytes(size, salt):
    # Fixed seed, no dependency on OS randomness. The hash independently binds all bytes.
    stripe = hashlib.shake_256(salt).digest(8192)
    return (stripe * (size // len(stripe) + 1))[:size]


def seed(binary, backend, root, large):
    cfg = root / "config"
    workspace = root / "workspace"
    cfg.mkdir(parents=True)
    workspace.mkdir()
    with Worker.open(binary, backend, MAX_FRAME) as worker:
        _, reply = worker.execute({"operation": "create", "config_root": str(cfg),
                                   "workspace_path": str(workspace), "session_id": SESSION_ID,
                                   "parent_session_id": None})
        desc = result(reply, "session")["descriptor"]
        session = desc["session"]
        _, reply = worker.execute({"operation": "acquire_writer", "session": session})
        lease = result(reply, "writer")["lease"]
        blobs = {}
        for name, blob in (
            ("empty", b""), ("mod1", b"\xff"), ("mod2", b"\x00\xff"),
            ("mod0", b"\x80\x00\xff"), ("128k", payload_bytes(128 * 1024, b"sample")),
            ("image5m", make_png(IMAGE_LIMIT)),
        ):
            reference = {"sha256": digest(blob), "bytes": len(blob)}
            _, reply = worker.execute({"operation": "put_blob", "lease": lease,
                                       "operation_id": str(uuid.uuid5(uuid.NAMESPACE_OID, name)),
                                       "data_base64": base64.b64encode(blob).decode(),
                                       "expected": reference})
            ensure(result(reply, "blob")["blob"] == reference, "PutBlob receipt changed")
            blobs[name] = reference
        _, reply = worker.execute({"operation": "compare_exchange_metadata", "lease": lease,
                                   "operation_id": str(uuid.uuid5(uuid.NAMESPACE_OID, "metadata")),
                                   "key": "ownership-proof", "expected_etag": None,
                                   "value": {"z": "brace\\\n田", "a": [1, None, False]}})
        result(reply, "metadata")
        _, reply = worker.execute({"operation": "open_snapshot", "session": session})
        source = result(reply, "snapshot")["snapshot"]
        _, reply = worker.execute({"operation": "write_cache", "session": session, "source": source,
                                   "key": "ownership-proof", "value": {"z": ["a"], "a": 3}})
        ensure(result(reply, "cache_written")["etag"], "real cache was not written")
        _, reply = worker.execute({"operation": "release_writer", "lease": lease})
        result(reply, "done")
    images = Path(desc["local_path"]) / "images"
    # Prepopulate read-only fixtures via filesystem only for caps, to decouple
    # input WriteBlob limits from output ReadBlob limits.
    sizes = {"over8m": 6 * MIB, "corrupted": 17}
    if large:
        sizes["max64m"] = MAX_BLOB
        sizes["over64m"] = MAX_BLOB + 1
    for label, size in sizes.items():
        original = payload_bytes(size, label.encode())
        reference = {"sha256": digest(original), "bytes": size}
        bytes_on_disk = b"!" * size if label == "corrupted" else original
        (images / reference["sha256"]).write_bytes(bytes_on_disk)
        blobs[label] = reference
    return session, images, blobs


def read_request(session, reference, by_hash, max_bytes=None):
    if by_hash:
        return {"operation": "read_blob_by_hash", "session": session, "sha256": reference["sha256"],
                "max_bytes": reference["bytes"] if max_bytes is None else max_bytes}
    return {"operation": "read_blob", "session": session, "blob": reference}


def check_blob(reply, reference, path):
    body = result(reply, "blob_data")
    ensure(body["blob"] == reference, "blob identity changed")
    encoded = body["data_base64"]
    expected_size = ((reference["bytes"] + 2) // 3) * 4
    ensure(len(encoded) == expected_size, "padded length mismatch")
    decoded = base64.b64decode(encoded, validate=True)
    ensure(len(decoded) == reference["bytes"] and digest(decoded) == reference["sha256"],
           "independent decode/digest mismatch")
    with path.open("rb") as source, memoryview(decoded) as data:
        for offset in range(0, len(data), MIB):
            ensure(source.read(min(MIB, len(data) - offset)) == data[offset:offset + MIB],
                   "decoded bytes differ from the real persisted file")
        ensure(not source.read(1), "persisted fixture unexpectedly grew")


def paired(arms, request, name, rows, *, method="execute", blob=None, path=None, error=None, variant=None):
    a, b = (w.execute(request, method=method) for w in arms)
    ensure(a[0] == b[0], f"exact stdout frame differs: {name}")
    if blob is not None:
        check_blob(a[1], blob, path)
    elif error:
        found = (a[1].get("error") or {}).get("message", "")
        ensure(error.lower() in found.lower(), f"wrong error for {name}: {a[1]}")
    elif variant is not None:
        result(a[1], variant)
    rows[name] = {"bytes_with_lf": len(a[0]), "sha256": digest(a[0])}
    return a[1]


def fatal_output(binary, backend, request, cap, sequence=None):
    with Worker.open(binary, backend, cap) as arm:
        arm.invoke(request, sequence=sequence)
        ready, _, _ = select.select([arm.child.stdout], [], [], 35)
        ensure(ready, "over-budget worker did not settle")
        ensure(not arm.buffer and arm.child.stdout.read(1) == b"", "oversized output wrote bytes")
        status = arm.child.wait(10)
        stderr = arm.child.stderr.read()
        ensure(status != 0 and b"worker output frame exceeded its configured byte budget" in stderr,
               f"unexpected oversized response: exit {status}, stderr {stderr[:700]!r}")
        return status


def run_pair(stock, candidate, backend, root, large):
    session, images, blobs = seed(stock, backend, root, large)
    rows = {}
    with Worker.open(stock, backend) as a, Worker.open(candidate, backend) as b:
        ensure(a.manifest == b.manifest, "initialize frame differs")
        rows["initialize"] = {"bytes_with_lf": len(a.manifest), "sha256": digest(a.manifest)}
        for label in ("empty", "mod1", "mod2", "mod0", "128k", "image5m"):
            blob = blobs[label]
            for hash_only in (False, True):
                paired((a, b), read_request(session, blob, hash_only), f"{label}-{'hash' if hash_only else 'ref'}",
                       rows, blob=blob, path=images / blob["sha256"])
        valid = blobs["mod2"]
        failures = [
            ("missing", read_request(session, {"sha256": MISSING, "bytes": 9}, True), "No such file"),
            ("corrupted", read_request(session, blobs["corrupted"], True), "blob hash mismatch"),
            ("wrong-length", read_request(session, dict(valid, bytes=1), False), "blob size/hash mismatch"),
            ("small-budget", read_request(session, valid, True, 1), "exceeds"),
            ("budget-too-large", read_request(session, valid, True, MAX_BLOB + 1), "budget"),
            ("uppercase", read_request(session, dict(valid, sha256=valid["sha256"].upper()), True), "invalid blob hash"),
            ("malformed-hash", read_request(session, dict(valid, sha256="!"), True), "digest"),
            ("wrong-session", read_request(dict(session, session_id=OTHER_SESSION), valid, False), "locator id/path mismatch"),
            ("wrong-shape", {"operation": "read_blob_by_hash", "session": session}, "missing field"),
            ("unnegotiated-projection", {"operation": "open_display_snapshot", "session": session}, "negotiated"),
        ]
        for name, request, error in failures:
            paired((a, b), request, name, rows, error=error)
        paired((a, b), read_request(session, valid, False), "wrong-method", rows, method="describe",
               error="is not allowed for slot session_storage")
        for branch in ("read_metadata", "read_cache"):
            request = {"operation": branch, "session": session, "key": "ownership-proof"}
            if branch == "read_cache":
                request["source"] = None
            observed = paired((a, b), request, branch, rows, variant="metadata")
            ensure(observed["result"]["document"] is not None, f"no real {branch} hit")
    ref = blobs["128k"]
    request = read_request(session, ref, True)
    expected = None
    for binary in (stock, candidate):
        with Worker.open(binary, backend, MAX_FRAME) as arm:
            raw, response = arm.execute(request)
            check_blob(response, ref, images / ref["sha256"])
            ensure(expected is None or raw == expected, "explicit frame cap altered bytes")
            expected = raw
    exact = len(expected)
    for binary in (stock, candidate):
        with Worker.open(binary, backend, exact) as arm:
            raw, _ = arm.execute(request)
            ensure(raw == expected, "line equal to exact launch budget was not preserved")
    rows["exact-cap"] = {"bytes_with_lf": exact, "sha256": digest(expected)}
    for label, req, cap in (
        ("exact-plus-one", request, exact - 1),
        ("default-over8m", read_request(session, blobs["over8m"], True), None),
    ):
        rows[label] = {"no_stdout_after_initialize_exit_status": [
            fatal_output(binary, backend, req, cap) for binary in (stock, candidate)
        ], "cap": cap if cap is not None else DEFAULT_LIMIT}
    # The successful BlobData line contains a fixed-length lowercase hash;
    # numeric byte count remains seven digits; Base64 grows in 4-byte quanta.
    overhead = exact - ((ref["bytes"] + 2) // 3) * 4 + 1  # 6-byte count -> 7
    groups, extra_id_digits = divmod(DEFAULT_LIMIT - overhead, 4)
    at_default = payload_bytes(groups * 3, b"default-exact")
    ensure(len(str(ref["bytes"])) + 1 == len(str(len(at_default))), "fixture changed count width")
    at_ref = {"sha256": digest(at_default), "bytes": len(at_default)}
    at_path = images / at_ref["sha256"]
    at_path.write_bytes(at_default)
    del at_default
    at_req = read_request(session, at_ref, True)
    seq = 10 ** extra_id_digits
    baseline = None
    for binary in (stock, candidate):
        with Worker.open(binary, backend) as arm:
            frame, parsed = arm.execute(at_req, sequence=seq)
            check_blob(parsed, at_ref, at_path)
            ensure(len(frame) == DEFAULT_LIMIT, "fixture did not reach exact standalone cap")
            ensure(baseline is None or baseline == frame, "exact standalone bytes changed")
            baseline = frame
    rows["default-exact8m"] = {"bytes_with_lf": DEFAULT_LIMIT, "sha256": digest(baseline)}
    rows["default-plus-one"] = {"no_stdout_after_initialize_exit_status": [
        fatal_output(binary, backend, at_req, None, sequence=seq * 10)
        for binary in (stock, candidate)], "cap": DEFAULT_LIMIT}
    if large:
        with Worker.open(stock, backend, MAX_FRAME) as a, Worker.open(candidate, backend, MAX_FRAME) as b:
            ref = blobs["max64m"]
            paired((a, b), read_request(session, ref, True), "raw-64m", rows,
                   blob=ref, path=images / ref["sha256"])
            paired((a, b), read_request(session, blobs["over64m"], True, MAX_BLOB),
                   "raw-64m-plus-one", rows, error="exceeds")
    return rows


def hash_file(binary):
    with binary.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--stock", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--work", type=Path, required=True)
    parser.add_argument("--features", required=True, choices=("default", "preserve_order"))
    parser.add_argument("--large", action="store_true")
    args = parser.parse_args()
    build = {label: hash_file(binary) for label, binary in
             (("stock", args.stock), ("candidate", args.candidate))}
    ensure(build["stock"] != build["candidate"], "stock/candidate binaries have identical digests")
    binaries = (args.stock.resolve(), args.candidate.resolve())
    args.work.mkdir(parents=True)
    result = {"binary_sha256": build, "features": args.features, "backends": {}}
    for backend in ("jsonl", "sqlite"):
        result["backends"][backend] = run_pair(*binaries, backend, args.work / backend, args.large)
    for name, rows in result["backends"]["jsonl"].items():
        if name.rsplit("-", 1)[0] in ("empty", "mod1", "mod2", "mod0", "128k", "image5m") or name in ("raw-64m", "exact-cap", "default-exact8m"):
            ensure(rows == result["backends"]["sqlite"][name], f"blob stdout differs across backends: {name}")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
