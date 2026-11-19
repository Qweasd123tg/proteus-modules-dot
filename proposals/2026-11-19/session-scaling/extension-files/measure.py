#!/usr/bin/env python3
"""Compare warm panel construction + destruction in paired fresh release processes."""
import hashlib, json, shutil, statistics, subprocess, sys
from pathlib import Path
base=Path(sys.argv[1]).resolve()
res={}
for n,reps in [(0,120),(16,30),(128,8),(512,3)]:
    def call(v,exe, *args,cpu=None):
        c=[str(base/v/exe),str(n),*map(str,args)]
        return subprocess.check_output(c if cpu is None else ['taskset','-c',str(cpu),*c])
    a,b=[call(v,'time','emit') for v in ['base','after']]
    assert a==b
    h={v:json.loads(call(v,'heap','heap')) for v in ['base','after']}
    assert h['base']['after_drop']==h['after']['after_drop']==0
    group={}
    for cpu in map(int,sys.argv[2:]):
        runs={'base':[], 'after':[]}
        for i in range(7):
            for v in (['after','base'] if i%2 else ['base','after']):
                runs[v].append(int(call(v,'time','time',reps,cpu=cpu)))
        group[cpu]={'ns_per_panel':runs,'median_ns':{k:statistics.median(r) for k,r in runs.items()}}
    res[str(n)]={'files':n,'rows':n+1,'compact_json_bytes':len(a),'sha256':hashlib.sha256(a).hexdigest(),'heap':h,'groups':group,'repetitions_per_process':reps}
    print(json.dumps(res[str(n)]),file=sys.stderr,flush=True)
print(json.dumps(res,indent=2))
