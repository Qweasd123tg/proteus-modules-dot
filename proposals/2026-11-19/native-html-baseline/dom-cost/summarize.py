import statistics as st,json,sys
from pathlib import Path
d=Path(sys.argv[1]);rows=[json.loads(x) for x in (d/'timing.jsonl').read_text().splitlines()]
heap=[json.loads(x) for x in (d/'heap.jsonl').read_text().splitlines()]
group={};cpu={}
for r in rows:
    name=r['case']; ps=group.setdefault(name,{}).setdefault(r['pair'],{}); ps[r['passes']]=r['elapsed_ns']/r['loops']/1000
    cpu.setdefault(name,{}).setdefault(r['pair'],{})[r['passes']]=r['thread_cpu_ns']/r['loops']/1000
summary={}
for n,p in group.items():
    m=lambda key:st.median(key)
    h=[r for r in heap if r['case']==n]
    assert len(p)==14 and len(h)==2
    assert h[0]['passes']==1 and h[1]['passes']==2 and h[1]['allocs']==2*h[0]['allocs'] and h[1]['requested']==2*h[0]['requested'] and h[0]['peak']==h[1]['peak']
    r={'HTML_bytes':h[0]['html_bytes'],'one_us':round(m(x[1] for x in p.values()),2),'two_us':round(m(x[2] for x in p.values()),2),'paired_extra_us':round(m(x[2]-x[1] for x in p.values()),2),'extra_cpu_us':round(m(x[2]-x[1] for x in cpu[n].values()),2),'two_slower_cpu_pairs':sum(x[2]>x[1] for x in cpu[n].values()),'two_slower_pairs':sum(x[2]>x[1] for x in p.values()),'allocations_one':h[0]['allocs'],'requested_bytes_one':h[0]['requested'],'peak_bytes_one':h[0]['peak']}
    summary[n]=r;print(n,r,flush=True)
(d/'summary.json').write_text(json.dumps(summary,indent=2,ensure_ascii=False)+'\n')
