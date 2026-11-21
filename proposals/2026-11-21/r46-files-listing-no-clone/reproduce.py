#!/usr/bin/env python3
"""Exact package test, release allocation probe, and real panel stdio/HTTP parity."""
import hashlib
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os
from pathlib import Path
import shutil
import subprocess as sp
import sys
import tempfile
import threading
from urllib.parse import parse_qs, urlsplit

BASE = "892f627570369ed60d7205eb0d351c753ec4305f"
HERE = Path(__file__).resolve().parent
REPO = Path(sys.argv[1]).resolve()
PATCH = HERE / "source.patch"
PKG = "extension-files"


def panel(binary):
    path = "/fixture/project"
    session = "/fixture/session"
    calls = []
    refreshes = 0
    listings = {
        "": [("first.rs", "file"), ("a", "directory"), ("last.rs", "file")],
        "a": [("β", "directory")],
        "a/β": [("visible.rs", "file"), ("symlink", "symlink")],
    }

    class Fixture(BaseHTTPRequestHandler):
        def do_GET(self):
            nonlocal refreshes
            url = urlsplit(self.path)
            query = parse_qs(url.query, keep_blank_values=True)
            assert query.get("session_dir") == [session], query
            assert self.headers["Authorization"] == "Bearer fixture"
            folder = query.get("path", [None])[0]
            calls.append((url.path, folder))
            if url.path == "/sessions/current":
                body = [{"session_dir": session, "workspace_path": path}]
            elif url.path == "/workspace/changes":
                refreshes += 1
                name = "visible.rs" if refreshes == 1 else "new.rs"
                body = {"repository": True, "entries": [{"path": f"a/β/{name}", "status":"modified"}]}
            elif url.path == "/workspace/list":
                entries = listings[folder]
                if folder == "a/β" and refreshes > 1:
                    entries = [("new.rs", "file"), entries[1]]
                body = {
                    "entries": [
                        {"name": name, "path": f"{folder}/{name}" if folder else name, "kind": kind}
                        for name, kind in entries
                    ],
                    "truncated": folder == "a/β",
                }
            else:
                raise AssertionError(url.path)
            encoded = json.dumps(body, ensure_ascii=False).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", len(encoded))
            self.end_headers()
            self.wfile.write(encoded)

        def log_message(self, *args):
            pass

    with HTTPServer(("127.0.0.1", 0), Fixture) as srv:
        thread = threading.Thread(target=srv.serve_forever, args=(0.05,))
        thread.start()
        try:
            address = {"context": "window", "session_dir": session}
            render = {"type": "render", "surface": "panel", "view": "files", **address}
            messages = [
                {"type": "hello", "protocol": 4, "workspace": path,
                 "server": {"origin": f"http://127.0.0.1:{srv.server_port}", "token": "fixture"},
                 "features": ["widgets.controls.v1", "surfaces.preview.v1", "documents.retarget.v1"]},
                render,
                render,
                {"type": "action", "view": "files", "sequence": 1, "action": "files",
                 "value": {"id": "a/β", "event": "expand"}, **address},
                {"type": "event", "event": "run_settled", **address},
            ]
            data = b"".join((json.dumps(m, ensure_ascii=False) + "\n").encode() for m in messages)
            result = sp.run([binary], input=data, capture_output=True, check=True, timeout=10)
        finally:
            srv.shutdown()
            thread.join()
    assert not result.stderr, result.stderr
    views = [json.loads(line) for line in result.stdout.splitlines()]
    assert len(views) == 4 and all(v["type"] == "view" for v in views), views
    assert views[0]["root"] == views[1]["root"]
    assert "visible.rs" not in result.stdout.splitlines()[0].decode()
    assert "visible.rs" in result.stdout.splitlines()[2].decode()
    assert "new.rs" in result.stdout.splitlines()[3].decode()
    assert calls == [
        ("/sessions/current",None), ("/workspace/changes",None), ("/workspace/list",""),
        ("/workspace/list","a"), ("/workspace/list","a/β"),
        ("/workspace/changes",None), ("/workspace/list",""),
        ("/workspace/list","a"), ("/workspace/list","a/β"),
    ], calls
    return result.stdout, calls


with tempfile.TemporaryDirectory(prefix="r46-files-listing-") as tmp:
    root = Path(tmp)
    src = root / "src"
    env = dict(os.environ, CARGO_TARGET_DIR=str(root/"target"), CARGO_INCREMENTAL="0", TZ="UTC")
    sp.run(["git", "clone", "--quiet", "--shared", "--no-checkout", REPO, src], check=True)

    def run(*args):
        sp.run(args, check=True, cwd=src, env=env)

    run("git", "checkout", "--quiet", "--detach", BASE)
    run("git", "apply", "--index", "--check", PATCH)
    wires = {}
    for arm in ("stock", "candidate"):
        print("BUILD", arm, flush=True)
        if arm == "candidate":
            run("git", "apply", "--whitespace=error", PATCH)
            run("git", "apply", "--reverse", "--check", PATCH)
            run("git", "diff", "--check")
            run("cargo", "fmt", "--check", "-p", PKG)
        run("cargo", "test", "--locked", "-p", PKG)
        run("cargo", "test", "--locked", "--release", "-p", PKG)
        run("cargo", "build", "--locked", "--release", "-p", PKG)
        exe = root / "target/release/files"
        wires[arm+"-panel"], calls = panel(exe)
        print(arm, "real_panel_calls", calls, flush=True)
        main = src / "packages/files/src/main.rs"
        original = main.read_text()
        marker = "fn main() {"
        assert original.count(marker) == 1
        main.write_text(
            original.replace(marker, "#[allow(dead_code)]\nfn process_main() {")
            + "\n" + (HERE/"probe.rs").read_text()
        )
        run("cargo", "build", "--locked", "--release", "-p", PKG)
        shutil.copy2(exe, root / arm)
        wires[arm+"-rows"] = sp.check_output([root/arm, "wire"])
        main.write_text(original)

    for scope in ("panel", "rows"):
        wire = wires["stock-"+scope]
        assert wire == wires["candidate-"+scope], scope
        print("wire", scope, "equal", len(wire), "bytes", "sha256", hashlib.sha256(wire).hexdigest())

    metrics = {}
    print("arm case cache rows reads alloc_calls requested_B peak_extra_live_B")
    for arm in ("stock", "candidate"):
        raw = sp.check_output([root/arm,"measure"]).decode()
        assert raw == sp.check_output([root/arm,"measure"]).decode(), "non-repeatable run"
        metrics[arm] = []
        for line in raw.splitlines():
            case, cache, rows, reads, calls, size, peak = line.split()
            metrics[arm].append((case,cache,int(rows),int(reads),int(calls),int(size),int(peak)))
            print(arm,line)
    for left, right in zip(metrics["stock"],metrics["candidate"],strict=True):
        assert left[:4] == right[:4], (left,right)
        if right[1] == "warm" and right[0] in {"flat-2000","mixed","fold-32"}:
            assert right[5] < left[5], (left,right)
