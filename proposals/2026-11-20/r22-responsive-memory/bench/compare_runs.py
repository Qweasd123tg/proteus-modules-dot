#!/usr/bin/env python3
"""Print per-run metrics before aggregation. Never pool different stand/client/fixture/relay identities."""
import json
import sys
from collections import defaultdict
from statistics import median

def cohort(r):
    fixed = ('stand_sha256','sampler_sha256','profile_sha256','client','desktop_client_sha256','reference_sha256',
             'wire_observer','history_global_deadline_s','index_state','canonical_sha_before','fixture_manifest_sha256',
             'archives','rows','companion_hashes','additional_observers')
    return tuple(json.dumps(r.get(k),sort_keys=True) for k in fixed)

def fmt(v):
    if v is None: return 'n/a'
    return f'{v:.3f}'.rstrip('0').rstrip('.')

def metrics(r):
    cold = r.get('first_open',{})
    pss = r.get('page_window_pss',{}).get('peak_kib',{})
    hot = r.get('hot',{})
    latest = [q.get('api_ms') for q in cold.get('rust_api',[])]
    return [round(max(latest)/1000,3) if len(latest)==4 and all(v is not None for v in latest) else None,
            round(hot['send_to_sse_first_text_ms']/1000,3) if hot.get('send_to_sse_first_text_ms') is not None else None,
            round(pss['tree']/1024,1) if 'tree' in pss else None,
            round(pss['core']/1024,1) if 'core' in pss else None,
            round(pss['worker']/1024,1) if 'worker' in pss else None]

def report(rows):
    groups = defaultdict(list)
    for r in rows:
        groups[cohort(r)].append(r)
    for gid,rs in enumerate(groups.values(),1):
        arms = defaultdict(list)
        print(f'\nCohort {gid}: relay={rs[0].get("wire_observer")} stand={(rs[0].get("stand_sha256") or "?")[:12]} '
              f'client={(rs[0].get("desktop_client_sha256") or "?")[:12]} rows={rs[0].get("rows")}')
        print('run | ok/n archives | all gates | largest Rust history call s (includes timeout) | first text s | tree peak MiB | core peak MiB | worker peak MiB')
        for r in sorted(rs,key=lambda x:x.get('cold_start_unix_ns') or 0):
            cold = r.get('first_open',{})
            passed = bool(r['passed'])
            m = metrics(r)
            head = [r['name'],f'{cold.get("ok_count",0)}/{cold.get("n",0)}',str(passed)]
            print(' | '.join(head+[fmt(v) for v in m]))
            arms[(r.get('core_sha256'),r.get('worker_sha256'))].append((passed,m))
        for (c,w),observations in arms.items():
            # A timeout/failure remains in run table, never silently discarded from aggregate.
            print(f'  {(c or "?")[:10]}+{(w or "?")[:10]}: '
                  f'{sum(ok for ok,_ in observations)}/{len(observations)} runs passed',end='')
            if len(observations)>=2 and all(ok and None not in vs for ok,vs in observations):
                print('; med [min,max]: '+', '.join(
                    f'{fmt(median(values))} [{fmt(min(values))},{fmt(max(values))}]'
                    for values in zip(*(vs for _,vs in observations))),end='')
            print()

if __name__=='__main__':
    report([r for p in sys.argv[1:] for r in json.load(open(p))])
