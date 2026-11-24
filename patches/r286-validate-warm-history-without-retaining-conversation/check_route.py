"""Check R286 physical cache-hit route and well-addressed typed failure boundaries."""
import hashlib,json,sys
from pathlib import Path
def expected_cases():
 keys=set()
 for r in ['projected','fallback']:
  for n,c in [(0,0),(1,0),(49,1),(50,1),(51,1),(449,0),(450,0),(451,110),(5000,0),(50000,0)]:
   keys.add((r,'history','ok',n,c,None))
  for f in ['cold-miss','cold-invalid','cold-page','cold-named','invalid-head','false-head','count-head',
     'initial-hash','initial-wrong-kind','initial-wrong-session','initial-missing','initial-release',
     'final-hash','final-revision','final-new-handle','final-wrong-kind','final-wrong-session','final-missing',
     'final-transport','final-release']:
   keys.add((r,'history',f,63,1,None))
  for section,c in [('conversation',1),('context',110),('transcript',1)]:
   for late in [False,True]:
    for f in ['type','count','missing','wrong-hash']:
     keys.add((r,'history',f,451,c,(section,late,f)))
  for section in ['conversation','transcript']:
   for f in ['deflate','packed-bytes','storage-wrong-kind','storage-failure']:
    keys.add((r,'history',f,451,1,(section,False,f)))
  for section,c in [('conversation',1),('context',110)]:
   f='singleton-bytes';keys.add((r,'history',f,451,c,(section,True,f)))
  keys.add((r,'history','typed-then-invalid',451,1,('conversation',True,'type')))
  for kind in ['full-model','named','page']:keys.add((r,kind,'ok',451,110,None))
 return keys
def verify(path):
 raw=path.read_bytes();records=[json.loads(row) for row in raw.splitlines()]
 keys=set(); physical={}; malformed=0; bad_counts=0; checked_handles=0
 for d in records:
  n,k,f,r,ctx=[d[x] for x in ['n','kind','fault','route','ctx']]
  t,trace=d['target'],d['trace']
  key=(r,k,f,n,ctx,(t['section'],t['late'],t['method']) if t else None)
  assert key not in keys;keys.add(key)
  if n>=5000:
   assert d['warm'] and k=='history' and d['rows']==d['capacity']==n
   assert d['seed_cache']['seed_stage_file_bytes']>n*400
   physical.setdefault(n,set()).add(d['seed_cache']['seed_stage_file_bytes'])
   assert d['fallback_stage']==dict(records=0,bytes=0,causal=False)
   assert trace[:4]==['OpenSession','ReadCache display-view-v1-head','OpenSnapshot','ReleaseSnapshot']
   assert trace[-2:]==['FinalOpen','FinalRelease'] and not any(x.startswith('WriteCache ') for x in trace)
   by_section={x['section']:x for x in d['seed_cache']['sections']}
   for s in ['conversation','transcript']:assert by_section[s]['rows']==n and by_section[s]['packs']>0
  if t is not None:
   assert not d['warm'] and 'FinalOpen' not in trace
   i=['conversation','context','transcript'].index(t['section'])
   attempts,good,wrong_count=d['typed_boundary'][i]
   how=t['method']
   if how in ['type','count']:
    assert attempts==good+1
    assert wrong_count==int(how=='count')
    assert (good>0)==t['late']
    assert ('ReadCache '+t['key']) in trace
    malformed+=how=='type';bad_counts+=how=='count'
   elif how=='singleton-bytes':
    assert not t['packed'] and attempts==0
   elif how in ['packed-bytes','deflate']:
    assert t['packed'] and attempts==0
  if 'FinalOpen' in trace:
   want=f not in ['final-missing','final-wrong-kind','final-wrong-session','final-transport']
   at=trace.index('FinalOpen')
   assert (trace[at+1:at+2]==['FinalRelease'])==want
   checked_handles+=want
 assert keys==expected_cases(),(keys-expected_cases(),expected_cases()-keys)
 assert all(len(v)==1 for v in physical.values())
 return {'status':'PASS','paired_cases':len(keys),'physical_large_cases':4,'seed_stage_file_bytes':{n:next(iter(v)) for n,v in physical.items()},'well_addressed_type_rejections':malformed,'well_addressed_count_rejections':bad_counts,'checked_final_handle_releases':checked_handles,'raw_sha256':hashlib.sha256(raw).hexdigest()}
if __name__=='__main__':
 print(json.dumps({p:verify(Path(p)) for p in sys.argv[1:]},indent=2,sort_keys=True))
