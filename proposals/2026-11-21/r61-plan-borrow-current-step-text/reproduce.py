#!/usr/bin/env python3
"""Exact Plan package tests, ordinary protocol frames and scoped allocator requests."""
from hashlib import sha256
import http.server
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
PKG = "extension-plan"
PACKAGE = Path("packages/plan")
SESSION = "/plan-fixture"
CONTEXT = "plan-view-fixture"


def ordinary(exe, src, env):
    features = json.loads((src / PACKAGE / "extension.json").read_text())["required_features"]
    reads = []
    def plan(label):
        return {"plan":[{"step":label,"status":"in_progress"},{"step":"ещё","status":"pending"}]}
    def entry(args):
        return {"role":"assistant","tool":{"name":"update_plan","call_id":"fixture-current","status":"completed",
                "args":plan("original arguments"),"effective_args":args}}

    class Api(http.server.BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            url = urlsplit(self.path)
            query = parse_qs(url.query)
            assert url.path == "/history/tool-state" and self.headers["Authorization"] == "Bearer fixture"
            assert query["name"] == ["update_plan"] and query["session_dir"] == [SESSION]
            reads.append((url.path,SESSION))
            data = {"revision":"fixture-revision","tool":{"name":"update_plan","call_id":"cached","status":"completed",
                    "args":plan("сохранённый шаг"),"effective_args":None}}
            data = json.dumps(data).encode()
            self.send_response(200)
            self.send_header("Content-Type","application/json")
            self.send_header("Content-Length",str(len(data)))
            self.end_headers()
            self.wfile.write(data)

    def scope(kind, **fields):
        return dict(type=kind,context=CONTEXT,session_dir=SESSION,**fields)
    def visual(revision, preferences):
        return scope("context", workspace="/plan-panel-fixture",
                     window_visual=dict(revision=revision,preferences=preferences))
    def update(start, remove, added):
        return scope("session_update",update={"type":"entries","start":start,"removed":remove,"entries":added})
    def render(view):
        return scope("render",view=view,surface=view)
    def close(view):
        return {"type":"close","view":view}

    with http.server.ThreadingHTTPServer(("127.0.0.1",0), Api) as server:
        thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval":0.025}, daemon=True)
        thread.start()
        try:
            inputs = [
                {"type":"hello","protocol":4,"features":features,"workspace":"/plan-panel-fixture",
                 "server":{"origin":f"http://127.0.0.1:{server.server_port}","token":"fixture"}},
                visual(0,{}), scope("session_snapshot", state={}, entries=[entry(plan("живой шаг"))]),
                render("badge"),close("badge"),render("popup"),
                update(0,1,[entry(json.dumps(plan("кодированный шаг")))]),
                update(0,1,[entry({})]),update(0,1,[entry(plan("восстановленный шаг"))]),
                update(1,0,[{"role":"user"}]),close("popup"),
                visual(1,{"visibility":"always"}),render("popup"),render("popup"),close("popup"),
                render("preview"),close("preview"),
            ]
            data = b"".join(json.dumps(msg).encode() + b"\n" for msg in inputs)
            p = sp.run([exe], input=data, cwd=src / PACKAGE, env=env, capture_output=True, check=True, timeout=15)
        finally:
            server.shutdown()
            thread.join()
    assert not p.stderr, p.stderr
    frames = [json.loads(line) for line in p.stdout.splitlines()]
    assert [m["view"] for m in frames] == ["badge"]+["popup"]*7+["preview"], frames
    assert frames[0]["type"] == "badge" and frames[0]["lines"] == ["живой шаг"]
    for m,label in zip(frames[1:], ["живой шаг","кодированный шаг",None,"восстановленный шаг",None,
                                    "сохранённый шаг","сохранённый шаг","Изучить задачу"]):
        if label is None:
            assert m["root"]["children"] == []
        else:
            assert label in json.dumps(m["root"],ensure_ascii=False)
    assert "original arguments" not in p.stdout.decode()
    assert reads == [("/history/tool-state",SESSION)], reads
    return p.stdout, reads


def main():
    with tempfile.TemporaryDirectory(prefix="plan-borrow-step-text-") as path:
        root = Path(path)
        arms = {}
        for arm, count in [("stock", 17), ("candidate", 18)]:
            src = root / arm
            targets = Path(os.environ.get("R61_PLAN_TARGETS", root / "targets")).resolve()
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
            executable = targets / arm / "release" / "plan"
            wire = ordinary(executable, src, env)
            main_rs = src / PACKAGE / "src/main.rs"
            start = "fn main() {\n    run(Plan::default());\n}"
            source = main_rs.read_text()
            assert source.count(start) == 1
            probe = (HERE / "probe.rs").read_text()
            if arm == "stock":
                # The historical API only built owned projections.
                assert probe.count("Snapshot::from_tool_owned") == 1
                probe = probe.replace("Snapshot::from_tool_owned", "Snapshot::from_tool")
            main_rs.write_text(source.replace(start, probe))
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
        print("allocator calls and requested bytes: 5 identical observations per arm")
        for arm, (_, _, counts) in arms.items():
            for line in counts.decode().splitlines():
                print(arm, line)


if __name__ == "__main__":
    main()
