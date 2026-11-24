#!/usr/bin/env python3
"""Actual old-SDK stdio ReadCache compatibility, source, and output cap A/B."""
from pathlib import Path
import argparse, hashlib, json, os, subprocess, tempfile, uuid

MAX = 128*1024*1024
hash_ = lambda x: hashlib.sha256(x).hexdigest()
def wire(raw):return [len(raw),hash_(raw)]
def compact(x,ordered=False):return json.dumps(x,ensure_ascii=False,separators=(',',':'),sort_keys=ordered).encode()
def etag(value):return hash_(compact(value,ordered=True))
def uid():return str(uuid.uuid4())

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
def make_session(w,home):
 cfg=home/'config';work=home/'workspace'
 cfg.mkdir(parents=True);work.mkdir()
 r,_=result(w,dict(operation='create',config_root=str(cfg),workspace_path=str(work),session_id=uid(),parent_session_id=None))
 session=r['descriptor']['session']
 r,_=result(w,dict(operation='acquire_writer',session=session))
 return session,r['lease'],r['revision']

def append(w,lease,rev,tag):
 n=rev['history_revision']
 msg={"id":uid(),"role":"User","phase":None,"parts":[{"part_id":uid(),"provenance":"user",
        "scope":"conversation","payload":{"Text":{"text":tag}}}],"name":None,"tool_call_id":None,"metadata":None}
 r,_=result(w,dict(operation='commit',commit=dict(lease=lease,operation_id=uid(),
       expected=rev,timestamp_ms=1038+n,attribution=dict(execution_id=None,thread_id=uid(),turn_id=None),
       entry=dict(kind='history_mutated',payload=dict(previous_revision=n,new_revision=n+1,
         mutation='append',messages=[msg],compaction=None,tool_results=[])))))
 return r['ack']['revision']

def opened(w,session):
 r,_=result(w,dict(operation='open_snapshot',session=session))
 return r['snapshot']

def cache_write(w,session,key,source,value):
 r,d=result(w,dict(operation='write_cache',session=session,key=key,source=source,value=value))
 return r['etag'],d

def cache_read(w,session,key,source=None):
 q=dict(operation='read_cache',session=session,key=key,source=source)
 r,d=result(w,q)
 assert r['result']=='metadata'
 return r['document'],d

def shape(exe,backend,feature,home,pack,capture):
 rows=pack['deflate_v1'];assert 2<=len(rows)<=8 and all(isinstance(x,str) for x in rows)
 assert len(compact(pack))<=256*1024
 key='display-data-'+etag(pack)
 checks={}
 with Worker(exe,backend,feature) as w:
  session,lease,rev=make_session(w,home)
  rev=append(w,lease,rev,'first fixture marker')
  source=opened(w,session)
  assert source['revision']==rev
  known,raw=cache_write(w,session,key,source,pack)
  assert known==etag(pack)
  checks['write']=wire(raw)
  doc,d=cache_read(w,session,key,source)
  assert doc==dict(etag=known,value=pack)
  checks['exact_source']=wire(d)
  if capture is not None:capture.write_bytes(d)
  another=opened(w,session)
  assert another['snapshot_id']!=source['snapshot_id'] and another['content_sha256']==source['content_sha256']
  doc,d=cache_read(w,session,key,another)
  assert doc==dict(etag=known,value=pack)
  checks['same_prefix_distinct_handle']=wire(d)
  doc,d=cache_read(w,session,key,dict(source,content_sha256='0'*64))
  assert doc is None
  checks['wrong_source']=wire(d)
  # Appending does not rewrite existing historical content pages.
  newest_rev=append(w,lease,rev,'same-locator durable later marker')
  newer=opened(w,session)
  assert newer['revision']==newest_rev
  doc,d=cache_read(w,session,key,newer)
  assert doc is None
  checks['stale_source']=wire(d)
  written,d=cache_write(w,session,key,source,dict(stale=True))
  assert written is None
  checks['stale_write']=wire(d)
  doc,d=cache_read(w,session,key)
  assert doc==dict(etag=known,value=pack)
  checks['content_addressed_unfiltered']=wire(d)
  absent,d=cache_read(w,session,'missing-disposable-page')
  assert absent is None
  checks['miss']=wire(d)
  path=json.loads(session['key'])['path']
  cache=Path(path)/('.storage-cache-'+hash_(key.encode())+'.json')
  original=cache.read_bytes()
  cache.write_bytes(original[:-1])
  doc,d=cache_read(w,session,key,source)
  assert doc is None
  checks['corrupt_disposable_fallback']=wire(d)
  cache.write_bytes(original)
  doc,d=cache_read(w,session,key,source)
  assert doc==dict(etag=known,value=pack)
  checks['restored']=wire(d)
  # Display negotiation and ReadMetadata aren't affected by the new branch.
  r,d=result(w,dict(operation='read_metadata',session=session,key='missing-metadata'))
  assert r==dict(result='metadata',document=None)
  checks['other_metadata_route']=wire(d)
  extras=[None,True,{"z":[{"β":"a\u001f\n","x":1.25},0],"a":False},["é",{"z":-0.0,"a":[]}, " "]]
  for i,val in enumerate(extras):
   k='alternate-'+str(i)
   saved,_=cache_write(w,session,k,newer,val)
   doc,d=cache_read(w,session,k,newer)
   assert doc==dict(etag=saved,value=val)
   assert saved==etag(val)
   checks[k]=wire(d)
  q=dict(operation='read_cache',session=session,key=key,source=None)
  v,d=w.execute(dict(q,key='../wrong'))
  assert v['error']['message']=='invalid storage metadata key'
  checks['invalid_key']=wire(d)
  v,d=w.execute(dict(q,extra=1))
  assert 'unknown field `extra`' in v['error']['message']
  checks['unknown_field']=wire(d)
  result(w,dict(operation='release_writer',lease=lease))
  assert not w.finish()
 # SDK exact output budget, a fresh process with identical first RPC ID.
 with Worker(exe,backend,feature) as w:
  d,first=cache_read(w,session,key)
  assert d==dict(etag=known,value=pack)
  assert not w.finish()
 for cap in [len(first),len(first)-1]:
  with Worker(exe,backend,feature,cap) as w:
   if cap==len(first):
    d,raw=cache_read(w,session,key)
    assert raw==first and d==dict(etag=known,value=pack)
    checks['sdk_cap_exact']=wire(raw)
    assert not w.finish()
   else:
    v,raw=w.execute(dict(operation='read_cache',session=session,key=key,source=None))
    assert v is None and raw==b''
    err=w.finish(expected_status=1)
    assert b'worker output frame exceeded its configured byte budget' in err
    checks['sdk_cap_one_below']=[cap,hash_(err)]
 return checks

def run(exe,arm,mode,pack,out,save=False):
 all_checks={}
 for backend in ('jsonl','sqlite'):
  checks={}
  for feature in (False,True):
   with tempfile.TemporaryDirectory(prefix='proteus-cache-proof-') as td:
    checks[str(feature).lower()]=shape(exe,backend,feature,Path(td),pack,
      out/f'{mode}-pack-worker-frame.json' if save and backend=='jsonl' and not feature else None)
  all_checks[backend]=checks
 (out/f'{arm}-{mode}.json').write_text(json.dumps(all_checks,indent=2)+'\n')
 return all_checks

def main():
 a=argparse.ArgumentParser(description=__doc__)
 for k in ['baseline','candidate','pack','out']:a.add_argument(k,type=Path)
 a.add_argument('mode',choices=('default','preserve_order'))
 cfg=a.parse_args()
 cfg.out.mkdir(parents=True,exist_ok=True)
 pack=json.loads(cfg.pack.read_text())
 old=run(cfg.baseline.resolve(),'baseline',cfg.mode,pack,cfg.out,True)
 new=run(cfg.candidate.resolve(),'candidate',cfg.mode,pack,cfg.out)
 assert old==new
 print(json.dumps(new,indent=2))

if __name__=='__main__':main()
