#!/usr/bin/env python3
"""Exact A/B Context tests, normal loopback protocol and scoped allocations."""
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

BASE = "892f627570369ed60d7205eb0d351c753ec4305f"
HERE = Path(__file__).resolve().parent
PKG = "extension-context"
PACKAGE = Path("packages/context")
SESSION = "/context-fixture-session"
CONTEXT = "context-map-fixture"


def ordinary(exe, src, env):
    features = json.loads((src / PACKAGE / "extension.json").read_text())["required_features"]
    spec = importlib.util.spec_from_file_location("wire_fixture", src / "tests/wire.py")
    wire = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(wire)
    snapshot = wire.context()
    usage = snapshot["latest_usage"]
    usage["categories"].extend([
        {"name":"provider_cache_read","tokens":5000},
        {"name":"extra_scope","tokens":100},
        {"name":"tiny_💬","tokens":1},
        {"name":"invalid","tokens":"300"},
    ])
    wire.context = lambda: snapshot
    with http.server.ThreadingHTTPServer(("127.0.0.1",0), wire.Api) as server:
        runner = threading.Thread(target=server.serve_forever, kwargs={"poll_interval":0.025}, daemon=True)
        runner.start()
        try:
            def scope(kind, **kwargs):
                return dict(type=kind, context=CONTEXT, session_dir=SESSION, **kwargs)
            first = {"used":20000,"max":200000,"trigger":180000}
            second = dict(first, used=26000)
            def update(usage):
                return scope("session_update", update={"type":"state", "state":{"context":usage}})
            popup = scope("render", view="popup", surface="popup")
            frames = [
                {"type":"hello","protocol":4,"features":features,"workspace":"/context-panel-fixture",
                 "server":{"origin":f"http://127.0.0.1:{server.server_port}","token":"fixture"}},
                scope("session_snapshot", state={"context":first}), popup, update(first), update(second),
                {"type":"close","view":"popup"}, popup, {"type":"close","view":"popup"},
                {"type":"render","context":CONTEXT,"session_dir":None,"view":"preview","surface":"preview"},
                {"type":"close","view":"preview"}
            ]
            data = b"".join(json.dumps(frame).encode() + b"\n" for frame in frames)
            p = sp.run([exe], input=data, cwd=src / PACKAGE, env=env, capture_output=True, check=True, timeout=20)
        finally:
            server.shutdown()
            runner.join()
    assert not p.stderr, p.stderr
    assert wire.READS == [("/context",SESSION)]*3 and not wire.WRITES, wire.READS
    rows = [json.loads(line) for line in p.stdout.splitlines()]
    assert [row["view"] for row in rows] == ["popup"]*4 + ["preview"], rows
    for index,row in enumerate(rows):
        assert row["type"] == "view"
        cell = next(node for node in wire.walk(row["root"]) if node["type"] == "cells")
        assert sum(segment["cells"] for segment in cell["segments"]) == 200
        labels = [segment["label"] for segment in cell["segments"]]
        assert "свободно" in labels and "резерв автокомпакта" in labels
        if index < 4:
            assert "extra scope" in labels and "tiny 💬" in labels and "invalid" not in labels
    return p.stdout, wire.READS


def main():
    with tempfile.TemporaryDirectory(prefix="context-window-map-") as path:
        root = Path(path)
        arms = {}
        for arm, count in [("stock", 3), ("candidate", 4)]:
            src = root / arm
            targets = Path(os.environ.get("R58_CONTEXT_TARGETS", root / "targets")).resolve()
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
            executable = targets / arm / "release" / "context"
            wire = ordinary(executable, src, env)
            main_rs = src / PACKAGE / "src/main.rs"
            start = "fn main() {\n    run(Context::default());\n}"
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
