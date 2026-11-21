#!/usr/bin/env python3
"""Time ReadRecords on warm proven or provisional SQLite snapshots, never real user data."""
import argparse
import csv
from hashlib import file_digest
import os
from pathlib import Path
import signal
import statistics
import tempfile
import time

from sdk_fixture import Client, fixture


def timeout(_sig, _frame):
    raise TimeoutError("SDK worker did not respond")


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("stock", type=Path)
    p.add_argument("candidate", type=Path)
    p.add_argument("--pairs", default=9, type=int)
    p.add_argument("--cpu", default=min(os.sched_getaffinity(0)), type=int)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    signal.signal(signal.SIGALRM, timeout)
    assert a.pairs >= 1
    binaries = [Path(x).resolve(strict=True) for x in (a.stock, a.candidate)]
    hashes = []
    for name, binary in zip(("stock", "candidate"), binaries):
        with binary.open("rb") as f:
            digest = file_digest(f, "sha256").hexdigest()
        hashes.append(digest)
        print(name, digest, flush=True)
    assert hashes[0] != hashes[1], "expected distinct source builds"
    print("CPU:", a.cpu, "ticks/second:", os.sysconf("SC_CLK_TCK"), flush=True)
    with a.output.open("w", newline="") as f:
        out = csv.writer(f, lineterminator="\n")
        out.writerow(("case", "pair", "build", "step", "after", "limit", "wall_ns", "cpu_ticks"))
        for name, count, body in (("short", 32, 512), ("many", 1536, 512), ("large", 256, 131072)):
            with tempfile.TemporaryDirectory() as tmp:
                listing, desc = fixture(binaries[0], a.cpu, Path(tmp), count, body)
                session = desc["session"]
                with Client(binaries[0], a.cpu) as seed:
                    rows = seed.call("list", audit=False, **listing)["sessions"]
                    assert rows[0]["message_count"] == count
                v1 = Path(desc["local_path"])/".storage-catalog-v1.json"
                before = v1.read_bytes()
                expected = {}
                phases = (
                    ("first", count-8, 4),
                    ("retry", count-8, 4),
                    ("back", count//2, 4),
                    ("deep", count-16, 4),
                    ("start", 0, 4),
                    ("tail", count-4, 8),
                    ("exhausted", count, 8),
                )
                values = {phase[0]: [[], []] for phase in phases}
                for pair in range(a.pairs+1):
                    for i in ((0, 1) if pair % 2 else (1, 0)):
                        with Client(binaries[i], a.cpu) as reader:
                            snapshot = reader.call("open_snapshot", session=session)["snapshot"]
                            for step, after, limit in phases:
                                cpu0 = reader.cpu()
                                start = time.perf_counter_ns()
                                result = reader.call("read_records", snapshot=snapshot, after_seq=after, limit=limit)
                                elapsed = time.perf_counter_ns()-start
                                ticks = reader.cpu()-cpu0
                                page = result["page"]
                                assert page["snapshot"] == snapshot
                                # A new opaque handle is random for each process, not ordered data.
                                del page["snapshot"]["snapshot_id"]
                                seq = list(range(after+1, min(after+limit, count)+1))
                                assert [r["session_seq"] for r in page["records"]] == seq
                                assert page["next_after_seq"] == (seq[-1] if seq and seq[-1] < count else None)
                                if step not in expected:
                                    expected[step] = result
                                assert result == expected[step], (name, step, i, pair)
                                if pair:
                                    out.writerow((name, pair, ("stock", "candidate")[i], step, after, limit, elapsed, ticks))
                                    values[step][i].append(elapsed/1e6)
                            assert v1.read_bytes() == before
                    f.flush()
                for step, sequence, _ in phases:
                    a_ms, b_ms = [statistics.median(xs) for xs in values[step]]
                    print(f"{name} N={count} {step} after={sequence}: {a_ms:.3f} -> {b_ms:.3f} ms; exact parity", flush=True)


if __name__ == "__main__":
    main()
