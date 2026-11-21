from pathlib import Path
from statistics import median
import json,sys
rows=list(map(json.loads,Path(sys.argv[1]).read_text().splitlines()))
assert len(rows)==112
for blob in (0,492):
    for case in ('cold_list','writer_open_snapshot'):
        for b in ('jsonl','sqlite'):
            items=[r for r in rows if (r['blobs_per_session'],r['case'],r['backend'])==(blob,case,b)]
            def values(variant,key):
                return [r[key]/1e6 for r in sorted(items,key=lambda x:x['trial']) if r['variant']==variant]
            assert len(items)==14
            print(b,case,'blobs',blob,':',end=' ')
            for k in (('encode_cpu_ns',) if 'encode_cpu_ns' in items[0] else ())+('encode_ns','rpc_ns'):
                s,c=(values(v,k) for v in ('stock','candidate'))
                print(f'{k[:-3]} ms {median(s):.4f} -> {median(c):.4f}, paired median {median(100*(1-y/x) for x,y in zip(s,c)):.1f}% reduction, faster {sum(x>y for x,y in zip(s,c))}/{len(s)}; ranges {min(s):.3f}..{max(s):.3f} / {min(c):.3f}..{max(c):.3f}',end='; ')
            print('sidecar bytes', min(r['bytes'] for r in items),'..',max(r['bytes'] for r in items))
