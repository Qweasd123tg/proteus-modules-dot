"""Exercise native Git Working Tree documents; all HTTP routes are synthetic and read-only."""
from hashlib import sha256
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import subprocess
import sys
from threading import Thread
from urllib.parse import parse_qs, urlsplit

git, out = (Path(p).resolve() for p in sys.argv[1:3])
meter = Path(sys.argv[3]) if len(sys.argv)==4 else None
LIMIT=4*1024*1024
name="Все изменения"

def enc(value):
    return json.dumps(value, separators=(",",":"), ensure_ascii=False).encode()

def item(n, text=None, kind="text"):
    row={"path":f'src/é-{n:02d} "quoted".rs',"status":"modified","revision":None}
    data={"path":row["path"],"kind":kind,"revision":None}
    if text is not None:
        assert len(text.encode())<512*1024
        data["patch"]=text
    return row,data

def info(row,data):
    return {"path":data["path"],"status":row["status"],"message":{
        "binary":"Двоичный файл","too_large":"Diff превышает предел 512 КБ",
        "unavailable":"Diff недоступен"}.get(data["kind"])}

def cost(row,data):
    return len(enc(info(row,data)))+len(enc(data.get("patch","")))+32

ordinary=[item(n, f"file {n}\n"+"p"*(465000-len(f"file {n}\n"))) for n in range(8)]
base_cost=sum(cost(*part) for part in ordinary)
slack=LIMIT-base_cost-cost(*item(8,""))
assert slack<512*1024
ordinary+=[item(8,"b"*(slack-2)+"\n"),item(9,"break\n"),item(10,"must not fetch\n")]
assert sum(cost(*part) for part in ordinary[:9])==LIMIT
escaped=[item(0,kind="binary"),item(1,""),item(2,"initial no newline"),
         item(3,kind="too_large"),item(4,kind="unavailable")]
escaped += [item(n,'\\\t"\r\n🧪λ'*37_000+"\n") for n in range(5,14)]
tight=[item(0,"+"+"x"*255+"\n")]
limit=[item(n,"+row "+str(n)+"\n") for n in range(45)]
groups={"ordinary":ordinary,"escaped":escaped,"tight":tight,"file-limit":limit,
        "empty":[],"http-error":[item(0,"fallback not admitted")]}
calls=[]

def expected(group):
    patch=""; files=[]; reads=[]; used=0
    for row,data in group[:40]:
        reads.append(row["path"])
        used+=cost(row,data)
        if used>LIMIT: break
        files.append(info(row,data))
        if "patch" in data:
            patch+=data["patch"]
            if not patch.endswith("\n"): patch+="\n"
    return patch,files,reads

class Server(BaseHTTPRequestHandler):
    protocol_version="HTTP/1.1"
    def do_GET(self):
        url=urlsplit(self.path); q=parse_qs(url.query)
        assert self.headers["Authorization"]=="Bearer git-synthetic"
        group=q.pop("session_dir")[0].removeprefix("/synthetic/")
        assert group in groups
        if url.path=="/workspace/changes":
            assert not q
            calls.append((group,"changes"))
            body={"repository":True,"branch":"native-synthetic","head":{"short":"abc1234"},
                  "refs_revision":"fixture","added":123,"deleted":45,
                  "entries":[row for row,_ in groups[group]]}
            status=200
        else:
            assert url.path=="/workspace/diff"
            [path]=q.pop("path")
            assert not q
            calls.append((group,path))
            body={row["path"]:data for row,data in groups[group]}[path]
            if group=="http-error":
                body={"error":"synthetic diff not available 🧪"}; status=503
            else:
                status=200
        content=enc(body)
        self.send_response(status); self.send_header("Content-Type","application/json")
        self.send_header("Content-Length",str(len(content))); self.send_header("Connection","close")
        self.end_headers(); self.wfile.write(content)
    def log_message(self,*_):
        pass

with ThreadingHTTPServer(("127.0.0.1",0),Server) as server:
    thread=Thread(target=server.serve_forever,daemon=True);thread.start()
    try:
        frames=[{"type":"hello","protocol":4,"features":[],
                 "server":{"origin":f"http://127.0.0.1:{server.server_address[1]}","token":"git-synthetic"}}]
        for group in groups:
            context={"view":"working","context":"fixture","session_dir":"/synthetic/"+group}
            frames += [{"type":"render",**context,"surface":"document","argument":name},
                       {"type":"close",**context}]
        process=subprocess.run([git],input=b"".join(enc(p)+b"\n" for p in frames),
                               stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=40,check=True)
    finally:
        server.shutdown();thread.join()

if meter:
    diags=process.stderr.decode().splitlines()
    assert len(diags)==4 and all(line.startswith("alloc ") for line in diags),diags[:5]
    meter.write_text(process.stderr.decode())
else:
    assert not process.stderr,process.stderr[:1000]
rows=list(map(json.loads,process.stdout.splitlines()))
assert len(rows)==len(groups),[(r.get("view"),r.get("type"),r.get("session_dir")) for r in rows]
wanted=[]
for (group,items),frame in zip(groups.items(),rows):
    assert frame["title"]=="Working Tree" and frame["session_dir"]=="/synthetic/"+group
    assert list(frame)==["type","session_dir","view","root","title","sequence","source_revision"]
    assert frame["sequence"]==0 and frame["type"]=="view" and frame["source_revision"] is None
    assert frame["root"]["type"]=="fill"
    children=frame["root"]["children"]
    patch,files,reads=expected(items)
    wanted += [(group,"changes"),*((group,p) for p in reads)]
    if group=="empty":
        assert children[1]["text"]=="Нет изменений для коммита"
    elif group=="http-error":
        assert len(children)==1 and children[0]["text"]=="synthetic diff not available 🧪"
    else:
        node=children[-1]
        assert list(node)==["type","id","patch","files"]
        assert node=={"type":"diff","id":"changes","patch":patch,"files":files},group
        assert len(files)=={"ordinary":9,"escaped":12,"tight":1,"file-limit":40}[group],(group,len(files))
        if len(files)<len(items):
            assert f"первые {len(files)} файлов из {len(items)}" in children[1]["text"]
        else:
            assert len(children)==2
assert wanted==calls,[(a,b) for a,b in zip(wanted,calls) if a!=b][:6]
out.write_bytes(process.stdout)
print(len(rows),len(process.stdout),sha256(process.stdout).hexdigest())
