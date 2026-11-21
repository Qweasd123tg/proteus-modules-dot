#!/usr/bin/env python3
"""Request-thread Rust allocation counts over resident, disk and cold catalog List."""
import argparse
from contextlib import ExitStack, closing
import csv
import hashlib
import json
import os
from pathlib import Path
import signal
import sqlite3
import statistics
import tempfile

from sdk_fixture import Client, u


CASES = (
    ("ordinary", 96, ["workspace"]),
    ("nested", 128, [f"group-{n:02d}" for n in range(9)] + ["детали"]),
    ("escaped", 96, ["team % | docs", "research 🤖", "résumé", "sprint 1", "таблица"]),
)


def timeout(_sig, _frame):
    raise TimeoutError("SDK worker did not respond")


def fixture(binary, cpu, backend, folder, parts, count):
    workspace = folder.joinpath(*parts)
    workspace.mkdir(parents=True)
    cfg = folder/"config"
    roots = dict(config_root=str(cfg), workspace_path=str(workspace))
    items = []
    with Client(binary, cpu, backend) as c:
        for i in range(count):
            descriptor = c.call("create", **roots, session_id=u(i+1), parent_session_id=None)["descriptor"]
            writer = c.call("acquire_writer", session=descriptor["session"])
            lease = writer["lease"]
            body = dict(id=u(10000+i*3), role="User", phase=None,
                        parts=[dict(part_id=u(10001+i*3), provenance="user", scope="conversation",
                                    payload={"Text": {"text": "row " + str(i)}})],
                        name=None, tool_call_id=None, metadata={})
            commit = dict(lease=lease, operation_id=u(10002+i*3),
                          expected=writer["revision"], timestamp_ms=i,
                          attribution=dict(execution_id=None, thread_id=u(2000+i), turn_id=None),
                          entry=dict(kind="history_mutated",
                                     payload=dict(previous_revision=0, new_revision=1, mutation="append",
                                                  messages=[body], compaction=None, tool_results=[])))
            result = c.call("commit", commit=commit)
            assert result["ack"]["revision"]["session_seq"] == 1
            c.call("release_writer", lease=lease)
            items.append(Path(descriptor["local_path"]))
    return roots, items


def normalized(obj):
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":")).encode()


def index_stamp(card):
    st = card.stat()
    return st.st_ino, st.st_mtime_ns, st.st_ctime_ns, card.read_bytes()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("stock", type=Path)
    p.add_argument("candidate", type=Path)
    p.add_argument("--pairs", type=int, default=7)
    p.add_argument("--cpu", type=int, default=min(os.sched_getaffinity(0)))
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--parity-only", action="store_true")
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
    print("Linux CPU", a.cpu, "SDK exact parity" if a.parity_only else "request-thread Rust allocations", flush=True)

    with a.output.open("w", newline="") as data:
        out = csv.writer(data, lineterminator="\n")
        out.writerow(("backend", "case", "pair", "build", "phase", "rows", "calls", "requested"))
        for backend in ("jsonl", "sqlite"):
            for case, count, parts in CASES:
                with tempfile.TemporaryDirectory() as tmp, ExitStack() as stack:
                    params, items = fixture(binaries[0], a.cpu, backend, Path(tmp), parts, count)
                    cards = [d/".storage-catalog-v1.json" for d in items]
                    if backend == "sqlite":
                        # Pin an ordinary reader so a zero-byte WAL cannot move
                        # descriptor timestamps between the paired workers.
                        for folder in items:
                            db = folder/"journal.sqlite"
                            conn = stack.enter_context(closing(sqlite3.connect(db.as_uri()+"?mode=ro", uri=True)))
                            conn.execute("BEGIN")
                            assert conn.execute("SELECT count(*) FROM journal").fetchone() == (1,)
                    phases = ("cold", "resident", "disk", "resident_no_sidecar")
                    samples = {phase: [[], []] for phase in phases}
                    expected = {}
                    for pair in range(a.pairs+1):
                        for i in ((0, 1) if pair % 2 else (1, 0)):
                            def read(c, phase):
                                reply = c.call("list", audit=False, **params)
                                if not a.parity_only:
                                    allocations = c.allocation()
                                    assert all(n > 0 for n in allocations)
                                rows = reply["sessions"]
                                assert len(rows) == count
                                assert {row["descriptor"]["session"]["session_id"] for row in rows} == {u(n+1) for n in range(count)}
                                ordering = [(row["descriptor"]["updated_at_ms"], row["descriptor"]["session"]["key"]) for row in rows]
                                assert ordering == sorted(ordering, reverse=True)
                                assert all(row["message_count"] == 1 for row in rows)
                                exact = normalized(reply)
                                assert expected.setdefault("rows", exact) == exact, (backend, case, phase)
                                if pair and not a.parity_only:
                                    samples[phase][i].append(allocations)
                                    out.writerow((backend, case, pair, labels[i], phase, count, *allocations))

                            assert all(not card.exists() for card in cards)
                            with Client(binaries[i], a.cpu, backend) as resident:
                                read(resident, "cold")
                                v1 = [index_stamp(card) for card in cards]
                                raw = [stamp[-1] for stamp in v1]
                                assert expected.setdefault("index", raw) == raw
                                read(resident, "resident")
                                assert [index_stamp(card) for card in cards] == v1
                                with Client(binaries[i], a.cpu, backend) as disk:
                                    read(disk, "disk")
                                assert [index_stamp(card) for card in cards] == v1
                                for card in cards:
                                    card.unlink()
                                read(resident, "resident_no_sidecar")
                                assert all(not card.exists() for card in cards)
                    data.flush()
                    for phase in phases:
                        if a.parity_only:
                            print(f"{backend} {case} {phase} ({count}): exact response and v1", flush=True)
                        else:
                            a1, b1 = [tuple(int(statistics.median(n)) for n in zip(*side)) for side in samples[phase]]
                            print(f"{backend} {case} {phase} ({count}): {a1} -> {b1}; exact response and v1", flush=True)


if __name__ == "__main__":
    main()
