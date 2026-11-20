#!/usr/bin/env python3
"""Reduce R21/R22 summary + sampled backend-tree traces without requiring four successes.
Optional relay joins use matched request IDs, session IDs and HTTP intervals. No payloads.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
from statistics import median
from uuid import UUID

ROLES = ("core", "worker", "reference", "other")
MS = 10**6
NS = 10**9


def valms(start, end):
    return None if start is None or end is None else round((end-start)/MS, 2)


def file_hash(path):
    with path.open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def jsonl(p):
    with p.open() as f:
        for line in f:
            yield json.loads(line)


def frame_join(wire):
    requests, responses, acks = {}, {}, []
    for e in wire:
        idx = e['id']
        if e['event'] == 'commit_ack':
            acks.append(e)
        elif e['event'] in ('request','response'):
            dest = requests if e['event'] == 'request' else responses
            if idx in dest:
                raise ValueError(f'duplicate {e["event"]} {idx}')
            dest[idx] = e
    if set(responses) - set(requests):
        raise ValueError('unmatched responses')
    pairs = defaultdict(list)
    for k, r in responses.items():
        q = requests[k]
        if (r['operation'], r['session_id'], r['request_end']) != (q['operation'], q['session_id'], q['t']):
            raise ValueError('response identity/timestamp mismatch')
        if not q['start'] <= q['t'] <= r['start'] <= r['t']:
            raise ValueError('invalid frame timestamps')
        pairs[q['session_id']].append((q, r))
    for group in pairs.values():
        group.sort(key=lambda p: p[0]['start'])
    return pairs, requests, acks, len(set(requests) - set(responses))


def windows(c, pairs):
    """Return disjoint **observed** phase boundaries for one archive, not causal ownership."""
    start, end = c['start_ns'], c['end_ns']
    pairs = [(q,r) for q,r in pairs if start<=q['start']<=r['t']<=end]
    def select(op): return [(q,r) for q,r in pairs if q['operation']==op]
    opens, reads, writes = (select(op) for op in ('open_display_snapshot','read_display_records','write_cache'))
    if not (len(opens)==1 and reads and writes):
        return [(start,end,'unclassified')]
    edges = [(start, 'pre-open'), (opens[0][0]['start'], 'open'),
             (opens[0][1]['t'], 'open-to-pages'), (reads[0][0]['start'], 'pages'),
             (reads[-1][1]['t'], 'pages-to-first-write'), (writes[0][0]['start'], 'writes'),
             (writes[-1][1]['t'], 'post-write'), (end, None)]
    if not all(a[0] <= b[0] for a,b in zip(edges,edges[1:])):
        return [(start,end,'unclassified')]
    return [(a,b,name) for (a,name),(b,_) in zip(edges,edges[1:]) if a<b]


def state_at(stages, ts):
    return dict(sorted(Counter(name for archive in stages for a,b,name in archive if a<=ts<b).items()))


def sizes(s):
    by_role = dict.fromkeys(ROLES,0)
    for p in s['processes']:
        by_role[p['role']] += p['pss']
    if sum(by_role.values()) != s['pss_kib']:
        raise ValueError('process sum differs from tree PSS')
    return dict(tree=s['pss_kib'], **by_role)


def peak_details(ss, origin, stages):
    def point(s):
        t = s['monotonic_ns']
        scan_end = t + round(s['scan_duration_seconds']*NS)
        return dict(ms_from_first_page_call=valms(origin,t), scan_ms=valms(t,scan_end),
                    pss_kib=sizes(s), archive_stages_at_scan_start=state_at(stages,t),
                    archive_stages_at_scan_end=state_at(stages,scan_end))
    return {k:point(max(ss,key=lambda s:sizes(s)[k])) for k in ('tree','core','worker')}


def by_phase(ss):
    if not ss:
        return dict(samples=0)
    complete = [s for s in ss if not s['memory_incomplete_pids'] and all(p.get('pss') is not None for p in s['processes'])]
    out = dict(samples=len(ss),complete_samples=len(complete))
    if not complete:
        return out
    series = list(map(sizes,complete))
    out['peak_kib'] = {k:max(p[k] for p in series) for k in series[0]}
    out['median_kib'] = {k:median(p[k] for p in series) for k in series[0]}
    # pid alone is not an identity. Keep reference components separate here.
    maxima = {}
    for sample in complete:
        for proc in sample['processes']:
            key = (proc['pid'],proc['start_ticks'],proc['role'])
            maxima[key] = max(maxima.get(key,0),proc['pss'])
    out['individual_peak_kib'] = [[pid,ticks,role,size] for (pid,ticks,role),size in sorted(maxima.items())]
    best = max(complete,key=lambda s:s['pss_kib'])
    out['at_tree_peak_kib'] = sizes(best)
    gaps = [valms(a['monotonic_ns'],b['monotonic_ns']) for a,b in zip(complete,complete[1:])]
    out['median_start_gap_ms'] = median(gaps) if gaps else None
    out['max_start_gap_ms'] = max(gaps,default=None)
    return out


def reduce_run(root):
    p = root/'summary.json'
    if not p.is_file():
        return dict(name=root.name,passed=False,reason='missing summary; run blocked or incomplete')
    s = json.loads(p.read_text())
    fields = ('core_commit','core_sha256','worker_sha256','reference_sha256','desktop_client_sha256',
              'stand_sha256','sampler_sha256','profile_sha256','fixture_manifest_sha256','canonical_sha_before',
              'canonical_sha_after','wire_observer','client','index_state','history_global_deadline_s','archives','rows',
              'cold_start_unix_ns','cold_start_loadavg','cold_end_loadavg')
    out = {k:s.get(k) for k in fields}
    out.update(name=root.name,passed=s['passed'],summary_sha256=file_hash(p))
    out['additional_observers'] = [f for f in ('worker-state.jsonl','arena-trace.txt','heap.jsonl')
                                   if (root/f).is_file()]
    out['companion_hashes'] = s.get('companion_file_hashes')
    if s.get('harness_error'): out['harness_error'] = s['harness_error']
    cold = sorted(s.get('cold', []),key=lambda c:c['index'])
    if not cold: return out
    start = min(c['start_ns'] for c in cold)
    end = max(c['end_ns'] for c in cold)
    hot = s.get('hot',{})
    sse = hot.get('sse',{})
    send = hot.get('start_ns')
    requests = s.get('desktop_api_requests',[])
    # Rust driver id order is submission order; first per archive is the cold latest.
    calls = {}
    for q in sorted(requests,key=lambda x:int(x['id'])):
        if q.get('mode')=='latest':
            calls.setdefault(q['session_leaf'], q)
    timings = [calls.get(f"{100+c['index']:010d}", {}) for c in cold]
    out['first_open'] = dict(
        ok_count=sum(c['ok'] for c in cold), n=len(cold), outer_wall_ms=valms(start,end),
        # Some errors also have api_ms, e.g. 30 s deadline. Keep status attached.
        rust_api=[{k:q[k] for k in ('ok','api_ms','error') if k in q} for q in timings],
        errors=[dict(index=c['index'],error=c['error']) for c in cold if not c['ok']],
        overlap_with_send_ms=valms(start,send), descriptor_count_at_trigger=len(hot.get('seen_cold_descriptors',[])),
    )
    out['hot'] = dict(send_to_sse_open_ms=valms(send,sse.get('durable_open_upper_bound_ns')),
                      send_to_sse_first_text_ms=valms(send,sse.get('first_text_ns')),
                      send_to_response_ms=valms(send,hot.get('end_ns')),
                      cold_pending=hot.get('cold_outstanding_at',{}))
    warm = s.get('warm',{})
    def per_page(p): return (p.get('ok') and p.get('validated_rows')==50 and p.get('http_status')==200)
    all_pages = {(kind,c['index']):c for kind,cs in [('cold',cold), *warm.items()] for c in cs}
    exact = all((kind,i) in all_pages and per_page(all_pages[(kind,i)])
                for kind in ('cold','latest','pinned') for i in range(4))
    stable_rev = all(all_pages[('cold',i)]['revision']==all_pages[(mode,i)]['revision']
                     for i in range(4) for mode in ('pinned','latest')) if exact else False
    out['checks'] = dict(canonical_unchanged=bool(s.get('canonical_sha_before')) and s['canonical_sha_before']==s.get('canonical_sha_after'),
                         selected_journals=s.get('cold_journals_observed'), nonactive_count=s.get('nonactive_count'),
                         unselected_cache_free=s.get('unselected_cache_free'), durable_success=s.get('hot_canonical',{}).get('durable_success'),
                         exact_boundary_fields=exact, within_run_revision_stable=stable_rev,
                         all_archive_bases_absent=(all(row['page_base'] is None for row in all_pages.values())
                                                   if exact and all('page_base' in row for row in all_pages.values()) else None),
                         complete_cold_pss=s.get('complete_cold_pss'))
    if exact and all('full_rows_sha256' in p for p in all_pages.values()):
        hashes = {str(i):{mode:all_pages[(mode,i)]['full_rows_sha256'] for mode in ('cold','pinned','latest')}
                  for i in range(4)}
        out['boundary_rows_sha256'] = hashes
        out['checks']['full_latest_matches_cold'] = all(v['latest']==v['cold'] for v in hashes.values())
    stages = []
    if s.get('wire_observer'):
        w = root/'wire.jsonl'
        if not w.is_file(): raise ValueError('declared relay missing')
        out['wire_sha256']=file_hash(w)
        groups, rq,acks,missing = frame_join(jsonl(w))
        out['unanswered_execute_count']=missing
        stages = [windows(c,groups[str(UUID(int=100+c['index']))]) for c in cold]
        good = [a for a in acks if a['kind']=='turn_opened' and a['verified'] and a['session_id']==str(UUID(int=9))
                and a['turn_id']==sse.get('turn_open_id') and send is not None and send<=a['t']<=hot.get('end_ns',0)]
        if len(good)==1:
            ack = good[0]
            out['hot'].update(verified_open_ack_ms=valms(send,ack['t']), send_to_commit_ms=valms(send,rq[ack['id']]['start']),
                              commit_to_ack_ms=valms(rq[ack['id']]['start'],ack['t']))
    trace = root/'trace.jsonl'
    if not trace.is_file(): return out
    out['trace_sha256'] = file_hash(trace)
    samples = list(jsonl(trace))
    out['stages'] = {k:by_phase([t for t in samples if t['stage']==k]) for k in sorted({t['stage'] for t in samples})}
    # Filter scan spans, not just their start, against actual outer cold page window.
    ss = [t for t in samples if t['stage']=='cold' and start<=t['monotonic_ns'] and t['monotonic_ns']+round(t['scan_duration_seconds']*NS)<=end]
    out['page_window_pss']=by_phase(ss)
    complete = [t for t in ss if not t['memory_incomplete_pids'] and all(p.get('pss') is not None for p in t['processes'])]
    if complete: out['page_window_peaks']=peak_details(complete,start,stages)
    return out


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('runs',nargs='+',type=Path,help='completed stand output directories')
    args=parser.parse_args()
    print(json.dumps([reduce_run(r) for r in args.runs],indent=2,ensure_ascii=False))
