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

