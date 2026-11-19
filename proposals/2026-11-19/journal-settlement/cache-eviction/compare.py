"""Linux. Paired A/B at equal seeded cache sizes, same deterministic mtime permutation."""
from worker_probe import run
from pathlib import Path
import argparse, json, statistics
from types import SimpleNamespace
p=argparse.ArgumentParser();p.add_argument('base');p.add_argument('opt');p.add_argument('--out',required=True)
p.add_argument('--counts',default='0,2048,8192');p.add_argument('--pairs',type=int,default=5);p.add_argument('--writes',type=int,default=9)
p.add_argument('--tmpdir',default='/tmp');p.add_argument('--cpu',type=int)
a=p.parse_args();rows=[]
for r in range(a.pairs):
    order=['base','opt'] if not r%2 else ['opt','base']
    for kind in ['jsonl','sqlite']:
        cs=[int(v) for v in a.counts.split(',')]
        if r%2: cs.reverse()
        for n in cs:
            for side in order:
                opts=SimpleNamespace(worker=getattr(a,side),tmpdir=a.tmpdir,writes=a.writes,cpu=a.cpu,shuffled_times=True)
                row=run(opts,kind,n,r);row['side']=side
                rows.append(row); Path(a.out).write_text(json.dumps(rows,indent=2)+'\n')
                print(kind,n,r,side, round(statistics.median(x['wall_us'] for x in row['samples']),1),flush=True)
