"""Raw Git stdio via a fail-closed, GET-only synthetic workspace."""
import http.server
import json
from pathlib import Path
import subprocess as sp
import threading
from urllib.parse import parse_qs, urlsplit

PKG = Path("packages/git")
SESSION = "/synthetic-history"
CONTEXT = "history-fixture"
GET = {"/".join(("", "workspace", endpoint)) for endpoint in ("changes", "branches", "log", "commit")}
FUTURE = 4_102_444_800


def hash_of(i):
    return f"{i:07x}" + f"{i:033x}"


def row(i, graph):
    subject = f"{'graph' if graph else 'branch'} entry {i}"
    if graph and i in (0, 2):
        subject = "Cross-Field" if i == 0 else "cross-field"
    parents = [hash_of(i + 1)] if i < 101 else []
    if i == 0:
        parents.append(hash_of(2))
    refs = [{"name":"release/β","kind":"tag"},{"name":"main","kind":"branch"},
            {"name":"release/α","kind":"tag"},None,{"name":"origin/main","kind":"remote"}] if i == 0 else []
    return {"hash":hash_of(i),"short":hash_of(i)[:7],"summary":subject,"author":"Tester",
            "email":"fixture@example.invalid","time":FUTURE,"parents":parents,"refs":refs}


def expected_rows(skip, graph):
    entries = [row(i, graph) for i in range(skip, min(skip + 100, 102))]
    if skip == 0:
        entries[4]["summary"] = ""
        entries[5] = None
        entries[6]["time"] = "not-a-number"
        entries[7]["parents"] = [None, hash_of(8), False]
    return entries


def walk(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk(child)


def render(view, surface, argument=None):
    return {"type":"render","view":view,"surface":surface,"context":CONTEXT,"session_dir":SESSION,
            "argument":argument}


def action(view, seq, name, value=None):
    return {"type":"action","view":view,"sequence":seq,"action":name,"value":value}


def close(view):
    return {"type":"close","view":view}


def replay_case(exe, src, env, case, inputs):
    reads, errors, writes = [], [], []
    failed_at_page = False

    class API(http.server.BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            writes.append(self.command)
            self.send_error(405)

        def do_GET(self):
            try:
                self.respond()
            except Exception as exc:
                errors.append(exc)
                self.send_error(500)

        def respond(self):
            nonlocal failed_at_page
            url = urlsplit(self.path)
            route = url.path.rsplit("/",1)[-1]
            query = parse_qs(url.query,keep_blank_values=True)
            assert url.path in GET and self.headers["Authorization"] == "Bearer fixture"
            assert query.pop("session_dir") == [SESSION]
            code = 200
            if route == "changes":
                assert not query
                head = {"short":hash_of(0)[:7],"summary":"Latest"} if case == "head" else None
                data = {"repository":True,"refs_revision":"fixture","branch":"main","head":head,
                        "upstream":"origin/main","ahead":2,"behind":0,"entries":[]}
                reads.append((route,))
            elif route == "branches":
                assert not query
                data = {"branches":[{"name":"main"}]}
                reads.append((route,))
            elif route == "log":
                assert set(query) == {"all","limit","skip"} and query["all"] in (["true"],["false"])
                graph = query["all"] == ["true"]
                skip, = query["skip"]
                limit, = query["limit"]
                skip, limit = int(skip), int(limit)
                reads.append((route,graph,skip,limit))
                if case == "head":
                    assert not graph and skip == 0 and limit in (1,100)
                    if limit == 1:
                        data = {"entries":[]}
                    else:
                        data = {"entries":[dict(row(0,False),parents=[None])],"has_more":False}
                else:
                    assert skip in (0,100) and limit == 100
                    if not graph and skip == 100 and not failed_at_page:
                        failed_at_page, code, data = True, 500, {"error":"synthetic log unavailable"}
                    else:
                        data = {"has_more":skip==0,"entries":expected_rows(skip,graph)}
            else:
                assert case == "loaded" and set(query) == {"hash"}
                hash_, = query["hash"]
                assert hash_ in (hash_of(0),hash_of(2))
                reads.append((route, hash_))
                data = {"hash":hash_,"short":hash_[:7],"summary":"Synthetic detail",
                        "body":"Commit detail stays raw","author":"Tester","email":"fixture@example.invalid",
                        "time":FUTURE,"parents":[hash_of(1)],"files":[]}
            raw = json.dumps(data,ensure_ascii=False).encode()
            self.send_response(code)
            self.send_header("Content-Type","application/json")
            self.send_header("Content-Length",str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

    with http.server.ThreadingHTTPServer(("127.0.0.1",0), API) as server:
        thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval":0.025}, daemon=True)
        thread.start()
        try:
            features=json.loads((src/PKG/"extension.json").read_text())["required_features"]
            hello = {"type":"hello","protocol":4,"features":features,"workspace":"/synthetic",
                     "server":{"origin":f"http://127.0.0.1:{server.server_port}","token":"fixture"}}
            data = [hello,{"type":"context","context":CONTEXT,"session_dir":SESSION},*inputs,
                    {"type":"close_context","context":CONTEXT}]
            out = sp.run([exe],cwd=src/PKG,env=env,input=b"".join(
                json.dumps(msg,ensure_ascii=False).encode()+b"\n" for msg in data),
                capture_output=True,check=True,timeout=20)
        finally:
            server.shutdown()
            thread.join()
    assert not out.stderr and not errors and not writes,(out.stderr,errors,writes)
    frames = [json.loads(line) for line in out.stdout.splitlines()]
    assert frames and all(f["type"]=="view" and f["session_dir"]==SESSION for f in frames)
    return out.stdout, reads, frames


def replay(exe,src,env):
    panel, graph = render("panel","panel"), render("graph","document","Граф коммитов")
    loaded,reads,frames = replay_case(exe,src,env,"loaded", [
        panel,action("panel",1,"tab",1),panel,action("panel",2,"more"),
        action("panel",3,"more"),panel,close("panel"),
        graph,action("graph",1,"graph_more"),graph,
        action("graph",2,"graph_search","Cross-Field Tester fixture@"),
        action("graph",3,"graph_next"),action("graph",4,"graph_previous"),
        action("graph",5,"graph_case"),action("graph",6,"graph_previous"),close("graph")])
    assert [(f["view"],f["sequence"]) for f in frames] == list(zip(
        ["panel"]*6+["graph"]*8, [0,1,1,2,3,3,0,1,1,2,3,4,5,6], strict=True)), [(f["view"],f["sequence"]) for f in frames]
    for i,(frame,count) in enumerate(zip(frames,[0,100,100,100,102,102,100,102,102,102,102,102,102,102],strict=True)):
        tree = list(walk(frame["root"]))
        nodes = [n for n in tree if n.get("type")==("list" if i<6 else "lanes")]
        assert sum(len(n["rows"]) for n in nodes)==count,(i,count)
        if not count:
            continue
        rows,=[n["rows"] for n in nodes]
        data=expected_rows(0,i>=6)
        if count>100:
            data+=expected_rows(100,i>=6)
        assert [r["label"] for r in rows]==[(d or {}).get("summary") or "(без описания)" for d in data]
        assert [r["id"] for r in rows]==[(d or {}).get("hash","") for d in data]
        if i<6:
            assert rows[0]["chips"]==["release/β","release/α"] and rows[0]["mark"]==rows[1]["mark"]=="arrow-up"
            assert "mark" not in rows[2] and rows[5]["meta"] == ["","",""] and rows[6]["meta"][1]==""
        else:
            assert [(r["label"],r["tone"]) for r in rows[0]["refs"]]==[
                ("release/β","warning"),("main","accent"),("release/α","warning"),("","muted"),("origin/main","muted")]
            assert len(rows[0]["down"])==2 and not rows[5]["refs"]
            assert rows[6]["cells"][2]==rows[5]["cells"][2]  # malformed/missing date -> epoch
            selected = [r["id"] for r in rows if r["selected"]]
            want = [[],[],[],[hash_of(0)],[hash_of(2)],[hash_of(0)],[hash_of(0)],[hash_of(0)]][i-6]
            assert selected==want,(i,selected,want)
            if want:
                body=json.dumps(frame,ensure_ascii=False)
                assert "Commit detail stays raw" in body
                assert ('"1/1"' if i>=12 else ('"2/2"' if i==10 else '"1/2"')) in body
    assert "synthetic log unavailable" in json.dumps(frames[3],ensure_ascii=False)
    expected = [("changes",),("branches",),("log",False,0,100),("log",False,100,100),
                ("log",False,100,100),("log",True,0,100),("log",True,100,100),
                ("commit",hash_of(0)),("commit",hash_of(2))]
    assert reads==expected,reads

    head, guard_reads, frames = replay_case(exe,src,env,"head",[
        panel,action("panel",1,"tab",1),panel,panel,close("panel")])
    assert [(f["view"],f["sequence"]) for f in frames]==[("panel",0),("panel",1),("panel",1),("panel",1)]
    undo = [any(n.get("action")=="uncommit" for n in walk(f["root"])) for f in frames]
    assert undo==[False,False,True,True],undo
    assert guard_reads==[("changes",),("branches",),("log",False,0,1),("log",False,0,1),("log",False,0,100)],guard_reads
    return (loaded,head), (reads,guard_reads)
