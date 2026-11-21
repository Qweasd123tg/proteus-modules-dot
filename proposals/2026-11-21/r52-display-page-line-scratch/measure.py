#!/usr/bin/env python3
"""Paired real SDK ReadDisplayRecords allocation counts on healthy local fixtures."""
import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import signal
import statistics
import tempfile

from sdk_fixture import Client, fixture


def timeout(_sig, _frame):
    raise TimeoutError("SDK worker did not respond")


def normalized(obj):
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":")).encode()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("stock", type=Path)
    p.add_argument("candidate", type=Path)
    p.add_argument("--pairs", type=int, default=7)
    p.add_argument("--parity-only", action="store_true", help="skip allocator instrumentation")
    p.add_argument("--cpu", type=int, default=min(os.sched_getaffinity(0)))
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    assert a.pairs >= 1
    signal.signal(signal.SIGALRM, timeout)
    binaries = [x.resolve(strict=True) for x in (a.stock, a.candidate)]
    labels = ("stock", "candidate")
    hashes = []
    for name, binary in zip(labels, binaries):
        with binary.open("rb") as f:
            hashes.append(hashlib.file_digest(f, "sha256").hexdigest())
        print(name, hashes[-1], flush=True)
    assert hashes[0] != hashes[1]
    print("Linux CPU", a.cpu, "parity only" if a.parity_only else "measured only Rust allocations on request thread", flush=True)
    with a.output.open("w", newline="") as data:
        out = csv.writer(data, lineterminator="\n")
        out.writerow(("backend", "case", "pair", "build", "phase", "rows", "calls", "requested"))
        for backend in ("jsonl", "sqlite"):
            for name, count, text, limit in (("ordinary", 504, 512, 320),
                                             ("mid", 300, 4400, 128),
                                             ("oversize", 40, 32768, 24)):
                with tempfile.TemporaryDirectory() as tmp:
                    _, desc = fixture(binaries[0], a.cpu, backend, Path(tmp), count, text)
                    phases = (("first", 0), ("continue", limit), ("rewind", count//4), ("retry", count//4))
                    samples = {phase: [[], []] for phase, _ in phases}
                    oracle = {}
                    for pair in range(a.pairs+1):
                        for i in ((0, 1) if pair % 2 else (1, 0)):
                            with Client(binaries[i], a.cpu, backend) as reader:
                                begin = reader.call("open_display_snapshot", session=desc["session"])["projection"]
                                snapshot = begin["snapshot"]
                                assert snapshot["revision"]["session_seq"] == count
                                assert len(begin["state"]["conversation"]["messages"]) == count
                                stable = dict(snapshot); del stable["snapshot_id"]
                                stable_begin = normalized(dict(snapshot=stable, state=begin["state"]))
                                assert oracle.setdefault("open", stable_begin) == stable_begin
                                for phase, after in phases:
                                    result = reader.call("read_display_records", snapshot=snapshot, after_seq=after, limit=limit)
                                    if not a.parity_only:
                                        events, amount = reader.allocation()
                                        assert events > 0 and amount > 0
                                    page = result["page"]
                                    assert page["snapshot"] == snapshot
                                    page["snapshot"] = stable
                                    stop = min(count, after+limit)
                                    assert [r["session_seq"] for r in page["records"]] == list(range(after+1,stop+1))
                                    assert page["next_after_seq"] == (stop if stop < count else None)
                                    exact = normalized(result)
                                    assert oracle.setdefault(phase, exact) == exact, (backend, name, phase)
                                    if pair and not a.parity_only:
                                        samples[phase][i].append((events, amount))
                                        out.writerow((backend, name, pair, labels[i], phase,
                                                      stop-after, events, amount))
                    data.flush()
                    for phase, _ in phases:
                        if a.parity_only:
                            print(f"{backend} {name} {phase}: response + projection exact", flush=True)
                        else:
                            rows = samples[phase]
                            numbers = [tuple(int(statistics.median(x)) for x in zip(*side)) for side in rows]
                            print(f"{backend} {name} {phase}: {numbers[0]} -> {numbers[1]} ({len(rows[0])} pairs), "
                                  "response + projection exact", flush=True)


if __name__ == "__main__":
    main()
