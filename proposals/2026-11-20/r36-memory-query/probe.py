#!/usr/bin/env python3
"""Run release probes against a clean baseline and this patch using one Cargo target."""
from pathlib import Path
import csv
import os
import subprocess
import sys
import tempfile

here = Path(__file__).resolve().parent
source = Path(sys.argv[1]).resolve()
base = sys.argv[2]
target = Path(os.environ["CARGO_TARGET_DIR"]).resolve()
with tempfile.TemporaryDirectory(prefix="memory-pack-probe-", dir=here) as scratch:
    outputs = {}
    for arm in ("stock", "candidate"):
        tree = Path(scratch) / arm
        subprocess.run(["git", "-c", "advice.detachedHead=false", "clone", "--quiet", "--shared", source, tree], check=True)
        subprocess.run(["git", "checkout", "--quiet", "--detach", base], cwd=tree, check=True)
        if arm == "candidate":
            subprocess.run(["git", "apply", here / "candidate.patch"], cwd=tree, check=True)
        module = tree / "context_provider" / "memory-pack" / "src"
        (module / "allocation_probe.rs").write_bytes((here / "probe.rs").read_bytes())
        with (module / "lib.rs").open("a") as lib:
            lib.write("\n#[cfg(test)]\nmod allocation_probe;\n")
        logs = subprocess.run(
            ["cargo", "test", "--locked", "--offline", "--release", "-p", "memory-pack", "--lib",
             "measure_recall_and_snapshot_exports", "--", "--nocapture", "--test-threads=1"],
             cwd=tree, check=True, text=True, stdout=subprocess.PIPE,
             env={**os.environ, "CARGO_TARGET_DIR": str(target)},
        ).stdout
        (here / f"{arm}-probe.log").write_text(logs)
        outputs[arm] = {
            kind: [line.split(kind + " ", 1)[1] for line in logs.splitlines() if kind + " " in line]
            for kind in ("WIRE", "ALLOC")
        }
stock, candidate = outputs["stock"], outputs["candidate"]
assert len(stock["WIRE"]) == 9 and stock["WIRE"] == candidate["WIRE"], outputs
assert len(stock["ALLOC"]) == len(candidate["ALLOC"]) == 45, outputs
(here / "wire-parity.jsonl").write_text("\n".join(stock["WIRE"]) + "\n")
with (here / "allocations.csv").open("w", newline="") as f:
    writer = csv.writer(f, lineterminator="\n")
    writer.writerow(("case", "text_shape", "text_bytes", "repeat", "stock_requests", "stock_bytes",
                     "candidate_requests", "candidate_bytes"))
    for stock_row, new_row in zip(stock["ALLOC"], candidate["ALLOC"]):
        a, b = stock_row.split(","), new_row.split(",")
        assert a[:4] == b[:4]
        assert int(a[4]) > int(b[4]) and int(a[5]) > int(b[5])
        writer.writerow(a + b[4:])
print("9 exact export reply/error pairs; 45 paired allocation samples")
