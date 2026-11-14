#!/usr/bin/env python3
"""Unmodified Files+SDK, synthetic loopback reads, never touches a real workspace."""
import argparse, http.server, json, pathlib, queue, subprocess, threading, time, urllib.parse
HERE=pathlib.Path(__file__).resolve().parent
A='/fixture/session-a'; B='/fixture/session-b'; CTX='window'; VIEW='panel'

def walk(v):
    if isinstance(v,dict):
        yield v
        for x in v.values(): yield from walk(x)
    elif isinstance(v,list):
        for x in v: yield from walk(x)

class Fixture:
    def __init__(self):
        self.requests=[]; self.block=False; self.entered=threading.Event(); self.release=threading.Event()
    def reply(self,url):
        u=urllib.parse.urlparse(url); q=urllib.parse.parse_qs(u.query); session=q.get('session_dir',[''])[0]
        self.requests.append({'method':'GET','path':u.path,'query':q})
        if u.path=='/sessions/current':
            if session==B and self.block:
                self.entered.set()
                assert self.release.wait(8), 'fixture release timed out'
                self.block=False
            return [{'session_dir':A,'workspace_path':'/fixture/project-a'},{'session_dir':B,'workspace_path':'/fixture/project-b'}]
        if u.path=='/workspace/changes': return {'repository':False,'entries':[]}
        if u.path=='/workspace/list':
            path='only-a.txt' if session==A else 'only-b.txt'
            return {'entries':[{'name':path,'path':path,'kind':'file'},{'name':'shared.txt','path':'shared.txt','kind':'file'}]}
        if u.path=='/workspace/file':
            path=q['path'][0]
            if path != 'shared.txt' and path != ('only-a.txt' if session==A else 'only-b.txt'): return {'error':'fixture file not found in '+session+': '+path}
            return {'kind':'text','text':('A' if session==A else 'B')+' content addressed as '+path}
        raise AssertionError(u.path)
class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        data=self.server.fixture.reply(self.path); raw=json.dumps(data).encode()
        self.send_response(404 if isinstance(data,dict) and 'error' in data else 200);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
    def do_POST(self): raise AssertionError('This reproduction must never send POST')
    def log_message(self,*a): pass
class Wire:
    def __init__(self,binary,origin):
        self.sent=[];self.received=[];self.q=queue.Queue()
        self.proc=subprocess.Popen([str(binary)],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,bufsize=1)
        threading.Thread(target=lambda:[self.q.put(json.loads(line)) for line in self.proc.stdout],daemon=True).start()
        self.send({'type':'hello','protocol':4,'features':[],'server':{'origin':origin,'token':'synthetic'},'workspace':'/fixture/project-a'})
    def send(self,msg):
        self.sent.append(msg);self.proc.stdin.write(json.dumps(msg)+'\n');self.proc.stdin.flush()
    def until(self,predicate):
        deadline=time.monotonic()+8
        while True:
            msg=self.q.get(timeout=max(.01,deadline-time.monotonic()));self.received.append(msg)
            if predicate(msg): return msg
    def context(self,session):
        self.send({'type':'context','context':CTX,'session_dir':session,'workspace':'/fixture/project-'+('a' if session==A else 'b')})
    def event(self,session):
        self.send({'type':'event','context':CTX,'event':'session_opened','session_dir':session})
    def render(self,session):
        self.send({'type':'render','context':CTX,'view':VIEW,'surface':'panel','session_dir':session})
    def action(self,path):
        self.send({'type':'action','view':VIEW,'sequence':1,'action':'files','value':{'id':path,'event':'open'}})
    def close(self):
        self.proc.stdin.close();self.proc.wait(timeout=8)
        err=self.proc.stderr.read(); assert self.proc.returncode==0,(self.proc.returncode,err);assert not err,err
        return {'input':self.sent,'output':self.received,'stderr':err}

def run(binary,mode):
    fixture=Fixture(); server=http.server.ThreadingHTTPServer(('127.0.0.1',0),Handler); server.fixture=fixture
    threading.Thread(target=server.serve_forever,daemon=True).start()
    wire=Wire(binary,f'http://127.0.0.1:{server.server_port}')
    try:
        wire.context(A);wire.render(A)
        initial=wire.until(lambda m:m.get('type')=='view' and m.get('view')==VIEW)
        assert any(n.get('id')=='only-a.txt' for n in walk(initial['root']))
        assert not any(n.get('id')=='only-b.txt' for n in walk(initial['root']))
        if mode=='before-switch-control':
            wire.action('only-a.txt'); expected=A; clicked='only-a.txt'; no_new_tree=False
        else:
            fixture.block=mode.startswith('stale-');wire.context(B);wire.event(B);wire.render(B)
            if mode.startswith('stale-'):
                assert fixture.entered.wait(4),'B API never began'
                no_new_tree=wire.q.empty();assert no_new_tree
                clicked='shared.txt' if mode=='stale-collision' else 'only-a.txt';wire.action(clicked);fixture.release.set()
            else:
                new=wire.until(lambda m:m.get('type')=='view' and m.get('session_dir')==B)
                assert any(n.get('id')=='only-b.txt' for n in walk(new['root']))
                wire.action('only-b.txt');clicked='only-b.txt';no_new_tree=False
            expected=B
        opened=wire.until(lambda m:m.get('type')=='open_document')
        assert opened['argument']==clicked
        assert opened['context']==CTX and opened['view']==VIEW
        after=wire.until(lambda m:m.get('type')=='view' and m.get('view')==VIEW and m.get('sequence')==1)
        assert after['session_dir']==expected
        # Desktop resolves open_document through its current scope, exactly as action response.
        # Feed that document back into the same context to expose the addressed session on real GET.
        wire.send({'type':'render','context':CTX,'view':'opened-doc','surface':'document','argument':opened['argument'],'session_dir':expected})
        doc=wire.until(lambda m:m.get('type')=='view' and m.get('view')=='opened-doc')
        reads=[r for r in fixture.requests if r['path']=='/workspace/file']
        assert reads[-1]['query']['session_dir']==[expected]
        result={'scenario':mode,'clicked_path':clicked,'no_B_tree_before_click':no_new_tree,'opened_argument':opened['argument'],'addressed_session':reads[-1]['query']['session_dir'][0],'initial_tree_session':A,'native_gui_run':False,'http_reads_only':all(r['method']=='GET' for r in fixture.requests),'document_text':[n['text'] for n in walk(doc['root']) if 'text' in n]}
        trace=wire.close()
        (HERE/(mode+'.json')).write_text(json.dumps({'result':result,'trace':trace,'api':fixture.requests},ensure_ascii=False,indent=2)+'\n')
        return result
    finally:
        fixture.release.set()
        if wire.proc.poll() is None:wire.proc.terminate();wire.proc.wait(timeout=3)
        server.shutdown();server.server_close()

def main():
    p=argparse.ArgumentParser();p.add_argument('--binary',type=pathlib.Path,default=HERE/'target/debug/files');p.add_argument('--require-safe',action='store_true');args=p.parse_args()
    results=[run(args.binary,m) for m in ['before-switch-control','stale-click','stale-collision','new-tree-control']]
    print(json.dumps(results,indent=2))
    if args.require_safe:
        assert results[1]['addressed_session']==A, 'old A tree must not open a file through session B'
    else:
        assert results[1]['no_B_tree_before_click'] and results[1]['addressed_session']==B
        assert any('B content addressed as shared.txt' == text for text in results[2]['document_text'])
if __name__=='__main__':main()
