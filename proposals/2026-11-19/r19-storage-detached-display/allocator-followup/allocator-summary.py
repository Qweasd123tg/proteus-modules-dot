"""Summarize idle and peak metrics, with allocator capacity distinct from PSS."""
import argparse, json, re
from pathlib import Path
from statistics import median
from xml.etree import ElementTree as ET

def arena_xml(path):
    text=path.read_text()
    samples=[]
    for epoch,pid,xml in re.findall(r"SAMPLE (\d+) (\d+)\n(<malloc .*?</malloc>)",text,re.S):
        root=ET.fromstring(xml)
        count=lambda k,t: int(root.find(f"{k}[@type='{t}']").get("size"))
        samples.append(dict(ns=int(epoch),pid=int(pid),heaps=len(root.findall("heap")),
            arena_system=count("system","current"),arena_free=count("total","fast")+count("total","rest"),
            mmapped=count("total","mmap")))
    return samples

def aggregate(out):
    s=json.loads((out/'summary.json').read_text())
    trace=[json.loads(l) for l in (out/'trace.jsonl').read_text().splitlines()]
    select=lambda phase:[r for r in trace if r['stage']==phase]
    units=lambda k:round(k/1024,2)
    workers=lambda r:sum(p['pss'] for p in r['processes'] if p['role']=='worker')
    cold=select('cold'); idle=select('retained_near_10')
    assert cold and idle
    data=dict(run=out.name,passed=s['passed'],worker_sha256=s['worker_sha256'],
        worker_arena=s.get('worker_arena_verified'),first_text_ms=s['hot'].get('first_text_ms'),
        archive_seconds=[round(r['ms']/1000,3) for r in s['cold']],
        peak_mib=units(max(r['pss_kib'] for r in cold)),
        worker_peak_mib=units(max(workers(r) for r in cold)),
        idle_near_10s_mib=units(median(r['pss_kib'] for r in idle)),
        worker_idle_mib=units(median(workers(r) for r in idle)))
    p=out/'arena-trace.txt'
    if p.exists():
        items=arena_xml(p)
        post=select('idle_post_trim')
        if post:
            data['trim_event_count']=p.read_text().count('IDLE_TRIM 1')
            data['after_trim_mib']=units(median(r['pss_kib'] for r in post))
            data['after_trim_worker_mib']=units(median(workers(r) for r in post))
        lo,hi=idle[0]['monotonic_ns'],idle[-1]['monotonic_ns']
        exact=[r for r in items if lo<=r['ns']<=hi and r['pid'] in {p['pid'] for i in idle for p in i['processes'] if p['role']=='worker'}]
        if exact:
            data['glibc_near_10s']=dict(samples=len(exact),heaps=median(r['heaps'] for r in exact),
                **{k+'_mib':round(median(r[k] for r in exact)/1048576,2) for k in ('arena_system','arena_free','mmapped')})
    return data

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('out',type=Path,nargs='+')
    args=p.parse_args()
    for out in args.out: print(json.dumps(aggregate(out)))
