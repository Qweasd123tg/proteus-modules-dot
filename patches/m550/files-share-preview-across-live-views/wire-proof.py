"""Real Files process: shared preview, both modes, close and refresh."""
from hashlib import sha256
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import subprocess
import sys
from threading import Thread
from urllib.parse import parse_qs,urlsplit

binary,out=(Path(p).resolve() for p in sys.argv[1:3])
meter=Path(sys.argv[3]) if len(sys.argv)==4 else None
session="/synthetic/file-preview"
context="syn-files"
path='src/перо "coat".rs'
binary_path="binary.bin"
failure_path="unavailable.rs"
failure="Синтетический отказ предпросмотра 🧪"
calls=[]
file_prefix="Текст \t\r\n ζ 🧪 '\\\""
patch_prefix="+diff \t\r\n Δ 🧪 '\\\""
extent=480_000

def payload(mode,n):
    prefix=file_prefix if mode=="file" else patch_prefix
    first=prefix+str(n)+": "
    text=first+"x"*(extent-len(first.encode()))
    assert len(text.encode())==extent<512*1024
    return text

class Server(BaseHTTPRequestHandler):
    protocol_version="HTTP/1.1"
    def do_GET(self):
        url=urlsplit(self.path)
        assert self.headers["Authorization"]=="Bearer synthetic-files"
        q=parse_qs(url.query); assert q.pop("session_dir")==[session]
        [p]=q.pop("path"); assert not q and p in [path,binary_path,failure_path]
        assert url.path in ("/workspace/file","/workspace/diff")
        mode=url.path.rsplit("/",1)[1]
        calls.append((mode,p))
        if p==path:
            n=calls.count((mode,p))
            data={"kind":"text","path":p,"text" if mode=="file" else "patch":payload(mode,n)}
            status=200
        elif p==binary_path:
            assert mode=="file"
            data={"kind":"binary","text":True}
            status=200
        else:
            assert mode=="file"
            data={"error":failure}
            status=503
        body=json.dumps(data,ensure_ascii=False,separators=(",",":")).encode()
        self.send_response(status);self.send_header("Content-Type","application/json")
        self.send_header("Content-Length",str(len(body)));self.send_header("Connection","close")
        self.end_headers();self.wfile.write(body)
    def log_message(self,*_):
        pass

def addressed(kind,view,**extra):
    return {"type":kind,"view":view,"context":context,"session_dir":session,**extra}
def render(view,argument=path):
    return addressed("render",view,surface="document",argument=argument)
def mode(view,sequence,name):
    return addressed("action",view,action="document-mode",sequence=sequence,value=[path,name])

with ThreadingHTTPServer(("127.0.0.1",0),Server) as server:
    thread=Thread(target=server.serve_forever,daemon=True);thread.start()
    try:
        hello={"type":"hello","protocol":4,"features":[],"server":{
            "origin":f"http://127.0.0.1:{server.server_address[1]}","token":"synthetic-files"}}
        requests=[hello,render("a"),render("b"),render("c"),
                  mode("a",41,"diff"),mode("b",42,"file"),addressed("close","a"),
                  render("b",binary_path),addressed("close","c"),render("d"),render("e",failure_path),
                  addressed("close","b"),addressed("close","e"),
                  addressed("event","d",event="run_settled",document=path)]
        run=subprocess.run([binary],input=b"".join((json.dumps(v,ensure_ascii=False)+"\n").encode() for v in requests),
                           stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=60,check=True)
    finally:
        server.shutdown();thread.join()
if meter:
    log=run.stderr.decode().splitlines()
    assert len(log)==13 and all(s.startswith("alloc ") for s in log),log[:15]
    meter.write_text(run.stderr.decode())
else:
    assert not run.stderr,run.stderr[:1000]
rows=list(map(json.loads,run.stdout.splitlines()))
targets=[
    ("a",0,"file",1),("b",0,"file",1),("c",0,"file",1),
    ("a",41,"diff",1),("b",0,"diff",1),("c",0,"diff",1),
    ("b",42,"file",1),("a",41,"file",1),("c",0,"file",1),
    ("b",42,"binary",0),("d",0,"file",2),("e",0,"error",0),("d",0,"file",3),
]
assert [(r["view"],r["sequence"]) for r in rows]==[v[:2] for v in targets]
for frame,(view,sq,mode,n) in zip(rows,targets):
    assert list(frame)==["type","session_dir","view","root","sequence","source_revision","keys"]
    assert frame["type"]=="view" and frame["source_revision"] is None and frame["keys"]=={}
    assert frame["session_dir"]==session and frame["root"]["type"]=="fill"
    assert len(frame["root"]["children"])==2
    header,body=frame["root"]["children"]
    assert header["direction"]=="row"
    if n:
        assert header["children"][0]["text"]==path
        assert body=={"type":"code","id":"content","text":payload(mode,n),"language":
                      ("rust" if mode=="file" else "diff")},(view,mode,n)
    else:
        assert body["text"]==("Двоичный файл" if mode=="binary" else failure),(view,body)
        assert body["tone"]==("muted" if mode=="binary" else "danger")
assert calls==[("file",path),("diff",path),("file",binary_path),("file",path),
               ("file",failure_path),("file",path)],calls
out.write_bytes(run.stdout)
print(len(rows),len(run.stdout),sha256(run.stdout).hexdigest())
