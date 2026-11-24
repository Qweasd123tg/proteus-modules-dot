"""Independent same-origin strict route and typed scope witness."""
import json,hashlib,sys
from pathlib import Path
def expected():
 e={(n,m,s,t) for n in (1<<20,4<<20,8<<20) for m,s,t in [('bound','plain','canceled'),('multiple','mixed','success'),('only-unbound','mixed','failed')]}
 for mode,status in [
  ('bound','success'),('bound','failed'),('bound','canceled'),
  ('multiple','canceled'),('only-unbound','success'),('owner-bypass','success'),('nested-detached','canceled'),
  ('no-effects','success'),('previous-turn','success'),('only-final','canceled'),('mixed-final','failed'),('late-part','success'),
  ('late-active','canceled'),('saturated','success'),('context','canceled'),('already-settled','success'),
  ('bad-seq','success'),('bad-session','success'),('bad-schema','success')]:
  for shape in ('plain','mixed'):e.add((137,mode,shape,status))
 e.add((0,'bound','plain','success'))
 return e
def verify(path):
 raw=path.read_bytes();seen=set();late=0;prim={}
 for line in raw.splitlines():
  x=json.loads(line);k=tuple(x[v] for v in ('n','mode','shape','status'));assert k not in seen;seen.add(k)
  n,m,s,t=k;state=x['state'];order=x['order'];visit=x['visited']
  assert state['original_ledger_alive'] and len(state['history_sha256'])==64
  assert x['physical_bytes']>n
  if m in ['bad-seq','bad-session','bad-schema','already-settled']:
   assert not visit and state['next_seq']==state['source_seq'] and state['error']
  elif m=='owner-bypass':
   assert order==['u'] and not visit and not state['error']
  elif m.startswith('late-'):
   at=order.index(x['culprit'])
   assert visit==order[:at+1] and len(visit)>=2 and state['error'] and state['bound_after']
   assert state['next_seq']==state['source_seq'] and state['revision']==state['before_rev']+2
   late+=1
  else:
   assert visit==order and state['next_seq']==state['source_seq']+1 and not state['error'] and not state['bound_after']
  if m in ['nested-detached','previous-turn']:assert visit==['a']
  if m=='context':assert len(state['context'])==1
  if n>=1<<20:
   a,b=[x['meters'][label]['pending'] for label in ('stock','candidate')]
   assert order==[r['call'] for r in a['eligible']]==[r['call'] for r in b['eligible']]
   assert x['physical_bytes']>=n*len(visit)
   assert not any(b['map_clone'].values())
   assert all(r['borrowed_body'] and r['shared_output'] for r in b['eligible'])
   assert all(not r['borrowed_body'] and not r['shared_output'] for r in a['eligible'])
   for i,j in zip(a['eligible'],b['eligible'],strict=True):
    assert i['output_len']==j['output_len']==n and i['canonical']==j['canonical']
    if i['canonical'] is not None:assert i['canonical']['owned_output']
   removed=a['prepare']['alloc_bytes']-b['prepare']['alloc_bytes']
   assert removed>=n*len(visit)
   prim[f'{m}/{n}']={"physical_bytes":x['physical_bytes'],"eligible":len(visit),"removed_requested_preparation":removed}
 assert seen==expected(),(seen-expected(),expected()-seen)
 return dict(status='PASS',paired_cases=len(seen),genuine_late_errors=late,physical_large_cases=len(prim),large=prim,raw_sha256=hashlib.sha256(raw).hexdigest())
if __name__=='__main__':
 print(json.dumps({p:verify(Path(p)) for p in sys.argv[1:]},sort_keys=True,indent=2))
