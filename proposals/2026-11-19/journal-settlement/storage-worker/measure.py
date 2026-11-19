#!/usr/bin/env python3
"""Compare only matched requests on freshly prepared independent local sessions."""
import argparse, csv, os, re, statistics as st, subprocess, sys
from pathlib import Path
p=argparse.ArgumentParser()
p.add_argument("base",type=Path); p.add_argument("after",type=Path); p.add_argument("out",type=Path)
p.add_argument("--pairs",type=int,default=8); p.add_argument("--lengths",default="0,128,512"); p.add_argument("--cpu",type=int)
a=p.parse_args(); a.out.mkdir(exist_ok=True,parents=True)
if a.cpu is not None: os.sched_setaffinity(0,{a.cpu})
rows=[]
def run(arm,pair):
    cmd=[str(getattr(a,arm).resolve()),"--exact","tests::performance::perf7_compare","--ignored","--nocapture","--test-threads=1"]
    res=subprocess.run(cmd,env={**os.environ,"PERF7_LENGTHS":a.lengths},stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,check=True).stdout
    (a.out/f"{arm}-{pair}.log").write_text(res)
    found=re.findall(r"SAMPLE,(Jsonl|Sqlite),(\d+),(\d+),(\d+),(\d+),(\d+),(\d+),(\d+)",res)
    assert len(found)==6*len(a.lengths.split(',')),(cmd,found)
    for backend,*nums in found:
        n,iter_,open_ns,opened,cmp_ns,decoded,rehash=map(int,nums)
        if pair: rows.append([pair,arm,backend,n,iter_,open_ns,opened,cmp_ns,decoded,rehash])
for pair in range(a.pairs+1):
    for arm in (("base","after") if pair%2==0 else ("after","base")): run(arm,pair)
with (a.out/"samples.csv").open('w') as f:
    w=csv.writer(f); w.writerow("pair arm backend n iter open_ns open_decoded cmp_ns cmp_decoded dedicated_verify_bytes".split()); w.writerows(rows)
def pair_values(backend,n,metric,arm):
    return [st.median([f[5]+f[7] if metric=="open+first" else f[7] for f in rows if f[0]==i and f[1:4]==[arm,backend,n] and (metric=="compare" or f[4]==0)]) for i in range(1,a.pairs+1)]
with (a.out/"summary.csv").open('w') as f:
    w=csv.writer(f);w.writerow("backend old_records metric base_us after_us median_paired_delta_pct faster pairs".split())
    for backend in ("Jsonl","Sqlite"):
        for n in map(int,a.lengths.split(',')):
            for metric in ["compare","open+first"]:
                b=pair_values(backend,n,metric,"base"); c=pair_values(backend,n,metric,"after")
                w.writerow([backend,n,metric,round(st.median(b)/1000,3),round(st.median(c)/1000,3),round(st.median(y/x-1 for x,y in zip(b,c))*100,4),sum(y<x for x,y in zip(b,c)),a.pairs])
print((a.out/"summary.csv").read_text())
