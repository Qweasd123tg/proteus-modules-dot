#!/usr/bin/env python3
"""Exact A/B Quota tests, ordinary frames, scoped warm render allocator counts."""
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
PKG = "extension-quota"
PACKAGE = Path("packages/quota")
SESSION = "/quota-fixture"
CONTEXT = "fixture"


def ordinary(exe, src, env):
    features = json.loads((src / PACKAGE / "extension.json").read_text())["required_features"]
    reads = []

    class Api(http.server.BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            url = urlsplit(self.path)
            assert url.path == "/model/quota" and self.headers["Authorization"] == "Bearer fixture"
            reads.append((url.path, parse_qs(url.query)["session_dir"][0]))
            snapshot = {"plan":"Fixture","buckets":[{"id":"regular","windows":[{"id":"weekly","used_percent":20}]}]}
            data = json.dumps(snapshot).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

    def scope(kind, **kwargs):
        return {"type": kind, "context": CONTEXT, "session_dir": SESSION, **kwargs}

    def update(config):
        return scope("session_update", update={"type":"state", "state":{"config":config}})

    model = {"provider":"fixture","name":"normal-model","metadata":{"tier":"base"}}
    reordered = {"metadata":{"tier":"base"},"name":"normal-model","provider":"fixture"}
    changed = dict(model, metadata={"tier":"changed"})
    with http.server.ThreadingHTTPServer(("127.0.0.1",0), Api) as server:
        thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval":0.025}, daemon=True)
        thread.start()
        try:
            inputs = [
                {"type":"hello","protocol":4,"features":features,"workspace":"/quota-panel-fixture",
                 "server":{"origin":f"http://127.0.0.1:{server.server_port}","token":"fixture"}},
                scope("session_snapshot", state={"config":{"model":model}}),
                scope("render", view="badge", surface="badge"),
                update({"model":reordered,"unrelated":1}),
                update({"model":changed}), update({}), update({"model":None}),
                {"type":"action","view":"badge","action":"refresh","sequence":1},
                {"type":"close","view":"badge"}, scope("render", view="popup", surface="popup"),
                update({"model":model}), {"type":"close","view":"popup"},
                {"type":"render","context":CONTEXT,"session_dir":"/second-fixture","view":"second","surface":"popup"},
                {"type":"close","view":"second"},
            ]
            data = b"".join(json.dumps(msg).encode() + b"\n" for msg in inputs)
            p = sp.run([exe], input=data, cwd=src / PACKAGE, env=env, capture_output=True, check=True, timeout=15)
        finally:
            server.shutdown()
            thread.join()
    assert not p.stderr, p.stderr
    frames = [json.loads(line) for line in p.stdout.splitlines()]
    assert [row["type"] for row in frames] == ["badge"]*6 + ["view"]*3, frames
    assert all(row["face"]["type"] == "ring" and row["session_dir"] == SESSION for row in frames[:6])
    assert "normal-model" not in json.dumps(frames[6]["root"])
    assert "normal-model" in json.dumps(frames[7]["root"])
    assert frames[8]["session_dir"] == "/second-fixture" and "normal-model" not in json.dumps(frames[8]["root"])
    assert reads == [("/model/quota", SESSION)] * 5 + [("/model/quota", "/second-fixture")], reads
    return p.stdout, reads


def main():
    with tempfile.TemporaryDirectory(prefix="quota-borrowed-model-") as path:
        root = Path(path)
        arms = {}
        for arm, count in [("stock", [7, 5]), ("candidate", [7, 6])]:
            src = root / arm
            targets = Path(os.environ.get("R57_QUOTA_TARGETS", root / "targets")).resolve()
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
                summary = [line for line in output.splitlines() if line.startswith("test result:")]
                assert len(summary) == len(count), summary
                assert all(f"ok. {n} passed; 0 failed;" in line for n, line in zip(count, summary)), summary
                print(arm, profile, "; ".join(summary), flush=True)
            run("cargo", "build", "--release", "--locked", "-j1", "-p", PKG)
            executable = targets / arm / "release" / "quota"
            wire = ordinary(executable, src, env)
            main_rs = src / PACKAGE / "src/main.rs"
            start = "fn main() {\n    run(Quota::default());\n}"
            source = main_rs.read_text()
            assert source.count(start) == 1
            main_rs.write_text(source.replace(start, (HERE / "probe.rs").read_text()))
            run("cargo", "build", "--release", "--locked", "-j1", "-p", PKG)
            def probe():
                p = sp.run([executable], cwd=src, env=env, capture_output=True, check=True, timeout=15)
                frames = [json.loads(line) for line in p.stdout.splitlines()]
                assert len(frames) == 24
                assert all(frames[i:i+4] == [frames[i]]*4 for i in range(0,24,4))
                values = p.stderr.decode().splitlines()
                assert len(values) == 18
                assert all(values[i:i+3] == [values[i]]*3 for i in range(0,18,3))
                return p.stdout, values[::3]
            view, counts = probe()
            assert all(probe() == (view, counts) for _ in range(4))
            arms[arm] = wire, view, counts

        a, b = arms.values()
        assert a[:2] == b[:2]
        print("synthetic HTTP read receipts", a[0][1])
        for label, content in [("ordinary protocol frames", a[0][0]), ("instrumented trees", a[1])]:
            print(label, len(content.splitlines()), len(content), sha256(content).hexdigest())
        print("allocator calls and requested bytes per warm render: 15 identical observations per arm")
        for arm, (_, _, counts) in arms.items():
            for line in counts:
                print(arm, line)


if __name__ == "__main__":
    main()
