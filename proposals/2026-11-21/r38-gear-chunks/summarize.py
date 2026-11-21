"""Summarize separate counted/uncounted runs. Ignore the first 3 of 27 pairs."""
import csv, statistics as st, sys
from pathlib import Path
p=Path(sys.argv[1]) if len(sys.argv)>1 else Path(__file__).resolve().parent
def load(name):
    data={}
    with (p/(name+'.csv')).open() as f:
        rows=csv.reader(f)
        assert next(rows)==['PARITY','60']
        for tag,mode,n,chunks,r,new,cpu,elapsed,cnt,sha in rows:
            assert tag=='ROW'
            key=(mode,int(n),int(chunks),int(r),new=='true')
            assert key not in data
            data[key]=(int(cpu),int(elapsed),int(cnt),sha)
    return data
work,timing=load('work'),load('timing')
assert len(work)==10 and len(timing)==270
print('mode,bytes,chunks,base_updates,new_updates,base_p50_cpu_ns,new_p50_cpu_ns,median_paired_cpu_ratio,new_faster_of_24,manifest_sha256')
for mode,n,k,r,new in work:
    if new: continue
    w=work[mode,n,k,0,False];c=work[mode,n,k,0,True]
    b=[];a=[]
    for i in range(27):
        s=timing[mode,n,k,i,False];v=timing[mode,n,k,i,True]
        assert s[3]==v[3]==w[3]==c[3]
        if i<3:continue
        b.append(s[0]);a.append(v[0])
    print(','.join(map(str,(mode,n,k,w[2],c[2],st.median(b),st.median(a),round(st.median(new/old for new,old in zip(a,b)),6),sum(new<old for new,old in zip(a,b)),w[3]))))
