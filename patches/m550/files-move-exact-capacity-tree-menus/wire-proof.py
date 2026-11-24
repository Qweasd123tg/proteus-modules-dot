"""Native Files panel, synthetic GET-only workspace. No menu write action runs."""
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
session="/synthetic/files-panel"
cwd='/synthetic/Проект π "tag"'
view="tree"
context="fixture"
focus='перо "phase".rs'
probes=[f"probe-{n:02d}" for n in range(65)]
calls=[]
changed=[(focus,"modified"),("chain/part/end.txt","deleted"),("symbolic","added")]

def item(path,kind):
    return {"name":path.rsplit("/",1)[-1],"path":path,"kind":kind}
leaves=[item(focus,"file"),item("symbolic","symlink")]
leaves.extend(item(f'Документ "record" {n:04d} '+("λ"*25)+".txt","file")
              for n in range(930))
root=[item("chain","directory"),item("clipped","directory")]
root += [item(p,"directory") for p in probes]
root += leaves+[item(".git","directory")]
assert len(root)==1000
folders={
    "":{"entries":root,"truncated":True},
    "chain":{"entries":[item("chain/part","directory")]},
    "chain/part":{"entries":[item("chain/part/end.txt","file")]},
    "clipped":{"entries":[item("clipped/later","directory")],"truncated":True},
    "probe-64":{"entries":[item("probe-64/child","directory")]},
}
for p in probes[:-1] + ["probe-64/child"]:
    folders[p]={"entries":[]}

class Server(BaseHTTPRequestHandler):
    protocol_version="HTTP/1.1"
    def do_GET(self):
        url=urlsplit(self.path)
        assert self.headers["Authorization"]=="Bearer synthetic-panel"
        args=parse_qs(url.query,keep_blank_values=True)
        assert args.pop("session_dir")==[session]
        if url.path=="/sessions/current":
            assert not args
            value=[{"session_dir":session,"workspace_path":cwd}]
            calls.append((url.path,None))
        elif url.path=="/workspace/changes":
            assert not args
            value={"repository":True,"entries":[{"path":p,"status":s} for p,s in changed]}
            calls.append((url.path,None))
        else:
            assert url.path=="/workspace/list"
            p=args.pop("path",[""])[0];assert not args
            calls.append((url.path,p))
            value=folders[p]
        body=json.dumps(value,ensure_ascii=False,separators=(",",":")).encode()
        self.send_response(200);self.send_header("Content-Type","application/json")
        self.send_header("Content-Length",str(len(body)));self.send_header("Connection","close")
        self.end_headers();self.wfile.write(body)
    def log_message(self,*_):
        pass

def addressed(kind,**extras):
    return {"type":kind,"view":view,"context":context,"session_dir":session,**extras}
def act(seq,entry,event):
    return addressed("action",sequence=seq,action="files",value={"id":entry,"event":event})
def run_process(requests):
    return subprocess.run([binary], input=b"".join((json.dumps(v,ensure_ascii=False)+"\n").encode()
                          for v in requests),stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                          timeout=60,check=True)
with ThreadingHTTPServer(("127.0.0.1",0),Server) as server:
    thread=Thread(target=server.serve_forever,daemon=True);thread.start()
    try:
        hello={"type":"hello","protocol":4,"features":[],"server":{
            "origin":f"http://127.0.0.1:{server.server_address[1]}","token":"synthetic-panel"}}
        args=[hello,addressed("render",surface="panel"),
              addressed("event",event="navigation_changed",document=focus),
              act(19,"chain/part","expand"),act(20,".","collapse"),act(21,".","expand")]
        real=run_process(args)
    finally:
        server.shutdown();thread.join()
preview=run_process([{"type":"hello","protocol":4,"features":[]},
                     addressed("render",surface="preview")])
assert not preview.stderr,preview.stderr
if meter:
    logs=real.stderr.decode().splitlines()
    assert len(logs)==5 and all(line.startswith("alloc ") for line in logs),logs[:20]
    meter.write_text(real.stderr.decode())
else:
    assert not real.stderr,real.stderr[:1000]

expected=[("/sessions/current",None),("/workspace/changes",None)]+[
    ("/workspace/list",p) for p in ["","chain","chain/part","clipped"]+probes+["probe-64/child"]]
assert calls==expected,[p for p in calls if p not in expected]
frames=list(map(json.loads,real.stdout.splitlines()))
assert [p["sequence"] for p in frames]==[0,0,19,20,21]
def tree(frame):
    assert frame["type"]=="view" and frame["session_dir"]==session and frame["keys"]=={"escape":"escape"}
    assert frame["root"]["type"]=="fill"
    return next(v for v in frame["root"]["children"] if v["type"]=="tree")
def indexed(frame):
    ordered=tree(frame)["rows"]
    assert len(ordered)==len({r["id"] for r in ordered})
    for row in ordered:
        assert list(row)==["id","label","depth","expanded","tone","selected","icon","icon_tone","hint","menu"]
    return {r["id"]:r for r in ordered}
first,selected,expanded,collapsed,last=list(map(indexed,frames))
assert len(first)==len(selected)==1000 and len(expanded)==len(last)==1001
assert list(collapsed)==["."] and not collapsed["."]["expanded"]
assert first["."]["hint"]==cwd and first["."]["expanded"]
assert first["chain/part"]["label"]=="chain/part" and not first["chain/part"]["expanded"]
assert expanded["chain/part"]["expanded"] and expanded["chain/part/end.txt"]["depth"]==2
assert "probe-64" in first and "probe-64/child" not in first
assert "probe-64/child" in selected and "clipped" in selected and "clipped/later" not in selected
assert ".git" not in first and not first[focus]["selected"] and selected[focus]["selected"]
assert first[focus]["tone"]=="warning" and first[focus]["hint"]==cwd+"/"+focus
assert first["symbolic"]["tone"]=="success" and first["symbolic"]["expanded"] is None
menu=first[focus]["menu"]
assert [v["action"] for v in menu]==[
    "new-file","new-folder","copy","copy","restore","ignore","ignore","diff","rename","delete"]
assert [i for i,v in enumerate(menu) if v.get("separated")]==[2,4,8]
assert menu[4]["confirm"]["danger"] and menu[-1]["confirm"]["danger"]
assert menu[2]["value"]==cwd+"/"+focus and menu[3]["value"]==focus
assert menu[8]["prompt"]["value"]==focus and menu[8]["prompt"]["stem"]
assert any(v.get("text","").startswith("Часть папок") for v in frames[0]["root"]["children"])
test=list(map(json.loads,preview.stdout.splitlines()))
assert len(test)==1 and test[0]["root"]["type"]=="tree" and test[0]["root"]["id"]=="files-preview"
assert len(test[0]["root"]["rows"])==5
raw=real.stdout+preview.stdout
out.write_bytes(raw)
print(6,len(raw),sha256(raw).hexdigest())
