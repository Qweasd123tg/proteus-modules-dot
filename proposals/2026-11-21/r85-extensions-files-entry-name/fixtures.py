"""Raw stdio replay of the real Files process against synthetic GET-only workspace listings."""
import http.server
import json
import subprocess as sp
import threading
from urllib.parse import parse_qs, urlsplit

SESSION = "/files-fixture"
CWD = "/panel-fixture"
CONTEXT = "r85-files"
FOLD = "poly/папка/leaf"
DESCENDANT = FOLD + "/deeper"
DEEP_FILE = DESCENDANT + "/shown.rs"
SIDE_FILE = "side/side.rs"
WIDE_COUNT = 1000


def entry(path, kind="file", label=None):
    return {"name": path.rsplit("/", 1)[-1] if label is None else label, "path": path, "kind": kind}


def wide_entries():
    common = [entry(f"wide/fixture_{i:04}_".ljust(len("wide/") + 25, "x") + ".rs")
              for i in range(WIDE_COUNT - 7)]
    return common + [
        entry("wide/папка.rs"),
        entry("wide/alias.rs", label="Ссылка.rs"),
        entry("wide/literal" + chr(92) + "name.rs"),
        entry("././wide/normalized.rs", "symlink"),
        entry("wide/type", "unknown"),
        entry("wide/blank.rs", label=""),
        entry("wide/ignored-alias", label=".git"),
    ]


def spec(scenario):
    if scenario == "fold":
        tree = {
            "": [entry("poly", "directory", "Poly alias"), entry("side", "directory")],
            "poly": [entry("poly/папка", "directory")],
            "poly/папка": [entry(FOLD, "directory", "Leaf alias")],
            FOLD: [entry(DESCENDANT, "directory"), entry(FOLD + "/plain.rs")],
            DESCENDANT: [entry(DEEP_FILE)],
            "side": [entry(SIDE_FILE, label="Side alias.rs")],
        }
        actions = [(FOLD, "expand"), (DESCENDANT, "expand"), ("side", "select"),
                   (FOLD, "collapse"), (FOLD, "expand"), ("side", "collapse"),
                   (".", "collapse"), (".", "expand")]
    elif scenario == "wide":
        tree = {"": [entry("wide", "directory")], "wide": wide_entries()}
        actions = [("wide", "expand")]
    elif scenario == "empty":
        tree, actions = {"": []}, []
    else:
        tree, actions = {"": None}, []
    return tree, actions


def walk(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk(child)


def verify(scenario, raw, reads):
    prefix = [("current", None), ("changes", None), ("list", "")]
    frames = [json.loads(line) for line in raw.splitlines()]
    assert all(frame["type"] == "view" and frame["view"] == "panel" for frame in frames)
    roots = [frame["root"] for frame in frames]
    rows = [next((node["rows"] for node in walk(r) if node.get("id") == "files"), None)
            for r in roots]
    idx = [{r["id"]: r for r in items} if items is not None else {} for items in rows]
    if scenario == "fold":
        assert [f["sequence"] for f in frames] == list(range(9))
        assert reads == prefix + [
            ("list", "poly"), ("list", "poly/папка"), ("list", FOLD),
            ("list", "side"), ("list", DESCENDANT),
        ], reads
        assert [FOLD in m for m in idx] == [True]*7 + [False, True]
        assert [DEEP_FILE in m for m in idx] == [False,False,True,True,False,True,True,False,True]
        assert [SIDE_FILE in m for m in idx] == [False,False,False,True,True,True,False,False,False]
        assert list(idx[7]) == ["."]
        assert [m[FOLD]["expanded"] for m in idx if FOLD in m] == [False,True,True,True,False,True,True,True]
        assert all(m[FOLD]["label"] == "Poly alias/папка/Leaf alias" for m in idx if FOLD in m)
        assert all(m[SIDE_FILE]["label"] == "Side alias.rs" for m in idx if SIDE_FILE in m)
    elif scenario == "wide":
        assert [f["sequence"] for f in frames] == [0,1]
        assert reads == prefix + [("list", "wide")], reads
        assert list(idx[0]) == [".", "wide"]
        expected = [x["path"].removeprefix("././") for x in wide_entries()[:-1]]
        assert list(idx[1]) == [".", "wide", *expected] and len(rows[1]) == 1001
        assert idx[1]["wide"]["expanded"] is True
        assert idx[1]["wide/папка.rs"]["label"] == "папка.rs"
        assert idx[1]["wide/alias.rs"]["label"] == "Ссылка.rs"
        assert idx[1]["wide/literal" + chr(92) + "name.rs"]["label"] == "literal" + chr(92) + "name.rs"
        assert idx[1]["wide/normalized.rs"]["label"] == "normalized.rs"
        assert idx[1]["wide/normalized.rs"]["icon"] != idx[1]["wide/папка.rs"]["icon"]
        assert idx[1]["wide/type"]["label"] == "type" and idx[1]["wide/type"]["expanded"] is None
        assert idx[1]["wide/blank.rs"]["label"] == ""
        assert "Часть папок показана не полностью" in raw.decode()
    elif scenario == "empty":
        assert len(rows) == 1 and list(idx[0]) == ["."] and reads == prefix
        assert "Папка пуста." in raw.decode()
    else:
        assert len(rows) == 1 and rows == [None] and reads == prefix, (frames, reads)
        assert b"fixture unavailable" in raw


def replay(exe, src, env, scenario):
    package = src / "packages/files"
    features = json.loads((package / "extension.json").read_text())["required_features"]
    tree, actions = spec(scenario)
    reads, errors = [], []

    class Api(http.server.BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            try:
                self.get()
            except Exception as error:
                errors.append(error)
                self.send_error(500)

        def get(self):
            url = urlsplit(self.path)
            query = parse_qs(url.query, keep_blank_values=True)
            assert query["session_dir"] == [SESSION] and self.headers["Authorization"] == "Bearer fixture"
            status = 200
            if url.path == "/sessions/current":
                reads.append(("current", None))
                body = [{"session_dir": SESSION, "workspace_path": CWD}]
            else:
                kind = url.path.split("/")
                assert kind[:2] == ["", "workspace"] and len(kind) == 3
                if kind[-1] == "changes":
                    reads.append(("changes", None))
                    body = {"repository":False, "entries":[]}
                else:
                    assert kind[-1] == "list"
                    folder, = query["path"]
                    reads.append(("list", folder))
                    if tree[folder] is None:
                        status, body = 503, {"error":"fixture unavailable"}
                    else:
                        body = {"entries":tree[folder], "truncated":scenario == "wide" and folder == "wide"}
            data = json.dumps(body, ensure_ascii=False).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

    with http.server.ThreadingHTTPServer(("127.0.0.1",0), Api) as server:
        thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval":0.025}, daemon=True)
        thread.start()
        try:
            messages = [
                {"type":"hello","protocol":4,"features":features,"workspace":CWD,
                 "server":{"origin":f"http://127.0.0.1:{server.server_port}","token":"fixture"}},
                {"type":"render","context":CONTEXT,"session_dir":SESSION,"view":"panel","surface":"panel"},
            ]
            for sequence,(path,event) in enumerate(actions,1):
                messages.append({"type":"action","view":"panel","action":"files","sequence":sequence,
                                 "value":{"id":path,"event":event}})
            messages.append({"type":"close","view":"panel"})
            inp = b"".join(json.dumps(msg,ensure_ascii=False).encode() + b"\n" for msg in messages)
            result = sp.run([exe],input=inp,cwd=package,env=env,capture_output=True,check=True,timeout=20)
        finally:
            server.shutdown()
            thread.join()
    assert not errors and not result.stderr, (errors, result.stderr)
    verify(scenario,result.stdout,reads)
    return result.stdout,reads
