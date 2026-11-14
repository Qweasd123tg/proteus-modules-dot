#!/usr/bin/env python3
"""Unmodified Files+SDK; timer starvation across session contexts after rehost.
Only synthetic data and loopback HTTP. Real five-second production poll.
"""
import argparse, http.server, json, pathlib, queue, threading, time, urllib.parse
from wire_fixture import API, Client, walk
HERE=pathlib.Path(__file__).resolve().parent
IDLE='/fixture/session-idle'; BUSY='/fixture/session-busy'; PATH='watched.rs'
class Fixture:
    def __init__(self): self.requests=[]; self.text='OLD'; self.start=time.monotonic()
    def reply(self,method,url,body):
        u=urllib.parse.urlparse(url); q=urllib.parse.parse_qs(u.query)
        self.requests.append({'at':round(time.monotonic()-self.start,3),'method':method,'path':u.path,'query':q})
        if u.path=='/sessions/current': return 200,[{'session_dir':s,'workspace_path':'/fixture/'+s.rsplit('/',1)[-1]} for s in [IDLE,BUSY]]
        if u.path=='/workspace/changes': return 200,{'repository':False,'entries':[]}
        if u.path=='/workspace/list': return 200,{'entries':[{'name':PATH,'path':PATH,'kind':'file'}]}
        if u.path=='/workspace/file': return 200,{'kind':'text','text':self.text}
        return 404,{'error':'unknown synthetic endpoint'}
    def reads(self): return sum(r['path']=='/workspace/file' and r['query'].get('session_dir')==[IDLE] for r in self.requests)
def context(c,s): return {'type':'context','context':c,'workspace':'/fixture/project','session_dir':s}
def event(c,s): return {'type':'event','context':c,'event':'navigation_changed','session_dir':s,'document':PATH if c=='detached' else None}
def render(v,c,s): return {'type':'render','context':c,'view':v,'surface':'document' if v=='document' else 'panel','argument':PATH if v=='document' else None,'session_dir':s}
def collect(c,seconds):
    end=time.monotonic()+seconds
    while time.monotonic()<end:
        try:c.output.append(c.q.get(timeout=min(.05,max(.001,end-time.monotonic()))))
        except queue.Empty:pass
def content(m):return [n['text'] for n in walk(m.get('root')) if n.get('type')=='code']
def run(binary,busy,same_session):
    f=Fixture();server=http.server.ThreadingHTTPServer(('127.0.0.1',0),API);server.fixture=f
    threading.Thread(target=server.serve_forever,daemon=True).start(); c=Client(binary,f'http://127.0.0.1:{server.server_port}','timer')
    try:
        c.send(context('source',IDLE));c.one(render('panel','source',IDLE),'panel')
        c.send(context('source:idle',IDLE));c.one(render('document','source:idle',IDLE),'document')
        c.send(context('detached',IDLE));c.send({'type':'rehost','view':'document','context':'detached'});c.send({'type':'close_context','context':'source:idle'})
        c.one(event('detached',IDLE),'document')
        session=IDLE if same_session else BUSY
        if not same_session:
            c.send(context('source',session));c.one({'type':'event','context':'source','event':'session_opened','session_dir':session,'document':None},'panel')
        collect(c,.1)
        assert f.reads()==1,(f.requests,c.output)
        start_index=len(c.output); f.text='NEW'; began=time.monotonic(); sent=0
        while time.monotonic()-began<11.0:
            if busy:
                c.one(event('source',session),'panel');sent+=1
            collect(c,min(.5,11.0-(time.monotonic()-began)))
        elapsed=time.monotonic()-began
        during=c.output[start_index:];reads_during=f.reads()
        # Recovery: cease source events and allow a genuine idle poll.
        if busy and not same_session:
            recovery_started=time.monotonic()
            c.until(lambda m:m.get('type')=='view' and m.get('view')=='document' and 'NEW' in content(m))
            recovery_elapsed=round(time.monotonic()-recovery_started,3)
        else:recovery_elapsed=None
        result={'traffic':busy,'same_session':same_session,'duration_seconds':round(elapsed,3),'source_navigation_events':sent,'file_reads_before_change':1,'file_reads_during_window':reads_during,'document_views_during_window':[{'session':m.get('session_dir'),'text':content(m)} for m in during if m.get('view')=='document'],'refreshed_during_window':any('NEW' in content(m) for m in during if m.get('view')=='document'),'idle_recovery_wait_seconds':recovery_elapsed,'file_reads_after_recovery':f.reads(),'native_gui':False}
        trace=c.close();name='same-session-control' if same_session else 'busy-multisession-repro' if busy else 'idle-multisession-control'
        (HERE/(name+'.json')).write_text(json.dumps({'result':result,'wire':trace,'api':f.requests},ensure_ascii=False,indent=2)+'\n')
        return result
    finally:
        if c.p.poll() is None:c.p.terminate();c.p.wait(timeout=3)
        server.shutdown();server.server_close()
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--binary',type=pathlib.Path,default=HERE/'target/debug/files');p.add_argument('--require-fixed',action='store_true');p.add_argument('--case',choices=['all','busy'],default='all');a=p.parse_args()
    bug=run(a.binary,True,False)
    if a.case=='busy':
        print(json.dumps(bug,indent=2),flush=True)
        if a.require_fixed:assert bug['refreshed_during_window'],bug
        else:assert not bug['refreshed_during_window'] and bug['file_reads_during_window']==1 and bug['file_reads_after_recovery']==2,bug
        raise SystemExit(0)
    idle=run(a.binary,False,False);same=run(a.binary,True,True)
    print(json.dumps([bug,idle,same],ensure_ascii=False,indent=2),flush=True)
    assert idle['refreshed_during_window'] and idle['file_reads_during_window']>=3,idle
    assert same['refreshed_during_window'] and same['file_reads_during_window']>=3,same
    if a.require_fixed:assert bug['refreshed_during_window'],bug
    else:assert not bug['refreshed_during_window'] and bug['file_reads_during_window']==1 and bug['file_reads_after_recovery']==2,bug
