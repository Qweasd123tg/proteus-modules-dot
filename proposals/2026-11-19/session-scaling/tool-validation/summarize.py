import pathlib,sys,statistics,json
h=pathlib.Path(sys.argv[1])
data={}
for v in ['base','candidate']:
    d={}
    for l in (h/f'{v}-heap.txt').read_text().splitlines():
        _,case,*xs=l.split()
        d[case]=dict(zip(['allocation_calls','allocation_bytes','live_bytes','peak_bytes'],map(int,xs)))
    timing={}
    for p in sorted(h.glob(f'{v}-time-*.txt')):
        for l in p.read_text().splitlines():
            _,case,rep,n,wall,cpu=l.split()
            if int(rep)>0:
                timing.setdefault(case,[[],[]])[0].append(int(wall)/int(n));timing[case][1].append(int(cpu)/int(n))
    for case,(wall,cpu) in timing.items():
        d[case].update(median_wall_ns=round(statistics.median(wall),2),median_thread_cpu_ns=round(statistics.median(cpu),2),batches=len(wall))
    data[v]=d
print(json.dumps(data,indent=2))
