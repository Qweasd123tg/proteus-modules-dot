import csv, pathlib, statistics as s, sys
root=pathlib.Path(sys.argv[1]); rows=[]
for v in ('before','after'):
    for l in (root/f'{v}.log').read_text().splitlines():
        if 'CACHE,' not in l: continue
        b,c,i,size,n,alloc,peak,t,etag=l.split('CACHE,')[1].split(',')
        rows.append((v,b,c,int(i),int(size),int(n),int(alloc),int(peak),int(t),etag))
d={(r[0],r[1],r[2],r[3]):r for r in rows}
assert len(d)==len(rows)==48
for (v,b,c,i),r in d.items():
    if v=='before':
        o=d['after',b,c,i]
        assert r[4]==o[4] and r[-1]==o[-1]
with (root/'results.csv').open('w') as f:
    w=csv.writer(f,lineterminator='\n'); w.writerow('version backend fixture pass file_bytes alloc_calls requested_bytes net_peak_bytes wall_us value_etag'.split()); w.writerows(rows)
for b in ('Jsonl','Sqlite'):
    for c in ['tiny','256KiB','structured','4MiB']:
        for v in ['before','after']:
            subset=[r for r in rows if r[0]==v and r[1]==b and r[2]==c]
            print(b,c,v,*(s.median(r[n] for r in subset) for n in (4,5,6,7,8)))
