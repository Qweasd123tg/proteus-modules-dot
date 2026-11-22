"""Actual Usage release binary, exact raw stdout and GET receipts from loopback only."""
import http.server
import re
import json
from pathlib import Path
import subprocess as sp
import threading
from urllib.parse import parse_qs, urlsplit

PKG = Path("packages/usage")
A, B, C = "/synthetic-usage-a", "/synthetic-usage-b", "/synthetic-usage-null"


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
    known = set(readings)

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
                    data=[{"session_dir":s,"preview":f"Synthetic {label}","message_count":2} for s,label in ((A,"A"),(B,"B"),(C,"C")) if s in known]
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
                       normal(range(20)),normal(range(1999,1979,-1))],shown[:5]
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
    other, other_reads = replay_breakdown(exe,src,env)
    return (raw,other),(reads,other_reads)

def breakdown_documents():
    def request(i,provider,model,turn,usage=None,status="completed"):
        return {"exchange_id":f"sum-{i:03}","model":{"provider":provider,"model":model},
                "turn_id":turn,"usage":usage,"status":status,"started_at_ms":1700000000000+i*1000,
                "finished_at_ms":1700000000500+i*1000,"origin":"direct","message_count":2,"tool_count":0}
    def pricing(inp):
        return {"input_tokens":inp,"output_tokens":10,"cached_input_tokens":0}
    a=[request(i,"fixture","gpt-6-astra","only",pricing(1000)) for i in range(20)]
    b=[request(i,*("a","b/gpt-6-astra") if i%2 else ("a/b","gpt-6-astra"),
               "alias",pricing(1000),"error" if i==0 else "completed") for i in range(50)]
    # A later group ties the first on tokens, so original first-seen order matters.
    b+=[request(50,"fixture","gpt-5.6-sol","other",pricing(50490)),
        request(51,"","",None,None),request(52,"","",None,None)]
    b[51]["model"]=7
    del b[52]["model"]
    return {A:{"requests":a,"latest_turn_id":"only"},B:{"requests":b,"latest_turn_id":"alias"},C:None}


def replay_breakdown(exe,src,env):
    events=[]
    def open_(ctx,session,view):
        events.extend([context(ctx,session),rendered(view,ctx,session)])
    def close_(view,ctx):
        events.extend([close(view),{"type":"close_context","context":ctx}])
    def acts(view,pairs):
        events.extend(action(view,i,k,v) for i,(k,v) in enumerate(pairs,1))

    open_("single",A,"single")
    acts("single",[("query","nothing"),("query","")])
    close_("single","single")
    open_("mixed",B,"mix")
    acts("mix",[("page",1),("model","a/b/gpt-6-astra"),("page",1),
                ("model","stale"),("status","problems"),("query","nothing"),
                ("model","/"),("model",None),("status","all"),("query",""),
                ("period","latest"),("period","other"),("period","irrelevant"),("period","all")])
    close_("mix","mixed")
    open_("fresh",B,"fresh")
    close_("fresh","fresh")
    open_("null",C,"null")
    close_("null","null")
    raw,reads,frames=run_case(exe,src,env,breakdown_documents(),events)
    assert [(f["view"],f["sequence"],f["session_dir"]) for f in frames] == (
        [("single",i,A) for i in range(3)]+[("mix",i,B) for i in range(15)]+[("fresh",0,B),("null",0,C)])
    def summarize(frame):
        summaries=[n for n in walk(frame["root"]) if n.get("title")=="Итог выбранного периода"]
        assert len(summaries)==1
        return summaries[0]
    def table(summary):
        return [n["rows"] for n in summary["children"] if n["type"]=="table"]
    assert any(n.get("text")=="Журнал расхода недоступен для этого чата." for n in walk(frames[-1]["root"]))
    assert not any(n.get("title")=="Итог выбранного периода" for n in walk(frames[-1]["root"]))
    summary=[summarize(f) for f in frames[:-1]]
    assert summary[:3]==[summary[0]]*3 and not table(summary[0])
    default=summary[3]
    want=[
        ["a/b/gpt-6-astra","50","50 500","≈ $0.2625"],
        ["fixture/gpt-5.6-sol","1","50 500","≈ $0.20216"],
        ["/","2","0","—"]
    ]
    assert table(default)==[want],table(default)
    for i in (4,7,8,9,11,12,13,17,18):
        assert summary[i]==default,(i,table(summary[i]))
    for i in (5,6,10,14,15,16):
        assert not table(summary[i]),(i,table(summary[i]))
    assert summary[5]==summary[6]==summary[14]
    assert "Стоимость учтена для 25 из 50 запросов" in json.dumps(summary[5],ensure_ascii=False)
    assert "стоимость неизвестна" in json.dumps(summary[10],ensure_ascii=False)
    assert len(cards(frames[8]))==1 and not cards(frames[9])
    # Invalid model selection resets to the picker’s selected All option.
    pickers=[n for n in walk(frames[7]["root"]) if n.get("id")=="model"]
    assert len(pickers)==1
    assert any(o["value"] is None and o["selected"] for o in pickers[0]["options"])
    assert reads==[(path,session) for session in (A,B,B,C) for path in ("/sessions","/usage")],reads
    return raw,reads
