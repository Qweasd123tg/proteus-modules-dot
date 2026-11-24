#!/usr/bin/env python3
"""Independent checker for the R285 native allocation-generation phase receipts."""
import collections
import json
import pathlib
import sys

OWNERS=('message_slots', 'parts','text','other')
NESTED=OWNERS[1:]
FLOORS={5000:{'half':1048576,'three_quarters':1572864},
        50000:{'half':10485760,'three_quarters':15728640}}
ZERO={g:{'allocs':0,'bytes':0} for g in OWNERS}

def owned_totals(c, groups):
    assert set(c)==set(OWNERS)
    for x in c.values():
        assert set(x)=={'bytes','allocs'} and all(type(v) is int and v>=0 for v in x.values())
    return {k:sum(c[g][k] for g in groups) for k in ('bytes','allocs')}

def compare_record(a,b):
    """A/B are receipts for the exact same source record, before output packing."""
    for k in ('seq','rows','outer_capacity','initial_owners','visited'):
        assert a[k]==b[k],(k,a[k],b[k])
    n=a['rows']
    assert a['visited']==n
    init=a['initial_owners']
    total_initial=owned_totals(init,OWNERS)
    assert a['exit_owners']==b['exit_owners']==ZERO
    assert a['outer_capacity']>=n
    assert init['message_slots']['allocs']==int(a['outer_capacity']>0)
    assert min(a['visit']['initial'],b['visit']['initial'])>=total_initial['bytes']
    obs={}
    prev_suffix=init
    for atr,btr,k,label in zip(a['milestones'],b['milestones'],[0,n//4,n//2,3*n//4,max(0,n-1)],
                               ['initial','quarter','half','three_quarters','last'],strict=True):
        assert atr['before_row']==btr['before_row']==k
        assert atr['suffix_expected']==btr['suffix_expected']
        exp=atr['suffix_expected']
        owned_totals(exp,OWNERS)
        assert exp['message_slots']==init['message_slots']
        assert all(exp[g][m]<=prev_suffix[g][m] for g in OWNERS for m in ('bytes','allocs'))
        prev_suffix=exp
        if n==0:
            assert atr['actual_live'] is btr['actual_live'] is None
            assert exp==init==ZERO
            continue
        assert atr['actual_live']==init and btr['actual_live']==exp
        assert atr['actual_live']['message_slots']==btr['actual_live']['message_slots']==init['message_slots']
        d=owned_totals(atr['actual_live'],NESTED)
        e=owned_totals(btr['actual_live'],NESTED)
        obs[label]={'before_row':k,'stock_nested':d,'candidate_nested':e,
                    'released':{m:d[m]-e[m] for m in d}}
    for q in (a,b):
        assert q['visit']['initial']<=q['visit']['peak']<=q['visit']['initial']+q['visit']['alloc_bytes']
    assert a['visit']['alloc_n']==b['visit']['alloc_n']
    assert a['visit']['alloc_bytes']==b['visit']['alloc_bytes']
    return dict(rows=n,seq=a['seq'],outer_capacity=a['outer_capacity'],entries=obs,initial_owners=init,
                callback_watch={'stock':a['visit'],'candidate':b['visit']})

def compare(a,b):
    assert (a is None)==(b is None)
    if a is None:
        return None
    assert a['scans']==b['scans']==1 and a['decodes']==b['decodes']
    assert len(a['records'])==len(b['records'])
    return {'decode_attempts':a['decodes'],'records':[compare_record(x,y) for x,y in zip(a['records'],b['records'],strict=True)]}

def load(path):
    return [json.loads(x) for x in pathlib.Path(path).read_text().splitlines()]

ROUTES=('projected','fallback','unstaged','projected-unstaged')
ERRORS={
    'late-lf':'incomplete transcript staging record',
    'late-decode':'key must be a string',
    'late-count':'transcript staging record count changed',
    'late-unstaged':'storage record page made no progress',
    'validator':'history revision must increment',
    'unknown-named':'history revision changed; refresh the session snapshot',
    'final-hash':'history source changed during recovery; refresh the session snapshot',
}
EARLY={'warm','validator','unknown-named'}
LATE={'late-lf','late-decode','late-count','late-unstaged'}

def expected_keys():
    return (
        {(route,'prepared','ok',n) for route in ROUTES[:3] for n in FLOORS} |
        {(route,'prepared',fault,n) for route in ROUTES for fault,n in [
            ('ok',0),('ok',1),('ok',63),('many-single',70),('reset',63),('warm',63),('validator',63)]} |
        {(route,'prepared',fault,63) for route in ROUTES[:2] for fault in [
            'late-lf','late-count','late-decode','page','prefix','named-write','head']} |
        {(route,kind,fault,63) for route in ROUTES[:2] for kind,fault in [
            ('unnamed-page','ok'),('named-full','ok'),('named-full','unknown-named'),('unnamed-page','final-hash')]} |
        {(route,'prepared','late-unstaged',63) for route in ROUTES[2:]} |
        {(route,'identity','ok',0) for route in ('suffix','codec')}
    )

def check_cases(rows):
    done=set()
    large={}
    nonnull=0
    visited=0
    unstaged_baseline_differences=[]
    for r in rows:
        n,route,kind,fault=map(r.get,['n','route','kind','fault'])
        k=(route,kind,fault,n)
        assert k not in done,k
        done.add(k)
        a,b=(r['meters'][x] for x in ('stock','candidate'))
        m=compare(a,b)
        if kind=='identity':
            assert r['passed'] and m is None
            if route=='codec':assert r['records']==10
            continue
        assert (m is None)==(fault in EARLY),k
        first,last=r['trace_first_last']
        assert len(first)==min(10,r['trace_count']) and len(last)==min(12,r['trace_count'])
        if kind=='prepared': assert first[0]=='OpenSession'
        if fault in ERRORS:
            assert ERRORS[fault] in r['result'] and r['result_rows']==r['result_capacity']==0,k
        else:
            assert len(r['result'])==64 and all(c in '0123456789abcdef' for c in r['result']),k
            wanted=n if kind=='named-full' or fault in ('page','named-write') else min(50,n)
            assert r['result_rows']==wanted and r['result_capacity']>=wanted,k
        if m is None:
            assert r['stage']=={'records':0,'file_bytes':0,'causal':False}
            continue
        nonnull+=1
        physical=route in ROUTES[:2]
        for rr in m['records']:
            watch=rr['callback_watch']
            diff=watch['stock']['initial']-watch['candidate']['initial']
            if physical:
                assert diff==0,(k,rr['seq'],diff)
            elif diff:
                unstaged_baseline_differences.append(dict(route=route,kind=kind,fault=fault,rows=rr['rows'],seq=rr['seq'],stock_minus_candidate=diff))
        record_sizes=[x['rows'] for x in m['records']]
        visited+=sum(record_sizes)
        if fault=='many-single': assert record_sizes==[1]*70,k
        elif fault=='reset': assert record_sizes==[3,63],k
        elif n==0: assert record_sizes==[],k
        else: assert record_sizes==[n],k
        if fault in LATE:
            assert 'Digest' not in first+last and not r['page_docs']
        if n in FLOORS:
            ms=m['records'][0]
            for point in FLOORS[n]:
                assert ms['entries'][point]['released']['bytes'] >= FLOORS[n][point],(k,point,ms['entries'][point])
            def t(i):
                return len(('Fixture row '+str(i)+'\n'+'Синтетический текст для замера памяти и прокрутки. '*4).encode())
            c=ms['initial_owners']
            assert c['text']=={'bytes':sum(t(i) for i in range(n)),'allocs':n}
            assert c['parts']['allocs']==n and c['other']==ZERO['other']
            for p in ms['entries'].values():
                # Independent deterministic known-text and singleton parts proof.
                ix=p['before_row']
                assert p['released']['allocs']==2*ix
                assert c['parts']['bytes']%n==0
                assert p['released']['bytes']==sum(t(i) for i in range(ix))+(c['parts']['bytes']//n)*ix
            assert r['result_rows']==50
            assert len(m['records'])==1 and m['decode_attempts']==1
            if route in ('projected','fallback'):
                assert r['stage']['records']==1 and r['stage']['file_bytes']>100 and r['stage']['causal']
            else: assert r['stage']=={'records':0,'file_bytes':0,'causal':False}
            watch=ms['callback_watch']
            ms['physical_callback_peak_reduction']=watch['stock']['peak']-watch['candidate']['peak'] if physical else None
            large[f'{route}/{n}']=ms
    expected=expected_keys()
    assert done==expected,{'missing':sorted(expected-done),'extra':sorted(done-expected)}
    return dict(paired_cases=len(done),paired_prefix_scans=nonnull,decoded_rows_visited=visited,
                unstaged_baseline_differences=unstaged_baseline_differences,large=large)

if __name__=='__main__':
    print(json.dumps(check_cases(load(sys.argv[1])),sort_keys=True,indent=2))
