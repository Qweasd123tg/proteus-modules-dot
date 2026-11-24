#!/usr/bin/env python3
"""Independently verify R287 selected String/Layout generation ownership."""
import pathlib
import json
import sys

ROUTES=('projected','fallback','unstaged')
SHAPES=('output','error','both','whitespace-error','whitespace-output','empty-error','structured','status-ok','status-fail','denied','reset','live','effect-final','effect-only','duplicate','causal','embedded','subagent')
SIZES=(1<<20,4<<20,8<<20)
STORAGE_FAULTS=('page','prefix','named-write','head','wrong-page')
SOURCE_FAILURE={'wrong-page':'storage changed the fixed snapshot while paging','initial-wrong-session':'storage snapshot belongs to another session'}
EXTRA=('lineage','late-scan','frontier','edge','causal-text')
AL=('alloc_bytes','allocs')
FR=('free_bytes','frees')
ZERO=(0,0)
PROBE_FLOOR=2<<20

def amount_equal_except(a,b,keys,expect):
    assert all(type(s[k]) is int and s[k]>=0 for s in (a,b) for k in keys)
    assert tuple(a[k]-b[k] for k in keys)==expect,(keys,a,b,expect)

def strip_identity(obj):
    return {k:obj[k] for k in ('len','capacity')} if obj is not None else None

def compare_record(a,b):
    for k in ('seq','call','selected','accepted','row_alive_after_record_drop'):
        assert a[k]==b[k],(k,a[k],b[k])
    for k in ('original','row'):
        assert strip_identity(a[k])==strip_identity(b[k]),(k,a,b)
        for record in (a,b):
            if v:=record[k]: assert 0<v['len']<=v['capacity'] and v['generation']>0
    original=a['original']
    if a['accepted']:
        assert a['row'] is not None and a['row_alive_after_record_drop']
        assert a['append'] is not None and b['append'] is not None
        if original is not None:
            assert a['row']['len']==a['row']['capacity']==original['len']
    else:
        assert a['row'] is b['row'] is a['append'] is b['append'] is None
        assert not a['row_alive_after_record_drop']
    assert (a['selected'] is None)==(original is None)
    assert a['selected'] in (None,'output','error')
    copy=bool(a['accepted'] and original and original['len']==original['capacity'])
    saved=original['len'] if copy else 0
    assert not a['same_generation'] and not a['original_alive_after_record_drop']
    assert b['same_generation']==b['original_alive_after_record_drop']==copy
    if copy: assert b['original']['generation']==b['row']['generation']
    if a['accepted']:
        amount_equal_except(a['append'],b['append'],AL,(saved,int(copy)))
        amount_equal_except(a['append'],b['append'],FR,ZERO)
    amount_equal_except(a['callback'],b['callback'],AL,(saved,int(copy)))
    amount_equal_except(a['callback'],b['callback'],FR,(saved,int(copy)))
    return dict(call=a['call'],accepted=a['accepted'],selected=a['selected'],original=strip_identity(a['original']),
                row=strip_identity(a['row']),avoided_requested_bytes=saved,avoided_allocs=int(copy),
                assembly_stock=a['append'],assembly_candidate=b['append'])

def compare_case(r):
    a,b=(r['meters'][x] for x in ('stock','candidate'))
    assert (a is None)==(b is None)
    if a is None:return []
    assert a['replays']==b['replays']==1 and len(a['records'])==len(b['records'])
    return [compare_record(x,y) for x,y in zip(a['records'],b['records'],strict=True)]

def case_ids(shape_list=SHAPES):
    out={(route,n,shape,'ok') for route in ROUTES for shape in ('output','error') for n in SIZES}
    out|={(route,89,shape,'ok') for route in ROUTES for shape in shape_list}
    out|={(route,89,'output',f) for route in ROUTES for f in STORAGE_FAULTS}
    out|={(route,89,'output',f) for route in ROUTES[:2] for f in ('stage-early','stage-late')}
    out.add(('unstaged',1024,'loose','ok'))
    out|={(route,89,'output','initial-wrong-session') for route in ROUTES[1:]}
    return out

def supplement(r,obs):
    name=r['case']; assert name in EXTRA and r['passed']
    assert r['passes']==(2 if name=='causal-text' else 4) and r['error']==(name=='late-scan')
    if name=='causal-text':assert obs==[]
    if name in ('lineage','late-scan'):
        assert [x['call'] for x in obs]==['win','win','wrong-root','no-request','detached','live']
        assert [x['accepted'] for x in obs]==[True]+[False]*5
    if name=='frontier':assert [x['call'] for x in obs]==['missing'] and obs[0]['accepted']
    if name=='edge':
        a,b=obs;assert (a['call'],b['call'])==('loose-error','empty-reserved-error')
        assert a['selected']=='error' and a['original']['capacity']>a['original']['len'] and a['avoided_requested_bytes']==0
        assert b['selected']=='output' and b['avoided_requested_bytes']==len('wins-output')
 
def check(path):
    rows=[json.loads(s) for s in pathlib.Path(path).read_text().splitlines()]
    routes=set(); direct=set(); large={}; probes=0
    for r in rows:
        obs=compare_case(r)
        probes+=len(obs)
        if r['route']=='adversarial':
            assert r['case'] not in direct
            direct.add(r['case']);supplement(r,obs);continue
        route,n,shape,fault=(r[k] for k in ('route','n','shape','fault'))
        k=(route,n,shape,fault);assert k not in routes
        routes.add(k)
        trace=r['trace']; stage=r['stage']
        early=fault=='stage-early';late=fault=='stage-late';dup=shape=='duplicate'
        prefailed=dup or fault in SOURCE_FAILURE
        failed=early or late or prefailed
        assert trace.count('Render')==int(not prefailed)
        assert ('OpenDisplaySnapshot' in trace)==(route!='unstaged')
        if failed:
            assert r['rows']==r['capacity']==0 and not any(e.startswith('WriteCache ') for e in trace)
            assert ('duplicate tool result' if dup else SOURCE_FAILURE.get(fault,'transcript staging record count changed')) in r['result']
            assert r['ownership_capacities_sha256']==''
        else:
            for field in ('result','ownership_capacities_sha256'):
                assert len(r[field])==64 and all(c in '0123456789abcdef' for c in r[field])
            assert r['rows']>0 or shape=='live'
        if prefailed or route=='unstaged':assert stage=={'records':0,'bytes':0,'causal':False}
        else: assert stage['records']>0 and stage['bytes']>n and stage['causal']==(shape in ('causal','embedded'))
        if early or prefailed or shape in ('causal','embedded'):assert obs==[]
        else:
            if shape=='reset':assert all(x['call']!='detached' for x in obs)
            else:assert any(x['call']=='detached' and not x['accepted'] for x in obs)
            accepted=[x for x in obs if x['accepted']]
            assert len(accepted)==int(shape not in ('live','effect-only'))
            if accepted:
                x=accepted[0];assert x['call']=='call-visible'
                field=None if shape in ('structured','status-ok','status-fail') else 'error' if shape in ('error','both','denied','whitespace-error') else 'output'
                assert x['selected']==field,(k,x)
                if not failed:assert x['row']['capacity']==r['capacity']
                if shape=='loose':
                    assert x['original']['capacity']>x['original']['len'] and x['avoided_requested_bytes']==0
                elif field is not None:
                    assert x['avoided_requested_bytes']==x['row']['len']
                    if shape=='whitespace-error':assert x['avoided_requested_bytes']==3
                    if shape=='whitespace-output':assert x['avoided_requested_bytes']==2
                if n in SIZES:
                    assert x['avoided_requested_bytes']==n and x['row']['len']==n
                    if route in ROUTES[:2] and n>=4<<20:assert x['avoided_requested_bytes']>=PROBE_FLOOR
                    large[f'{route}/{shape}/{n}']=x
    expected=case_ids();assert routes==expected,{'missing':sorted(expected-routes),'extra':sorted(routes-expected)}
    assert direct==set(EXTRA) and len(large)==18
    return dict(paired_route_cases=len(routes),adversarial_renderer_only_cases=len(direct),observed_final_record_pairs=probes,large=large)

if __name__=='__main__':
    print(json.dumps(check(sys.argv[1]),sort_keys=True,indent=2))
