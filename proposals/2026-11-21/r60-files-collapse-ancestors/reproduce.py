#!/usr/bin/env python3
"""Exact Files package Rust tests, protocol output and scoped collapse counters."""
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
CONTEXT = "fold-fixture"


def ordinary(exe, src, env):
    features = json.loads((src / PACKAGE / "extension.json").read_text())["required_features"]
    spec = importlib.util.spec_from_file_location("wire_fixture", src / "tests/wire.py")
    wire = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(wire)
    reads = []
    fold, descendant = "poly/папка/leaf", "poly/папка/leaf/deeper"
    deep_file, side_file = descendant + "/shown.rs", "side/side.rs"
    tree = {"":[("poly",True),("side",True)], "poly":[("папка",True)],
            "poly/папка":[("leaf",True)], fold:[("deeper",True),("plain.rs",False)],
            descendant:[("shown.rs",False)], "side":[("side.rs",False)]}

    class Api(http.server.BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
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
                    data = {"repository":False,"entries":[]}
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
                (fold,"expand"),(descendant,"expand"),("side","select"),(fold,"collapse"),(fold,"expand"),
                ("side","collapse"),(".","collapse"),(".","expand"),
            ],1):
                inputs.append({"type":"action","view":"panel","action":"files","sequence":sequence,
                               "value":{"id":path,"event":event}})
            inputs.append({"type":"close","view":"panel"})
            data = b"".join(json.dumps(msg).encode() + b"\n" for msg in inputs)
            p = sp.run([exe], input=data, cwd=src / PACKAGE, env=env, capture_output=True, check=True, timeout=15)
        finally:
            server.shutdown()
            thread.join()
    assert not p.stderr, p.stderr
    frames = [json.loads(line) for line in p.stdout.splitlines()]
    assert [row["sequence"] for row in frames] == list(range(9))
    rows = [{r["id"]:r for r in next(n for n in wire.walk(v["root"]) if n.get("id") == "files")["rows"]} for v in frames]
    assert [fold in m for m in rows] == [True]*7 + [False,True]
    assert [deep_file in m for m in rows] == [False, False, True, True, False, True, True, False, True]
    assert [side_file in m for m in rows] == [False, False, False, True, True, True, False, False, False]
    assert list(rows[7]) == ["."]
    assert [m[fold]["expanded"] for m in rows if fold in m] == [False,True,True,True,False,True,True,True]
    assert reads == [("current",None),("changes",None),("list",""),("list","poly"),("list","poly/папка"),
                     ("list",fold),("list","side"),("list",descendant)], reads
    return p.stdout, reads


def main():
    with tempfile.TemporaryDirectory(prefix="files-collapse-ancestors-") as path:
        root = Path(path)
        arms = {}
        for arm, count in [("stock", 37), ("candidate", 38)]:
            src = root / arm
            targets = Path(os.environ.get("R60_FILES_TARGETS", root / "targets")).resolve()
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
            marker = "pub fn within(path: &str, folder: &str) -> bool {"
            assert paths_source.count(marker) == 1
            paths_rs.write_text(paths_source.replace(marker, marker + "\n    crate::record_prefix_check();"))
            run("cargo", "build", "--release", "--locked", "-j1", "-p", PKG)
            views = run(executable, "wire")
            counts = run(executable, "counts")
            assert all(run(executable, "counts") == counts for _ in range(4))
            arms[arm] = wire, views, counts

        a, b = arms.values()
        assert a[:2] == b[:2]
        print("synthetic HTTP read receipts", a[0][1])
        for label, content in [("ordinary protocol frames", a[0][0]), ("instrumented expansion sets", a[1])]:
            print(label, len(content.splitlines()), len(content), sha256(content).hexdigest())
        print("chain depth, unrelated folders, allocator calls, requested bytes and prefix predicate invocations: 5 identical observations per arm")
        for arm, (_, _, counts) in arms.items():
            for line in counts.decode().splitlines():
                print(arm, line)


if __name__ == "__main__":
    main()
