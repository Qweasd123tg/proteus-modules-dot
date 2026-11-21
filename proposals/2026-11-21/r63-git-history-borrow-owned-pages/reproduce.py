#!/usr/bin/env python3
"""Exact Git log ownership A/B: package tests, normal wire and scoped allocator counts."""
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
PKG = "extension-git"
PACKAGE = Path("packages/git")
SESSION = "/git-log-fixture"
CONTEXT = "git-log-view-fixture"


def ordinary(exe, src, env):
    features = json.loads((src / PACKAGE / "extension.json").read_text())["required_features"]
    spec = importlib.util.spec_from_file_location("wire_fixture", src / "tests/wire.py")
    wire = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(wire)
    reads = []
    failed = False

    class Api(http.server.BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            nonlocal failed
            url = urlsplit(self.path)
            route = url.path.split("/")
            query = parse_qs(url.query)
            assert route[:2] == ["","workspace"] and len(route) == 3
            assert query["session_dir"] == [SESSION] and self.headers["Authorization"] == "Bearer fixture"
            code = 200
            route = route[-1]
            if route == "changes":
                reads.append(("changes",))
                value = {"repository":True,"refs_revision":"fixture","branch":"main","entries":[]}
            elif route == "branches":
                reads.append(("branches",))
                value = {"branches":[{"name":"main"}]}
            else:
                assert route == "log" and query["limit"] == ["100"]
                all_refs = query["all"] == ["true"]
                skip, = query["skip"]
                skip = int(skip)
                assert skip in (0,2)
                reads.append(("log", all_refs, skip))
                if not all_refs and skip==2 and not failed:
                    failed,code,value = True,500,{"error":"synthetic log unavailable"}
                else:
                    value = {"has_more":skip==0,"entries":[
                        {"hash":f"{i:040x}","short":f"{i:07x}","summary":f"{'graph' if all_refs else 'branch'} entry {i}",
                         "author":"Fixture","email":"example@fixture.local","parents":[],"refs":[]}
                        for i in range(skip,skip+2)
                    ]}
            payload = json.dumps(value).encode()
            self.send_response(code)
            self.send_header("Content-Type","application/json")
            self.send_header("Content-Length",str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

    def render(view, surface, argument=None):
        return {"type":"render","context":CONTEXT,"session_dir":SESSION,"view":view,"surface":surface,"argument":argument}
    def action(view,seq,name,value=None):
        return {"type":"action","view":view,"sequence":seq,"action":name,"value":value}
    def close(view):
        return {"type":"close","view":view}

    with http.server.ThreadingHTTPServer(("127.0.0.1",0), Api) as server:
        thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval":0.025}, daemon=True)
        thread.start()
        try:
            panel = render("panel","panel")
            graph = render("graph","document","Граф коммитов")
            inputs = [
                {"type":"hello","protocol":4,"features":features,"workspace":"/git-log-panel-fixture",
                 "server":{"origin":f"http://127.0.0.1:{server.server_port}","token":"fixture"}},
                panel, action("panel",1,"tab",1), panel, action("panel",2,"more"),
                action("panel",3,"more"), panel, close("panel"),
                graph, action("graph",1,"graph_more"), graph, close("graph"),
            ]
            data = b"".join(json.dumps(msg).encode() + b"\n" for msg in inputs)
            p = sp.run([exe], input=data, cwd=src / PACKAGE, env=env, capture_output=True, check=True, timeout=15)
        finally:
            server.shutdown()
            thread.join()
    assert not p.stderr, p.stderr
    frames = [json.loads(line) for line in p.stdout.splitlines()]
    assert [f["view"] for f in frames] == ["panel"]*6+["graph"]*3, frames
    assert [f["sequence"] for f in frames] == [0,1,1,2,3,3,0,1,1]
    for i,(frame,count) in enumerate(zip(frames,[0,2,2,2,4,4,2,4,4])):
        nodes = [n for n in wire.walk(frame["root"]) if n.get("type")==("list" if i<6 else "lanes")]
        assert sum(len(node["rows"]) for node in nodes) == count, (i,count,nodes)
        if nodes:
            assert [r["label"] for r in nodes[0]["rows"]] == [
                f"{'branch' if i<6 else 'graph'} entry {n}" for n in range(count)
            ]
    assert "synthetic log unavailable" in json.dumps(frames[3],ensure_ascii=False)
    assert reads == [("changes",),("branches",),("log",False,0),("log",False,2),("log",False,2),
                     ("log",True,0),("log",True,2)], reads
    return p.stdout, reads


def main():
    with tempfile.TemporaryDirectory(prefix="git-log-owned-") as path:
        root = Path(path)
        arms = {}
        for arm, count in [("stock", 41), ("candidate", 42)]:
            src = root / arm
            targets = Path(os.environ.get("R63_GIT_TARGETS", root / "targets")).resolve()
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
            executable = targets / arm / "release" / "git"
            wire = ordinary(executable, src, env)
            main_rs = src / PACKAGE / "src/main.rs"
            start = "fn main() {\n    run(Git::default());\n}"
            source = main_rs.read_text()
            assert source.count(start) == 1
            main_rs.write_text(source.replace(start, (HERE / "probe.rs").read_text()))
            run("cargo", "build", "--release", "--locked", "-j1", "-p", PKG)
            views = run(executable, "wire")
            counts = run(executable, "counts")
            assert all(run(executable, "counts") == counts for _ in range(4))
            arms[arm] = wire, views, counts

        a, b = arms.values()
        assert a[:2] == b[:2]
        print("synthetic HTTP read receipts", a[0][1])
        for label, content in [("ordinary protocol frames", a[0][0]), ("instrumented trees", a[1])]:
            print(label, len(content.splitlines()), len(content), sha256(content).hexdigest())
        print("allocator calls, requested bytes and serialized bytes: 5 identical observations per arm")
        for arm, (_, _, counts) in arms.items():
            for line in counts.decode().splitlines():
                print(arm, line)


if __name__ == "__main__":
    main()
