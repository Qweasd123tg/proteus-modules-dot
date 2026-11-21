"""Verify the recorded fixture invariants and summarize observed service latencies."""
import json,statistics,sys
from pathlib import Path
def read(p):return list(map(json.loads,Path(p).read_text().splitlines()))
main=read(sys.argv[1]); ext=read(sys.argv[2])
assert len(main)==220 and len(ext)==40,(len(main),len(ext))
print('backend n label stage samples memory disk replay median_service_ms')
for b in ['jsonl','sqlite']:
    for n in [1024,1025]:
        for label in ['base','cand']:
            for key,arms in [('cold',{'full1'}),('repeat',{'full2','full3'}),('alternating_full',{'altfull1','altfull2','altfull3'}),('small',{'small1','small2','small3'})]:
                rs=[r for r in main if r['backend']==b and r['n']==n and r['label']==label and r['stage'] in arms]
                expected=[0,n,0] if key=='cold' else [8,0,0] if key=='small' else [1024,0,0] if n==1024 else [1024,1,0] if label=='cand' else [0,1025,0]
                assert len(rs)==3*len(arms) and all(r['counts']==expected for r in rs)
                if label=='base':
                    assert all(r['order']==list(range(8 if key=='small' else n,0,-1)) for r in rs)
                print(b,n,label,key,len(rs),*expected,round(statistics.median(r['service_ns']/1e6 for r in rs),2))
    for label in ['base','cand']:
        expect={'cold-A':[0,1025,0],'repeat-A':[1024,1,0] if label=='cand' else [0,1025,0],'switch-B':[0,1025,0],'repeat-B':[1024,1,0] if label=='cand' else [0,1025,0],'hot-before':[0,8,0],'hot-after':[0,8,0],'hot-after2':[0,8,0],'global':[1024,1034,0] if label=='cand' else [8,2050,0],'global2':[1024,1034,0] if label=='cand' else [8,2050,0]}
        if label=='cand':expect['missing-and-corrupt-sidecars']=[0,2056,2]
        rs=[r for r in ext if r['backend']==b and r['label']==label]
        assert {r['stage']:r['counts'] for r in rs}==expect
        for r in rs:print(b,2058,label,r['stage'],1,*r['counts'],round(r['service_ns']/1e6,2))
