"""Independent R290 actual index path and source geometry assertions."""
import hashlib,json,sys
from pathlib import Path
def expected():
 e={(n,m,'plain',t) for n in [5000,50000] for m,t in [
  ('final-middle','success'),('final-tail','success'),('final-shared','success'),('settle-unique','canceled'),('settle-shared','canceled')]}
 for m,t in [('final-middle','success'),('final-tail','success'),('final-shared','success'),('settle-unique','canceled'),('settle-shared','canceled'),
 ('unbound-final','success'),('no-owner-settle','failed'),('none-followup','success'),('collision-after-part','success'),('collision-before-part','success'),
 ('collision-after-message','success'),('collision-before-message','success'),('both-conflicts','success'),('known-after','success'),
 ('settle-late','failed'),('duplicate-final','success'),('lost-final','success'),('bad-seq','success'),('saturated','success'),('context','canceled'),('settle-nested','canceled')]:
  for s in ['plain','mixed']:e.add((17,m,s,t))
 e.add((0,'final-middle','plain','success'))
 return e
def verify(path):
 raw=path.read_bytes();seen=set();direct=set();positive={};middle=0;tail=0;fall=0
 for line in raw.splitlines():
  d=json.loads(line);a,b=[d['meters'][arm]['active_checks'] for arm in ('stock','candidate')]
  if 'direct' in d:
   name=d['direct'];assert name not in direct;direct.add(name)
   assert d['passed'] and len(a)==len(b)==1 and a==b and not b[0]['fast']
   assert b[0]['scanned_rows']==b[0]['history_len']
   continue
  n,m,s,t=tuple(d[k] for k in ('n','mode','shape','status'))
  key=(n,m,s,t);assert key not in seen;seen.add(key)
  state=d['state'];assert len(a)==len(b)==len(state['captured'])
  assert d['physical_bytes']>n*400 and len(state['history_sha256'])==64
  for x,y in zip(a,b,strict=True):
   assert not x['fast'] and x['index']==y['index'] and x['history_len']==y['history_len']
   if y['fast']:
    assert y['pre_unique'] and y['pre_present'] and y['result_ok']
    assert y['scanned_rows']==y['scanned_parts']==0
   else:
    assert (x['scanned_rows'],x['scanned_parts'],x['layout'],x['result_ok'])==(y['scanned_rows'],y['scanned_parts'],y['layout'],y['result_ok'])
    fall+=1
  if m=='final-middle':
   assert b[0]['index']+1<b[0]['history_len'];middle+=1
  if m=='final-tail':
   assert b[0]['index']+1==b[0]['history_len'];tail+=1
  if m=='settle-shared':
   assert len(b)==2 and not b[0]['fast'] and b[1]['fast']
  if m in ('known-after','settle-late'):
   assert state['after_present'] and state['error'] and all(z['result_ok'] for z in b)
  if m=='none-followup':
   assert not state['before_present'] and not state['after_present'] and not b[0]['fast']
  if n>=5000 and m in ('final-middle','final-tail'):
   savings=a[0]['layout']['alloc_bytes']-b[0]['layout']['alloc_bytes']
   assert b[0]['fast'] and savings >= (100<<10 if n==5000 else 1<<20)
   positive[f'{m}/{n}']=dict(removed_requested_layout=savings,stock_scan_rows=a[0]['scanned_rows'],stock_scan_parts=a[0]['scanned_parts'])
 assert seen==expected(),(seen-expected(),expected()-seen)
 assert direct=={'unknown-index','not-singleton','weak-index'}
 return dict(status='PASS',physical_pairs=len(seen),private_direct_pairs=len(direct),middle=middle,tail=tail,fallback_checks=fall,primary=positive,raw_sha256=hashlib.sha256(raw).hexdigest())
if __name__=='__main__':print(json.dumps({p:verify(Path(p)) for p in sys.argv[1:]},sort_keys=True,indent=2))
