"""Check actual measured route matrix, stage geometry and publication ordering."""
import hashlib,json,sys
from pathlib import Path
def checks(path):
 raw=path.read_bytes();data=[json.loads(line) for line in raw.splitlines()]
 expected=set()
 for route in ['projected','fallback','unstaged','projected-unstaged']:
  for f,n in [('ok',0),('ok',1),('ok',63),('many-single',70),('reset',63),('warm',63),('validator',63)]:
   expected.add((n,route,'prepared',f))
 for route in ['projected','fallback']:
  for f in ['late-lf','late-count','late-decode','page','prefix','named-write','head']:
   expected.add((63,route,'prepared',f))
  for kind,f in [('unnamed-page','ok'),('named-full','ok'),('named-full','unknown-named'),('unnamed-page','final-hash')]:
   expected.add((63,route,kind,f))
 for route in ['unstaged','projected-unstaged']:
  expected.add((63,route,'prepared','late-unstaged'))
 for route in ['suffix','codec']:
  expected.add((0,route,'identity','ok'))
 for route in ['projected','fallback','unstaged']:
  for n in [5000,50000]:expected.add((n,route,'prepared','ok'))
 seen=set();stages={};counters={}
 for r in data:
  key=tuple(r[k] for k in ['n','route','kind','fault']);assert key not in seen;seen.add(key)
  n,route,kind,f=key
  if kind=='identity':
   assert r['passed']
   continue
  head,tail=r['trace_first_last']
  if kind=='prepared':
   assert head[0]=='OpenSession' and head[1]=='ReadCache display-view-v1-head',key
  if n>=5000:
   assert len(r['result'])==64 and r['result_rows']==50
   assert any(event.startswith('ReadCache display-revision-') for event in tail)
   assert 'WriteCache display-view-v1-head' in tail and 'FinalOpen' not in tail
   expected_stage=n*400 if route!='unstaged' else -1
   if expected_stage>0:
    assert r['stage']['causal'] and r['stage']['records']==1 and r['stage']['file_bytes']>expected_stage
    stages.setdefault(n,set()).add(r['stage']['file_bytes'])
   else:assert r['stage']==dict(causal=False,records=0,file_bytes=0)
   d=[r['meters'][arm] for arm in ['stock','candidate']]
   assert all(arm['scans']==arm['decodes']==1 and len(arm['records'])==1 and arm['records'][0]['rows']==n for arm in d)
  if f.startswith('late-'):
   for arm in r['meters'].values():
    assert arm['scans']==1 and len(arm['records'])==1 and arm['records'][0]['visited']==n
    assert arm['decodes']==(2 if f=='late-decode' else 1)
   assert tail[-1]=='ReleaseSnapshot' and 'Digest' not in tail
   assert r['page_docs']==0 and not any(t.startswith('WriteCache ') for t in head+tail)
   counters[f]=counters.get(f,0)+1
  if f=='many-single':
   for arm in r['meters'].values():
    assert [(p['seq'],p['rows']) for p in arm['records']]==[(i+1,1) for i in range(n)]
  if f=='warm':
   assert r['meters']=={'stock':None,'candidate':None} and 'OpenDisplaySnapshot' not in head+tail
 assert seen==expected,(seen-expected,expected-seen)
 assert all(len(x)==1 for x in stages.values())
 assert counters=={x:2 for x in ['late-decode','late-count','late-lf','late-unstaged']}
 return dict(status='PASS',cases=len(seen),large_paired_cases=6,stage_records=1,stage_file_bytes={n:next(iter(x)) for n,x in sorted(stages.items())},faults_after_actual_callback=counters,raw_sha256=hashlib.sha256(raw).hexdigest())
if __name__=='__main__':
 print(json.dumps({str(p):checks(Path(p)) for p in sys.argv[1:]},sort_keys=True,indent=2))
