#!/usr/bin/env python3
"""Verify first R290 indexed capture receipts and untouched fallback."""
import json
import pathlib
import sys

BIG=(
 ('final-middle','success'),('final-tail','success'),('final-shared','success'),
 ('settle-unique','canceled'),('settle-shared','canceled'))
SMALL=BIG+(
 ('unbound-final','success'),('no-owner-settle','failed'),('none-followup','success'),
 ('collision-after-part','success'),('collision-before-part','success'),
 ('collision-after-message','success'),('collision-before-message','success'),
 ('both-conflicts','success'),('known-after','success'),('settle-late','failed'),
 ('duplicate-final','success'),('lost-final','success'),('bad-seq','success'),
 ('saturated','success'),('context','canceled'),('settle-nested','canceled'))
DIRECT={'unknown-index','not-singleton','weak-index'}
FLOOR={5000:100*1024,50000:1024*1024}
NOCHECK={'unbound-final','no-owner-settle','bad-seq','duplicate-final','lost-final'}
COLLISIONS={'none-followup','collision-after-part','collision-before-part','collision-after-message','collision-before-message','both-conflicts'}
ERRORS={
 'duplicate-final':'duplicate tool result',
 'lost-final':'checkpoint history suffix was lost',
 'bad-seq':'journal sequence mismatch',
 'known-after':'changed after it was recorded',
 'settle-late':'changed after it was recorded',
 'none-followup':'duplicate part id',
 'collision-after-part':'duplicate part id',
 'collision-before-part':'duplicate part id',
 'collision-after-message':'duplicate message id',
 'collision-before-message':'duplicate message id',
 'both-conflicts':'duplicate message id',
}
FIELDS=('alloc_bytes','allocs','free_bytes','frees')

def validate(x):
    assert all(type(x[k]) is int and x[k]>=0 for k in FIELDS)
    assert x['net_bytes']==x['alloc_bytes']-x['free_bytes']

def digest(s):
    assert len(s)==64 and all(c in '0123456789abcdef' for c in s)

def compare(r):
    a,b=(r['meters'][k] for k in ('stock','candidate'))
    for x in (a,b):validate(x['total'])
    found=[]
    for p,q in zip(a['active_checks'],b['active_checks'],strict=True):
        for k in ('index','history_len','pre_present','pre_unique','result_ok'):
            assert p[k]==q[k],(k,p,q)
        assert not p['fast']
        assert p['scanned_rows']<=p['history_len']
        if p['result_ok']:assert p['scanned_rows']==p['history_len']
        for x in (p,q):validate(x['layout'])
        if q['fast']:
            assert q['pre_present'] and q['pre_unique'] and q['result_ok']
            assert q['index']<q['history_len']
            assert q['scanned_rows']==q['scanned_parts']==0
            assert p['layout']['alloc_bytes']>=q['layout']['alloc_bytes']
            assert p['layout']['allocs']>=q['layout']['allocs']
        else:
            for k in ('scanned_rows','scanned_parts','layout'):
                assert p[k]==q[k],(k,p,q)
        found.append(dict(index=p['index'],history_len=p['history_len'],
                          pre_present=p['pre_present'],pre_unique=p['pre_unique'],
                          result_ok=p['result_ok'],fast=q['fast'],
                          avoided_bytes=p['layout']['alloc_bytes']-q['layout']['alloc_bytes'],
                          avoided_allocs=p['layout']['allocs']-q['layout']['allocs'],
                          stock_rows=p['scanned_rows'],stock_parts=p['scanned_parts'],
                          stock_layout=p['layout'],candidate_layout=q['layout']))
    for k,short in (('alloc_bytes','avoided_bytes'),('allocs','avoided_allocs')):
        assert a['total'][k]-b['total'][k]==sum(x[short] for x in found),(k,a['total'],b['total'],found)
    return found

def direct(r,checks):
    mode=r['direct']; assert mode in DIRECT and r['passed'] and r['n']==17
    assert len(checks)==1
    c=checks[0]
    assert c['index']==r['index'] and c['pre_present'] and c['result_ok'] and not c['fast']
    assert c['pre_unique']==(mode!='weak-index')
    assert (c['index']>=c['history_len'])==(mode=='unknown-index')
    assert c['stock_rows']==c['history_len']
    digest(r['history_sha256'])

def want_keys():
    return ({(n,m,'plain',status) for n in FLOOR for m,status in BIG}
             | {(17,m,h,status) for m,status in SMALL for h in ('plain','mixed')}
             | {(0,'final-middle','plain','success')})

def check(path):
    rows=[json.loads(s) for s in pathlib.Path(path).read_text().splitlines()]
    seen=set();edges=set();large={};active_checks=0;fast_checks=0
    for r in rows:
        checks=compare(r)
        if 'direct' in r:
            assert r['direct'] not in edges
            direct(r,checks);edges.add(r['direct']);continue
        n,m,h,t=(r[k] for k in ('n','mode','shape','status'))
        k=(n,m,h,t);assert k not in seen
        seen.add(k)
        s=r['state'];err=s['error']
        if m in ERRORS:assert ERRORS[m] in err,(m,err)
        else:assert err is None,(m,err)
        assert r['physical_bytes']>0
        digest(s['history_sha256'])
        assert s['rows']==s['before_rows']+len(s['captured'])
        assert s['revision']==min(2**64-1,s['before_revision']+len(s['captured']))
        assert s['next_seq']==s['source_seq']+int(err is None)
        if m in NOCHECK:assert checks==[] and not s['captured']
        else:assert len(checks)==len(s['captured'])
        if checks:
            assert checks[0]['pre_unique']==s['before_unique']
            assert checks[0]['pre_present']==s['before_present']
        if m in COLLISIONS:
            assert not s['after_present'] and all(not c['result_ok'] and not c['fast'] for c in checks)
        if m=='none-followup':assert not s['before_present']
        if m in ('known-after','settle-late'):
            assert s['after_present'] and all(c['result_ok'] and c['fast'] for c in checks)
        if m=='final-middle':assert len(checks)==1 and checks[0]['fast'] and checks[0]['index']+1<checks[0]['history_len']
        if m=='final-tail':assert len(checks)==1 and checks[0]['fast'] and checks[0]['index']+1==checks[0]['history_len']
        if m=='final-shared':assert len(checks)==1 and not checks[0]['fast'] and not checks[0]['pre_unique']
        if m=='settle-shared':
            assert len(checks)==2 and [c['fast'] for c in checks]==[False,True]
        if m=='settle-unique':
            assert len(checks)==2 and all(c['fast'] for c in checks)
        if m in ('collision-after-part','collision-before-part'):
            assert err.endswith('at message 00000000-0000-0000-0000-00000000'+('1fad' if m=='collision-after-part' else '2328'))
        if m=='saturated':assert s['before_revision']==s['revision']==2**64-1
        if t=='canceled' and err is None and m.startswith('settle'):
            assert len(s['interruptions'])==1
        if n in FLOOR:
            if m in ('final-middle','final-tail'):assert checks[0]['avoided_bytes']>=FLOOR[n]
            assert r['physical_bytes']>n*400
            large[f'{m}/{n}']=checks
        active_checks+=len(checks);fast_checks+=sum(c['fast'] for c in checks)
    wanted=want_keys()
    assert seen==wanted,{'missing':sorted(wanted-seen),'extra':sorted(seen-wanted)}
    assert edges==DIRECT and len(large)==10
    return dict(paired_strict_cases=len(seen),direct_shape_cases=len(edges),
                actual_active_checks=active_checks,actual_fast_checks=fast_checks,large=large)

if __name__=='__main__':
    print(json.dumps(check(sys.argv[1]),sort_keys=True,indent=2))
