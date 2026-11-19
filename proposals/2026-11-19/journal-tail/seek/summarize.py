"""Summarize medians of independent matched process pairs; all results in milliseconds."""
from pathlib import Path
from statistics import median
import csv, sys
out=Path(sys.argv[1])
runs=[list(csv.DictReader(p.open())) for p in sorted(out.glob('pair-*.csv'))]
assert runs
print('cut,phase,sample,pairs,base_wall_ms,candidate_wall_ms,median_paired_delta_pct,wins')
for n in sorted({int(r['cut']) for r in runs[0]}):
    for phase,pop in [('page1','first'),('page1','retry'),('page2','first'),('total','first')]:
        pairs=[]
        for run in runs:
            vals=[]
            for arm in ('baseline','candidate'):
                rr=[r for r in run if r['arm']==arm and int(r['cut'])==n and (int(r['pair'])==0 if pop=='first' else int(r['pair'])>0)]
                if phase!='total': rr=[r for r in rr if r['phase']==phase]
                assert rr and (len(rr)==4 if phase=='total' else True)
                reduce=sum if phase=='total' else median
                vals.append([reduce([int(r[k]) for r in rr])/1e6 for k in ('wall_ns','worker_cpu_ns')])
            pairs.append(vals)
        cols=[[v[idx][k] for v in pairs] for k in (0,1) for idx in (0,1)]
        diffs=[100*(b[0]/a[0]-1) for a,b in pairs]
        print(','.join(map(str,[n,phase,pop,len(pairs),round(median(cols[0]),4),round(median(cols[1]),4),round(median(diffs),2),sum(x<0 for x in diffs)])))
