#!/usr/bin/env python3
"""Independently check R289 exact same-origin pending scan and Layout receipts."""
import json
import pathlib
import sys

COUNT_FIELDS=('alloc_bytes','allocs','free_bytes','frees')
ZERO={k:0 for k in (*COUNT_FIELDS,'net_bytes')}
FLOOR=2*2**20

def stat(s):
    assert s.keys()==ZERO.keys()
    assert all(type(x) is int and x>=0 for k,x in s.items() if k!='net_bytes')
    assert s['net_bytes']==s['alloc_bytes']-s['free_bytes']

def delta(a,b,k):return tuple(a[x]-b[x] for x in k)

def compare(a,b):
    for x in (a,b):stat(x['settlement'])
    p=a['pending'];q=b['pending']
    assert (p is None)==(q is None)
    if p is None:
        assert a==b
        return None
    assert p['map_clone'] is None and q['map_clone']==ZERO
    for x in (p,q):
        stat(x['prepare']);stat(x['visit_scope'])
    saved_bytes,saved_allocs=delta(p['prepare'],q['prepare'],('alloc_bytes','allocs'))
    assert saved_bytes>=0 and saved_allocs>=0
    assert delta(a['settlement'],b['settlement'],('alloc_bytes','allocs'))==(saved_bytes,saved_allocs)
    assert delta(a['settlement'],b['settlement'],('free_bytes','frees'))==(saved_bytes,saved_allocs)
    assert a['settlement']['net_bytes']==b['settlement']['net_bytes']
    for u,v in zip(p['eligible'],q['eligible'],strict=True):
        for k in ('call','output_len','ledger_capacity','capture','canonical'):
            assert u[k]==v[k],(k,u[k],v[k])
        assert not u['borrowed_body'] and v['borrowed_body']
        if u['output_len']:
            assert not u['shared_output'] and v['shared_output']
            assert u['input_capacity']==u['output_len']
        else:assert u['shared_output'] is None and v['shared_output'] is None
        assert v['input_capacity']==v['ledger_capacity']
        if u['capture'] is not None:
            stat(u['capture'])
            if u['canonical'] is None:
                assert u['capture']==ZERO
            else:
                assert u['canonical']['owned_output']
                assert u['canonical']['bytes']==u['canonical']['capacity']==u['output_len']
                assert u['canonical']['part_capacity']>=1
                assert u['capture']['allocs']>0 and u['capture']['alloc_bytes']>=u['output_len']
        else:
            assert u['canonical'] is None
    return dict(eligible=[x['call'] for x in p['eligible']],
                captured=[x['call'] for x in p['eligible'] if x['canonical'] is not None],
                capture_errors=[x['call'] for x in p['eligible'] if x['capture'] is None],
                skipped=[x['call'] for x in p['eligible'] if x['capture'] is not None and x['canonical'] is None],
                avoided_prepare_requested_bytes=saved_bytes,avoided_prepare_allocs=saved_allocs,
                stock_prepare=p['prepare'],candidate_prepare=q['prepare'],payloads=p['eligible'])

def check(path):
    cases=[json.loads(l) for l in pathlib.Path(path).read_text().splitlines()]
    return check_cases(cases)

SMALL=(
 ('bound','success'),('bound','failed'),('bound','canceled'),('multiple','canceled'),('only-unbound','success'),
 ('owner-bypass','success'),('nested-detached','canceled'),('no-effects','success'),('previous-turn','success'),('only-final','canceled'),
 ('mixed-final','failed'),('late-part','success'),('late-active','canceled'),('saturated','success'),('context','canceled'),
 ('already-settled','success'),('bad-seq','success'),('bad-session','success'),('bad-schema','success'))
BIG=(('bound','plain','canceled'),('multiple','mixed','success'),('only-unbound','mixed','failed'))
ERRORS={'late-part':'changed after it was recorded','late-active':'active history contains duplicate message',
        'bad-schema':'unsupported journal schema_version','bad-session':'belongs to session',
        'bad-seq':'journal sequence mismatch','already-settled':'was already settled'}

def keys():
    return ({(137,m,h,t) for m,t in SMALL for h in ('plain','mixed')} |
            {(n,m,h,t) for n in (1<<20,4<<20,8<<20) for m,h,t in BIG} |
            {(0,'bound','plain','success')})

def check_cases(cases):
    seen=set()
    large={}
    late_errors=0
    same_origin_scopes=0
    order_differences=0
    empty_prep=next(r['meters']['candidate']['pending']['prepare'] for r in cases if r['mode']=='no-effects')
    # The existing im ref iterator has one scratch-stack allocation, independent
    # of content count; use the actual empty-effect control rather than infer bytes.
    assert empty_prep['allocs']==1 and empty_prep['free_bytes']==empty_prep['frees']==0
    for r in cases:
        n,m,h,t=(r[k] for k in ('n','mode','shape','status'))
        key=(n,m,h,t)
        assert key not in seen
        seen.add(key)
        a,b=(r['meters'][k] for k in ('stock','candidate'))
        result=compare(a,b)
        state=r['state']
        assert state['original_ledger_alive']
        assert r['physical_bytes']>0
        assert len(state['history_sha256'])==64
        assert all(c in '0123456789abcdef' for c in state['history_sha256'])
        if m in ERRORS:assert ERRORS[m] in state['error'],key
        else:assert state['error'] is None,key
        ok=state['error'] is None
        assert state['next_seq']==state['source_seq']+int(ok)
        assert state['bound_after']==(state['bound_before'] and not ok)
        visited=r['visited']
        if result is None:assert not visited
        else:
            same_origin_scopes+=1
            assert result['candidate_prepare']==empty_prep
            assert result['eligible']==visited
            assert not result['capture_errors'],key
            if visited:
                assert r['order'][:len(visited)]==visited
                assert result['avoided_prepare_requested_bytes']>=sum(row['output_len'] for row in result['payloads'])
                assert all(row['output_len']==n for row in result['payloads'])
            else:assert result['avoided_prepare_requested_bytes']==result['avoided_prepare_allocs']==0
            # Layout count for unrelated validation and capture is same; an
            # unbound ledger effect didn't even produce a new canonical part.
            assert result['skipped']==[x for x in visited if x=='u']
        captured=result['captured'] if result else []
        assert state['rows']==state['before_rows']+len(captured)
        assert state['revision']==min(2**64-1,state['before_rev']+len(captured))
        late=m.startswith('late-')
        if late:
            late_errors+=1
            assert len(captured)==2 and captured[-1]==r['culprit']
            assert state['bound_after'] and visited[-1]==r['culprit']
        else:assert r['culprit'] is None
        if m in ('owner-bypass','bad-seq','bad-session','bad-schema','already-settled'):
            assert result is None
        if m in ('only-unbound','no-effects','only-final'):assert not captured
        if m in ('no-effects','only-final'):assert not visited
        if m=='multiple':assert set(captured)=={'a','b'} and 'u' in visited
        if m in ('nested-detached','previous-turn'):assert visited==['a']
        if m=='mixed-final':assert set(visited)=={'a','u'} and captured==['a']
        if m=='saturated':assert state['before_rev']==state['revision']==2**64-1 and captured==['a']
        if m not in ('already-settled',) and ok and t=='canceled':assert len(state['interruptions'])==1
        if len(captured)>1 and sorted(captured)!=captured:order_differences+=1
        if n>=1<<20:
            assert r['physical_bytes']>n
            if n>=4<<20 and m!='only-unbound':
                assert result['avoided_prepare_requested_bytes']>=FLOOR and captured
            if m=='only-unbound':assert result['skipped']==['u'] and not captured
            large[f'{m}/{n}']=result
    wanted=keys()
    assert seen==wanted,{'missing':sorted(wanted-seen),'extra':sorted(seen-wanted)}
    assert len(large)==9 and late_errors==4
    return dict(paired_strict_cases=len(seen),paired_pending_scopes=same_origin_scopes,
                genuine_late_error_cases=late_errors,observed_iteration_different_from_binding_order=order_differences,
                candidate_iter_prepare=empty_prep,large=large)

if __name__=='__main__':
    print(json.dumps(check(sys.argv[1]),sort_keys=True,indent=2))
