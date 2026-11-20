"""Extract test oracle, thread identity witnesses, and worker/tree PSS."""
import argparse
import json
import re
from pathlib import Path
from statistics import median

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('path', type=Path, nargs='+')
for d in p.parse_args().path:
    s=json.loads((d/'summary.json').read_text())
    raw=(d/'worker.stderr').read_text()
    begin=re.findall(r'^DIAG_FOLD begin ThreadId\((\d+)\)$',raw,re.M)
    end=re.findall(r'^DIAG_FOLD end ThreadId\((\d+)\) (\d+) (\w+)$',raw,re.M)
    assert begin == [x[0] for x in end]
    big=[(tid,int(us)/1000) for tid,us,ok in end if int(us)>500000 and ok=='true']
    assert len(big)==4, big
    assert len({tid for tid,_ in big})==(4 if s['fold_requested']=='direct' else 1)
    statuses=[r['http_status'] for r in s['cold']]
    trace=[json.loads(l) for l in (d/'trace.jsonl').read_text().splitlines()]
    phases={}
    for phase in ['cold','retained','retained_near_10','retained_near_60']:
        rows=[r for r in trace if r['stage']==phase]
        if rows:
            f=max if phase=='cold' else median
            phases[phase]={
              'tree_pss_mib':round(f(r['pss_kib'] for r in rows)/1024,2),
              'worker_pss_mib':round(f(sum(v['pss'] for v in r['processes'] if v['role']=='worker') for r in rows)/1024,2),
            }
    assert s['passed'] and statuses==[200]*4 and s['canonical_sha_before']==s['canonical_sha_after']
    print(json.dumps(dict(run=d.name,placement=s['fold_requested'],passed=s['passed'],
        fold_ids=[tid for tid,_ in big],fold_ms=[ms for _,ms in big],
        first_text_ms=s['hot']['first_text_ms'],durable_open_ms=s['hot']['durable_open_upper_bound_ms'],
        hot_settled_ms=s['hot']['ms'],cold_ms=[r['ms'] for r in s['cold']],
        worker_arena_limit=s['worker_arena_verified'],phases=phases)))
