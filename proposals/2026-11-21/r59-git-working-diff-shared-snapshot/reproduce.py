#!/usr/bin/env python3
"""Exact Git working diff A/B: package tests, ordinary protocol and allocator requests."""
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
SESSION = "/worktree-fixture"
CONTEXT = "git-worktree-fixture"


def ordinary(exe, src, env):
    features = json.loads((src / PACKAGE / "extension.json").read_text())["required_features"]
    spec = importlib.util.spec_from_file_location("wire_fixture", src / "tests/wire.py")
    wire = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(wire)
    reads = []
    version = 0

    class Api(http.server.BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            nonlocal version
            url = urlsplit(self.path)
            route = url.path.split("/")
            query = parse_qs(url.query)
            assert route[:2] == ["", "workspace"] and len(route) == 3
            assert query["session_dir"] == [SESSION] and self.headers["Authorization"] == "Bearer fixture"
            route = route[2]
            if route == "changes":
                version += 1
                reads.append((route, None))
                data = {"repository":True,"branch":"main","entries":[
                    {"path":"a.txt","status":"modified","revision":f"v{version}"},{"path":"b.txt","status":"modified","revision":None}]}
            else:
                assert route == "diff"
                path, = query["path"]
                assert path in ("a.txt", "b.txt")
                reads.append((route, path))
                data = {"path":path,"kind":"text","revision":f"v{version}" if path=="a.txt" else None,
                        "patch":f"+ synthetic {path} version {version} \"Ж\"\n"}
            encoded = json.dumps(data).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

    def render(view, argument):
        return {"type":"render","context":CONTEXT,"session_dir":SESSION,"view":view,"surface":"document","argument":argument}

    single = render("one", "a.txt · diff")
    all_changes = render("all", "Все изменения")
    with http.server.ThreadingHTTPServer(("127.0.0.1",0), Api) as server:
        thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval":0.025}, daemon=True)
        thread.start()
        try:
            inputs = [
                {"type":"hello","protocol":4,"features":features,"workspace":"/worktree-panel-fixture",
                 "server":{"origin":f"http://127.0.0.1:{server.server_port}","token":"fixture"}},
                single, single, {"type":"close","view":"one"}, single, {"type":"close","view":"one"},
                all_changes, all_changes, {"type":"event","context":CONTEXT,"session_dir":SESSION,"event":"run_settled"},
                {"type":"close","view":"all"},
            ]
            data = b"".join(json.dumps(msg).encode() + b"\n" for msg in inputs)
            p = sp.run([exe], input=data, cwd=src / PACKAGE, env=env, capture_output=True, check=True, timeout=15)
        finally:
            server.shutdown()
            thread.join()
    assert not p.stderr, p.stderr
    frames = [json.loads(line) for line in p.stdout.splitlines()]
    assert [row["view"] for row in frames] == ["one"]*3 + ["all"]*3, frames
    assert all(row["type"] == "view" and row["session_dir"] == SESSION for row in frames)
    for i,row in enumerate(frames):
        diff = next(node for node in wire.walk(row["root"]) if node["type"] == "diff")
        v = 1 if i < 5 else 2
        expect = [f'+ synthetic {path} version {v} "Ж"\n' for path in (["a.txt"] if i < 3 else ["a.txt","b.txt"])]
        assert diff["patch"] == "".join(expect)
    assert reads == [
        ("changes", None), ("diff", "a.txt"), ("diff", "b.txt"), ("diff", "b.txt"),
        ("changes", None), ("diff", "a.txt"), ("diff", "b.txt"),
    ], reads
    return p.stdout, reads


def cold(exe, src, env):
    reads = []
    patch = ("+ cold fixture строка\n" * 400).rstrip() + "\n"

    class Api(http.server.BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            url = urlsplit(self.path)
            assert url.path.split("/") == ["", "workspace", "diff"]
            query = parse_qs(url.query)
            path, = query["path"]
            assert query["session_dir"] == [SESSION] and self.headers["Authorization"] == "Bearer fixture"
            reads.append(path)
            data = {"path":path, "kind":"text", "patch":patch, "revision":"v1" if path == "a.txt" else None}
            # Both encoded revision values take the same number of bytes.
            encoded = json.dumps(data, ensure_ascii=False, separators=(",",":")).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

    with http.server.ThreadingHTTPServer(("127.0.0.1",0), Api) as server:
        thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval":0.025}, daemon=True)
        thread.start()
        try:
            origin = f"http://127.0.0.1:{server.server_port}"
            def run(path):
                process = sp.run([exe,"cold",path,origin], cwd=src, env=env, capture_output=True, check=True, timeout=15)
                assert json.loads(process.stdout)["children"][-1]["patch"] == patch
                return process.stdout,process.stderr
            result = [run(path) for path in ["a.txt","b.txt"]]
            assert all([run(path) for path in ["a.txt","b.txt"]] == result for _ in range(4))
        finally:
            server.shutdown()
            thread.join()
    assert reads == ["a.txt", "b.txt"] * 5, reads
    return b"".join(output for output,_ in result), b"".join(counts for _,counts in result)


def main():
    with tempfile.TemporaryDirectory(prefix="git-working-diff-") as path:
        root = Path(path)
        arms = {}
        for arm, count in [("stock", 41), ("candidate", 42)]:
            src = root / arm
            targets = Path(os.environ.get("R59_GIT_TARGETS", root / "targets")).resolve()
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
            # Start cold counting only once the loopback response is decoded;
            # this includes Rc construction/cache admission/widget building,
            # but excludes kernel-fragmentation-dependent HTTP allocations.
            document_rs = src / PACKAGE / "src/document.rs"
            doc = document_rs.read_text()
            read = 'host.api("/workspace/diff", &[("path", path)])?'
            assert doc.count(read) == 1
            doc = doc.replace(read, "{ let value = " + read + "; crate::reset_counters(); value }")
            document_rs.write_text(doc)
            run("cargo", "build", "--release", "--locked", "-j1", "-p", PKG)
            views = run(executable, "wire")
            counts = run(executable, "counts")
            assert all(run(executable, "counts") == counts for _ in range(4))
            cold_views, cold_counts = cold(executable, src, env)
            arms[arm] = wire, views + cold_views, counts + cold_counts

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
