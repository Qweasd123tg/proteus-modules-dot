#!/usr/bin/env python3
"""Summarize synthetic inventory measurements and genuine worker parity/timings."""
import argparse
import csv
import json
from pathlib import Path
from statistics import median

p=argparse.ArgumentParser(description=__doc__)
p.add_argument("probe_log",type=Path)
p.add_argument("sdk_jsonl",type=Path)
p.add_argument("--extract",type=Path)
a=p.parse_args()
header="case,entries,trial,variant,alloc_ops,requested_bytes,peak_bytes,cpu_ns,wall_ns"
lines=[header]+[l[l.index("R47,")+4:] for l in a.probe_log.read_text().splitlines() if "R47," in l]
if a.extract:
    a.extract.write_text("\n".join(lines)+"\n")
rows=list(csv.DictReader(lines))
assert len(rows)==240

def summary(stock,candidate):
    assert len(stock)==len(candidate)
    paired=median(100*(1-c/s) for s,c in zip(stock,candidate) if s)
    return f"{median(stock):.4f} -> {median(candidate):.4f}; paired {paired:+.1f}% less; range {min(stock):.4f}–{max(stock):.4f} / {min(candidate):.4f}–{max(candidate):.4f}"

def values(items,key,v,div):
    return [int(r[key])/div for r in sorted((x for x in items if x['variant']==v),key=lambda r:int(r['trial']))]

for case in ("missing","flat","nested"):
    subset=[r for r in rows if r['case']==case]
    assert len(subset)==80
    print(case,subset[0]['entries'],"entries, 40 pairs")
    for key,div in (("alloc_ops",1),("requested_bytes",1),("peak_bytes",1),("cpu_ns",1000),("wall_ns",1000)):
        x,y=(values(subset,key,v,div) for v in ('stock','candidate'))
        print(" ",key if div==1 else key.replace("_ns","_us"), summary(x,y))
sdk=[json.loads(l) for l in a.sdk_jsonl.read_text().splitlines()]
for backend in ('jsonl','sqlite'):
    subset=[r for r in sdk if r['backend']==backend and 'trial' in r]
    assert len(subset)==14
    assert any(r.get('stale_repair_identical') and r['backend']==backend for r in sdk)
    print(backend,"full SDK RPC, 7 pairs, exact bytes + rows; valid sidecars not rewritten")
    for key in ("cold_ns","disk_ns","cold_worker_cpu_ns","disk_worker_cpu_ns"):
        if key not in subset[0]:
            continue
        x,y=(values(subset,key,v,1_000_000) for v in ('stock','candidate'))
        print(" ",key.replace("_ns","_ms"), summary(x,y))
