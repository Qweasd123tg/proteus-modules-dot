#!/usr/bin/env python3
"""Two unchanged Files+SDK processes; only a synthetic loopback API, no user files."""
import argparse, http.server, json, pathlib, queue, subprocess, threading, time, urllib.parse
HERE = pathlib.Path(__file__).resolve().parent
SESSION='/fixture/session'

class Fixture:
    def __init__(self):
        self.files={'src/local.rs':'local fixture', 'src/remote.rs':'remote fixture'}
        self.requests=[]
    def reply(self,method,url,body):
        u=urllib.parse.urlparse(url); q=urllib.parse.parse_qs(u.query); path=q.get('path',[''])[0]
        self.requests.append({'method':method,'path':u.path,'query':q,'body':body})
        if u.path=='/workspace/rename':
            old,new=body['from'],body['to']; self.files={new+p[len(old):] if p==old or p.startswith(old+'/') else p:v for p,v in self.files.items()}; return 200,{'ok':True}
        if u.path=='/sessions/current': return 200,[{'session_dir':SESSION,'workspace_path':'/fixture/project'}]
        if u.path=='/workspace/changes': return 200,{'repository':False,'entries':[]}
        if u.path=='/workspace/list':
            prefix=path+'/' if path else ''; entries={}
            for p in self.files:
                if not p.startswith(prefix): continue
                rest=p[len(prefix):]; first=rest.split('/')[0]
                if first: entries[first]={'name':first,'path':prefix+first,'kind':'directory' if '/' in rest else 'file'}
            return 200,{'entries':list(entries.values())}
        if u.path=='/workspace/file':
            if path in self.files: return 200,{'kind':'text','text':self.files[path]}
            return 404,{'error':'Fixture file not found: '+path}
        return 404,{'error':'Unknown fixture endpoint'}

class API(http.server.BaseHTTPRequestHandler):
    def answer(self,method):
        body=json.loads(self.rfile.read(int(self.headers['Content-Length']))) if method=='POST' else None
        status,result=self.server.fixture.reply(method,self.path,body); raw=json.dumps(result).encode()
        self.send_response(status); self.send_header('Content-Type','application/json'); self.send_header('Content-Length',str(len(raw))); self.end_headers(); self.wfile.write(raw)
    def do_GET(self): self.answer('GET')
    def do_POST(self): self.answer('POST')
    def log_message(self,*_): pass

def context(name): return {'type':'context','context':name,'workspace':'/fixture/project','session_dir':SESSION}
def render(view,ctx,path=None): return {'type':'render','context':ctx,'view':view,'surface':'document' if path is not None else 'panel','argument':path,'session_dir':SESSION}
def action(view,seq,kind,value=None): return {'type':'action','view':view,'sequence':seq,'action':kind,'value':value}
def walk(node):
    if isinstance(node,dict):
        yield node
        for v in node.values(): yield from walk(v)
    elif isinstance(node,list):
        for v in node: yield from walk(v)

class Client:
    def __init__(self,binary,origin,name):
        self.name=name; self.messages=[]; self.output=[]; self.q=queue.Queue()
        self.p=subprocess.Popen([str(binary)],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,bufsize=1)
        self.reader=threading.Thread(target=self.read,daemon=True); self.reader.start()
        self.send({'type':'hello','protocol':4,'server':{'origin':origin,'token':'synthetic-fixture'},'features':['documents.retarget.v1']})
    def read(self):
        for line in self.p.stdout: self.q.put(json.loads(line))
    def send(self,msg):
        self.messages.append(msg); self.p.stdin.write(json.dumps(msg)+'\n'); self.p.stdin.flush()
    def until(self,predicate):
        captured=[]; deadline=time.monotonic()+8
        while time.monotonic()<deadline:
            msg=self.q.get(timeout=max(.01,deadline-time.monotonic())); self.output.append(msg); captured.append(msg)
            if predicate(msg): return captured
        raise AssertionError('No expected output: '+self.name)
    def one(self,msg,view,seq=None):
        self.send(msg)
        return self.until(lambda m:m.get('type')=='view' and m.get('view')==view and (seq is None or m.get('sequence')==seq))
    def close(self):
        self.p.stdin.close(); self.p.wait(timeout=8); self.reader.join(timeout=1)
        while not self.q.empty(): self.output.append(self.q.get_nowait())
        err=self.p.stderr.read(); assert self.p.returncode==0,err; assert not err,err
        return {'input':self.messages,'output':self.output,'stderr':err}

def run(binary,name,shared=False,local=False,moved=False):
    fixture=Fixture(); server=http.server.ThreadingHTTPServer(('127.0.0.1',0),API); server.fixture=fixture
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start(); origin=f'http://127.0.0.1:{server.server_port}'
    a=Client(binary,origin,'rename-runtime'); b=a if shared else Client(binary,origin,'document-runtime')
    try:
        a.send(context('window-b-panel')); a.one(render('panel','window-b-panel'),'panel')
        if local: a.one(render('local-doc','window-b-panel','src/local.rs'),'local-doc')
        b.send(context('window-a-root')); b.one(render('remote-doc','window-a-root','src/remote.rs'),'remote-doc')
        if moved:
            b.send(context('window-b-root')); b.send({'type':'rehost','view':'remote-doc','context':'window-b-root'}); b.send({'type':'close_context','context':'window-a-root'})
        target_context='window-b-root' if moved else 'window-a-root'
        start=len(a.output)
        a.one(action('panel',1,'rename',{'value':'src','text':'lib'}),'panel',1)
        # Deterministic barrier after action renders all retained views. render is read-only.
        a.one(render('panel','window-b-panel'),'panel',1)
        retargets=[m for m in a.output[start:] if m.get('type')=='retarget_document']
        pairs={(m['from'],m['to']) for m in retargets}
        # Host callback is exact-match only; model its routing of received pairs.
        path='src/remote.rs'
        for old,new in pairs:
            if path==old: path=new
        b.one(render('remote-doc',target_context,path),'remote-doc')
        before=b.output[-1]
        # Real unrelated run_settled clears document cache, making bad target observable.
        b.send({'type':'event','context':target_context,'event':'run_settled','session_dir':SESSION,'document':path})
        b.one(render('remote-doc',target_context,path),'remote-doc')
        after=b.output[-1]
        texts=[n.get('text') for n in walk(after['root']) if 'text' in n]
        error=next((t for t in texts if t and 'Fixture file not found' in t),None)
        correct=any(n.get('type')=='code' and n.get('text')=='remote fixture' for n in walk(after['root']))
        result={'scenario':name,'shared_runtime':shared,'local_doc':local,'rehosted':moved,'rename_succeeded':set(fixture.files)=={'lib/local.rs','lib/remote.rs'},'retarget_pairs':sorted(pairs),'remote_argument':path,'remote_error_after_invalidation':error,'remote_content_after_invalidation':correct,'remote_view_before_invalidation':before,'remote_view_after_invalidation':after,'native_gui':False,'host_exact_pair_fanout':'modeled from production retarget_arguments; no GPUI'}
        traces={'rename_runtime':a.close()}
        if b is not a: traces['document_runtime']=b.close()
        (HERE/(name+'.json')).write_text(json.dumps({'result':result,'traces':traces,'api':fixture.requests},ensure_ascii=False,indent=2)+'\n')
        return result
    finally:
        for c in {a,b}:
            if c.p.poll() is None: c.p.terminate();c.p.wait(timeout=3)
        server.shutdown();server.server_close()

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--binary',type=pathlib.Path,default=HERE/'target/debug/files');parser.add_argument('--require-fixed',action='store_true');args=parser.parse_args()
    results=[run(args.binary,'separate-panel-only'),run(args.binary,'separate-partial-ownership',local=True),run(args.binary,'rehost-into-existing-panel-runtime',moved=True),run(args.binary,'shared-runtime-rehost-control',shared=True,moved=True)]
    for r in results: assert r['rename_succeeded'],r
    assert results[-1]['retarget_pairs']==[('src/remote.rs','lib/remote.rs')],results[-1]
    assert results[-1]['remote_content_after_invalidation'] and results[-1]['remote_error_after_invalidation'] is None,results[-1]
    assert results[1]['retarget_pairs']==[('src/local.rs','lib/local.rs')],results[1]
    if not args.require_fixed:
        for r in results[:-1]:
            assert r['remote_argument']=='src/remote.rs' and r['remote_error_after_invalidation'],r
    print(json.dumps([{k:v for k,v in r.items() if not k.startswith('remote_view')} for r in results],ensure_ascii=False,indent=2))
    if args.require_fixed:
        for r in results: assert r['remote_content_after_invalidation'],r['scenario']+': renamed remote document must remain usable'
if __name__=='__main__':main()
