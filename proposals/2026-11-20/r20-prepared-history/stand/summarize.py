#!/usr/bin/env python3
import argparse, json, statistics,sys
from collections import Counter
from pathlib import Path
def summary(out):
    s=json.loads((out/'summary.json').read_text())
    if not s.get('hot'):return {'passed':False,'error':s.get('harness_error')}
    trace=[json.loads(l) for l in (out/'trace.jsonl').read_text().splitlines()]
    total=s['cold']
    def span(group):
        low=min(x['start_ns'] for x in group);hi=max(x['end_ns'] for x in group)
        samples=[r for r in trace if low<=r['monotonic_ns']<=hi and not r['memory_incomplete_pids']]
        return dict(count=len(samples),peak_tree_kib=max((r['pss_kib'] for r in samples),default=None),
                    elapsed_ms=round((hi-low)/1e6,3))
    h=s['hot'];w=s['warm']
    failures=[{'archive':x['index'],'ms_to_error':x['ms'],'error':x['error']} for x in total if not x['ok']]
    r=dict(arm=out.name,passed=s['passed'],state=s['index_state'],wire=s['wire_observer'],
           client=s['client'],core=s['core_sha256'],worker=s['worker_sha256'],corpus=s['canonical_sha_before'],
           cold_ms=[x['ms'] if x['ok'] else None for x in total],cold_failures=failures,cold_window=span(total),cold_and_hot_peak_kib=s['phases']['cold']['peak_pss_kib'],
           idle_tree_pss_kib=s['phases']['idle']['median_pss_kib'],retained_tree_pss_kib=s['phases']['retained']['median_pss_kib'],
           durable_open_upper_ms=h.get('durable_open_upper_bound_ms'),durable_user_upper_ms=h.get('durable_user_upper_bound_ms'),
           first_text_ms=h.get('first_text_ms'),terminal_http_ms=h.get('ms'),cold_outstanding=h['cold_outstanding_at'],
           latest_warm_ms=[x['ms'] for x in w['latest']],pinned_warm_ms=[x['ms'] for x in w['pinned']],
           passive_canonical_immutable=s['canonical_sha_before']==s['canonical_sha_after'],
           foreground_canonical_ok=s['hot_canonical']['durable_success'],
           disk_heads_opened=s.get('disk_heads_opened'),journals_opened=s['cold_journals_observed'],
           catalog_at_restart=s.get('preparation',{}).get('catalog_present'),preparer_tree_gone=s.get('preparation',{}).get('preparation_process_exited'))
    if s['wire_observer']:
        wire=[json.loads(l) for l in (out/'wire.jsonl').read_text().splitlines()]
        turn=s['hot']['sse']['turn_open_id'];acks=[o for o in wire if o['event']=='commit_ack' and o['verified'] and o['turn_id']==turn]
        assert len([x for x in acks if x['kind']=='turn_opened'])==1
        a=next(x for x in acks if x['kind']=='turn_opened')
        assert next(x for x in acks if x['kind']=='turn_settled')['t']>a['t']
        r['wire_turn_open_worker_ack_ms']=round((a['t']-h['start_ns'])/1e6,3)
        r['wire_turn_open_operation_id']=a['operation_id']
        r['cold_outstanding_at_wire_ack']=sum(c['start_ns']<=a['t']<c['end_ns'] for c in total)
        for name,group in [('restart',total),('pinned',w['pinned']),('latest',w['latest'])]:
            counts=[]
            for i,c in enumerate(group):
                sid=f"00000000-0000-0000-0000-{100+i:012x}"
                ops=Counter(o['operation'] for o in wire if o['event']=='request' and o['session_id']==sid and c['start_ns']<=o['t']<=c['end_ns'])
                counts.append(dict(ops))
            r[name+'_operations']=counts
    return r
if __name__=='__main__':print(json.dumps([summary(Path(o)) for o in sys.argv[1:]],indent=2))
