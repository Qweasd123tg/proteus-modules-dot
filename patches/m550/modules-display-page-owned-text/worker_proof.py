#!/usr/bin/env python3
"""Direct old-SDK worker stdio comparison on one synthetic, shared source."""
from pathlib import Path
import argparse, concurrent.futures, hashlib, json, os, re, subprocess, tempfile

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
def seed(exe,frame,out):
 import uuid
 out.mkdir(parents=True,exist_ok=True)
 rows=json.loads(frame.read_bytes())['result']['projection']['state']['conversation']['messages']
 assert len(rows)==50000
 manifest={}
 uuid_=lambda: str(uuid.uuid4())
 for backend in ('jsonl','sqlite'):
  manifest[backend]={}
  for shape in ('single','multi'):
   dest=out/f'{backend}-{shape}'
   root=dest/'config';work=dest/'workspace'
   root.mkdir(parents=True);work.mkdir()
   with Worker(exe,backend,True) as w:
    r,_=result(w,dict(operation='create',config_root=str(root),workspace_path=str(work),session_id=uuid_(),parent_session_id=None))
    session=r['descriptor']['session']
    r,_=result(w,dict(operation='acquire_writer',session=session))
    lease=r['lease'];rev=r['revision']
    expected=0
    parts=[rows] if shape=='single' else [rows[i:i+3500] for i in range(0,10500,3500)]
    for messages in parts:
     r,_=result(w,dict(operation='commit',commit=dict(lease=lease,operation_id=uuid_(),
       expected=rev,timestamp_ms=1234+expected,
       attribution=dict(execution_id=None,thread_id=uuid_(),turn_id=None),
       entry=dict(kind='history_mutated',payload=dict(previous_revision=expected,new_revision=expected+1,
         mutation='append',messages=messages,compaction=None,tool_results=[])))))
     rev=r['ack']['revision']
     expected+=1
     assert rev==dict(session_seq=expected,history_revision=expected)
    result(w,dict(operation='release_writer',lease=lease))
    assert not w.finish()
    manifest[backend][shape]=session
 artifact=out/'manifest.json'
 artifact.write_text(json.dumps(manifest,indent=2)+'\n')
 return artifact

def run(exe,manifest,mode,arm,out,save=False):
 normalized={}
 cap=4*1024*1024
 for k,cases in manifest.items():
  out_={}
  for kind,session in cases.items():
   with Worker(exe,k,True) as w:
    op=dict(operation='open_display_snapshot',session=session)
    r,data=result(w,op)
    projection=r['projection']
    assert projection['snapshot']['revision']['session_seq']==(1 if kind=='single' else 3)
    row_count=50000 if kind=='single' else 10500
    assert len(projection['state']['conversation']['messages'])==row_count
    snapshot=projection['snapshot']; del projection,r
    open_size=len(data)
    checks={'opener':normalize(data,1)}
    del data
    first=None
    if kind=='single':
     req=dict(operation='read_display_records',snapshot=snapshot,after_seq=0,limit=10)
     r,data=result(w,req)
     page=r['page'];assert page['next_after_seq'] is None and len(page['records'])==1
     ms=page['records'][0]['entry']['payload']['messages'];assert len(ms)==50000
     assert ms[0]['parts'][0]['payload']['Text']['text'].startswith('Fixture row 1\n')
     assert ms[-1]['parts'][0]['payload']['Text']['text'].startswith('Fixture row 50000\n')
     first=normalize(data,1);checks['one_record']=first
     assert len(data)>open_size and len(data)>cap
     if save and k=='jsonl':(out/f'{mode}-records-frame.json').write_bytes(data)
     del r,data,page,ms
     r,data=result(w,dict(req,after_seq=1))
     assert r['page']['records']==[] and r['page']['next_after_seq'] is None
     checks['terminal_empty']=normalize(data,1)
    else:
     for after in [0,1,2,0]:
      req=dict(operation='read_display_records',snapshot=snapshot,after_seq=after,limit=100)
      r,data=result(w,req)
      page=r['page'];assert [p['session_seq'] for p in page['records']]==[after+1]
      assert len(page['records'][0]['entry']['payload']['messages'])==3500
      assert page['next_after_seq']==(None if after==2 else after+1)
      assert len(data)<cap
      witnessed=normalize(data,1)
      if after==0:
       # A retry has the same JSON result but a different top-level RPC id.
       without_rpc_id=re.sub(rb'"id":"h:1:\d+"',b'"id":"h:1:0"',data,count=1)
       retry_wire=normalize(without_rpc_id,1)
       if 'seek-0' in checks:
        assert fixed_first_page==retry_wire
        checks['seek-retry']=witnessed
        continue
       fixed_first_page=retry_wire
      checks[f'seek-{after}']=witnessed
    if k=='jsonl' and kind=='multi':
     v,d=w.execute(dict(operation='read_display_records',snapshot=snapshot,after_seq=4,limit=2))
     assert v['error']=={'code':-32000,'message':'storage record cursor exceeds its snapshot'}; checks['cursor_error']=normalize(d,0)
     v,d=w.execute(dict(operation='read_display_records',snapshot=snapshot,after_seq=0,limit=1025))
     assert v['error']=={'code':-32000,'message':'invalid storage record page limit'}; checks['limit_error']=normalize(d,0)
     v,d=w.execute(dict(operation='read_display_records',snapshot=snapshot,after_seq=0,limit=1,extra=10))
     assert 'extra' in v['error']['message']; checks['invalid_error']=normalize(d,0)
     wrong=dict(snapshot,content_sha256='0'*64)
     v,d=w.execute(dict(operation='read_display_records',snapshot=wrong,after_seq=0,limit=1))
     assert v['error']=={'code':-32000,'message':'snapshot identity/revision/fingerprint mismatch'}
     checks['identity_error']=normalize(d,0)
    assert not w.finish()
   if kind=='single' and k=='jsonl':
    with Worker(exe,k,False) as w:
     v,d=w.execute(dict(operation='read_display_records',snapshot=snapshot,after_seq=0,limit=1))
     assert 'not negotiated' in v['error']['message']
     checks['negotiation_error']=normalize(d,0)
     assert not w.finish()
    for proposed in [first[0],first[0]-1]:
     assert proposed>=open_size
     with Worker(exe,k,True,cap=proposed) as w:
      r,d=result(w,op)
      snap=r['projection']['snapshot'];del r,d
      v,d=w.execute(dict(operation='read_display_records',snapshot=snap,after_seq=0,limit=10))
      if proposed==first[0]:
       assert v is not None and isinstance(v.get('result'),dict)
       # Request id normally differs because earlier controls run later; this
       # deliberately sends the same two calls as the first comparison.
       assert normalize(d,1)==first
       checks['exact_limit']=proposed
       assert not w.finish()
      else:
       assert v is None and not d
       err=w.finish(expected_status=1)
       assert b'worker output frame exceeded its configured byte budget' in err
       checks['one_below_empty_stderr_sha256']=hash_(err)
   out_[kind]=checks
  normalized[k]=out_
 (out/f'{arm}-{mode}.json').write_text(json.dumps(normalized,indent=2)+'\n')
 return normalized

def main():
 a=argparse.ArgumentParser()
 sub=a.add_subparsers(dest='verb',required=True)
 s=sub.add_parser('seed')
 for key in ['worker','existing_50k_frame','out']: s.add_argument(key,type=Path)
 t=sub.add_parser('pair')
 for key in ['baseline','candidate','manifest','out']:t.add_argument(key,type=Path)
 t.add_argument('mode')
 args=a.parse_args()
 if args.verb=='seed':
  print(seed(args.worker.resolve(),args.existing_50k_frame,args.out.resolve()))
  return
 m=json.loads(args.manifest.read_text());args.out.mkdir(parents=True,exist_ok=True)
 with concurrent.futures.ThreadPoolExecutor(2) as p:
  results=list(p.map(lambda a:run(a[0].resolve(),m,args.mode,a[1],args.out,a[1]=='baseline'),
       [(args.baseline,'baseline'),(args.candidate,'candidate')]))
 assert results[0]==results[1]
 print(json.dumps(results[0],indent=2))

if __name__=='__main__':main()
