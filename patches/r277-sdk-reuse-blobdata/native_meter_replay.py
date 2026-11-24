#!/usr/bin/env python3
"""Real SDK invocation allocation phase markers and blocked stdout pipe proof."""
import argparse
import array
import fcntl
import json
import os
from pathlib import Path
import select
import termios
import time

from native_protocol import Worker, MAX_FRAME, check_blob, digest, ensure, hash_file, read_request, seed

PHASES = ("backend", "converted", "counted", "flushed", "dropped")
FIELDS = ("length", "capacity", "generation", "allocation_size", "live", "peak", "requested", "events", "overflow")


class Meter:
    def __init__(self, worker):
        self.fd = worker.child.stderr.fileno()
        self.events = {}
        self.buffer = bytearray()

    def pump(self, timeout):
        readable, _, _ = select.select([self.fd], [], [], timeout)
        if not readable:
            return
        data = os.read(self.fd, 8192)
        ensure(data, "instrumented child stopped producing phase markers")
        self.buffer.extend(data)
        while (offset := self.buffer.find(b"\n")) >= 0:
            message = bytes(self.buffer[:offset + 1])
            del self.buffer[:offset + 1]
            prefix, *rest = message.decode().split()
            ensure(prefix == "R277M", f"unexpected stderr {message!r}")
            name, phase, *readings = rest
            ensure(name.startswith("component-invocation-h-1-") and phase in PHASES,
                   f"unexpected marker {message!r}")
            rid = "h:1:" + name.rsplit("-", 1)[1]
            ensure(len(readings) == len(FIELDS), f"malformed measurement: {message!r}")
            entry = dict(zip(FIELDS, map(int, readings), strict=True))
            ensure(entry["overflow"] == 0, "allocation tracker overflowed")
            inv = self.events.setdefault(rid, {})
            ensure(phase not in inv, f"duplicate phase for {rid}: {phase}")
            inv[phase] = entry

    def wait(self, ids, phase, timeout=35):
        deadline = time.monotonic() + timeout
        while not all(phase in self.events.get(rid, {}) for rid in ids):
            left = deadline - time.monotonic()
            ensure(left > 0, f"timed out waiting for {ids} {phase}")
            self.pump(left)


def pipe_pressure(fd):
    unread = array.array("i", [0])
    fcntl.ioctl(fd, termios.FIONREAD, unread, True)
    return unread[0]


def blocked_threads(child):
    states = []
    for task in Path("/proc", str(child.pid), "task").iterdir():
        try:
            name = (task / "comm").read_text().strip()
            if name.startswith("component-invoc"):
                states.append((task / "wchan").read_text().strip())
        except FileNotFoundError:
            continue
    return sorted(states)


def measure(binary, backend, session, images, ref, count):
    with Worker.open(binary, backend, MAX_FRAME) as worker:
        meter = Meter(worker)
        ids = [worker.invoke(read_request(session, ref, idx % 2 == 0)) for idx in range(count)]
        meter.wait(ids, "counted")
        pipe_fd = worker.child.stdout.fileno()
        pipe_size = fcntl.fcntl(pipe_fd, fcntl.F_GETPIPE_SZ)
        # Pipe ring pages can be occupied despite a fractional final page in
        # FIONREAD. Require a real writer parked in the kernel and the rest
        # behind its write mutex before draining anything.
        deadline = time.monotonic() + 3
        while True:
            pressure = pipe_pressure(pipe_fd)
            states = blocked_threads(worker.child)
            valid = len(states) == count and sum("pipe_write" in state for state in states) == 1 and \
                sum("futex" in state for state in states) == count - 1
            if valid:
                break
            ensure(time.monotonic() < deadline, f"no native stalled writer at {pressure}/{pipe_size}: {states}")
            meter.pump(0.02)
        meter.pump(0.12)
        ensure(0 < pressure <= pipe_size and states == blocked_threads(worker.child)
               and all("flushed" not in meter.events[rid] for rid in ids),
               "an invocation unexpectedly finished the stalled flush")
        frames = {}
        for _ in ids:
            raw = worker.line()
            reply = json.loads(raw)
            check_blob(reply, ref, images / ref["sha256"])
            rid = reply["id"]
            ensure(rid in ids and rid not in frames, "missing or duplicate response during drain")
            frames[rid] = digest(raw)
        meter.wait(ids, "dropped")
        return {"pipe_capacity": pipe_size, "pipe_bytes_while_held": pressure,
                "kernel_wait_states": states, "frames": frames, "events": meter.events}


def verify(stock, candidate, raw_size):
    require = "native response ownership evidence"
    expected = (raw_size + 2) // 3 * 4
    ensure(stock["frames"] == candidate["frames"], "instrumented raw wire differs")
    for rid in stock["events"]:
        a, b = (side["events"][rid] for side in (stock, candidate))
        for s in (a, b):
            ensure(tuple(s) == PHASES, f"incomplete or out of order phase trace for {rid}")
            be, cv, ct, fl, dr = (s[k] for k in PHASES)
            ensure(be["capacity"] == be["length"] == be["allocation_size"] == expected
                   and be["generation"] > 0, "native Base64 did not allocate one tight tracked string")
            ensure(all(phase["length"] == phase["allocation_size"] == phase["live"] == expected
                       for phase in (cv, ct, fl)), "retained bytes grew during count/write/flush")
            ensure(cv["generation"] == ct["generation"] == fl["generation"] > 0,
                   "transport replaced the serialized string allocation")
            ensure(dr["live"] == 0, "payload is still live after dropping RPC response")
            ensure(all((phase["requested"], phase["events"]) == (cv["requested"], cv["events"])
                       for phase in (ct, fl, dr)), "a later transport phase allocated a large buffer")
        ensure(a["converted"]["generation"] != a["backend"]["generation"], require + ": stock copied")
        ensure(b["converted"]["generation"] == b["backend"]["generation"], require + ": candidate moved")
        ensure(a["converted"]["requested"] - b["converted"]["requested"] == expected, require + ": requested bytes")
        ensure(a["converted"]["peak"] - b["converted"]["peak"] == expected, require + ": conversion peak")
        ensure(a["converted"]["events"] - b["converted"]["events"] == 1, require + ": allocation count")
        ensure(a["backend"] == b["backend"], require + ": identical prior read/encode phase")
        complete_a, complete_b = (max(reading["peak"] for reading in side.values()) for side in (a, b))
        ensure(complete_a == max(a["backend"]["peak"], 2 * expected),
               require + ": stock full measured span")
        ensure(complete_b == max(b["backend"]["peak"], expected),
               require + ": candidate full measured span")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--stock", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--work", type=Path, required=True)
    args = parser.parse_args()
    stock, candidate = args.stock.resolve(), args.candidate.resolve()
    out = {"stock_sha256": hash_file(stock), "candidate_sha256": hash_file(candidate),
           "backends": {}}
    ensure(out["stock_sha256"] != out["candidate_sha256"], "used the same binary for both arms")
    args.work.mkdir(parents=True)
    for backend in ("jsonl", "sqlite"):
        session, images, refs = seed(stock, backend, args.work / backend, False)
        ref = refs["image5m"]
        out["backends"][backend] = {}
        for count in (1, 4):
            a, b = (measure(binary, backend, session, images, ref, count) for binary in (stock, candidate))
            verify(a, b, ref["bytes"])
            out["backends"][backend][str(count)] = {"raw_blob_bytes": ref["bytes"],
                                                  "held_responses": count, "stock": a, "candidate": b,
                                                  "through_flush_peak_by_invocation": {
                                                      label: {rid: max(p["peak"] for p in phases.values())
                                                              for rid, phases in frame["events"].items()}
                                                      for label, frame in (("stock", a), ("candidate", b))
                                                  }}
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
