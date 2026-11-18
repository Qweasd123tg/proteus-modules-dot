"""Build and time the actual backend before/after. Linux, Rust 1.95, pinned checkout.

Usage: python native_benchmark.py /path/to/Proteus-modules > native-results.json
Requires dependency access or seeded CARGO_HOME; supports CARGO_NET_OFFLINE=true.
Temporary source copies only. Respects CARGO_TARGET_DIR to reuse the build cache.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import statistics
import subprocess
import sys
import tempfile

HERE = Path(__file__).resolve().parent
BASE = "37b3d9c4db0b8cb5c4ca6cec690ebf7ce64c1979"
FILE = "storage/session-storage/src/backend/sqlite.rs"
TEST = "backend::sqlite::dot_perf_probe::measure"


def build(checkout, work, target, side):
    src = work / ("src-" + side)
    env = dict(os.environ, CARGO_TARGET_DIR=str(target))
    # --shared only reads objects from the caller's clone; do not change its worktrees.
    subprocess.run(["git", "clone", "-q", "--shared", "--no-checkout", str(checkout), str(src)], check=True)
    subprocess.run(["git", "checkout", "-q", "--detach", BASE], cwd=src, check=True)
    if side == "after":
        subprocess.run(["git", "apply", "--whitespace=error", str(HERE / "sqlite-journal-reads.patch")], cwd=src, check=True)
    probe = src / "storage/session-storage/src/backend/sqlite/dot_perf_probe.rs"
    probe.parent.mkdir(exist_ok=True)
    shutil.copyfile(HERE / "native_probe.rs", probe)
    with open(src / FILE, "a") as f:
        f.write("\n#[cfg(test)]\nmod dot_perf_probe;\n")
    output = subprocess.check_output(["cargo", "test", "-p", "session-storage", "--locked", "--release",
                                      "--lib", "--no-run", "--message-format=json"], env=env, cwd=src, text=True)
    executable = next(Path(obj["executable"]) for line in output.splitlines()
                      if (obj := json.loads(line)).get("executable") and obj["target"]["name"] == "session_storage")
    return shutil.copy2(executable, work / side)


def invoke(binary, mode, dir_, n, size, digest=""):
    env = dict(os.environ, JOURNAL_BENCH_MODE=mode, JOURNAL_BENCH_DIR=str(dir_), JOURNAL_BENCH_ROWS=str(n),
               JOURNAL_BENCH_BYTES=str(size), JOURNAL_BENCH_SHA256=digest)
    text = subprocess.check_output([binary, "--exact", TEST, "--ignored", "--nocapture",
                                    "--test-threads=1"], env=env, text=True)
    assert "1 passed" in text, text
    if mode != "seed":
        match = re.search(r"MEASURE mode=(\w+) rows=(\d+) us=(\d+) rss_kib=(\d+) sqlite=([\d.]+)", text)
        assert match and (match[1], int(match[2])) == (mode, n), text
        return {"us": int(match[3]), "rss_kib": int(match[4]), "sqlite": match[5]}


def main(checkout):
    with tempfile.TemporaryDirectory() as temp:
        work = Path(temp)
        target = Path(os.environ.get("CARGO_TARGET_DIR", work / "target")).resolve()
        bins = {side: build(checkout, work, target, side) for side in ["before", "after"]}
        version = subprocess.check_output(["rustc", "-V"], text=True).strip()
        out = dict(revision=BASE, rustc=version, profile="release test harness, single test per process",
                   runner="Linux /proc/self/status VmHWM; 8 alternating paired runs after one warmup pair")
        for mode, n, size in [("next", 12_000, 256), ("cold_hash", 1, 16 * 2**20), ("prefix_hash", 1, 16 * 2**20)]:
            dir_ = work / f"fixture-{n}"
            if not dir_.exists():
                invoke(bins["before"], "seed", dir_, n, size)
            digest = hashlib.sha256()
            payload_bytes = 0
            with sqlite3.connect(f"file:{dir_/'journal.sqlite'}?mode=ro", uri=True) as db:
                for seq, data in db.execute("SELECT sequence,payload FROM journal ORDER BY sequence"):
                    digest.update(data)
                    payload_bytes += len(data)
                assert seq == n
            sha = digest.hexdigest()
            data = {s: [] for s in bins}
            for i in range(9):
                for s in (("before", "after") if i % 2 == 0 else ("after", "before")):
                    res = invoke(bins[s], mode, dir_, n, size, sha)
                    if i:
                        data[s].append(res)
            out[mode] = dict(rows=n, message_text_bytes=size, total_payload_bytes=payload_bytes,
                             sha256=sha, samples=data, median={s: {
                                 k: statistics.median(r[k] for r in records) for k in ["us", "rss_kib"]
                             } for s, records in data.items()})
        print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main(Path(sys.argv[1]).resolve())
