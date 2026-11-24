"""Drive the native Analysis package against a bounded synthetic loopback API."""
from array import array
from hashlib import sha256
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import fcntl
import json
import os
from pathlib import Path
import select
import subprocess
import sys
from threading import Thread
from time import monotonic, sleep
from termios import FIONREAD
from urllib.parse import parse_qs, urlsplit

binary, output = (Path(p).resolve() for p in sys.argv[1:3])
meter = Path(sys.argv[3]) if len(sys.argv) > 3 else None
session = "/synthetic/report-scope"
context = "owner-again"
view = "analysis"
nonce = "A" * 196_000 + ' 🧪 CRLF\r\n quote " tail'
failure = "Ошибка списка сессий 🧪"
paths = []

def report(revision, tool_bytes):
    steps = [{"sequence":4,"started_at_ms":2000,"finished_at_ms":2300,
              "data":{"kind":"model","request":{"model":{"model":"fixture"}},
                      "response":{"finish_reason":"Stop","messages":[{"role":"Assistant","parts":[
                          {"payload":{"Text":{"text":"Answer "+nonce}}}]}]}}}]
    for i in range(16,32):
        steps.append({"sequence":i,"started_at_ms":3000+i,"finished_at_ms":4000+i,
                      "data":{"kind":"tool","call":{"name":f"example-{i}","args":{"index":i}},
                              "result":{"ok":True,"output":f"TOOL {revision}:{i} "+"x"*tool_bytes}}})
    return {"session_id":"report-scope","revision":revision,"turns":[
        {"turn_id":"turn","status":"success","number":revision,"prompt_preview":"Синтетический ход 🧪"}],
        "selected":{"turn_id":"turn","task":{"text":"Read-only timeline"},"steps":steps,
                    "output":{"text":"Report "+str(revision)},"module_epoch":0,"config_snapshot":{}}}

class Fixture(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    def do_GET(self):
        url = urlsplit(self.path)
        assert parse_qs(url.query)=={"session_dir":[session]},self.path
        assert self.headers["Authorization"]=="Bearer synthetic-only"
        paths.append(url.path)
        if url.path=="/analysis":
            n=paths.count("/analysis")
            if n==4:
                body=b'"'+b'x'*(10*1024*1024)+b'"'
            else:
                width={1:550_000,2:550_000,3:550_000,5:400_000,6:1_000}[n]
                body=json.dumps(report(n,width),ensure_ascii=False,separators=(",",":")).encode()
                if n in (1,2,3):
                    assert 8*1024*1024<len(body)<10*1024*1024
                elif n==5:
                    assert 6*1024*1024<len(body)<8*1024*1024
            status=200
        else:
            assert url.path=="/sessions"
            status=503 if paths.count("/sessions")==2 else 200
            value={"error":failure} if status==503 else [
                {"session_dir":session,"message_count":17,"preview":"тетрадь 🧪","session_id":"test"}]
            body=json.dumps(value,ensure_ascii=False,separators=(",",":")).encode()
        self.send_response(status)
        self.send_header("Content-Type","application/json")
        self.send_header("Content-Length",str(len(body)))
        self.send_header("Connection","close")
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            assert url.path=="/analysis" and n==4
    def log_message(self,*_):
        pass

def addressed(kind, **extra):
    return {"type":kind,"view":view,"context":context,"session_dir":session,**extra}

def ready(stream, timeout=15):
    assert select.select([stream],[],[],timeout)[0],"native process did not reach this boundary"

def frame(proc, payload):
    proc.stdin.write((json.dumps(payload,ensure_ascii=False)+"\n").encode())
    proc.stdin.flush()

def nodes(tree):
    yield tree
    for c in tree.get("children",[]):
        yield from nodes(c)

def has(tree,text):
    return any(n.get("text")==text for n in nodes(tree))

with ThreadingHTTPServer(("127.0.0.1",0),Fixture) as server:
    thread=Thread(target=server.serve_forever,daemon=True)
    thread.start()
    try:
        frames=[
            addressed("render",surface="page"),
            addressed("action",action="step",value=17,sequence=2),
            addressed("action",action="refresh",sequence=3),
            addressed("action",action="refresh",sequence=4),
            addressed("action",action="refresh",sequence=5),
            addressed("action",action="step",value=4,sequence=6),
            addressed("close"),
            addressed("render",surface="page"),
        ]
        proc=subprocess.Popen([binary],stdin=subprocess.PIPE,stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE)
        packets=[]; stats=[]; pipe_size=fcntl.fcntl(proc.stdout,fcntl.F_GETPIPE_SZ)
        deadline=15
        try:
            frame(proc,{"type":"hello","protocol":4,"features":[],
                       "server":{"origin":f"http://127.0.0.1:{server.server_address[1]}","token":"synthetic-only"}})
            for i,message in enumerate(frames):
                frame(proc,message)
                if i==6:
                    continue
                if meter and i not in (2,3):
                    # The handler prints at the write boundary; no stdout has
                    # been drained yet, and the next frame exceeds pipe size.
                    ready(proc.stderr); stats.append(proc.stderr.readline().decode().strip())
                ready(proc.stdout)
                if meter:
                    # Wait before reading a byte. Linux often leaves part of
                    # a page unused because the next write cannot fit there.
                    # Wait for the writer itself to be blocked on this pipe.
                    until=monotonic()+3
                    buffered=array("i",[0])
                    wchan=Path(f"/proc/{proc.pid}/wchan")
                    blocked=""
                    while monotonic()<until:
                        blocked=wchan.read_text().strip()
                        fcntl.ioctl(proc.stdout,FIONREAD,buffered,True)
                        if "pipe_write" in blocked and buffered[0]>0:
                            break
                        sleep(.001)
                    assert "pipe_write" in blocked and 0<buffered[0]<=pipe_size,(i,blocked,buffered[0],pipe_size)
                packet=proc.stdout.readline()
                assert len(packet)>pipe_size, (i,len(packet),pipe_size)
                packets.append(packet)
            proc.stdin.close()
            assert proc.wait(timeout=deadline)==0
            assert not proc.stderr.read()
            assert not proc.stdout.read()
        finally:
            if proc.poll() is None:
                proc.kill();proc.wait()
    finally:
        server.shutdown();thread.join()
assert paths==["/analysis","/sessions","/analysis","/analysis","/sessions",
               "/analysis","/analysis","/sessions","/analysis","/sessions"],paths
rows=list(map(json.loads,packets))
assert [(p["type"],p["sequence"]) for p in rows]==[("view",i) for i in (0,2,3,4,5,6,0)]
assert all(p["view"]==view and p["session_dir"]==session for p in rows)
for i,revision in ((0,1),(1,2),(4,5),(5,5),(6,6)):
    assert has(rows[i]["root"],f"Report {revision}")
assert has(rows[0]["root"],"Answer "+nonce)
assert has(rows[1]["root"],"TOOL 2:17 "+"x"*550_000)
assert has(rows[4]["root"],"TOOL 5:17 "+"x"*400_000)
assert has(rows[5]["root"],"Answer "+nonce)
for i in (2,3):
    assert rows[i]["root"]["children"][1]==rows[1]["root"]
assert failure in packets[2].decode()
assert b"limit" in packets[3].lower(),packets[3][:500]
if meter:
    assert len(stats)==5 and all(s.startswith("alloc ") for s in stats),stats
    meter.write_text("\n".join(stats)+"\n")
raw=b"".join(packets)
output.write_bytes(raw)
print(len(rows),len(raw),sha256(raw).hexdigest())
