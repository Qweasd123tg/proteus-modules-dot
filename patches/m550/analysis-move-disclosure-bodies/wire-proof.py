"""Actual Analysis process, only the read-only report server is synthetic."""
from hashlib import sha256
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import subprocess
import sys
from threading import Thread
from urllib.parse import parse_qs, urlsplit

binary, output = (Path(p).resolve() for p in sys.argv[1:])
session = "/synthetic/analysis-output"
view = "fixture"
context = "fixture-window"
text = "Проверка 🦀\r\n\0 quoted \"text\" / &amp; ".replace("\\0","\0") * 24_000
fixture_error = "Синтетическая ошибка 🦀"
endpoint=[]
detail = 'Инструкция 🦀 & "quotes"\t\r\n' * 11_000
request_text = 'Запрос 🧪 \0\u2028' * 15_000
response_text = 'Ответ 🦀 \r\n "literal"' * 10_000
def message(role,text):
    return {"role":role,"parts":[{"payload":{"Text":{"text":text}}}]}
def report(rev):
    return {"session_id":"show-last", "revision":rev, "turns":[
                {"turn_id":"turn", "status":"success","number":rev,"prompt_preview":"Synthetic task"}],
            "selected":{"turn_id":"turn","task":{"text":"Synthetic task"},"steps":[
                            {"sequence":4,"started_at_ms":2000,"finished_at_ms":2060,
                             "data":{"kind":"model","exchange_id":"fixture",
                                     "request":{"model":{"model":"demo"},
                                                "instructions":[{"kind":"system","priority":11,"text":detail}],
                                                "messages":[message("User",request_text)],
                                                "tools":[{"name":"first"},{"name":None}]},
                                     "response":{"messages":[message("Assistant",response_text)],"finish_reason":"Stop"}}}],
                        "module_epoch":0,"output":{"text":f"Report {rev}: {text}"},"config_snapshot":{}}}
class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    def do_GET(self):
        request = urlsplit(self.path)
        assert parse_qs(request.query)=={"session_dir":[session]}
        assert self.headers["Authorization"]=="Bearer synthetic-fixture"
        endpoint.append(request.path)
        if request.path=="/analysis":
            n=endpoint.count("/analysis")
            status, value = {
                1: (200,report(7)),
                2: (503,{"error":fixture_error}),
                3: (200,report(9)),
                4: (503,{"error":fixture_error}),
                5: (200,report(11)),
            }[n]
        else:
            assert request.path=="/sessions"
            status,value=200,[{"session_dir":session,"message_count":2,"session_id":"test"}]
        data=json.dumps(value,ensure_ascii=False).encode()
        self.send_response(status);self.send_header("Content-Type","application/json")
        self.send_header("Content-Length",str(len(data)));self.send_header("Connection","close")
        self.end_headers();self.wfile.write(data)
    def log_message(self,*_):
        pass

def render(surface, **extra):
    return {"type":"render","view":view,"context":context,"session_dir":session,"surface":surface,**extra}

def act(sequence, action, value=None):
    return {"type":"action","view":view,"context":context,"session_dir":session,
            "sequence":sequence,"action":action,"value":value}

with ThreadingHTTPServer(("127.0.0.1",0),Handler) as server:
    thread=Thread(target=server.serve_forever,daemon=True);thread.start()
    try:
        port=server.server_address[1]
        frames=[{"type":"hello","protocol":4,"features":[],"server":{"origin":f"http://127.0.0.1:{port}","token":"synthetic-fixture"}},
                render("page"),act(41,"step",None),act(42,"step",[]),act(43,"refresh"),act(44,"refresh"),
                {"type":"close","view":view,"context":context,"session_dir":session},
                render("page"),render("content",content={"language":"synthetic","source":"fixture","source_revision":17}),
                act(45,"step",{})]
        encoded = b"".join((json.dumps(x,ensure_ascii=False)+"\n").encode() for x in frames)
        run=subprocess.run([binary],input=encoded,stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=True,timeout=35)
    finally:
        server.shutdown()
        thread.join()
assert not run.stderr, run.stderr[:1000]
rows=[json.loads(line) for line in run.stdout.split(b"\n") if line]
assert [(r["type"],r["sequence"]) for r in rows] == [
    ("view",0),("view",41),("view",42),("view",43),("view",44),("view",0),("view",0),("content_error",45)], [
        (r["type"], r["sequence"],r.get("error")) for r in rows]
assert endpoint==["/analysis","/sessions","/analysis","/analysis","/sessions","/analysis","/analysis","/sessions"], endpoint
def known_body(r,rev):
    nodes=[r["root"]]
    found=set()
    while nodes:
        n=nodes.pop()
        if n.get("type")=="code":
            if n.get("text")==f"Report {rev}: {text}":
                found.add("report")
            if n.get("text")=="[system · приоритет 11]\n"+detail:
                found.add("instruction")
            if n.get("text")==request_text.strip():
                found.add("request")
            if n.get("text")==response_text:
                found.add("answer")
            if n.get("text")=="first\nNone":
                found.add("tool")
        nodes.extend(n.get("children",[]))
    return found=={"report","instruction","request","answer","tool"}
assert all(known_body(rows[i],rev) for i,rev in [(0,7),(4,9),(6,11)])
for i in (1,2,3):
    children=rows[i]["root"]["children"]
    assert len(children)==2 and children[1]==rows[0]["root"]
    assert list(rows[i])==["type","session_dir","view","sequence","keys","root"]
    assert rows[i]["keys"]=={}
assert len(rows[5]["root"]["children"])==1 and fixture_error in str(rows[5]["root"])
assert rows[7]["source_revision"]==17 and rows[7]["view"]==view and "root" not in rows[7]
assert all(r["session_dir"]==session for r in rows)
output.write_bytes(run.stdout)
print(len(rows),len(run.stdout),sha256(run.stdout).hexdigest())
