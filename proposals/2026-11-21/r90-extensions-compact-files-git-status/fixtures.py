"""GET-only real Files wire: prior ordinary flow plus explicit window/session scopes."""
import http.server
import importlib.util
import json
from pathlib import Path
import subprocess as sp
import threading
from urllib.parse import urlsplit, parse_qs

PACKAGE = Path("packages/files")
SESSION = "/files-fixture"
CONTEXT = "status-fixture"


def ordinary(exe, src, env):
    features = json.loads((src / PACKAGE / "extension.json").read_text())["required_features"]
    spec = importlib.util.spec_from_file_location("wire_fixture", src / "tests/wire.py")
    wire = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(wire)
    reads = []
    refreshes = 0
    fold, descendant = "poly/папка/leaf", "poly/папка/leaf/deeper"
    deep_file, side_file = descendant + "/shown.rs", "side/side.rs"
    tree = {"":[("poly",True),("side",True)], "poly":[("папка",True)],
            "poly/папка":[("leaf",True)], fold:[("deeper",True),("plain.rs",False),("new.rs",False)],
            descendant:[("shown.rs",False)], "side":[("side.rs",False)]}

    class Api(http.server.BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            nonlocal refreshes
            url = urlsplit(self.path)
            query = parse_qs(url.query, keep_blank_values=True)
            assert query["session_dir"] == [SESSION] and self.headers["Authorization"] == "Bearer fixture"
            if url.path == "/sessions/current":
                reads.append(("current", None))
                data = [{"session_dir":SESSION,"workspace_path":"/panel-fixture"}]
            else:
                route = url.path.split("/")
                assert route[:2] == ["","workspace"] and len(route) == 3
                if route[-1] == "changes":
                    reads.append(("changes", None))
                    states = [[
                        (deep_file, "deleted"), (fold + "/plain.rs", "modified"),
                        (fold + "/new.rs", "untracked"), (side_file, "ignored"),
                        ("../outside.rs", "conflict"),
                    ], [
                        (deep_file, "untracked"), (fold + "/plain.rs", "ignored"),
                        (fold + "/new.rs", "untracked"), (side_file, "deleted"),
                    ]]
                    data = {"repository":True,"entries":[{"path":path,"status":status}
                                                         for path,status in states[refreshes]]}
                    refreshes += 1
                else:
                    assert route[-1] == "list"
                    folder, = query["path"]
                    reads.append(("list", folder))
                    entries = [{"name":name,"path":f"{folder}/{name}".lstrip("/"),
                                "kind":"directory" if is_dir else "file"} for name,is_dir in tree[folder]]
                    data = {"entries":entries,"truncated":False}
            data = json.dumps(data).encode()
            self.send_response(200)
            self.send_header("Content-Type","application/json")
            self.send_header("Content-Length",str(len(data)))
            self.end_headers()
            self.wfile.write(data)

    with http.server.ThreadingHTTPServer(("127.0.0.1",0), Api) as server:
        thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval":0.025}, daemon=True)
        thread.start()
        try:
            inputs = [
                {"type":"hello","protocol":4,"features":features,"workspace":"/panel-fixture",
                 "server":{"origin":f"http://127.0.0.1:{server.server_port}","token":"fixture"}},
                {"type":"render","context":CONTEXT,"session_dir":SESSION,"view":"panel","surface":"panel"},
            ]
            for sequence,(path,event) in enumerate([
                (fold,"expand"),(descendant,"expand"),("side","select"),
            ],1):
                inputs.append({"type":"action","view":"panel","action":"files","sequence":sequence,
                               "value":{"id":path,"event":event}})
            inputs.append({"type":"event","context":CONTEXT,"event":"run_settled","session_dir":SESSION})
            inputs.append({"type":"close","view":"panel"})
            data = b"".join(json.dumps(msg).encode() + b"\n" for msg in inputs)
            p = sp.run([exe], input=data, cwd=src / PACKAGE, env=env, capture_output=True, check=True, timeout=15)
        finally:
            server.shutdown()
            thread.join()
    assert not p.stderr, p.stderr
    frames = [json.loads(line) for line in p.stdout.splitlines()]
    assert [row["sequence"] for row in frames] == [0, 1, 2, 3, 3]
    rows = [{r["id"]:r for r in next(n for n in wire.walk(v["root"]) if n.get("id") == "files")["rows"]} for v in frames]
    assert [fold in m for m in rows] == [True] * 5
    assert [deep_file in m for m in rows] == [False, False, True, True, True]
    assert [side_file in m for m in rows] == [False, False, False, True, True]
    def tone(frame, path):
        return rows[frame][path]["tone"]

    assert [tone(i, ".") for i in range(5)] == ["danger","danger","danger","danger","danger"]
    assert [tone(i, fold) for i in range(5)] == ["danger","danger","danger","danger","success"]
    assert tone(3, fold + "/plain.rs") == "warning" and tone(4, fold + "/plain.rs") == "muted"
    assert tone(3, deep_file) == "danger" and tone(4, deep_file) == "success"
    assert tone(3, side_file) == "muted" and tone(4, side_file) == "danger"
    def has_action(frame, path, action):
        return any(item.get("action") == action for item in rows[frame][path]["menu"])

    assert has_action(3, deep_file, "restore") and not has_action(4, deep_file, "restore")
    assert has_action(3, side_file, "diff") and not has_action(3, side_file, "restore")
    assert has_action(4, side_file, "restore")
    assert reads == [("current",None),("changes",None),("list",""),("list","poly"),("list","poly/папка"),
                     ("list",fold),("list","side"),("list",descendant),("changes",None),("list",""),
                     ("list","poly"),("list","poly/папка"),("list",fold),("list",descendant),("list","side")], reads
    return p.stdout, reads



def scoped(exe, src, env):
    A, B = "/status-a", "/status-b"
    LEFT, RIGHT, SIBLING, MOVED = "left", "right", "sibling", "moved"
    known = ("modified", "renamed", "deleted", "added", "untracked", "conflict")
    controls = ("old", "empty", "bad", "missing", "same", "absent")
    leafnames = (*known, *controls)
    folder = "dir"
    path = lambda name: f"{folder}/{name}.rs"
    records = [
        {"path":path(name),"status":name} for name in known
    ] + [
        {"path":path("old"),"status":"deleted"},
        {"path":path("old"),"status":"desconocido"},
        {"path":path("empty"),"status":""},
        {"path":path("bad"),"status":{"wrong":"type"}},
        {"path":path("missing")},
        {"path":path("same"),"status":"unknown"},
        {"path":path("same"),"status":"deleted"},
        {"path":"../skipped.rs","status":"conflict"},
        {"path":"","status":"conflict"},
    ]
    new_records = [{"path":path("old"),"status":"renamed"},{"path":path("added"),"status":"added"}]
    names = {"":[("dir","directory")], "dir":[(name+".rs","file") for name in leafnames]}
    reads,errors=[],[]
    refreshes={A:0,B:0}

    class Api(http.server.BaseHTTPRequestHandler):
        def log_message(self,*args):
            pass
        def do_GET(self):
            try:
                self.get()
            except Exception as error:
                errors.append(error)
                self.send_error(500)
        def do_POST(self):
            errors.append(AssertionError("fixture only allows GET"))
            self.send_error(405)
        def get(self):
            url=urlsplit(self.path)
            q=parse_qs(url.query,keep_blank_values=True)
            session,=q["session_dir"]
            assert session in (A,B) and self.headers["Authorization"]=="Bearer fixture"
            if url.path=="/sessions/current":
                reads.append((session,"current",None))
                data=[{"session_dir":session,"workspace_path":"/repo-a" if session==A else "/repo-b"}]
            else:
                route=url.path.split("/")
                assert route[:2]==["","workspace"] and len(route)==3
                if route[-1]=="changes":
                    name="changes"
                    reads.append((session,name,None))
                    at=refreshes[session]
                    refreshes[session]+=1
                    if session==A:
                        data={"repository":True,"entries":[records,new_records][at]}
                    else:
                        assert at==0
                        # Status still colors the row; repository=false keeps
                        # both destructive and read-only Git actions hidden.
                        data={"repository":False,"entries":[{"path":path("modified"),"status":"deleted"}]}
                else:
                    assert route[-1]=="list"
                    label,=q["path"]
                    reads.append((session,"list",label))
                    data={"entries":[{"name":n,"kind":kind,"path":f"{label}/{n}".lstrip("/")}
                                     for n,kind in names[label]],"truncated":False}
            payload=json.dumps(data,ensure_ascii=False).encode()
            self.send_response(200)
            self.send_header("Content-Type","application/json")
            self.send_header("Content-Length",str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

    def context(context,session):
        return {"type":"context","context":context,"session_dir":session}
    def render(context,session,view):
        return {"type":"render","context":context,"session_dir":session,"view":view,"surface":"panel"}
    def expand(view,sequence):
        return {"type":"action","view":view,"action":"files","sequence":sequence,"value":{"id":"dir","event":"expand"}}

    with http.server.ThreadingHTTPServer(("127.0.0.1",0),Api) as server:
        thread=threading.Thread(target=server.serve_forever,kwargs={"poll_interval":0.025},daemon=True)
        thread.start()
        try:
            features=json.loads((src/PACKAGE/"extension.json").read_text())["required_features"]
            inp=[
                {"type":"hello","protocol":4,"features":features,"workspace":"/synthetic",
                 "server":{"origin":f"http://127.0.0.1:{server.server_port}","token":"fixture"}},
                context(LEFT,A),render(LEFT,A,"pane-a"),expand("pane-a",1),
                context(RIGHT,B),render(RIGHT,B,"pane-b"),expand("pane-b",7),
                context(SIBLING,A),render(SIBLING,A,"pane-sibling"),
                context(MOVED,A),{"type":"rehost","view":"pane-a","context":MOVED},
                {"type":"event","context":MOVED,"event":"run_settled","session_dir":A},
            ]
            inp+= [{"type":"close","view":v} for v in ("pane-a","pane-sibling","pane-b")]
            inp+= [{"type":"close_context","context":c} for c in (LEFT,RIGHT,SIBLING,MOVED)]
            raw=b"".join(json.dumps(msg,ensure_ascii=False).encode()+b"\n" for msg in inp)
            proc=sp.run([exe],input=raw,cwd=src/PACKAGE,env=env,capture_output=True,check=True,timeout=12)
        finally:
            server.shutdown()
            thread.join()
    assert not errors and not proc.stderr,(errors,proc.stderr)
    frames=[json.loads(line) for line in proc.stdout.splitlines()]
    names=[
        ("pane-a",A,0),("pane-a",A,1),("pane-b",B,0),("pane-b",B,7),
        ("pane-sibling",A,0),("pane-a",A,1),("pane-a",A,1),("pane-sibling",A,0),
    ]
    actual=[(f["view"],f["session_dir"],f["sequence"]) for f in frames]
    assert actual==names,actual
    assert all(f["type"]=="view" for f in frames)

    def tree_rows(node):
        if isinstance(node,dict):
            if node.get("id")=="files":
                return node["rows"]
            for value in node.values():
                result=tree_rows(value)
                if result is not None:
                    return result
        elif isinstance(node,list):
            for item in node:
                result=tree_rows(item)
                if result is not None:
                    return result
        return None
    per_frame=[{row["id"]:row for row in tree_rows(frame["root"])} for frame in frames]
    assert list(per_frame[0])==[".","dir"] and list(per_frame[2])==[".","dir"]
    def flags(index, row_path):
        row=per_frame[index][row_path]
        menu={m.get("action"):m for m in row["menu"]}
        if "restore" in menu:
            confirm=menu["restore"]["confirm"]
            assert menu["restore"]["value"]==row_path and confirm["danger"] is True
            assert confirm["title"]==f"Отменить изменения в `{row_path.rsplit('/',1)[-1]}`?"
            assert confirm["ok"]=="Discard Changes" and confirm["message"]
        return row["tone"],"diff" in menu,"restore" in menu
    expected={
        "modified":("warning",True,True),"renamed":("warning",True,True),"deleted":("danger",True,True),
        "added":("success",True,False),"untracked":("success",True,False),"conflict":("warning",True,False),
        "old":("muted",True,False),"empty":("muted",True,False),"bad":("muted",True,False),
        "missing":("muted",True,False),"same":("danger",True,True),"absent":("muted",False,False),
    }
    for i in (1,4,5):
        assert {name:flags(i,path(name)) for name in leafnames}==expected
        assert flags(i,"dir")==("warning",False,False)
    for name in leafnames:
        assert flags(3,path(name))==(("danger" if name=="modified" else "muted"),False,False)
    for i in (6,7):
        for name in leafnames:
            expected_after={"old":("warning",True,True),"added":("success",True,False)}
            assert flags(i,path(name))==expected_after.get(name,("muted",False,False))
        assert flags(i,"dir")==("warning",False,False)
    prefix=lambda session:[(session,"current",None),(session,"changes",None),(session,"list",""),(session,"list","dir")]
    assert reads==prefix(A)+prefix(B)+[(A,"changes",None),(A,"list",""),(A,"list","dir")],reads
    return proc.stdout,reads
