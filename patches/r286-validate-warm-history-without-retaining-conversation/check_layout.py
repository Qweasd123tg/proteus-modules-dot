#!/usr/bin/env python3
"""Independent R286 checker against original warm/cold route raw JSONL."""
import pathlib
import json
import sys

GROUPS=('canonical_leaf','canonical_aggregate','canonical_parts','canonical_text','canonical_other',
        'context_leaf','context_aggregate','transcript_leaf','transcript_aggregate','transcript_other')
SECTIONS=('canonical','context','transcript')
MEM=('bytes','allocs')
ZERO={'bytes':0,'allocs':0}
FLOOR={5000:3*2**20,50000:30*2**20}
FAULTS=('cold-miss','cold-invalid','cold-page','cold-named','invalid-head','false-head','count-head',
        'initial-hash','initial-wrong-kind','initial-wrong-session','initial-missing','initial-release',
        'final-hash','final-revision','final-new-handle','final-wrong-kind','final-wrong-session',
        'final-missing','final-transport','final-release')
VALID={'ok','initial-release','final-new-handle','final-release'}
TARGETS=('conversation','context','transcript')

def total(owners,groups):
    assert set(owners)==set(GROUPS)
    assert all(set(c)==set(MEM) and all(type(c[k])==int and c[k]>=0 for k in MEM) for c in owners.values())
    return {k:sum(owners[g][k] for g in groups) for k in MEM}

def check_meters(r):
    a,b=(r['meters'][v] for v in ('stock','candidate'))
    kind=r['kind']; n=r['n'];ctx=r['ctx']
    if kind in ('named','page'):
        assert a is None and b is None
        return None
    assert a['load_n']==b['load_n']==1
    assert set(a['sections'])==set(b['sections'])==set(SECTIONS)
    secs=a['sections']; d=b['sections']
    for i,k in enumerate(SECTIONS):
        x=secs[k]; y=d[k]
        for j in ('entered','leaves','decoded','accepted','max_leaf_rows','leaf_layouts'):
            assert x[j]==y[j],(k,j,x[j],y[j])
        assert x['decoded']==x['accepted'] and x['max_leaf_rows']<=50
        assert bool(x['leaves'])==bool(x['accepted'])
        assert bool(x['entered']) or x['leaves']==0
        if i and x['entered']:assert secs[SECTIONS[i-1]]['entered']
        if k=='transcript' or kind=='full-model':
            assert x['aggregate_layouts']==y['aggregate_layouts']
            assert x['aggregate_peak_rows']==y['aggregate_peak_rows']==x['accepted']
        else:
            assert y['aggregate_layouts']==ZERO and y['aggregate_peak_rows']==0
        assert x['aggregate_layouts']['allocs']==int(x['accepted']!=0)
        assert x['aggregate_peak_rows']==x['accepted']
        for o in (x['enter_owners'],y['enter_owners']):
            assert all(o[g]==ZERO for g in ('canonical_leaf','context_leaf','transcript_leaf'))
        if kind=='history':assert total(y['enter_owners'],GROUPS[:7])==ZERO
        if k in ('context','transcript') and x['entered']:
            assert x['enter_owners']['canonical_aggregate']==secs['canonical']['aggregate_layouts']
        if k=='transcript' and x['entered']:
            assert x['enter_owners']['context_aggregate']==secs['context']['aggregate_layouts']
    af=a['final_owners'];bf=b['final_owners']
    assert (af is None)==(bf is None)
    assert (af is None)==('FinalOpen' not in r['trace'])
    if af is not None:
        assert af['transcript_aggregate']==bf['transcript_aggregate']==secs['transcript']['aggregate_layouts']
        assert af['transcript_other']==bf['transcript_other']
        assert af['transcript_leaf']==bf['transcript_leaf']==ZERO
        if kind=='history':
            assert total(bf,GROUPS[:7])==ZERO
            for g in GROUPS[:7]:assert af[g]==secs['transcript']['enter_owners'][g]
        else: assert af==bf
    if r['warm']:
        for k,num in zip(SECTIONS,(n,ctx,n),strict=True):
            assert secs[k]['entered'] and secs[k]['accepted']==num
            page=next(v for v in r['seed_cache']['sections'] if v['section']==('conversation' if k=='canonical' else k))
            assert page['pages']==secs[k]['leaves'] and page['rows']==num
        assert af is not None
        if n in FLOOR:
            x=secs['canonical']
            before=secs['transcript']['enter_owners']
            retained=total(before,GROUPS[:7])
            assert retained['bytes']>=FLOOR[n]
            assert af['canonical_aggregate']==x['aggregate_layouts']
            assert af['canonical_text']['allocs']==af['canonical_parts']['allocs']==n
            exact_text=sum(len(('Fixture row '+str(i)+'\n'+'Синтетический текст для замера памяти и прокрутки. '*4).encode()) for i in range(n))
            assert af['canonical_text']['bytes']==exact_text
            assert af['canonical_other']==ZERO
            assert a['canonical_typed_high_water']>=retained['bytes']
            assert 0 < b['canonical_typed_high_water'] < retained['bytes']
            assert secs['canonical']['max_leaf_rows']==50
            return dict(retained_stock_before_transcript=retained,owned_candidate_before_transcript=ZERO,
                        tagged_stock_before_final=total(af,GROUPS[:7]),tagged_candidate_before_final=total(bf,GROUPS[:7]),
                        final_rendered=total(af,GROUPS[7:]),typed_canonical_high_water_stock=a['canonical_typed_high_water'],
                        typed_canonical_high_water_candidate=b['canonical_typed_high_water'],max_decoded_leaf=x['max_leaf_rows'],
                        aggregate_buffer=x['aggregate_layouts'],typed_canonical_leaves=x['leaves'])
    return None

def case_ids():
    ids=set()
    for route in ('projected','fallback'):
        def add(n,ctx,kind,fault,tar=None):
            ids.add((route,n,ctx,kind,fault,tar))
        for n,ctx in ((0,0),(1,0),(49,1),(50,1),(51,1),(449,0),(450,0),(451,110),(5000,0),(50000,0)):
            add(n,ctx,'history','ok')
        for f in FAULTS:add(63,1,'history',f)
        for section,ctx in [('conversation',1),('context',110),('transcript',1)]:
            for late in (False,True):
                for f in ('type','count','missing','wrong-hash'):
                    add(451,ctx,'history',f,(section,late,f))
        for section in ('conversation','transcript'):
            for f in ('deflate','storage-wrong-kind','storage-failure','packed-bytes'):
                add(451,1,'history',f,(section,False,f))
        for section,ctx in [('conversation',1),('context',110)]:
            add(451,ctx,'history','singleton-bytes',(section,True,'singleton-bytes'))
        add(451,1,'history','typed-then-invalid',('conversation',True,'type'))
        for k in ('full-model','named','page'):add(451,110,k,'ok')
    return ids

def check(path):
    rows=[json.loads(s) for s in pathlib.Path(path).read_text().splitlines()]
    seen=set(); large={}; corrupted=set(); context=0; pristine_hits=0
    for r in rows:
        n,ctx,route,kind,fault=map(r.get,['n','ctx','route','kind','fault'])
        x=r['target']
        target=(x['section'],x['late'],x['method']) if x is not None else None
        key=(route,n,ctx,kind,fault,target)
        assert key not in seen
        seen.add(key)
        t=r['trace']
        bad=bool(fault in ('cold-invalid','typed-then-invalid'))
        assert r['warm']==(fault in VALID)
        if kind=='history': assert t[0]=='OpenSession'
        if r['warm']:
            assert not any(s.startswith('WriteCache ') or s in ('Render','OpenDisplaySnapshot') for s in t)
            if kind in ('history','full-model'):
                assert t.count('OpenSnapshot')==t.count('ReleaseSnapshot')==t.count('FinalOpen')==t.count('FinalRelease')==1
                i=t.index('OpenSnapshot')
                h=t.index('ReadCache display-view-v1-head')
                assert h<i and t[i+1]=='ReleaseSnapshot' and t[-2:]==['FinalOpen','FinalRelease']
                if kind=='history':pristine_hits+=1
            if kind=='history' and ctx:
                context+=1
        else:
            assert t.count('Render')==int(not bad)
            if bad: assert t.count('FinalOpen')==0 and not any(s.startswith('WriteCache ') for s in t)
        if bad:assert 'history revision must increment' in r['result'] and r['rows']==r['capacity']==0
        else:
            assert len(r['result'])==64 and all(c in '0123456789abcdef' for c in r['result'])
            assert r['rows']==(min(n,50) if kind=='page' else n) and r['capacity']>=r['rows']
            if kind=='history' and r['warm']:assert r['capacity']==r['rows']
        if x is not None:
            s,late,how=target
            assert 'FinalOpen' not in t
            assert x['packed']==(s!='context' and not late),(key,x)
            if how in ('type','count'):
                a,b,c=r['typed_boundary'][TARGETS.index(s)]
                assert a==b+1 and c==int(how=='count')
                assert len(x['key'])==len('display-data-')+64 and x['key'].startswith('display-data-')
                assert f'ReadCache {x["key"]}' in t
                corrupted.add((s,late,how,route))
        m=check_meters(r)
        if m is not None:
            assert r['seed_cache']['seed_stage_file_bytes']>n*400
            assert len(r['seed_cache']['sections'])==3
            assert all(s['packs']>0 for s in r['seed_cache']['sections'] if s['section']!='context')
            large[f'{route}/{n}']=m
    expected=case_ids()
    assert seen==expected,{'missing':sorted(map(str,expected-seen)),'unexpected':sorted(map(str,seen-expected))}
    assert len(large)==4 and len(corrupted)==24
    return dict(paired_route_cases=len(seen),warm_full_history_pairs=pristine_hits,
                warm_context_pairs=context,protected_readdressed_type_cardinality_paths=len(corrupted),
                large=large)

if __name__=='__main__':
    print(json.dumps(check(sys.argv[1]),sort_keys=True,indent=2))
