"""Actual Analysis release binary, exact raw stdout and GET receipts from loopback only."""
import copy
import http.server
import importlib.util
import json
from pathlib import Path
import subprocess as sp
import threading
from urllib.parse import parse_qs, urlsplit

PKG = Path("packages/analysis")
A, B = "/synthetic-analysis-a", "/synthetic-analysis-b"
KINDS = ("model","hook","tool","compaction")
NAMES = ("Model","Хуки","Инструмент","Context")


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

        def do_GET(self):
            try:
                url = urlsplit(self.path)
                query = parse_qs(url.query, keep_blank_values=True)
                assert url.path in ("/analysis","/sessions") and self.headers["Authorization"]=="Bearer fixture"
                session, = query.pop("session_dir")
                assert session in known
                if url.path=="/sessions":
                    assert not query
                    data=[{"session_dir":s,"preview":f"Synthetic {label}","message_count":2} for s,label in ((A,"A"),(B,"B"))]
                    turn = None
                else:
                    turn, = query.pop("turn_id",[None])
                    assert not query and (session,turn) in readings,(session,turn)
                    data=readings[session,turn]
                receipts.append((url.path,session,turn))
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


def docs(api_fixture):
    a = api_fixture()
    a["selected"]["task"]["cwd"] = "/synthetic"
    base = a["selected"]["steps"]
    rows = []
    for i in range(420):
        s = copy.deepcopy(base[i%4])
        s["sequence"] = i*2+1
        d = s["data"]
        if d["kind"]=="hook":
            d["trace"]["steps"]=[
                {"invocation_id":f"h{j}","module_id":"fixture",
                 "outcome":{"status":"failed" if i%8==1 and j==4 else "accepted","message":"synthetic"}}
                for j in range(5)
            ]
        elif d["kind"]=="tool":
            d["call"]["name"]="ПРОВЕРКА 🦀"+(" «Край»" if i==418 else "")
            d["result"]["ok"] = i%8==2
            d["result"]["output"] = 'Ответ "А"\r\n🦀\n'
            if i%8==6:
                d["result"]["error"]="synthetic failure"
        elif d["kind"]=="model" and i%8==0:
            d["response"]=None
        elif d["kind"]=="compaction":
            d["report"]["changed"]=i%8==3
        if i==416:
            s["data"]={"kind":"future-kind"}
        elif i==417:
            s["data"]={"kind":False}
        rows.append(s)
    a["selected"]["steps"]=rows
    previous=api_fixture()
    previous["selected"]["task"]["cwd"]="/synthetic"
    previous["selected"]["turn_id"]="turn-9"
    previous["selected"]["steps"]=base[:1]  # all other fixed kind chips are absent
    empty=api_fixture()
    empty["selected"]["task"]["cwd"]="/synthetic"
    empty["selected"]["steps"]=[]
    return {(A,None):a,(A,"turn-9"):previous,(B,None):empty}


def pane(frame):
    return frame["root"]["children"][0]["children"][1]["children"]


def rows(pane_):
    return [n for n in pane_[3:] if n.get("type")=="stack"]


def ids(pane_):
    return [n["children"][0]["children"][0]["value"] for n in rows(pane_)]


def chips(pane_):
    return [(b["value"],b["label"],b.get("selected",False)) for b in pane_[1]["children"]]


def replay(exe, src, env):
    spec=importlib.util.spec_from_file_location("source_wire_fixture",src/"tests/wire.py")
    wire=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(wire)
    data=docs(wire.analysis)
    main=rendered("page","left",A)
    query=" \tпРоВеРкА 🦀  "
    query_tail=" кРаЙ» "
    raw,receipts,frames=run_case(exe,src,env,data,[
        context("left",A), main,
        action("page",1,"query"," \t "), action("page",2,"query",query),
        action("page",3,"kind","tool"),action("page",4,"problems",True),
        action("page",5,"query",query_tail),action("page",6,"problems",False),
        action("page",7,"step",{"id":837}),action("page",8,"step",837),
        action("page",9,"turn","turn-9"),
        context("sibling",A),rendered("sibling-page","sibling",A),
        close("page"),close("sibling-page"),
        {"type":"close_context","context":"left"},{"type":"close_context","context":"sibling"},
        context("other",B),rendered("other-page","other",B),close("other-page"),
        rendered("preview","other",B,"preview"),close("preview"),
        {"type":"close_context","context":"other"},
    ])
    assert [(f["view"],f["session_dir"],f["sequence"]) for f in frames] == (
        [("page",A,i) for i in range(10)] +
        [("sibling-page",A,0),("other-page",B,0),("preview",B,0)]
    ),[(f["view"],f.get("session_dir"),f["sequence"]) for f in frames]
    base=pane(frames[0])
    assert ids(base)==list(range(1,800,2))
    assert base[0]["text"]=="Шаги · 420"
    assert base[-1]["text"]=="Показаны первые 400 из 420 — уточните фильтр."
    assert chips(base)==[
       ("all","Все · 420",True),("model","Model · 104",False),("tool","Инструмент · 105",False),
       ("compaction","Context · 105",False),("hook","Хуки · 104",False),
       (True,"Ошибки и без результата · 156",False)]
    assert ids(pane(frames[1]))==ids(base) and pane(frames[1])[2]["value"]==" \t "
    tools=list(range(5,840,8))
    assert ids(pane(frames[2]))==ids(pane(frames[3]))==tools
    assert pane(frames[2])[2]["value"]==query
    assert ids(pane(frames[4]))==list(range(13,840,16))
    assert pane(frames[4])[0]["text"]=="Шаги · 52 из 420"
    assert not ids(pane(frames[5])) and pane(frames[5])[3]["text"]=="Подходящих шагов нет."
    assert ids(pane(frames[6]))==ids(pane(frames[7]))==ids(pane(frames[8]))==[837]
    assert "837:output" in {n.get("id") for n in wire.walk(frames[7]["root"])}
    assert "837:output" not in {n.get("id") for n in wire.walk(frames[8]["root"])}
    for frame in frames[9:11]:
        assert chips(pane(frame))[2]==("tool","Инструмент · 0",True)
        assert not ids(pane(frame))
    assert pane(frames[11])[3]["text"]=="В ходе нет записанных шагов."
    assert "Синтетический ход" in json.dumps(frames[12],ensure_ascii=False)
    assert receipts==[("/analysis",A,None),("/sessions",A,None),("/analysis",A,"turn-9"),
                      ("/analysis",B,None),("/sessions",B,None)],receipts
    return (raw,),(receipts,)
