"""Actual Git process against a synthetic GET-only local workspace catalogue."""
import http.server
import json
from pathlib import Path
import subprocess as sp
import threading
from urllib.parse import parse_qs, urlsplit

PKG = Path("packages/git")
A, B, C = "/branch-a", "/branch-b", "/branch-none"
GET = {"/".join(("", "workspace", n)) for n in ("changes","branches")}


def branch_rows():
    rows=[
        {"name":f"feature/fixture-{i:04}","upstream":f"origin/feature/fixture-{i:04}",
         "last_commit_time":1803978000,"last_commit_summary":f"Summary {i:04}".ljust(96,"x"),
         "author":"Synthetic Author"} for i in range(66)
    ]
    rows[0]["name"]="main"
    rows[8]["name"]="ветка/λ"
    rows[10]["name"]="main"
    rows[17]={"name":False}
    rows[58]={"name":""}
    rows[59]=None
    rows[60]={"upstream":"ignored-without-name"}
    rows[61]={"name":"topic/end"}
    return rows


def names(rows):
    return [r["name"] if isinstance(r,dict) and isinstance(r.get("name"),str) else "" for r in rows]


def status(session, generation):
    return {"repository":session != C, "branch":"main" if session==A else None, "head":None,
            "refs_revision":"same-refs" if generation<2 else "new-refs",
            "upstream":None,"ahead":0,"behind":0,"entries":[]}


def catalogue(session, generation):
    if session==B:
        return [{"name":"—"},{"name":None},{"name":"別の枝"}]
    first=branch_rows()
    if generation==0:
        return first
    if generation==1:
        return [{"name":"after-refresh"},*first]
    return [{"name":"new-refs"},*first[1:]]


def walk(value):
    if isinstance(value,dict):
        yield value
        for child in value.values():
            yield from walk(child)
    elif isinstance(value,list):
        for child in value:
            yield from walk(child)


def replay(exe,src,env):
    reads,errs=[],[]
    polls={A:0,B:0,C:0}

    class API(http.server.BaseHTTPRequestHandler):
        def log_message(self,*args):
            pass
        def do_POST(self):
            errs.append("unexpected write")
            self.send_error(405)
        def do_GET(self):
            try:
                self.get()
            except Exception as exc:
                errs.append(exc)
                self.send_error(500)
        def get(self):
            url=urlsplit(self.path)
            assert url.path in GET and self.headers["Authorization"]=="Bearer fixture"
            session,=parse_qs(url.query,keep_blank_values=True)["session_dir"]
            assert session in polls
            endpoint=url.path.rsplit("/",1)[-1]
            reads.append((session,endpoint))
            if endpoint=="changes":
                data=status(session,polls[session])
                polls[session]+=1
            else:
                assert session!=C and polls[session]>=1
                data={"current":"wrong-header-not-the-current-sentinel",
                      "branches":catalogue(session,polls[session]-1),"truncated":False}
            raw=json.dumps(data,ensure_ascii=False).encode()
            self.send_response(200)
            self.send_header("Content-Type","application/json")
            self.send_header("Content-Length",str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

    def context(scope,session):
        return {"type":"context","context":scope,"session_dir":session}
    def render(view,surface,scope,session):
        return {"type":"render","view":view,"surface":surface,"context":scope,"session_dir":session}
    def act(view,seq,action,value):
        return {"type":"action","view":view,"sequence":seq,"action":action,"value":value}

    with http.server.ThreadingHTTPServer(("127.0.0.1",0),API) as server:
        thread=threading.Thread(target=server.serve_forever,kwargs={"poll_interval":0.025},daemon=True)
        thread.start()
        try:
            features=json.loads((src/PKG/"extension.json").read_text())["required_features"]
            inp=[
                {"type":"hello","protocol":4,"features":features,"workspace":"/synthetic",
                 "server":{"origin":f"http://127.0.0.1:{server.server_port}","token":"fixture"}},
                context("a-left",A),render("a-panel","panel","a-left",A),
                context("a-right",A),render("a-popup","popup","a-right",A),
                act("a-panel",1,"message","Draft only · λ"),
                context("b",B),render("b-panel","panel","b",B),render("b-popup","popup","b",B),
                context("none",C),render("outside","panel","none",C),
                context("a-moved",A),{"type":"rehost","view":"a-popup","context":"a-moved"},
                act("a-panel",2,"refresh",None),
                {"type":"event","event":"run_settled","session_dir":A,"context":"a-moved"},
            ]
            inp.extend({"type":"close","view":v} for v in ("a-panel","a-popup","b-panel","b-popup","outside"))
            inp.extend({"type":"close_context","context":c} for c in ("a-left","a-right","a-moved","b","none"))
            out=sp.run([exe],cwd=src/PKG,env=env,input=b"".join(json.dumps(m,ensure_ascii=False).encode()+b"\n" for m in inp),
                       capture_output=True,check=True,timeout=15)
        finally:
            server.shutdown()
            thread.join()
    assert not errs and not out.stderr,(errs,out.stderr)
    frames=[json.loads(line) for line in out.stdout.splitlines()]
    want=[
        ("a-panel",A,0,0),("a-popup",A,0,0),("a-panel",A,1,0),("a-popup",A,0,0),
        ("b-panel",B,0,0),("b-popup",B,0,0),("outside",C,0,0),("a-popup",A,0,0),
        ("a-panel",A,2,1),("a-popup",A,0,1),("a-panel",A,2,2),("a-popup",A,0,2),
    ]
    assert [(f["view"],f["session_dir"],f["sequence"]) for f in frames]==[p[:3] for p in want]
    for frame,(view,session,seq,gen) in zip(frames,want,strict=True):
        assert frame["type"]=="view",frame
        tree=list(walk(frame["root"]))
        if session==C:
            assert "Нет git-репозитория" in json.dumps(frame,ensure_ascii=False)
            assert not any(o.get("action") in ("checkout","create_branch") for o in tree)
            continue
        current="main" if session==A else "—"
        catalogue_names=names(catalogue(session,gen))
        if view.endswith("panel"):
            menu,=[o for o in tree if o.get("type")=="menu"
                   and any(i.get("action")=="create_branch" for i in o.get("items",[]))]
            assert menu["label"]==current
            choices=[i for i in menu["items"] if i.get("action")=="checkout"]
            catalogue_names=catalogue_names[:60]
            if session==A and seq:
                field,=[o for o in tree if o.get("type")=="input" and o.get("id")=="message"]
                assert field["value"]=="Draft only · λ"
        else:
            picker,=[o for o in tree if o.get("type")=="picker" and o.get("id")=="branches"]
            assert picker["action"]=="checkout"
            choices=picker["options"]
        assert [i["value"] for i in choices]==catalogue_names
        assert [i["label"] for i in choices]==catalogue_names
        assert [i["selected"] for i in choices]==[name==current for name in catalogue_names]
    assert reads==[(A,"changes"),(A,"branches"),(B,"changes"),(B,"branches"),(C,"changes"),
                   (A,"changes"),(A,"branches"),(A,"changes"),(A,"branches")],reads
    return out.stdout,reads
