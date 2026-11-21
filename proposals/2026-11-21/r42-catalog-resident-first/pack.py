"""Losslessly compress repeated visit-order arrays into streams of inclusive ascending/descending ID ranges."""
import sys,json
from pathlib import Path
src=[Path(p) for p in sys.argv[1:]]
rows=[]; orders=[]
for p in src:
    for r in map(json.loads,p.read_text().splitlines()):
        ids=r.pop('order'); ranges=[]; i=0
        while i<len(ids):
            j=i+1
            if j<len(ids) and abs(ids[j]-ids[i])==1:
                step=ids[j]-ids[i]
                while j<len(ids) and ids[j]==ids[j-1]+step:j+=1
            ranges.append([ids[i],ids[j-1]])
            i=j
        reconstructed=[x for a,b in ranges for x in range(a,b+(1 if b>=a else -1),1 if b>=a else -1)]
        assert ids==reconstructed
        if ranges not in orders:orders.append(ranges)
        r['order']=orders.index(ranges);rows.append(r)
print(json.dumps({'orders':orders,'observations':rows},separators=(',',':')))
