#!/usr/bin/env python3
"""Build exact SDK/workspace, release binaries, and an allocator probe in a temporary checkout."""
from contextlib import contextmanager
import hashlib
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os
from pathlib import Path
from statistics import median
import subprocess as sp
import sys
import tempfile
import threading
from urllib.parse import parse_qs, urlsplit

BASE = "892f627570369ed60d7205eb0d351c753ec4305f"
HERE = Path(__file__).resolve().parent
PATCH = HERE / "source.patch"
ACTIVE, SAVED = "/fixture/active", "/fixture/other"


def encode(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode()


def payloads():
    sessions = [
        {"session_dir": ACTIVE, "message_count": 8, "preview": "Синтетическая активная"},
        {"session_dir": SAVED, "message_count": 12, "preview": "Синтетическая сохранённая"},
    ]
    turns = [
        {"turn_id": f"turn-{n}", "number": n, "status": "completed", "task": f"Задача {n}"}
        for n in range(1, 13)
    ]
    usage = {"requests": [
        {"exchange_id": f"req-{n}", "turn_id": f"turn-{1+n%12}",
         "model": {"provider": "fixture", "model":"model"}, "origin": "direct",
         "started_at_ms": 1803978000000+n, "finished_at_ms": 1803978001500+n,
         "status": "completed", "finish_reason": "Stop",
         "usage": {"input_tokens": 2400+n, "output_tokens": 180, "cached_input_tokens": 40},
         "message_count": 2, "tool_count": 1} for n in range(120)
    ]}
    analysis = {
        "revision": "fixture", "turns": turns,
        "selected": {"turn_id": "turn-12", "task": "Разбор 🦀", "steps": [
            {"sequence": n, "kind": "tool", "status":"ok",
             "data": {"name": "fixture", "result": "synthetic result"*32}} for n in range(1, 21)
        ]},
    }
    raw = {
        "/tiny":{"case":"tiny","revision":1},
        "/scalar-1m":{"case":"scalar-1m","revision":1,"source":"a"*1024**2},
        "/nested":{"case":"nested","revision":1,"rows":[
            {"id":n,"line":"строка\\\"\t\n"*16,"meta":{"domain":"fixture","flag":True,"turn":n}}
            for n in range(3072)]},
        "/oversized":{"case":"oversized","revision":1,"source":"x"*(8*1024**2+128)},
        "/sessions":sessions, "/usage": usage, "/analysis":analysis,
    }
    return {key: encode(value) for key,value in raw.items()}


@contextmanager
def fixture(bodies):
    calls = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            assert self.headers.get("Authorization") == "Bearer fixture"
            part = urlsplit(self.path)
            session, = parse_qs(part.query)["session_dir"]
            calls.append((part.path, session))
            body = bodies[part.path]
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", len(body))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    with HTTPServer(("127.0.0.1", 0), Handler) as server:
        thread = threading.Thread(target=server.serve_forever, args=(0.05,))
        thread.start()
        try:
            yield f"http://127.0.0.1:{server.server_port}", calls
        finally:
            server.shutdown()
            thread.join()


def rp_page(exe, name, bodies, env):
    with fixture(bodies) as (origin, calls):
        common = {"view":"page","context":"one","session_dir":ACTIVE}
        render = {"type":"render","surface":"page",**common}
        action = {"type":"action",**common}
        lines = [
            {"type":"hello","protocol":4,"workspace":"/fixture",
             "server":{"origin":origin,"token":"fixture"}},
            render, render,
            {**action,"sequence":1,"action":"refresh","value":None},
            {**action,"sequence":2,"action":"session","value":SAVED},
            {"type":"close",**common},
        ]
        out = sp.run([exe], input=b"".join(encode(row)+b"\n" for row in lines),
                     capture_output=True, check=True, timeout=10, env=env)
    assert not out.stderr, out.stderr
    views = [json.loads(row) for row in out.stdout.splitlines()]
    assert len(views)==4 and all(row["type"]=="view" and "children" in row["root"] for row in views), views
    assert views[0]["root"]==views[1]["root"]==views[2]["root"]
    order = ["/analysis","/sessions"] if name=="analysis" else ["/sessions","/usage"]
    assert calls==[(path,session) for session in [ACTIVE,ACTIVE,SAVED] for path in order], calls
    return out.stdout, calls


def rp_alloc(exe, bodies, env):
    with fixture(bodies) as (origin, calls):
        out = sp.run([exe,origin],capture_output=True,check=True,timeout=20,env=env)
    assert not out.stderr, out.stderr
    assert calls==[(path,ACTIVE) for path in ("/tiny","/scalar-1m","/nested","/oversized","/oversized")]
    return out.stdout.decode(), calls


with tempfile.TemporaryDirectory(prefix="r47-analytics-shared-") as directory:
    root = Path(directory)
    src = root/"src"
    build = Path(os.environ.get("R47_TARGET", str(root/"target"))).resolve()
    sp.run(["git","clone","--quiet","--shared","--no-checkout",str(Path(sys.argv[1]).resolve()),src],check=True)
    env = dict(os.environ,CARGO_TARGET_DIR=str(build),CARGO_INCREMENTAL="0",TZ="UTC")

    def run(*args):
        sp.run(args,check=True,cwd=src,env=env)

    run("git","checkout","--quiet","--detach",BASE)
    run("git","apply","--index","--check",PATCH)
    bodies = payloads()
    print("payload_bytes", {path:len(body) for path,body in bodies.items()},flush=True)
    wires, metrics, workspace_status = {}, {}, {}
    for arm in ("stock","candidate"):
        print("ARM",arm,flush=True)
        if arm=="candidate":
            run("git","apply","--whitespace=error",PATCH)
            run("git","apply","--reverse","--check",PATCH)
            run("git","diff","--check")
            run("cargo","fmt","--check","-p","proteus-extension","-p","extension-analysis","-p","extension-usage")
        cmd = ["cargo","test","--locked","--workspace","--no-fail-fast"]
        result = sp.run(cmd,cwd=src,env=env,stdout=sp.PIPE,stderr=sp.STDOUT)
        sys.stdout.buffer.write(result.stdout)
        sys.stdout.buffer.flush()
        if result.returncode:
            # Some execution environments do not expose the renderer child
            # through /proc/.../children. Require the only failed target and
            # exact assertion to match on both arms, never report it as a pass.
            report = result.stdout.decode(errors="replace")
            assert "different_sessions_share_one_worker_and_last_close_and_eof_reap_it" in report
            assert "packages/mermaid-render/tests/wire.rs:155:5" in report
            assert "left: 0" in report and "right: 1" in report
            assert report.count("test result: FAILED.")==1 and "error: 1 target failed:" in report
            assert "`-p extension-mermaid-render --test wire`" in report
            workspace_status[arm] = "FAIL (Mermaid /proc child count)"
        else:
            workspace_status[arm] = "PASS"
        print("workspace",arm,workspace_status[arm],flush=True)
        packages = ("-p","proteus-extension","-p","extension-analysis","-p","extension-usage")
        run("cargo","test","--locked","--release",*packages)
        run("cargo","build","--locked","--release","-p","extension-analysis","-p","extension-usage")
        for name in ("analysis","usage"):
            wires[arm,name], calls = rp_page(build/"release"/name,name,bodies,env)
            print("page_HTTP",arm,name,calls,flush=True)
        probe = src/"sdk/examples/r47-analytics-probe.rs"
        probe.write_text((HERE/"probe.rs").read_text().replace("__FETCH__",
            "fetch_shared" if arm=="candidate" else "fetch"))
        run("cargo","build","--release","--locked","-p","proteus-extension","--example","r47-analytics-probe")
        binary = build/"release/examples/r47-analytics-probe"
        samples = {}
        for rep in range(5):
            raw, calls = rp_alloc(binary,bodies,env)
            for line in raw.splitlines():
                case, phase, calls_count, size = line.split()
                key = (case, phase)
                samples.setdefault(key, []).append((int(calls_count),int(size)))
        print("probe_HTTP",arm,calls,flush=True)
        metrics[arm] = {}
        for key, values in samples.items():
            if key[1] == "repeat" and key[0] != "oversized":
                assert len(set(values)) == 1, (arm,key,values)
            counts, sizes = zip(*values)
            result = (median(counts),median(sizes))
            metrics[arm][key] = result
            print("probe_samples",arm,*key,values,flush=True)
        probe.unlink()

    assert workspace_status["stock"] == workspace_status["candidate"], workspace_status
    for name in ("analysis","usage"):
        wire = wires["stock",name]
        assert wire==wires["candidate",name], name
        print("wire",name,len(wire),"sha256",hashlib.sha256(wire).hexdigest())
    print("arm case cache alloc_calls requested_B")
    for arm in ("stock","candidate"):
        for key, result in metrics[arm].items():
            print(arm,*key,*result)
    for case in ("scalar-1m","nested"):
        key = (case, "repeat")
        assert metrics["candidate"][key][1] < metrics["stock"][key][1]
