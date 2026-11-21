#!/usr/bin/env python3
"""Read the R46 benchmark CSV and report medians (logical heap, not RSS)."""
import argparse
import csv
from collections import defaultdict
from statistics import median
from pathlib import Path

HEADER = (
    "backend,blobs,wire_bytes,trial,variant,load_alloc_ops,load_requested_bytes,"
    "load_peak_bytes,hash_alloc_ops,hash_requested_bytes,hash_peak_bytes,"
    "load_cpu_ns,hash_cpu_ns,load_wall_ns"
)
p = argparse.ArgumentParser(description=__doc__)
p.add_argument("input", type=Path)
p.add_argument("--extract", type=Path, help="write CSV from R46-tagged Cargo test stdout")
a = p.parse_args()
data = a.input.read_text().splitlines()
if a.extract:
    data = [HEADER] + [line[line.index("R46,") + 4:] for line in data if "R46," in line]
    a.extract.write_text("\n".join(data) + "\n")
groups = defaultdict(lambda: defaultdict(list))
for parsed in csv.DictReader(data):
    key = (parsed.pop("backend"), int(parsed.pop("blobs")))
    variant = parsed.pop("variant")
    groups[key][variant].append({k: int(v) for k, v in parsed.items()})
assert groups
for (backend, blobs), variants in groups.items():
    print(f"{backend}: {blobs} regular files in blobs, {variants['stock'][0]['wire_bytes']:,} on-wire bytes")
    print("variant       n  req KiB  peak KiB  allocs  hash req KiB  hash peak KiB  load CPU ms  hash CPU ms  load wall ms")
    for variant, rows in variants.items():
        def m(key, scale=1):
            return median(row[key] for row in rows) / scale
        assert len(rows) == (7 if blobs > 492 else 16)
        assert {row['trial'] for row in rows} == set(range(len(rows)))
        print(f"{variant:11} {len(rows):3} {m('load_requested_bytes',1024):8.2f} {m('load_peak_bytes',1024):9.2f}"
              f" {m('load_alloc_ops'):7.0f} {m('hash_requested_bytes',1024):13.2f} {m('hash_peak_bytes',1024):14.2f}"
              f" {m('load_cpu_ns',1e6):12.3f} {m('hash_cpu_ns',1e6):12.3f} {m('load_wall_ns',1e6):13.3f}")
    print()
