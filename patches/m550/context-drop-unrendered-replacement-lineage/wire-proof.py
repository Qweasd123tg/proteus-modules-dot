"""Real Context IPC against synthetic typed-compatible /context HTTP snapshots."""
from hashlib import sha256
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import subprocess
import sys
from threading import Thread
from urllib.parse import parse_qs,urlsplit
from uuid import UUID

binary,out=(Path(p).resolve() for p in sys.argv[1:3])
meter=Path(sys.argv[3]) if len(sys.argv)==4 else None
session="/synthetic/context"
context="fixture"
failure="Synthetic context report unavailable"
calls=[]
def pair(i):
    # Only two MessageId string fields, the actual Core shape. Core already
    # clears report summary and metadata for this endpoint.
    return {"source_message_id":str(UUID(int=i+1)),
            "replacement_message_id":str(UUID(int=i+1+2**64))}
def report(n, count=0, malformed=False):
    return {
        "session_dir":session,"session_id":str(UUID(int=721)),
        "workspace_path":"/synthetic/tree","activity":None,
        "history":{"messages":24000,"user_messages":11000,"assistant_messages":11000,
                   "system_messages":0,"tool_results":2000,"estimated_tokens":70000},
        "latest_usage":None,"latest_context":None,
        "latest_compaction":{
            "status":"completed","summary_present":True,"turn_id":None,"timestamp_ms":0,
            "report":False if malformed else {
                "changed":True,"user_message_replacements":[pair(i) for i in range(count)],
                "reason":"compact","input_messages":24000+n,"output_messages":19800+n,
                "original_token_estimate":90000,"output_token_estimate":70000,
                "trigger_tokens":80000,"summary_source":"fixture","skipped_reason":None,
                "summary":None,"metadata":None}},
        "tools":{"requested":0,"finished":0,"failed":0,"names":[]},
        "diagnostics":[f"snapshot-marker-{n}"],
    }

class Server(BaseHTTPRequestHandler):
    protocol_version="HTTP/1.1"
    def do_GET(self):
        url=urlsplit(self.path)
        assert url.path=="/context" and parse_qs(url.query)=={"session_dir":[session]}
        assert self.headers["Authorization"]=="Bearer synthetic-context"
        calls.append(url.path); n=len(calls)
        value=None
        if n in (1,2):
            status,value=200,report(n,8192)
        elif n==3:
            status,value=503,{"error":failure}
        elif n==4:
            status,value=200,report(n,malformed=True)
        elif n==5:
            status,value=200,report(n)
        else:
            raise AssertionError("unexpected context HTTP read")
        body=json.dumps(value,ensure_ascii=False,separators=(",",":")).encode()
        if n in (1,2):
            assert 900_000<len(body)<10*1024*1024
        self.send_response(status);self.send_header("Content-Type","application/json")
        self.send_header("Content-Length",str(len(body)));self.send_header("Connection","close")
        self.end_headers();self.wfile.write(body)
    def log_message(self,*_):
        pass

def addr(kind,**kwargs):
    return {"type":kind,"context":context,"session_dir":session,**kwargs}
def state(used):
    return {"context":{"used":used,"max":120000,"trigger":100000}}
def update(used):
    return addr("session_update",update={"type":"state","state":state(used)})
def open_popup(view):
    return addr("render",surface="popup",view=view)

with ThreadingHTTPServer(("127.0.0.1",0),Server) as server:
    t=Thread(target=server.serve_forever,daemon=True);t.start()
    try:
        hello={"type":"hello","protocol":4,"features":[],"server":{
            "origin":f"http://127.0.0.1:{server.server_address[1]}","token":"synthetic-context"}}
        frames=[hello,addr("session_snapshot",state=state(2300),entries=[]),
                open_popup("one"),update(2300),open_popup("two"),addr("close",view="two"),
                update(2500),update(2500),addr("close",view="one"),open_popup("one"),
                update(2500),addr("close",view="one"),addr("close_context")]
        run=subprocess.run([binary],input=b"".join((json.dumps(v)+"\n").encode() for v in frames),
                           stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=True,timeout=50)
    finally:
        server.shutdown();t.join()
if meter:
    logs=run.stderr.decode().splitlines()
    assert len(logs)==7 and all(line.startswith("alloc ") for line in logs),logs[:15]
    meter.write_text(run.stderr.decode())
else:
    assert not run.stderr,run.stderr[:1000]

rows=list(map(json.loads,run.stdout.splitlines()))
assert [(r["type"],r["view"],r["sequence"]) for r in rows]==[
    ("view",v,0) for v in ("one","one","two","one","one","one","one")]
assert all(r["session_dir"]==session for r in rows)
assert calls==["/context"]*5,calls
def text(n):
    return json.dumps(rows[n]["root"],ensure_ascii=False)
assert rows[0]["root"]==rows[1]["root"]
assert rows[3]["root"]["children"][1]==rows[0]["root"] and failure in text(3)
for i,n in ((0,1),(1,1),(2,2),(4,4),(5,5),(6,5)):
    assert f"snapshot-marker-{n}" in text(i)
    assert "сохранена, текст скрыт" in text(i)
    assert "user_message_replacements" not in text(i)
    if i!=4:
        assert f"{24000+n} → {19800+n}" in text(i)
    else:
        assert "Сообщений" in text(i) and "→" not in text(i)
assert rows[5]["root"]==rows[6]["root"]
out.write_bytes(run.stdout)
print(len(rows),len(run.stdout),sha256(run.stdout).hexdigest())
