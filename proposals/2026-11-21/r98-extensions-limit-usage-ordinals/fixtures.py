"""Actual Usage release binary, exact raw stdout and GET receipts from loopback only."""
import http.server
import re
import json
from pathlib import Path
import subprocess as sp
import threading
from urllib.parse import parse_qs, urlsplit

PKG = Path("packages/usage")
A, B = "/synthetic-usage-a", "/synthetic-usage-b"


def rendered(view, scope, session, surface="page"):
    return {"type":"render","view":view,"context":scope,"session_dir":session,"surface":surface}


def context(scope, session):
    return {"type":"context","context":scope,"session_dir":session}


def action(view, seq, name, value):
    return {"type":"action","view":view,"sequence":seq,"action":name,"value":value}


def close(view):
    return {"type":"close","view":view}


def run_case(exe, src, env, readings, inp):
    receipts, errors, writes = [], [], []
    known = {A, B}

    class API(http.server.BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            writes.append(self.command)
            self.send_error(405)

        do_DELETE = do_PUT = do_PATCH = do_POST

        def do_GET(self):
            try:
                url = urlsplit(self.path)
                query = parse_qs(url.query, keep_blank_values=True)
                assert url.path in ("/usage","/sessions") and self.headers["Authorization"]=="Bearer fixture"
                session, = query.pop("session_dir")
                assert session in known
                if url.path=="/sessions":
                    assert not query
                    data=[{"session_dir":s,"preview":f"Synthetic {label}","message_count":2} for s,label in ((A,"A"),(B,"B"))]
                else:
                    assert not query and session in readings,session
                    data=readings[session]
                receipts.append((url.path,session))
                payload=json.dumps(data,ensure_ascii=False,allow_nan=False).encode()
                self.send_response(200)
                self.send_header("Content-Type","application/json")
                self.send_header("Content-Length",str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
            except Exception as exc:
                errors.append(exc)
                self.send_error(500)

    with http.server.ThreadingHTTPServer(("127.0.0.1",0),API) as server:
        thread=threading.Thread(target=server.serve_forever,kwargs={"poll_interval":0.025},daemon=True)
        thread.start()
        try:
            features=json.loads((src/PKG/"extension.json").read_text())["required_features"]
            hello={"type":"hello","protocol":4,"features":features,"workspace":"/synthetic",
                   "server":{"origin":f"http://127.0.0.1:{server.server_port}","token":"fixture"}}
            out=sp.run([exe],cwd=src/PKG,env=env,input=b"".join(
                json.dumps(msg,ensure_ascii=False).encode()+b"\n" for msg in [hello,*inp]),
                capture_output=True,check=True,timeout=20)
        finally:
            server.shutdown()
            thread.join()
    assert not (out.stderr or errors or writes),(out.stderr,errors,writes)
    frames=[json.loads(line) for line in out.stdout.splitlines()]
    assert frames and all(f["type"]=="view" for f in frames),[f["type"] for f in frames]
    return out.stdout, receipts, frames


def documents():
    def sample(i):
        return {"exchange_id":f"req-{i:04}","turn_id":"odd" if i%2 else "even",
                "origin":"direct","status":"error" if i%3==0 else "completed",
                "model":{"provider":"fixture","model":"gpt-6-astra" if i%5 else "local"},
                "started_at_ms":1700000000000+i*1000,"finished_at_ms":1700000000650+i*1000,
                "usage":None if i%7==0 else {"input_tokens":i+1,"output_tokens":3},
                "message_count":2,"tool_count":1}
    def snapshot(rows, latest):
        return {"requests":rows,"latest_turn_id":latest,"session_id":"fixture","revision":1}
    large=[sample(i) for i in range(2000)]
    odd=[sample(i) for i in range(45)]
    for i,r in enumerate(odd):
        r.update(turn_id="show" if i<9 else "hide",status="error" if i<9 else "completed")
        r["model"]["model"]="visible" if i<9 else "excluded"
    for i in (0,1,42):
        odd[i]["exchange_id"]="повтор 🦀"
    for i in (2,44):
        del odd[i]["exchange_id"]
    for i,v in ((3,None),(4,17),(5,""),(6,[3]),(7,{"id":"bad"}),(8,"tail"),(43,"")):
        odd[i]["exchange_id"]=v
    return {A:snapshot(large,"odd"),B:snapshot(odd,"show")}


def walk(node):
    if isinstance(node,dict):
        yield node
        for item in node.get("children",[]):
            yield from walk(item)


def cards(frame):
    out=[]
    for n in walk(frame["root"]):
        if n.get("action")=="request":
            match=re.fullmatch(r"([▾▸]) #(\d+) · (.*)",n["label"])
            assert match and ("value" in n)
            is_open=match[1]=="▾"
            assert is_open==n.get("selected",False)
            assert n["hint"]==("Свернуть" if is_open else "Подробнее")
            out.append((int(match[2]),n["value"],is_open))
    return out


def replay(exe,src,env):
    fixtures=documents()
    events=[]
    def open_(ctx,session,view,surface="page"):
        events.extend([context(ctx,session),rendered(view,ctx,session,surface)])
    def close_(view,ctx):
        events.extend([close(view),{"type":"close_context","context":ctx}])
    def acts(view,pairs):
        events.extend(action(view,i,k,v) for i,(k,v) in enumerate(pairs,1))
    open_("left",A,"page")
    acts("page",[("page",1),("page",2**63-1),("page",-2),("order","newest"),
                 ("period","latest"),("model","fixture/gpt-6-astra"),("status","problems"),
                 ("query","NO MATCH AT ALL")])
    open_("sibling",A,"second")
    close_("second","sibling")
    close_("page","left")
    open_("other",B,"bad")
    acts("bad",[("period","latest"),("model","fixture/visible"),("status","problems"),
                ("request",17),("request",""),("request","повтор 🦀"),
                ("query"," ПОВТОР 🦀 "),("order","newest")])
    close_("bad","other")
    open_("fresh",B,"fresh-page")
    close_("fresh-page","fresh")
    open_("preview-ctx",B,"preview","preview")
    close_("preview","preview-ctx")
    raw,reads,frames=run_case(exe,src,env,fixtures,events)
    expected=[("page",A,i) for i in range(9)]+[("second",A,0)]+[("bad",B,i) for i in range(9)]+[
              ("fresh-page",B,0),("preview",B,0)]
    assert [(f["view"],f["session_dir"],f["sequence"]) for f in frames]==expected
    shown=[cards(f) for f in frames]
    def normal(ix):
        return [(i+1,f"req-{i:04}",False) for i in ix]
    assert shown[:5]==[normal(range(20)),normal(range(20,40)),normal(range(1980,2000)),
                       normal(range(20)),normal(range(1999,1979,-1))]
    for n,pred in [(5,lambda i: i%2),(6,lambda i:i%2 and i%5),
                   (7,lambda i:i%2 and i%5 and i%3==0)]:
        assert shown[n]==normal([i for i in reversed(range(2000)) if pred(i)][:20])
    assert shown[8]==shown[9]==[]
    assert all("По этим фильтрам запросов нет." in [n.get("text") for n in walk(frames[i]["root"])] for i in (8,9))
    # Literal keys and raw values: last raw duplicate index, not visible index; nonstrings share "".
    values=["повтор 🦀","повтор 🦀",None,None,17,"",[3],{"id":"bad"},"tail"]
    nums=[43,43,45,45,45,45,45,45,9]
    closed=[(n,v,False) for n,v in zip(nums,values)]
    assert shown[10][:9]==closed and len(shown[10])==20
    assert shown[11:14]==[closed]*3
    assert shown[14]==[(n,v,n==45) for n,v in zip(nums,values)]
    assert shown[15]==closed
    assert shown[16]==[(n,v,n==43) for n,v in zip(nums,values)]
    assert shown[17]==shown[18]==[(43,"повтор 🦀",True)]*2
    assert shown[19]==shown[10] and shown[20]==[(1,"demo-request-1",False),(2,"demo-request-2",False)]
    assert reads==[(path,session) for session in (A,B,B) for path in ("/sessions","/usage")],reads
    return (raw,),(reads,)
