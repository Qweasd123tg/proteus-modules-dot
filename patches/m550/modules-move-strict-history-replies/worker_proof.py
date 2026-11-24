#!/usr/bin/env python3
"""Direct old-SDK worker stdio comparison on one synthetic, shared source."""
from pathlib import Path
import argparse, hashlib, json, os, re, subprocess, tempfile

MAX = 128*1024*1024
hash_ = lambda x: hashlib.sha256(x).hexdigest()
snapshot_key = re.compile(rb'"snapshot_id":"[0-9a-fA-F-]{36}"')
def normalize(raw,count):
 norm,n=snapshot_key.subn(b'"snapshot_id":"00000000-0000-0000-0000-000000000000"',raw)
 assert n==count,(n,count)
 return [len(raw),hash_(norm)]

class Worker:
 def __init__(self,exe,backend,feature,cap=MAX):
  self.err=tempfile.TemporaryFile(mode='w+b')
  self.p=subprocess.Popen([exe],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=self.err,
                         env=dict(os.environ,PROTEUS_MODULE_MAX_FRAME_BYTES=str(cap)))
  self.module=backend
  self.sequence=0
  self.send({
   "jsonrpc":"2.0","id":"h:1:0","method":"initialize",
   "params":{"protocol_version":"v3","component_id":"storage-proof",
             "exports":[{"slot":"session_storage","module_id":backend,"contract_version":"v2",
                         "composition":"select_one","module_config":{},
                         "host_features":["display_projection"] if feature else []}]}})
  self.hello=self.p.stdout.readline()
  h=json.loads(self.hello)
  assert h["id"]=="h:1:0" and h["result"]["exports"][0]["module_features"]==(["display_projection"] if feature else [])
 def send(self,frame):
  self.p.stdin.write(json.dumps(frame,separators=(',',':')).encode()+b'\n')
  self.p.stdin.flush()
 def execute(self,req,method='execute'):
  self.sequence+=1
  i=f"h:1:{self.sequence}"
  self.send({"jsonrpc":"2.0","id":i,"method":method,
             "params":{"export":{"slot":"session_storage","module_id":self.module},
                       "lineage":{"root_invocation_id":i,"parent_invocation_id":None,"depth":0},
                       "params":req}})
  line=self.p.stdout.readline()
  if not line:return None,b''
  assert line.endswith(b'\n')
  v=json.loads(line)
  assert v['id']==i and v['jsonrpc']=='2.0'
  return v,line
 def finish(self,expected_status=0):
  self.p.stdin.close()
  assert self.p.wait(timeout=30)==expected_status
  extra=self.p.stdout.read()
  self.err.seek(0)
  stderr=self.err.read()
  self.err.close()
  assert not extra
  return stderr
 def __enter__(self):return self
 def __exit__(self,*exc):
  if self.p.poll() is None:
   self.p.kill()
   self.p.wait(timeout=30)
  for f in [self.p.stdin,self.p.stdout,self.err]:
   if not f.closed:f.close()

def result(w,req):
 v,b=w.execute(req)
 assert v is not None and 'result' in v,(req.get('operation'),str(v)[:350])
 return v['result'],b
def pending_cases(exe,backend,session,projection,cap=MAX,save=None):
 with Worker(exe,backend,projection,cap) as w:
  if projection:
   v,d=result(w,dict(operation='open_display_snapshot',session=session))
   assert v=={'result':'display_snapshot','projection':None}
   fallback=normalize(d,0)
  else:
   fallback=None
  v,d=result(w,dict(operation='open_snapshot',session=session))
  snap=v['snapshot']
  assert snap['revision']==dict(session_seq=3,history_revision=3)
  req=dict(operation='read_records',snapshot=snap,after_seq=0,limit=2)
  checks={'open':normalize(d,1),'fallback':fallback}
  for after,want,msgs in [(0,1,1),(1,2,50000),(2,3,1),(3,None,0)]:
   req['after_seq']=after
   v,d=result(w,req)
   p=v['page'];assert v['result']=='records' and p['snapshot']==snap
   assert [r['session_seq'] for r in p['records']]==([] if want is None else [want])
   assert p['next_after_seq']==(want if want in (1,2) else None)
   if want is not None:
    r,=p['records']; e=r['entry']
    h=e['payload']; ms=h['messages']
    assert r['session_id']==session['session_id'] and e['kind']=='history_mutated'
    assert h['previous_revision']==after and h['new_revision']==want and h['mutation']=='append'
    assert len(ms)==msgs
    if want==2:
     assert len(d)>32*1024*1024  # Above the real projection state cap.
     assert ms[0]['parts'][0]['payload']['Text']['text'].startswith('Fixture row 1\n')
     assert ms[-1]['parts'][0]['payload']['Text']['text'].startswith('Fixture row 50000\n')
     if save is not None: save.write_bytes(d)
    del h,e,r,ms
   checks[f'page-{after}']=normalize(d,1)
   del d,p,v
  # Same snapshot and cold-rewind; compare all bytes except JSON-RPC ID.
  for after in [0,1]:
   req['after_seq']=after
   _,d=result(w,req)
   new_id='h:1:'+str(w.sequence)
   previous_id='h:1:'+str((2 if projection else 1)+after+1)
   d=d.replace(b'"id":'+json.dumps(new_id).encode(), b'"id":'+json.dumps(previous_id).encode(),1)
   assert normalize(d,1)==checks[f'page-{after}']
   del d
  def error(label,query,text,exact=True,method='execute'):
   v,d=w.execute(query,method)
   assert v['error']['code']==-32000, v
   message=v['error']['message']
   assert (message==text if exact else text in message),(label,message)
   checks[label]=normalize(d,0)
  error('cursor_before_limit',dict(req,after_seq=99,limit=0),'storage record cursor exceeds its snapshot')
  error('invalid_limit',dict(req,after_seq=1,limit=0),'invalid storage record page limit')
  error('identity',dict(req,snapshot=dict(snap,content_sha256='0'*64)),'snapshot identity/revision/fingerprint mismatch')
  error('unknown_field',dict(req,extra=1),'unknown field `extra`',False)
  error('wrong_method',req,'is not allowed for slot session_storage',False,'storage_probe_unsupported')
  if not projection:
   error('display_open_rejected',dict(operation='open_display_snapshot',session=session),'session storage display projection was not negotiated')
   error('display_read_rejected',dict(req,operation='read_display_records'),'session storage display projection was not negotiated')
  v,_=result(w,dict(operation='release_snapshot',snapshot=snap)); assert v['result']=='done'
  error('released_snapshot',req,'snapshot handle expired or unknown')
  assert not w.finish()
  return checks

def exact_frames(exe,session,first):
 checks={}
 for cap in [first[0],first[0]-1]:
  with Worker(exe,'jsonl',False,cap) as w:
   r,_=result(w,dict(operation='open_snapshot',session=session))
   q=dict(operation='read_records',snapshot=r['snapshot'],after_seq=0,limit=2)
   v,_=result(w,q); assert [p['session_seq'] for p in v['page']['records']]==[1]
   v,d=w.execute(dict(q,after_seq=1))
   if cap==first[0]:
    assert v is not None and normalize(d,1)==first
    assert not w.finish()
    checks['exact']=cap
   else:
    assert v is None and d==b''
    err=w.finish(expected_status=1)
    assert b'worker output frame exceeded its configured byte budget' in err
    checks['one_below']=[cap,hash_(err)]
 return checks

def small_controls(exe,fixtures):
 checks={}
 for backend,data in fixtures.items():
  session=data['multi']
  with Worker(exe,backend,True) as w:
   p,d=result(w,dict(operation='open_display_snapshot',session=session))
   projection=p['projection']; snap=projection['snapshot']
   assert snap['revision']==dict(session_seq=3,history_revision=3)
   n=len(projection['state']['conversation']['messages']);assert n==10500
   checks[backend]={'display_open':normalize(d,1)}
   r,d=result(w,dict(operation='read_display_records',snapshot=snap,after_seq=0,limit=100))
   assert [x['session_seq'] for x in r['page']['records']]==[1]
   checks[backend]['display_records']=normalize(d,1)
   v,d=result(w,dict(operation='open_snapshot',session=session))
   assert v['snapshot']['revision']==snap['revision']
   strict=v['snapshot']
   for after in (0,1,2):
    r,d=result(w,dict(operation='read_records',snapshot=strict,after_seq=after,limit=2))
    assert [x['session_seq'] for x in r['page']['records']]==[after+1]
    checks[backend]['strict-'+str(after)]=normalize(d,1)
   assert not w.finish()
 return checks

def run(exe,manifest,small,mode,arm,out,save=False):
 checks={}
 for k,session in manifest:
  backend=k.lower()
  legacy=pending_cases(exe,backend,session,False,
           save=(out/f'{mode}-strict-50k-frame.json') if save and backend=='jsonl' else None)
  projection=pending_cases(exe,backend,session,True)
  assert legacy['page-1'][0]==projection['page-1'][0]
  checks[backend]={'legacy':legacy,'negotiated_none':projection}
  if backend=='jsonl':
   checks[backend]['cap']=exact_frames(exe,session,legacy['page-1'])
 if small is not None:
  checks['preserved_display_and_multi']=small_controls(exe,small)
 (out/f'{arm}-{mode}.json').write_text(json.dumps(checks,indent=2)+'\n')
 return checks

def main():
 a=argparse.ArgumentParser(description=__doc__)
 for k in ['baseline','candidate','manifest','out']: a.add_argument(k,type=Path)
 a.add_argument('mode',choices=('default','preserve_order'))
 a.add_argument('--small-manifest',type=Path)
 a.add_argument('--save-frame',action='store_true')
 cfg=a.parse_args()
 corpus=json.loads(cfg.manifest.read_text())
 small=json.loads(cfg.small_manifest.read_text()) if cfg.small_manifest is not None else None
 cfg.out.mkdir(parents=True,exist_ok=True)
 old=run(cfg.baseline.resolve(),corpus,small,cfg.mode,'baseline',cfg.out,cfg.save_frame)
 new=run(cfg.candidate.resolve(),corpus,small,cfg.mode,'candidate',cfg.out)
 assert old==new
 print(json.dumps(new,indent=2))

if __name__=='__main__': main()
