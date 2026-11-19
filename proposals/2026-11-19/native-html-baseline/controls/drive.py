"""Native real TestAppContext delayed-push and above-threshold controls, no instrumented parser."""
import argparse,hashlib,json,os,statistics,subprocess
from pathlib import Path
p=argparse.ArgumentParser(description=__doc__)
for k in ('baseline','candidate','cases'): p.add_argument(k,type=Path)
p.add_argument('--only',nargs='*',help='list of mode/case keys, default all');p.add_argument('--cpu',type=int,required=True);p.add_argument('--pairs',type=int,default=12);p.add_argument('--runs',type=int,default=8)
a=p.parse_args();os.sched_setaffinity(0,{a.cpu})
out={'cpu':a.cpu,'pairs':a.pairs,'runs_per_process':a.runs,
     'input_sha256':hashlib.sha256(a.cases.read_bytes()).hexdigest(),
     'elf_sha256':[hashlib.sha256(b.read_bytes()).hexdigest() for b in (a.baseline,a.candidate)],'work':{}}
for scenario,name,views in [('init','md-selection',32),('append','md-selection',32),('append','md-table-4096',32),
                            ('init','plain-4097',32),('init','table-4097',32),('init','long-53k',8),('init','long-markdown-html',4)]:
    if a.only and scenario+'/'+name not in a.only:continue
    pairs=[];raw=[];cpairs=[];craw=[]
    for i in range(a.pairs):
        order=(0,1) if i%2==0 else (1,0)
        results=[None,None];cycles=[None,None]
        for j in order:
            b=(a.baseline,a.candidate)[j]
            r=json.loads(subprocess.check_output([b.resolve(),a.cases.resolve(),scenario,name,str(views),str(a.runs)]))
            assert len(r['samples_ns'])==a.runs and r['workload']==name
            results[j]=r['samples_ns'];cycles[j]=r['cpu_ns']
        pairs.append(list(map(statistics.median,results)));raw.append(results);cpairs.append(list(map(statistics.median,cycles)));craw.append(cycles)
    delta=[b/a-1 for a,b in pairs];cdelta=[b/a-1 for a,b in cpairs]
    out['work'][scenario+'/'+name]={'states':views,'ms_before_after':[statistics.median(x)/1e6 for x in zip(*pairs)],
        'median_paired_delta_percentage':100*statistics.median(delta),'pairs_faster':sum(x<0 for x in delta),'paired_raw_ns':raw,'process_cpu_ms':[statistics.median(x)/1e6 for x in zip(*cpairs)],'process_cpu_median_paired_delta_percentage':100*statistics.median(cdelta),'cpu_pairs_faster':sum(x<0 for x in cdelta),'paired_process_cpu_raw_ns':craw}
print(json.dumps(out,indent=2))
