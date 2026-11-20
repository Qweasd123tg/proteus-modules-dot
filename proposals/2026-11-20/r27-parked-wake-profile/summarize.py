#!/usr/bin/env python3
"""Verify completed traces and print phase medians and stdout-byte counts (warmup excluded)."""
import json, statistics, sys
from collections import defaultdict

def med(xs): return statistics.median(xs)
print("| corpus | journal B | durable ctx rows | initial rows (+older) | head | n | launch→snapshot ms | snapshot→ACK ms | launch→ACK ms [range] | snapshot / ACK / through ACK B |")
print("|---|---:|---:|---:|---|---:|---:|---:|---:|---:|")
for fn in sys.argv[1:]:
    with open(fn,encoding="utf-8") as f: records=[json.loads(line) for line in f]
    assert records and records[0]["record"]=="manifest"
    fixtures={};groups=defaultdict(list)
    for row in records[1:]:
        s=row["shape"]
        if row["record"]=="fixture":
            assert s not in fixtures;fixtures[s]=row
            continue
        assert row["record"]=="sample" and all(row[k] for k in ("inode_and_stat_unchanged","journal_unchanged","verified_exact_checkpoint"))
        assert row["order"]==["pending_requests_updated","session_snapshot","response"]
        assert row["snapshot"]["ordinal"]==2 and row["ready"]["ordinal"]==3
        assert row["snapshot"]["arrival_ms"]<=row["ready"]["arrival_ms"]
        groups[s,row["head"]].append(row)
    for shape,f in fixtures.items():
        present,missing=groups[shape,"present"],groups[shape,"missing"]
        assert present and [r["round"] for r in present]==[r["round"] for r in missing]==list(range(1,len(present)+1))
        signatures={(r["snapshot"]["rows"],r["snapshot"]["older_rows"],r["snapshot"]["wire_bytes"],r["ready"]["wire_bytes"],r["ready"]["cumulative_stdout_bytes"]) for r in present+missing}
        assert len(signatures)==1
        n,older,ss,ack,total=signatures.pop()
        for arm,rows in (("present",present),("missing",missing)):
            start=[r["snapshot"]["arrival_ms"] for r in rows]
            stop=[r["ready"]["arrival_ms"] for r in rows]
            after=[e-b for b,e in zip(start,stop)]
            print(f'| {shape} | {f["journal_bytes"]:,} | {f["active_history_rows"]} | {n} (+{older:,}) | {arm} | {len(rows)} | {med(start):.1f} | {med(after):.1f} | {med(stop):.1f} [{min(stop):.1f}–{max(stop):.1f}] | {ss:,} / {ack:,} / {total:,} |')
