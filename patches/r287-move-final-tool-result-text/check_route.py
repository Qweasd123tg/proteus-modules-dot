"""Independent exact route matrix and physical/lineage/late-failure assertions."""
import hashlib,json,sys
from pathlib import Path
ROUTES=('projected','fallback','unstaged')
SHAPES=('output','error','both','whitespace-error','whitespace-output','empty-error',
 'structured','status-ok','status-fail','denied','reset','live','effect-final','effect-only',
 'duplicate','causal','embedded','subagent')
CASES=('lineage','late-scan','frontier','edge','causal-text')
def expected():
 e=set()
 for r in ROUTES:
  for n in [1<<20,4<<20,8<<20]:
   for shape in ['output','error']:e.add((r,shape,n,'ok'))
  for s in SHAPES:e.add((r,s,89,'ok'))
  if r=='unstaged':e.add((r,'loose',1024,'ok'))
  for f in ['page','prefix','named-write','head','wrong-page']:e.add((r,'output',89,f))
  if r!='projected':e.add((r,'output',89,'initial-wrong-session'))
  if r!='unstaged':
   for f in ['stage-early','stage-late']:e.add((r,'output',89,f))
 for n in CASES:e.add(('adversarial',n,0,'renderer-only'))
 return e
def check(p):
 raw=p.read_bytes();seen=set();first={};physical=[];dircaps=set();negative=0
 for l in raw.splitlines():
  d=json.loads(l);r=d['route']
  if r=='adversarial':
   assert d['passed'] and d['kind']=='renderer-only'
   k=(r,d['case'],0,'renderer-only');assert k not in seen;seen.add(k)
   continue
  shape,n,f=[d[k] for k in ('shape','n','fault')]
  k=(r,shape,n,f);assert k not in seen;seen.add(k);trace=d['trace'];spooled=r!='unstaged'
  failed=f in ['stage-early','stage-late','wrong-page','initial-wrong-session'] or shape=='duplicate'
  if failed:
   negative+=1
   assert d['rows']==d['capacity']==0 and d['ownership_capacities_sha256']==""
   assert not any(t.startswith('WriteCache ') for t in trace)
  else:
   assert len(d['result'])==len(d['ownership_capacities_sha256'])==64
   dircaps.add(d['ownership_capacities_sha256'])
  if f in ['wrong-page','initial-wrong-session'] or shape=='duplicate':
   assert 'Render' not in trace
  else:
   assert trace.count('Render')==1 and 'ReleaseSnapshot' in trace
  if n>=1<<20:
   assert d['capacity']==n and d['rows']==2
   assert d['stage']['records']==(9 if spooled else 0)
   assert d['stage']['bytes']>n if spooled else d['stage']['bytes']==0
   assert not d['stage']['causal']
   scan='ReadDisplayRecords' if r=='projected' else 'ReadRecords'
   assert f'{scan} 0' in trace
   if n>=4<<20:assert any(t.startswith(scan+' ') and t!=f'{scan} 0' for t in trace)
   assert any(t.startswith('WriteCache display-revision-') for t in trace)
   a,b=[next(x for x in d['meters'][g]['records'] if x['call']=='call-visible') for g in ['stock','candidate']]
   assert a['accepted'] is b['accepted'] is True and b['same_generation'] and not a['same_generation']
   assert a['append']['alloc_bytes']-b['append']['alloc_bytes']==n
   assert a['append']['allocs']-b['append']['allocs']==1
   first.setdefault(r,[]).append(n)
   if spooled:physical.append((r,n,shape,d['stage']['bytes']))
 assert seen==expected(),(seen-expected(),expected()-seen)
 return dict(status='PASS',raw_sha256=hashlib.sha256(raw).hexdigest(),paired_cases=len(seen),
    physical_primary=len(physical),rejected_store_cases=negative,
    affected_requested_copy_bytes_by_route={r:sum(q) for r,q in first.items()},physical_stage_bytes=physical)
if __name__=='__main__':
 print(json.dumps({s:check(Path(s)) for s in sys.argv[1:]},sort_keys=True,indent=2))
