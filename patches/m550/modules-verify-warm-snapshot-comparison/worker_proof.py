#!/usr/bin/env python3
"""Actual old-SDK stdio warm CompareSnapshots and following suffix pages."""
from pathlib import Path
import argparse, hashlib, json, os, re, subprocess, tempfile

MAX = 128*1024*1024
hash_ = lambda x: hashlib.sha256(x).hexdigest()
def wire(raw):return [len(raw),hash_(raw)]
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
UUID = re.compile(rb'"snapshot_id":"[0-9a-fA-F-]{36}"')
def norm(raw):
 b,count=UUID.subn(b'"snapshot_id":"00000000-0000-0000-0000-000000000000"',raw)
 assert count==1
 return wire(b)

def open_snapshot(w,source):
 r,d=result(w,dict(operation='open_snapshot',session=source))
 return r['snapshot'],d

def compare(w,head,old,want):
 req=dict(operation='compare_snapshots',snapshot=head,prefix=old)
 v,d=result(w,req)
 assert v=={'result':'snapshot_prefix','matches':want}
 return wire(d)

def checked(exe,backend,feature,old):
 session=old['session']
 with Worker(exe,backend,feature) as w:
  first,_=open_snapshot(w,session)
  head,d=open_snapshot(w,session)
  assert head['snapshot_id']!=first['snapshot_id']
  assert head['revision']=={'history_revision':3,'session_seq':519}
  assert head['content_sha256']==first['content_sha256']
  assert old['revision']=={'history_revision':1,'session_seq':513}
  out={'warm_open':norm(d)}
  # The prefix's handle belongs to an earlier process and has been released.
  # The new head must still compare its authenticated older boundary.
  out['compare_released_older']=compare(w,head,old,True)
  out['retry_same']=compare(w,head,old,True)
  wrong_rev=dict(old,revision=dict(old['revision'],history_revision=0))
  out['wrong_revision']=compare(w,head,wrong_rev,False)
  out['wrong_hash']=compare(w,head,dict(old,content_sha256='0'*64),False)
  out['same_head']=compare(w,head,first,True)
  out['before_suffix']=compare(w,head,old,True)
  r,d=result(w,dict(operation='read_records',snapshot=head,after_seq=old['revision']['session_seq'],limit=16))
  assert r['page']['snapshot']==head
  assert r['page']['next_after_seq'] is None
  rows=r['page']['records'];assert [r['session_seq'] for r in rows]==list(range(514,520))
  assert [r['entry']['kind'] for r in rows]==[
   'history_mutated','turn_opened','model_request_recorded','model_response_recorded','turn_settled','history_mutated']
  out['suffix']=norm(d)
  out['reset_page_cursor']=compare(w,head,old,True)
  r,d=result(w,dict(operation='read_records',snapshot=head,after_seq=old['revision']['session_seq'],limit=16))
  assert rows==r['page']['records'] and r['page']['snapshot']==head
  out['same_suffix_again']=norm(d)
  r,d=result(w,dict(operation='read_usage',snapshot=head))
  assert len(r['usage']['requests'])==129
  out['independent_usage']=wire(d)
  r,d=result(w,dict(operation='read_conversation',snapshot=head,point=dict(kind='current')))
  assert r['conversation']['revision']==head['revision'] and len(r['conversation']['messages'])==3
  assert r['conversation']['model_context']
  out['independent_conversation']=wire(d)
  result(w,dict(operation='release_snapshot',snapshot=head))
  v,d=w.execute(dict(operation='compare_snapshots',snapshot=head,prefix=old))
  assert v['error']['message']=='snapshot handle expired or unknown'
  out['released_head']=wire(d)
  assert not w.finish()
 return out

def run(exe,mode,arm,fixtures,out):
 totals={k.lower():{str(feature).lower():checked(exe,k.lower(),feature,old) for feature in [False,True]} for k,old in fixtures}
 (out/f'{arm}-{mode}.json').write_text(json.dumps(totals,indent=2)+'\n')
 return totals

def main():
 a=argparse.ArgumentParser(description=__doc__)
 for arg in ['baseline','candidate','fixture','out']:a.add_argument(arg,type=Path)
 a.add_argument('mode',choices=('default','preserve_order'))
 c=a.parse_args()
 c.out.mkdir(parents=True,exist_ok=True)
 p=json.loads(c.fixture.read_text())
 old=run(c.baseline.resolve(),c.mode,'baseline',p,c.out)
 new=run(c.candidate.resolve(),c.mode,'candidate',p,c.out)
 assert old==new
 print(json.dumps(new,indent=2),flush=True)

if __name__=='__main__': main()
