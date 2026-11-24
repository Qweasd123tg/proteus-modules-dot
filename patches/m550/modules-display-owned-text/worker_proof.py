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

def run(exe,manifest,mode,arm,out,save=False):
 header={}
 for backend in ['jsonl','sqlite']:
  which={n:s for k,n,s in manifest if k.lower()==backend}
  req={'operation':'open_display_snapshot','session':which[4]}
  with Worker(exe,backend,False) as w:
   v,line=w.execute(req)
   assert 'not negotiated' in v['error']['message']
   deny=normalize(line,0)
   assert not w.finish()
  saved={}
  with Worker(exe,backend,True) as w:
   hello=normalize(w.hello,0)
   # Actual M372 service display state; no fabricated output in worker.
   v,line=w.execute(req)
   projection=v['result']['projection']
   assert v['result']['result']=='display_snapshot'
   messages=projection['state']['conversation']['messages']
   assert len(messages)==50_000
   assert messages[0]['parts'][0]['payload']['Text']['text'].startswith('Fixture row 1\n')
   assert messages[-1]['parts'][0]['payload']['Text']['text'].startswith('Fixture row 50000\n')
   snapshot=projection['snapshot']
   assert snapshot['revision']=={'session_seq':50_000,'history_revision':50_000}
   size=len(line)
   saved['display']=normalize(line,1)
   if save and backend=='jsonl':
    (out/f'{mode}-real-frame.json').write_bytes(line)
   del v,line,projection,messages
   v,line=w.execute({'operation':'read_display_records','snapshot':snapshot,'after_seq':0,'limit':1})
   assert v['result']['page']['records'][0]['session_seq']==1
   saved['delegated_read']=normalize(line,1)
   v,line=w.execute({'operation':'open_display_snapshot','session':which[5]})
   assert v['result']=={'result':'display_snapshot','projection':None}
   saved['over_cap']=normalize(line,0)
   v,line=w.execute(dict(req,unexpected_member=0))
   assert v['error']['code']==-32000 and 'unexpected_member' in v['error']['message']
   saved['malformed']=normalize(line,0)
   v,line=w.execute(req,method='not_an_allowed_method')
   assert v['error']['code']==-32000 and 'not allowed for slot' in v['error']['message']
   saved['method_authority']=normalize(line,0)
   assert not w.finish()
  if backend=='jsonl':
   # Same full 50k frame, once at exact accepted budget and once byte below.
   with Worker(exe,backend,True,cap=size) as w:
    v,line=w.execute(req)
    assert v['result']['projection'] and normalize(line,1)==saved['display']
    del v,line
    assert not w.finish()
   with Worker(exe,backend,True,cap=size-1) as w:
    v,line=w.execute(req)
    assert v is None and line==b''
    stderr=w.finish(expected_status=1)
    assert b'worker output frame exceeded its configured byte budget' in stderr
    saved['exact_cap']=size
    saved['one_below_cap_stderr_sha256']=hash_(stderr)
  header[backend]={'hello':hello,'not_negotiated':deny,**saved}
 (out/f'{arm}-{mode}-worker.json').write_text(json.dumps(header,indent=2)+'\n')
 return header

def main():
 p=argparse.ArgumentParser(description=__doc__)
 for k in ['baseline_default','candidate_default','baseline_preserve','candidate_preserve','manifest','out']:
  p.add_argument(k,type=Path)
 a=p.parse_args();a.out.mkdir(parents=True,exist_ok=True)
 args=[(exe,a.manifest,m,b,a.out,b=='baseline') for m,bl,ca in [
    ('default',a.baseline_default,a.candidate_default),('preserve_order',a.baseline_preserve,a.candidate_preserve)]
   for b,exe in [('baseline',bl),('candidate',ca)]]
 a.manifest=json.loads(a.manifest.read_text())
 args=[(e,a.manifest,m,b,o,s) for e,_,m,b,o,s in args]
 with concurrent.futures.ThreadPoolExecutor(2) as pool:
  out=list(pool.map(lambda row:run(*row),args))
 assert out[0]==out[1] and out[2]==out[3]
 print(json.dumps({'default':out[0],'preserve_order':out[2]},indent=2))
if __name__=='__main__':main()
