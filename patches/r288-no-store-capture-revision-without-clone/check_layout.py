#!/usr/bin/env python3
"""Independent R288 scoped Layout and typed capture-state checker."""
import pathlib
import json
import struct
import math
import sys

FLOORS={5000:3*2**20,50000:30*2**20}
PLAIN_SMALL=(
 ('final','unbound'),('final','bound'),('final','persisted-bound'),('final','duplicate'),('final','lost'),('final','foreign'),
 ('final','sink-error'),('final','cancel-sink'),('final','resume-sink'),('final','cancel-effects'),('final','cancel-history'),('final','cancel-grant'),('final','resume-history'),
 ('settle','empty'),('settle','unbound'),('settle','bound'),('settle','persisted-noop'),('settle','lost'),('settle','partial'),('settle','cancel-history'),('settle','resume-history'))
FLOATS=('nan32','nan64','infinity32','minus-infinity64','negative-zero32','positive-zero64')
FLOAT_MODES=(('final','unbound'),('final','persisted-bound'),('final','foreign'),('settle','unbound'),('settle','partial'))
LARGE=(('final','unbound'),('final','bound'),('final','persisted-bound'),('settle','unbound'),('settle','bound'),('settle','partial'))
PARTS={'image','text','context','file','call','result','patch','summary','reasoning','opaque','hosted-file','hosted-web','citation'}
NO_SCOPE={'empty','persisted-noop','foreign','sink-error','cancel-sink','cancel-effects','cancel-history','cancel-grant'}

def bits(kind,e):
    n=int(e['bits'],16)
    assert e['old_and_new_changed']==math.isnan(struct.unpack('!'+kind,n.to_bytes(4 if kind=='f' else 8,'big'))[0])
    return n

def eq_control(row):
    assert row['passed'] and set(row['part_shapes'])==PARTS and len(row['part_shapes'])==13
    assert {bits('f',e) for e in row['f32']}=={0,0x80000000,0x7f800000,0xff800000,0x3f054321,0x7fc12345,0xffc12345,0x7f812345,0xff812345}
    assert {bits('d',e) for e in row['f64']}=={0,0x8000000000000000,0x7ff0000000000000,0xfff0000000000000,
            0x3ff00123456789ab,0x7ff80123456789ab,0xfff80123456789ab,0x7ff00123456789ab,0xfff00123456789ab}

def validate_stat(x):
    assert x['scopes']==1
    for k in ('alloc_bytes','free_bytes','allocs','frees','peak_net_bytes'):
        assert type(x[k])==int and x[k]>=0
    assert x['alloc_bytes']-x['free_bytes']==x['net_bytes']
    assert max(x['net_bytes'],0)<=x['peak_net_bytes']<=x['alloc_bytes']

def check_state(r):
    op,m,s=r['op'],r['mode'],r['state']
    nan=r['shape'].startswith('nan')
    expected_revision=13
    expected_suffix=[]
    expected_effects=[]
    expected_events=[]
    expected_error={
      'sink-error':'typed recorder sink failed',
      'duplicate':'checkpoint received a duplicate tool result',
      'partial':'checkpoint received a duplicate tool result',
      'lost':'checkpoint history suffix was lost',
    }.get(m,'ok')
    if op=='final':
        expected_events=['final-enter']+([] if m=='cancel-sink' else ['final-error' if m=='sink-error' else 'final-ok'])
        if not m.startswith('persisted'):
            expected_effects=['a','b'] if m in NO_SCOPE or m in ('duplicate','lost') else ['b']
        if m=='duplicate':
            expected_revision+=1;expected_suffix=['a']
        elif expected_error=='ok' and m not in NO_SCOPE:
            expected_suffix=[] if m=='unbound' else ['a']
            if not m.startswith('persisted') and (m!='unbound' or nan):
                expected_revision+=1
    else:
        if m=='cancel-history':expected_effects=['c','b','a']
        if m=='partial':expected_suffix=['b']
        if m in ('bound','resume-history','wrap'):
            expected_suffix=['a','b','c'];expected_revision+=1
        elif m=='unbound' and nan:
            expected_revision+=1
    if m=='wrap':expected_revision=0  # original SeqCst fetch_add from u64::MAX
    assert s['revision']==expected_revision
    assert s['suffix']==expected_suffix and s['effects']==expected_effects
    assert s['all_locks_released'] and s['outcome']==expected_error
    assert s['rows']==s['from_rows']+len(expected_suffix)-int(m=='duplicate')
    assert len(s['retained'])==64 and all(c in '0123456789abcdef' for c in s['retained'])
    assert [e[0] for e in s['events']]==expected_events

def check_meters(r):
    op,m,n=r['op'],r['mode'],r['n']
    clone=r['baseline'];validate_stat(clone)
    assert clone['net_bytes']==0 and clone['allocs']==clone['frees']
    assert clone['alloc_bytes']==clone['free_bytes']==clone['peak_net_bytes']
    a,b=(r['meters'][k] for k in ('stock','candidate'))
    if m in NO_SCOPE:
        assert a is None and b is None
        return
    assert a is not None and b is not None
    for x in (a,b):validate_stat(x)
    save=not m.startswith('persisted')
    for k in ('alloc_bytes','free_bytes','allocs','frees'):
        assert a[k]-b[k]==(clone[k] if save else 0),(m,op,k,a,b,clone)
    assert a['net_bytes']==b['net_bytes']
    if m=='unbound':
        assert b['alloc_bytes']==b['allocs']==0
        if n in FLOORS:
            assert clone['allocs']==2*n+1
            assert clone['alloc_bytes']>=FLOORS[n]
    if n in FLOORS and save:assert clone['alloc_bytes']>=FLOORS[n]
    return dict(stock=a,candidate=b,avoided_requested_bytes=clone['alloc_bytes'] if save else 0,
                avoided_allocations=clone['allocs'] if save else 0,from_rows=r['state']['from_rows'],rows=r['state']['rows'])

def keys():
    k={(n,'plain',op,m) for n in (0,1) for op,m in PLAIN_SMALL}
    k|={(1,float_case,op,m) for float_case in FLOATS for op,m in FLOAT_MODES}
    k|={(n,'plain',op,m) for n in FLOORS for op,m in LARGE}
    k|={(1,'plain',op,'wrap') for op in ('final','settle')}
    return k

def check(path):
    rows=[json.loads(l) for l in pathlib.Path(path).read_text().splitlines()]
    seen=set();large={};typed_equality=0;scope_count=0
    for r in rows:
        if r.get('case')=='typed-equality':
            eq_control(r);typed_equality+=1;continue
        key=(r['n'],r['shape'],r['op'],r['mode'])
        assert key not in seen
        seen.add(key)
        check_state(r)
        m=check_meters(r)
        scope_count+=int(m is not None)
        if r['n'] in FLOORS:
            large[f"{r['op']}/{r['mode']}/{r['n']}"]=m
    want=keys()
    assert seen==want,{'missing':sorted(want-seen),'unexpected':sorted(seen-want)}
    assert typed_equality==1 and len(large)==12
    return dict(paired_route_cases=len(seen),typed_equality_controls=typed_equality,scoped_pairs=scope_count,large=large)

if __name__=='__main__':
    print(json.dumps(check(sys.argv[1]),sort_keys=True,indent=2))
