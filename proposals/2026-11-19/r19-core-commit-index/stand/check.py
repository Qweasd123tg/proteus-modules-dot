import pathlib, re, statistics, sys
rows=[]
for line in pathlib.Path(sys.argv[1]).read_text().splitlines():
    match=re.fullmatch(r'(\d+) (stock|candidate) n=(\d+) scans=(\d+) rows=(\d+) etag=([a-f0-9]{64}) retained_scan1=(-?\d+) elapsed_scan1_us=(\d+) elapsed_scan2_us=(\d+)',line)
    if match is None:
        raise SystemExit('unrecognized row: '+line)
    rows.append(match.groups())
assert len(rows)>=4 and len(rows)%2==0
assert len({r[5] for r in rows})==1
assert all(r[3]=='2' and r[2]==r[4] for r in rows)
for i in range(0,len(rows),2):
    assert {rows[i][1],rows[i+1][1]}=={'stock','candidate'} and rows[i][0]==rows[i+1][0]
for variant in ['stock','candidate']:
    group=[r for r in rows if r[1]==variant]
    allocated={int(r[6]) for r in group};assert len(allocated)==1
    retained=allocated.pop();assert retained>0 if variant=='stock' else retained==0
    print(variant, 'pairs=',len(group),'net first-pass live requested bytes=',retained,'median first-pass usec=',statistics.median(int(r[7]) for r in group))
print('PASS: identical full ordered row digest in every run',rows[0][5])
