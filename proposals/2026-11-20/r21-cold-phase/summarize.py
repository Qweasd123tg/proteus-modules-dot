#!/usr/bin/env python3
"""Join archive request windows with bounded frames; per-archive walls aren't additive across archives."""
import json,sys,statistics
from collections import Counter
from pathlib import Path
from uuid import UUID

def session_id(n):return str(UUID(int=n))
def ms(a,b):return round((b-a)/1e6,3)
def total(xs):return round(sum(xs),3)
def stats(values):
    return dict(min=round(min(values),3),med=round(statistics.median(values),3),max=round(max(values),3))

def report(root):
    summary=json.loads((root/'summary.json').read_text())
    events=[json.loads(l) for l in (root/'wire.jsonl').open()]
    requests={e['id']:e for e in events if e['event']=='request'}
    responses=[e for e in events if e['event']=='response']
    if len(requests)!=len(responses) or len({e['id'] for e in responses})!=len(requests):
        raise ValueError('response pairing incomplete')
    def collect(before,after,sid,op=None,key=None):
        return sorted([e for e in responses if before<=requests[e['id']]['start']<=e['t']<=after and e['session_id']==sid and (op is None or op==e['operation']) and (key is None or key==e['key'])],key=lambda e:requests[e['id']]['start'])
    def span(xs):
        return ms(requests[xs[0]['id']]['start'],xs[-1]['t']) if xs else None
    def cost(xs):
        return total(ms(requests[e['id']]['start'],e['t']) for e in xs)
    def bytes_(xs,key):return sum(e['bytes'] if key=='response' else requests[e['id']]['bytes'] for e in xs)
    rows=[]
    for c in summary['cold']:
        idx=c['index'];beg=c['start_ns'];end=c['end_ns'];sid=session_id(100+idx)
        xs=collect(beg,end,sid)
        groups={op:[e for e in xs if e['operation']==op] for op in ('open_display_snapshot','read_display_records','read_records','release_snapshot','describe','read_cache','write_cache','open_snapshot')}
        opens=groups['open_display_snapshot']; pages=groups['read_display_records']
        if len(opens)!=1 or not pages:raise ValueError(f'missing expected cold display RPCs for {idx}')
        writes=groups['write_cache'];reads=groups['read_cache'];describes=groups['describe'];release=groups['release_snapshot']
        # In this specific text/compaction corpus no tools are written. Stock save_model
        # releases the source, reads the previous head, then checks/writes each content
        # leaf, writes latest prefix, revision and HEAD last. Keep read counters scoped
        # to after the first content write, in case the relay did not decode key names.
        if len(writes)<4 or len(describes)!=1 or not release:raise ValueError(f'missing publishing path for {idx}')
        body_reads=[x for x in reads if x['key']=='content' or (x['key']=='other' and writes[0]['t']<=requests[x['id']]['start']<=writes[-1]['t'])]
        assert all(a['t']<=requests[b['id']]['start'] for a,b in zip(xs,xs[1:])), 'expected sequential per-archive calls'
        ordered_groups={op:dict(count=len(group),rpc_total_ms=cost(group),request_bytes=bytes_(group,'request'),response_bytes=bytes_(group,'response')) for op,group in groups.items() if group}
        rows.append(dict(index=idx,total_ms=c['ms'],open_ms=span(opens),open_first_byte_ms=ms(requests[opens[0]['id']]['start'],opens[0]['start']),open_complete_from_hot_start_ms=ms(summary['hot']['start_ns'],opens[0]['t']),page_phase_ms=span(pages),page_serial_rpc_ms=cost(pages),last_page_to_describe_request_ms=ms(pages[-1]['t'],requests[describes[0]['id']]['start']),page_end_to_first_write_ms=ms(pages[-1]['t'],requests[writes[0]['id']]['start']),write_phase_span_ms=span(writes),last_write_ack_to_http_end_ms=ms(writes[-1]['t'],end),interleaved_read_miss_count=sum(e['cached'] is False for e in body_reads),interleaved_read_hit_count=sum(e['cached'] is True for e in body_reads),groups=ordered_groups))
    hot=summary['hot']
    first_commit=[e for e in events if e['event']=='commit_ack' and e['session_id']==session_id(9) and e['kind']=='turn_opened' and e['verified'] and e['t']>=hot['start_ns']]
    if len(first_commit)!=1:raise ValueError('missing verified active open acknowledgment')
    req=requests[first_commit[0]['id']];ack=first_commit[0]['t'];send=hot['start_ns']
    h=collect(send,hot['end_ns'],session_id(9))
    cold_start=min(c['start_ns'] for c in summary['cold']);cold_end=max(c['end_ns'] for c in summary['cold'])
    samples=[t for t in map(json.loads,(root/'trace.jsonl').open()) if cold_start<=t['monotonic_ns']<=cold_end]
    peaks={role:max(sum(p['pss'] for p in t['processes'] if p['role']==role) for t in samples) for role in ('core','worker','reference','other')}
    peaks['tree']=max(t['pss_kib'] for t in samples)
    return dict(passed=summary['passed'],client=summary['client'],seed_sha256=summary['canonical_sha_before'],archive_canonical_unchanged=(summary.get('canonical_sha_before')==summary.get('canonical_sha_after')),worker_sha256=summary['worker_sha256'],core_sha256=summary['core_sha256'],name=root.name,cold=rows,sampled_cold_peak_pss_kib=peaks,hot=dict(ack_from_send_ms=ms(send,ack),commit_request_from_send_ms=ms(send,req['start']),commit_round_trip_ms=ms(req['start'],ack),sse_open_from_ack_ms=ms(ack,hot['sse']['durable_open_upper_bound_ns']),first_text_from_send_ms=ms(send,hot['sse']['first_text_ns']),remaining_cold_at_ack=sum(c['start_ns']<=ack<c['end_ns'] for c in summary['cold']),prior_active_rpc=[dict(operation=e['operation'],milliseconds=span([e])) for e in h if e['t']<req['start']]),measurements_are_relay_observations=True)

if __name__=='__main__':
    print(json.dumps([report(Path(p)) for p in sys.argv[1:]],indent=2))
