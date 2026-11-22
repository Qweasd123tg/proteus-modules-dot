"""Actual Git release binary replay: only synthetic read-only workspace receipts."""
import http.server
import json
from pathlib import Path
import subprocess as sp
import threading
from urllib.parse import parse_qs, urlsplit

PKG=Path("packages/git")
SESSION="/synthetic-worktree"
ARG="Все изменения"

def patch(n=96):
    return ("diff --git a/notes.txt b/notes.txt\n--- a/notes.txt\n+++ b/notes.txt\n"
            +f"@@ -0,0 +1,{n} @@\n"
            +"".join(f'+Line {i:03}: retention check, "quoted" note, data and UTF-8 Ж.\n' for i in range(n)))

def render(view,arg=ARG,ctx="left"):
    return {"type":"render","view":view,"context":ctx,"session_dir":SESSION,"surface":"document","argument":arg}

def close(view):
    return {"type":"close","view":view}

def context(ctx):
    return {"type":"context","context":ctx,"session_dir":SESSION}

def shut(ctx):
    return {"type":"close_context","context":ctx}

def event(ctx):
    return {"type":"event","context":ctx,"session_dir":SESSION,"event":"run_settled"}

def walk(value):
    if isinstance(value,dict):
        yield value
        for child in value.values():
            yield from walk(child)
    elif isinstance(value,list):
        for child in value:
            yield from walk(child)

def run(exe,src,env,case,events):
    reads,errors,writes=[],[],[]
    generation=0
    ordinary=patch()
    assert ordinary.endswith("\n") and 2048<=len(ordinary.encode())<=12288
    fields={
        "binary":("binary",None),"empty":("text",""),"long":("text",patch(40).rstrip("\n")),
        "short":("text",'+Ж "q"\t\r\n'),"numeric":("text",7),
        "unavailable":("unavailable",None),"large":("too_large",None),
    }
    paths={
        "ordinary":["notes.txt"],
        "mixed":list(fields),
        "failure":["failure.txt"],
        "count":[f"file-{i:02}.txt" for i in range(41)],
    }[case]

    class Server(http.server.BaseHTTPRequestHandler):
        def log_message(self,*args):
            pass
        def do_POST(self):
            writes.append(self.command)
            self.send_error(405)
        do_PUT=do_DELETE=do_PATCH=do_POST
        def do_GET(self):
            try:
                self.reply()
            except Exception as exc:
                errors.append(exc)
                self.send_error(500)
        def reply(self):
            nonlocal generation
            url=urlsplit(self.path)
            query=parse_qs(url.query,keep_blank_values=True)
            assert self.headers.get("Authorization")=="Bearer fixture"
            assert query.pop("session_dir")==[SESSION]
            status=200
            def rev(path):
                return None if path=="numeric" else f"version-{generation}"
            if url.path=="/workspace/changes":
                assert not query
                generation+=1
                reads.append(("changes",generation))
                value={"repository":True,"branch":"main","refs_revision":"stable","added":96,"deleted":0,
                       "entries":[{"path":p,"status":"modified","revision":rev(p)} for p in paths]}
            else:
                assert url.path=="/workspace/diff"
                p,=query.pop("path")
                assert not query and p in paths
                reads.append(("diff",p,generation))
                if case=="failure":
                    status,value=500,{"error":"synthetic diff unavailable"}
                else:
                    if case=="ordinary":
                        kind,content="text",ordinary.replace("retention check","retention check" if generation==1 else "next generation")
                    elif case=="mixed":
                        kind,content=fields[p]
                    else:
                        kind,content="text",""
                    value={"path":p,"revision":rev(p),"kind":kind}
                    if content is not None:
                        value["patch"]=content
            body=json.dumps(value,separators=(",",":"),ensure_ascii=False).encode()
            self.send_response(status)
            self.send_header("Content-Type","application/json")
            self.send_header("Content-Length",str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    with http.server.ThreadingHTTPServer(("127.0.0.1",0),Server) as server:
        thread=threading.Thread(target=server.serve_forever,kwargs={"poll_interval":0.025},daemon=True)
        thread.start()
        try:
            features=json.loads((src/PKG/"extension.json").read_text())["required_features"]
            hello={"type":"hello","protocol":4,"features":features,"workspace":"/synthetic",
                   "server":{"origin":f"http://127.0.0.1:{server.server_port}","token":"fixture"}}
            proc=sp.run([exe],cwd=src/PKG,env=env,input=b"".join(
                json.dumps(v,ensure_ascii=False).encode()+b"\n" for v in [hello,*events]),
                capture_output=True,check=True,timeout=20)
        finally:
            server.shutdown()
            thread.join()
    assert not (proc.stderr or errors or writes),(proc.stderr,errors,writes)
    frames=[json.loads(line) for line in proc.stdout.splitlines()]
    assert frames and all(f["type"]=="view" and f["session_dir"]==SESSION for f in frames)
    diffs=[[n for n in walk(f["root"]) if n.get("type")=="diff"] for f in frames]
    return proc.stdout,reads,frames,diffs

def replay(exe,src,env):
    a,ar,af,ad=run(exe,src,env,"ordinary",[
        context("left"),render("all"),render("all"),render("one","notes.txt · diff"),close("one"),
        event("left"),close("all"),shut("left"),context("fresh"),render("fresh",ctx="fresh"),
        close("fresh"),shut("fresh")])
    assert [f["view"] for f in af]==["all","all","one","all","fresh"],af
    old=patch()
    new=old.replace("retention check","next generation")
    assert [ds[0]["patch"] for ds in ad]==[old,old,old,new,new]
    assert [ds[0]["id"] for ds in ad]==["changes","changes","diff","changes","changes"]
    for ds in ad:
        node,=ds
        assert list(node)==["type","id","patch","files"]
        assert node["files"]==[{"path":"notes.txt","status":"modified","message":None}]
    assert ar==[("changes",1),("diff","notes.txt",1),("changes",2),("diff","notes.txt",2),
                ("changes",3),("diff","notes.txt",3)],ar

    b,br,bf,bd=run(exe,src,env,"mixed",[
        context("left"),render("all"),render("all"),close("all"),shut("left")])
    assert [f["view"] for f in bf]==["all","all"]
    paths=["binary","empty","long","short","numeric","unavailable","large"]
    assert br==[("changes",1)]+[("diff",p,1) for p in paths]+[("diff","numeric",1)],br
    for ds in bd:
        node,=ds
        assert node["patch"]=="\n"+patch(40)+'+Ж "q"\t\r\n'
        assert [f["path"] for f in node["files"]]==paths
        assert [f["message"] for f in node["files"]]==["Двоичный файл",None,None,None,None,"Diff недоступен","Diff превышает предел 512 КБ"]

    c,cr,cf,cd=run(exe,src,env,"failure",[
        context("left"),render("all"),close("all"),shut("left")])
    assert cr==[("changes",1),("diff","failure.txt",1)] and cd==[[]]
    assert "synthetic diff unavailable" in json.dumps(cf,ensure_ascii=False)
    d,dr,df,dd=run(exe,src,env,"count",[
        context("left"),render("all"),close("all"),shut("left")])
    assert dr==[("changes",1)]+[("diff",f"file-{i:02}.txt",1) for i in range(40)]
    assert len(dd)==1 and len(dd[0])==1 and len(dd[0][0]["files"])==40 and dd[0][0]["patch"]=="\n"
    assert "Показаны первые 40 файлов из 41" in json.dumps(df,ensure_ascii=False)
    return (a,b,c,d),(ar,br,cr,dr)
