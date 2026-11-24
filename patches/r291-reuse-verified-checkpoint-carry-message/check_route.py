"""Independent actual strict/live route and generation-scope checker."""
import hashlib,json,sys
from pathlib import Path
def expected():
 e={(route,n,'carry',s) for route in ['strict','live'] for n in [1<<20,4<<20,8<<20] for s in ['output','error','structured']}
 e|={(route,173,m,s) for route in ['strict','live'] for m in ['carry','partial-ack','ack-all','none','changed-ack','delete-binding','changed-binding','changed-pending-binding','compacted','equal-prefix','before-revision'] for s in ['output','error','structured']}
 e|={('strict',173,'late-active',s) for s in ['output','error','structured']}
 e|={(route,0,'carry','output') for route in ['strict','live']}
 return e
def check(path):
 raw=path.read_bytes();seen=set();direct=set();large={};held=0;late=0
 for line in raw.splitlines():
  d=json.loads(line)
  if 'direct' in d:
   name=d['direct'];assert name not in direct;direct.add(name);continue
  r,n,m,s=(d[k] for k in ['route','n','mode','shape']);k=(r,n,m,s);assert k not in seen;seen.add(k)
  a,b=[d['meters'][x]['carries'] for x in ['stock','candidate']]
  assert len(a)==len(b)==len(d['carry'])
  if r=='strict':assert d['physical_bytes']>n
  else:
   assert d['physical_bytes']==0 and len(d['state']['sink_trace'])>=8
   held+=d['state']['checkpoint_locks_confirmed']
  if m=='late-active':
   assert len(a)==len(b)==2 and 'duplicate message id' in d['state']['error'];late+=1
  if m=='changed-binding':
   assert ('reuses a previously recorded result part identity' if r=='strict' else 'changed a pending tool result binding') in d['state']['error']
  if m=='changed-pending-binding':
   assert 'changed a pending tool result binding' in d['state']['error']
  for x,y in zip(a,b,strict=True):
   assert x['prepared_layout']==y['prepared_layout']
   for z in ['id','part_id','lengths','capacities']:assert x['inserted'][z]==y['inserted'][z]
   assert not any(x['prepared_live_at_insert']) and not any(x['prepared_owner_reused'])
   for ptr,reused,alive in zip(y['prepared']['owners'],y['prepared_owner_reused'],y['prepared_live_at_insert'],strict=True):
    assert reused==alive==(ptr is not None)
   assert x['layout']['alloc_bytes']-y['layout']['alloc_bytes']==x['prepared_layout']['alloc_bytes']
   assert x['layout']['allocs']-y['layout']['allocs']==x['prepared_layout']['allocs']
  if n>=1<<20:
   assert len(a)==1 and d['state']['error'] is None
   sel={'output':0,'error':1,'structured':4}[s]
   assert b[0]['prepared']['lengths'][sel]==n
   assert b[0]['prepared']['owners'][sel]['requested']==n
   difference=a[0]['layout']['alloc_bytes']-b[0]['layout']['alloc_bytes']
   assert difference>=n
   large[f'{r}/{s}/{n}']={'exact_removed_layout_bytes':difference,'body_bytes':n,'physical_bytes':d['physical_bytes']}
 assert seen==expected(),(seen-expected(),expected()-seen)
 assert len(direct)==13 and held==1 and late==3
 return dict(status='PASS',paired_actual_routes=len(seen),paired_direct=len(direct),physical_late_failures=late,
             live_lock_wait=held,large=large,raw_sha256=hashlib.sha256(raw).hexdigest())
if __name__=='__main__':print(json.dumps({p:check(Path(p)) for p in sys.argv[1:]},sort_keys=True,indent=2))
