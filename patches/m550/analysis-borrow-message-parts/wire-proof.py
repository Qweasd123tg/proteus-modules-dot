"""Real Analysis process, synthetic read-only loopback reports and exact message layouts."""
from hashlib import sha256
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import subprocess
import sys
from threading import Thread
from urllib.parse import parse_qs, urlsplit

binary,out=(Path(p).resolve() for p in sys.argv[1:3])
meter=Path(sys.argv[3]) if len(sys.argv)==4 else None
session="/synthetic/multipart"
view="analysis"
context="fixture"
failure="Синтетический запрет чтения отчёта 🧪"
calls=[]

def part(kind,value):
    return {"payload":{kind:value}}
def message(parts,role="User"):
    return {"role":role,"parts":parts}
def fields(extent):
    return (
        "A"+("Я é : \\\" 🧪"*extent)+"tail A",
        "\r\nfile "+("κ typed \u2028 café \t"*extent)+"\r\n",
        "primary "+("tool é \u0000 q 🧪"*extent)+"tool-end",
        "B"+("ε repeat ' quote "*extent)+"tail B",
    )

def request(extent):
    a,f,t,b=fields(extent)
    return [
        message([part("Text",{"text":"\u2003"+a+"\r\n"}),
                 part("ReasoningSummary",{"summary":"not shown"}),
                 part("FileRef",{"path":"src/é.py","content":f}),
                 part("ToolResult",{"result":{"call_id":"pick","output":t+" \t\r\n","error":"not chosen"}}),
                 part("Text",{"text":"\t"+b+"\u2003"})]),
        message([part("Reasoning",{"text":"not shown"}),part("Text",{"text":"\u2003\t"}),
                 part("FileRef",{"path":None,"content":False}),
                 part("ToolResult",{"result":{"call_id":"second","output":0,
                    "error":{"z":[1,False],"a":"🧪"}}}),
                 part("ToolResult",{"result":{"call_id":"empty","output":" \r\n",
                    "error":"not chosen"}}),
                 part("FileRef",{"path":[1,2],"content":{"n":False}}),
                 part("Image",{}),part("ToolCall",{"call":{"name":"utility","args":{"k":2,"a":False}}}),
                 part("Future",{"unknown":[None,1]})]),
        message([part("Text",{"text":"\n\t"}),part("ReasoningSummary",{"summary":"invisible"})]),
    ]

response=[
    message([part("Text",{"text":"  одно сообщение 🧪  "})],"Assistant"),
    message([part("Reasoning",{}),part("FileRef",{"path":"src"}),part("Text",{"text":"\r\n"})],"Assistant"),
]
def report(revision, extent):
    return {"session_id":"messages","revision":revision,"turns":[
        {"turn_id":"turn","status":"success","number":revision,"prompt_preview":"Fixture"}],
        "selected":{"turn_id":"turn","task":{"text":"Synthetic read only"},"steps":[
            {"sequence":4,"started_at_ms":2000,"finished_at_ms":2660,
             "data":{"kind":"model","exchange_id":"fixture",
                     "request":{"model":{"model":"fixture"},"messages":request(extent)},
                     "response":{"finish_reason":"Stop","messages":response}}}],
            "output":{"text":f"Summary {revision}"},"module_epoch":0,"config_snapshot":{}}}

class Server(BaseHTTPRequestHandler):
    protocol_version="HTTP/1.1"
    def do_GET(self):
        url=urlsplit(self.path)
        assert parse_qs(url.query)=={"session_dir":[session]}
        assert self.headers["Authorization"]=="Bearer synthetic-multipart"
        calls.append(url.path)
        if url.path=="/analysis":
            n=calls.count("/analysis")
            status,value = {
                1:(200,lambda:report(7,26_000)),
                2:(503,lambda:{"error":failure}),
                3:(200,lambda:report(8,26_000)),
                4:(200,lambda:report(9,1)),
            }[n]
            value=value()
        else:
            assert url.path=="/sessions"
            status,value=200,[{"session_dir":session,"session_id":"fixture","message_count":2}]
        body=json.dumps(value,ensure_ascii=False,separators=(",",":")).encode()
        if url.path=="/analysis" and status==200 and n in (1,3):
            assert 1_000_000<len(body)<8*1024*1024
        self.send_response(status);self.send_header("Content-Type","application/json")
        self.send_header("Content-Length",str(len(body)));self.send_header("Connection","close")
        self.end_headers();self.wfile.write(body)
    def log_message(self,*_):
        pass

def addressed(kind,**extra):
    return {"type":kind,"view":view,"context":context,"session_dir":session,**extra}
def action(seq,name,value=None):
    return addressed("action",sequence=seq,action=name,value=value)

with ThreadingHTTPServer(("127.0.0.1",0),Server) as server:
    thread=Thread(target=server.serve_forever,daemon=True);thread.start()
    try:
        hello={"type":"hello","protocol":4,"features":[],"server":{
            "origin":f"http://127.0.0.1:{server.server_address[1]}","token":"synthetic-multipart"}}
        opened=addressed("render",surface="page")
        steps=[hello,opened,action(2,"step",4),action(3,"refresh"),action(4,"step",4),
               addressed("close"),opened]
        run=subprocess.run([binary],input=b"".join((json.dumps(v,ensure_ascii=False)+"\n").encode() for v in steps),
                           stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=True,timeout=60)
    finally:
        server.shutdown();thread.join()
if meter:
    logs=run.stderr.decode().splitlines()
    assert len(logs)==15 and all(s.startswith("alloc ") for s in logs),logs[:20]
    meter.write_text(run.stderr.decode())
else:
    assert not run.stderr,run.stderr[:1000]
rows=list(map(json.loads,run.stdout.splitlines()))
assert [(p["type"],p["sequence"]) for p in rows]==[("view",i) for i in (0,2,3,4,0)]
assert all(p["session_dir"]==session and p["view"]==view for p in rows)
assert calls==["/analysis","/sessions","/analysis","/analysis","/sessions","/analysis","/sessions"],calls
assert rows[2]["root"]["children"][1]==rows[1]["root"]
assert failure in str(rows[2]["root"]["children"][0])

def walk(tree):
    yield tree
    for c in tree.get("children",[]):
        yield from walk(c)
def disclosure(tree,id):
    return next(node["children"][0]["text"] for node in walk(tree) if node.get("id")==id)
def verify(row,rev,n):
    root=row["root"]
    a,f,t,b=fields(n)
    assert disclosure(root,"turn:turn:output")==f"Summary {rev}"
    assert disclosure(root,"4:message-0")=="\n".join([a,"Файл src/é.py\n"+f,"Результат pick:\n"+t,b])
    assert disclosure(root,"4:message-1")=="\n".join([
        "Файл None",'Результат second:\n{"z": [1, false], "a": "🧪"}',"Результат empty:",
        'Файл [1, 2]\n{"n": false}',"[изображение]",'Вызов utility: {"k": 2, "a": false}',
        '{\n  "Future": {\n    "unknown": [\n      null,\n      1\n    ]\n  }\n}'])
    assert disclosure(root,"4:message-2")==json.dumps(request(n)[-1],ensure_ascii=False,indent=2)
    assert disclosure(root,"4:answer")=="одно сообщение 🧪\n\nФайл src"
verify(rows[0],7,26_000)
verify(rows[3],8,26_000)
verify(rows[4],9,1)
assert not any(n.get("id")=="4:message-0" for n in walk(rows[1]["root"]))
out.write_bytes(run.stdout)
print(len(rows),len(run.stdout),sha256(run.stdout).hexdigest())
