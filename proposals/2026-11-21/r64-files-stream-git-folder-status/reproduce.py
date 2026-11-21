#!/usr/bin/env python3
"""Exact Files package tests, wire parity and Git folder-rollup counters."""
from hashlib import sha256
import http.server
import importlib.util
import json
import os
from pathlib import Path
import subprocess as sp
import sys
import tempfile
import threading
from urllib.parse import urlsplit, parse_qs

BASE = "892f627570369ed60d7205eb0d351c753ec4305f"
HERE = Path(__file__).resolve().parent
PKG = "extension-files"
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


def main():
    with tempfile.TemporaryDirectory(prefix="files-git-folder-rollup-") as path:
        root = Path(path)
        arms = {}
        for arm, count in [("stock", 37), ("candidate", 38)]:
            src = root / arm
            targets = Path(os.environ.get("R64_FILES_TARGETS", root / "targets")).resolve()
            env = dict(os.environ, CARGO_TARGET_DIR=str(targets / arm), CARGO_INCREMENTAL="0", TZ="UTC")
            sp.run(["git", "-c", "advice.detachedHead=false", "clone", "-q", "--no-checkout", str(Path(sys.argv[1]).resolve()), src], check=True)

            def run(*cmd):
                result = sp.run(cmd, cwd=src, env=env, capture_output=True)
                if result.returncode:
                    raise RuntimeError((cmd, result.stderr.decode(), result.stdout.decode()))
                return result.stdout

            patch = HERE / "source.patch"
            run("git", "checkout", "-q", "--detach", BASE)
            assert run("git", "rev-parse", "HEAD").decode().strip() == BASE
            run("git", "apply", "--index", "--check", patch)
            if arm == "candidate":
                run("git", "apply", "--whitespace=error", patch)
                run("git", "apply", "--reverse", "--check", patch)
                run("git", "diff", "--check")
            run("cargo", "fmt", "--check", "-p", PKG)
            for profile, flags in [("debug", []), ("release", ["--release"])]:
                output = run("cargo", "test", "--locked", "-j1", "-p", PKG, *flags).decode()
                summary = next(line for line in output.splitlines() if line.startswith("test result:"))
                assert f"ok. {count} passed; 0 failed;" in summary, summary
                print(arm, profile, summary, flush=True)
            run("cargo", "build", "--release", "--locked", "-j1", "-p", PKG)
            executable = targets / arm / "release" / "files"
            wire = ordinary(executable, src, env)
            main_rs = src / PACKAGE / "src/main.rs"
            start = "fn main() {\n    run(Files::default());\n}"
            source = main_rs.read_text()
            assert source.count(start) == 1
            main_rs.write_text(source.replace(start, (HERE / "probe.rs").read_text()))
            paths_rs = src / PACKAGE / "src/paths.rs"
            paths_source = paths_rs.read_text()
            marker = "pub fn parent(path: &str) -> &str {"
            assert paths_source.count(marker) == 1
            paths_rs.write_text(paths_source.replace(marker, marker + "\n    crate::record_parent_step();"))
            run("cargo", "build", "--release", "--locked", "-j1", "-p", PKG)
            views = run(executable, "wire")
            counts = run(executable, "counts")
            assert all(run(executable, "counts") == counts for _ in range(4))
            arms[arm] = wire, views, counts

        a, b = arms.values()
        assert a[:2] == b[:2]
        print("synthetic HTTP read receipts", a[0][1])
        for label, content in [("ordinary protocol frames", a[0][0]), ("instrumented file and folder statuses", a[1])]:
            print(label, len(content.splitlines()), len(content), sha256(content).hexdigest())
        print("case, file count, parent group count, depth, allocator calls, requested bytes and lexical parent steps: 5 identical observations per arm")
        for arm, (_, _, counts) in arms.items():
            for line in counts.decode().splitlines():
                print(arm, line)


if __name__ == "__main__":
    main()
