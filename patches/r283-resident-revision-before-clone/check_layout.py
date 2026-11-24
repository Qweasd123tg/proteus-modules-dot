#!/usr/bin/env python3
"""Check a single after-build raw JSONL independently of the Rust comparisons."""
import json,pathlib,sys
def check(p):
 rows=[json.loads(s) for s in pathlib.Path(p).read_text().splitlines()]
 ns=[(0,False),(1,False),(5000,False),(50000,False),(63,True)]
 actions=[('Lease','Park'),('Good','Park'),('Lease','Cancel'),
          ('WorkerError','Now'),('WrongResponse','Now'),('WrongSession','Now'),
          ('WorkerError','Park'),('Lease','Now'),('Good','Now'),('ReleaseError','Now'),('Good','NoStore')]
 assert {(r['rows'],r['mixed'],r['mode'],r['op']) for r in rows}=={(n,m,v,k) for n,m in ns for v,k in actions} and len(rows)==len(ns)*len(actions)
 layouts={r['layout'] for r in rows};assert len(layouts)==1 and layouts<={'default','preserve_order'}
 # Fixed lengths from independently known UTF-8 constructor (no benchmark constants).
 txt=lambda i:len(('Fixture row '+str(i)+'\n'+'Синтетический текст для замера памяти и прокрутки. '*4).encode())
 one=next(r['reference']['net_bytes'] for r in rows if r['rows']==1)
 static_per_row=one-txt(0)
 assert static_per_row>0
 summary={}
 for r in rows:
  n,m,op=r['rows'],r['mode'],r['op'];ref=r['reference'];a,b=r['stock'],r['candidate']
  assert ref['net_bytes']==ref['alloc_bytes'] and ref['free_bytes']==ref['free_n']==0
  if not r['mixed']:
   assert ref['alloc_n']==2*n+int(n!=0)
   assert ref['net_bytes']==n*static_per_row+sum(txt(i) for i in range(n))
  for k in ('trace','capacities_hash','outcome'):assert a[k]==b[k]
  for x in (a,b):
   for k in ('future_box','to_pending','to_exit'):
    s=x[k]; assert s['alloc_bytes']-s['free_bytes']==s['net_bytes']
   assert x['future_box']['alloc_n']==1 and x['future_box']['net_bytes']>0
  if op in ('Park','Cancel'):
   assert all(v==0 for v in b['to_pending'].values())
   assert a['to_pending']==ref
  if op=='Cancel':
   assert a['outcome']=='cancelled; retry revision 41' and a['trace']==[]
   assert all(sum(x[k]['net_bytes'] for k in ('future_box','to_pending','to_exit'))==0 for x in (a,b))
   continue
  fail=m in ('WrongSession','WrongResponse','WorkerError')
  for k in ('alloc_bytes','alloc_n','net_bytes'):
   diff=sum(a[q][k]-b[q][k] for q in ('to_pending','to_exit'))
   assert diff==(ref[k] if fail and k!='net_bytes' else 0)
  exp_rev=29 if op=='NoStore' else 41 if m=='Lease' else 73
  expect_error={'WrongSession':'storage snapshot belongs to another session','WrongResponse':'storage returned an unexpected snapshot response','WorkerError':'session no longer exists'}
  assert a['trace']==(['open'] if fail else [] if op=='NoStore' or m=='Lease' else ['open','release'])
  assert a['outcome']==expect_error.get(m,'ok revision '+str(exp_rev))
  if m=='Lease' and op=='Park':
   summary[str(n)]=dict(ref,stock_box=a['future_box']['net_bytes'],candidate_box=b['future_box']['net_bytes'])
 return {'layout':layouts.pop(),'paired_actions':len(rows),'public_combined_element_bytes':static_per_row,'pending_payload':summary}
if __name__=='__main__':print(json.dumps(check(sys.argv[1]),sort_keys=True,indent=2))
