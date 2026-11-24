#!/usr/bin/env python3
"""Check R284 raw per-arm allocation-generation and route evidence."""
import collections
import json
import pathlib
import sys

DROPPED = (
    'canonical_messages', 'canonical_parts', 'canonical_text', 'canonical_other',
    'model_context', 'history_digests',
    'prefix_messages', 'prefix_parts', 'prefix_committed_parts',
    'prefix_turns', 'prefix_exchanges', 'prefix_calls', 'summary', 'usage',
)
RENDERED = ('rendered_rows', 'rendered_owned')
GROUPS = set(DROPPED + RENDERED + ('unclassified',))
PRIMARY = ('canonical_messages', 'canonical_parts', 'canonical_text', 'history_digests',
           'prefix_messages', 'prefix_parts', 'prefix_committed_parts')
PASS_MIN_BYTES = {5000: 3670016, 50000: 36700160} # 3.5/35 MiB; gates set before execution.

def total(measurement, keys):
    return {k: sum(measurement[g][k] for g in keys) for k in ('bytes', 'allocs')}

def arm_groups(label, meter):
    before = meter['capture']
    assert set(before) == GROUPS
    for step in ('final_open', 'final_release'):
        phase = meter[step]
        if phase is None:
            continue
        assert set(phase) == GROUPS
        for k in GROUPS:
            assert set(before[k]) == set(phase[k]) == {'bytes', 'allocs'}
            for metric in ('bytes', 'allocs'):
                got = phase[k][metric]
                assert type(got) is int and 0 <= got <= before[k][metric]
            if k in RENDERED or label == 'stock' and k in DROPPED:
                assert phase[k] == before[k], (step, k, phase[k], before[k])
            elif k in DROPPED:
                assert phase[k] == {'bytes': 0, 'allocs': 0}, (step, k, phase[k])
    assert meter['final_open'] is not None

def compare_meters(a,b):
    assert (a is None) == (b is None)
    if a is None:
        return None
    assert a['shape']==b['shape']
    assert (a['final_release'] is None)==(b['final_release'] is None)
    arm_groups('stock',a)
    arm_groups('candidate',b)
    for k in DROPPED+RENDERED:
        assert a['capture'][k]==b['capture'][k], (k,a['capture'][k],b['capture'][k])
    shape=a['shape']
    n=shape['messages']
    assert shape['digests']==n and shape['message_capacity']>=n
    assert shape['transcript_capacity']>=shape['transcript_rows']
    assert a['capture']['history_digests']['bytes']>=32*n
    assert a['capture']['history_digests']['bytes']%32==0
    return dict(shape=shape,dropped=total(a['capture'],DROPPED),
                rendered=total(a['capture'],RENDERED),
                bytes_by_group={k:a['capture'][k]['bytes'] for k in DROPPED+RENDERED},
                release=a['final_release'] is not None)

EARLY = {'unknown-named','named-race','validator','renderer','late-prefix','warm'}
NO_RELEASE = {'final-wrong-kind','final-wrong-session','final-missing','final-transport'}
ERRORS = {
 'final-hash':'history source changed during recovery; refresh the session snapshot',
 'final-revision':'history source changed during recovery; refresh the session snapshot',
 'named-race':'history source changed during recovery; refresh the session snapshot',
 'invalid-final':'history source changed during recovery; refresh the session snapshot',
 'final-wrong-kind':'storage returned an unexpected snapshot response',
 'final-wrong-session':'storage snapshot belongs to another session',
 'final-transport':'fixture worker disconnected',
 'final-missing':'session no longer exists',
 'invalid-before':'history position is outside the requested revision',
 'unknown-named':'history revision changed; refresh the session snapshot',
 'validator':'history revision must increment',
 'renderer':'transcript staging record count changed',
 'late-prefix':'transcript staging record count changed',
}
ROUTES=('projected','fallback','unsupported')
KINDS=('unnamed-page','named-page','named-full')
def expected_keys():
    x={(route,kind,'ok',n,None,False) for route in ROUTES[:2] for kind in KINDS for n in PASS_MIN_BYTES}
    x|={(route,kind,fault,n,before,n==63) for route in ROUTES for kind in KINDS
          for fault,n,before in [('ok',0,None),('ok',1,0),('ok',63,None),('warm',63,None),('final-new-handle',63,None)]
          if kind!='named-full' or before is None}
    more=[
       ('unknown-named','named-page',None),('named-race','named-page',None),('validator','unnamed-page',None),
       ('renderer','unnamed-page',None),('late-prefix','named-full',None),
       ('page','unnamed-page',None),('prefix','unnamed-page',None),('named-write','unnamed-page',None),('head','unnamed-page',None),
       ('final-wrong-kind','unnamed-page',None),('final-wrong-session','named-page',None),('final-hash','unnamed-page',None),
       ('final-revision','unnamed-page',None),('final-missing','named-full',None),('final-transport','unnamed-page',None),
       ('final-release','named-page',None),('context','named-page',None),('invalid-before','unnamed-page',64),('invalid-final','unnamed-page',64),
    ]
    x|={(route,kind,fault,63,before,True) for route in ROUTES[:2] for fault,kind,before in more}
    return x

def check_cases(items):
    seen=set()
    summaries={}
    context_coverage=0
    observed=0
    for r in items:
        n,route,kind,fault,mixed,before=map(r.get,['n','route','kind','fault','mixed','before'])
        case=(route,kind,fault,n,before,mixed)
        assert case not in seen, case
        seen.add(case)
        a,b=(r['meters'][k] for k in ('stock','candidate'))
        s=compare_meters(a,b)
        assert (s is None)==(fault in EARLY),case
        head,tail=r['trace_first_last']
        assert len(head)==min(r['trace_count'],10) and len(tail)==min(r['trace_count'],12)
        if fault in ERRORS:
            assert ERRORS[fault] in r['result'] and r['result_rows']==0,case
        else:
            assert len(r['result'])==64 and all(ch in '0123456789abcdef' for ch in r['result']),case
            end=n if before is None else before
            assert r['result_rows']==(n if kind=='named-full' else min(50,end)),case
        if s is None:
            assert 'FinalOpen' not in tail and 'FinalRelease' not in tail,case
            continue
        assert 'FinalOpen' in tail and ('FinalRelease' in tail)==s['release'],case
        assert s['release']==(fault not in NO_RELEASE),case
        assert s['shape']['messages']==s['shape']['transcript_rows']==n,case
        if not mixed:
            counts=a['capture']
            fixture=lambda i:len(('Fixture row '+str(i)+'\n'+'Синтетический текст для замера памяти и прокрутки. '*4).encode())
            assert counts['canonical_parts']['allocs']==counts['canonical_text']['allocs']==counts['rendered_owned']['allocs']//2==n
            assert counts['canonical_text']['bytes']==sum(fixture(i) for i in range(n))
            assert counts['rendered_owned']['bytes']>=counts['canonical_text']['bytes']
            assert counts['canonical_messages']['allocs']==counts['rendered_rows']['allocs']==int(n>0)
            assert all(counts[k]['allocs']==int(n>0) for k in ('prefix_messages','prefix_parts','prefix_committed_parts'))
        if n in PASS_MIN_BYTES:
            assert sum(s['bytes_by_group'][k] for k in PRIMARY)>=PASS_MIN_BYTES[n],(case,s)
            summaries[f'{route}/{kind}/{n}']=s
        if fault=='context':
            assert s['shape']['context']==1 and a['capture']['model_context']['allocs']==1
            assert a['capture']['model_context']['bytes']>0
        context_coverage+=int(s['shape']['context']>0)
        observed+=1
    expected=expected_keys()
    assert seen==expected,{'missing':sorted(map(str,expected-seen)),'extra':sorted(map(str,seen-expected))}
    assert context_coverage==2
    return dict(paired_route_cases=len(seen),paired_final_observations=observed,
                nonempty_model_context_cases=context_coverage,large=summaries)

def check(path):
    items=[json.loads(x) for x in pathlib.Path(path).read_text().splitlines()]
    return check_cases(items)

if __name__=='__main__':
    print(json.dumps(check(sys.argv[1]),sort_keys=True,indent=2))
