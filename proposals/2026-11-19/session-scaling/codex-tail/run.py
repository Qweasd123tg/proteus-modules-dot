import csv, itertools, os, sys, subprocess, statistics
from pathlib import Path
base=Path(__file__).resolve().parent; out=base/'raw.csv';os.chdir(base)
dims=[(0,0),(20,0),(20,32),(20,256),(49,256)]
raw=[]
for pipe in (False,True):
 for pair in range(9):
  for j,(r,f) in enumerate(dims):
   for v in (['stock','after'] if (pair+j)%2==0 else ['after','stock']):
    arg=[str(base/(v+'-executable')),str(r),str(f),'512','16']
    env=os.environ.copy()
    if pipe:env['PIPE']=str(base/'peer.py')
    line=subprocess.check_output(['taskset','-c',os.environ.get('CPU',str(min(os.sched_getaffinity(0)))),*arg],env=env,text=True).strip()
    raw.append([int(pipe),pair,v,*map(int,line.split(','))])
with open(out,'w') as fd:
 w=csv.writer(fd);w.writerow(['pipe','pair','variant','tools','files_per_tool','deltas','delta_bytes','retained_rows','before_logical_bytes','rows_evicted','after_logical_bytes','text_bytes','us']);w.writerows(raw)
for pipe,(r,f) in itertools.product((0,1),dims):
 series={v:[a[-1]/1000 for a in raw if a[0]==pipe and a[2]==v and a[3]==r and a[4]==f] for v in ('stock','after')}
 print(pipe,r,f, ' '.join(f"{v}={statistics.median(x):.3f} [{min(x):.3f},{max(x):.3f}]" for v,x in series.items()))
