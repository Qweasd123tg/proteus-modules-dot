#!/usr/bin/env python3
"""Exact TPS tests, loopback process parity and scoped sampling counters."""
from collections import Counter
from hashlib import sha256
import http.server
import json
import os
from pathlib import Path
import re
import subprocess as sp
import sys
import tempfile
import threading
from urllib.parse import urlsplit, parse_qs

BASE = "892f627570369ed60d7205eb0d351c753ec4305f"
HERE = Path(__file__).resolve().parent
PKG = "extension-tps"
PACKAGE = Path("packages/tps")
SESSION = "/tps-fixture"
CONTEXT = "tps-fixture"


def row(end, output, provider="fixture", model="model", **extra):
    return {"origin":"direct","status":"completed","started_at_ms":1000,
            "finished_at_ms":end,"usage":{"output_tokens":output},
            "model":{"provider":provider,"model":model}, **extra}


def ordinary(exe, src, env):
    features = json.loads((src / PACKAGE / "extension.json").read_text())["required_features"]
    reads = []
    base = [row(3000, 40), row(4100, 999, origin="compaction"), row(None, 800),
            row(3000, 160), row(5000, 500, provider="new-provider"),
            row(4800, 300, model="different"), row(4300, 950, status="unfinished")]
    replies = [base, base + [row(3000, None)], base, base]

    class Api(http.server.BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            url = urlsplit(self.path)
            query = parse_qs(url.query, keep_blank_values=True)
            assert url.path == "/usage"
            assert query == {"session_dir":[SESSION]} and self.headers["Authorization"] == "Bearer fixture"
            data = json.dumps({"requests":replies[len(reads)]}).encode()
            reads.append((url.path, query["session_dir"][0]))
            self.send_response(200)
            self.send_header("Content-Type","application/json")
            self.send_header("Content-Length",str(len(data)))
            self.end_headers()
            self.wfile.write(data)

    with http.server.ThreadingHTTPServer(("127.0.0.1",0), Api) as server:
        thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval":0.025}, daemon=True)
        thread.start()
        try:
            def state(model):
                return {"execution":{"active":None},"activity":{"running_runs":0},
                        "config":{"model":model}}

            def render(surface):
                return {"type":"render","context":CONTEXT,"view":surface,
                        "surface":surface,"session_dir":SESSION}

            def close(view):
                return {"type":"close","view":view}

            def update(model):
                return {"type":"session_update","context":CONTEXT,"session_dir":SESSION,
                        "update":{"type":"state","state":state(model)}}

            inputs = [
                {"type":"hello","protocol":4,"features":features,"workspace":"/project-fixture",
                 "server":{"origin":f"http://127.0.0.1:{server.server_port}","token":"fixture"}},
                {"type":"session_snapshot","context":CONTEXT,"session_dir":SESSION,
                 "state":state({"provider":"fixture","name":"model"})},
                render("badge"), render("popup"), close("badge"),
                {"type":"action","view":"popup","action":"refresh","sequence":4,"value":None},
                close("popup"), update({"provider":"fixture","name":"absent"}),
                render("badge"), close("badge"), update(None), render("badge"), close("badge"),
                render("preview"), close("preview"),
            ]
            data = b"".join(json.dumps(msg).encode() + b"\n" for msg in inputs)
            p = sp.run([exe], input=data, cwd=src / PACKAGE, env=env, capture_output=True, check=True, timeout=15)
        finally:
            server.shutdown()
            thread.join()
    assert not p.stderr, p.stderr
    frames = [json.loads(line) for line in p.stdout.splitlines()]
    assert [f["view"] for f in frames] == ["badge","popup","popup","badge","badge","preview"]
    assert frames[0]["face"]["text"] == "80,0 TPS"
    assert frames[1]["root"]["children"][1]["text"] == "80,0 TPS"
    no_usage = "Провайдер не сообщил число выходных токенов."
    assert frames[2]["sequence"] == 4 and frames[2]["root"]["children"][1]["text"] == no_usage
    assert frames[3]["face"]["text"] == "— TPS"
    assert frames[3]["lines"] == ["Появится после завершённого запроса выбранной модели."]
    assert frames[4]["face"]["text"] == "125,0 TPS" and frames[4]["lines"][1] == "new-provider/model"
    assert frames[5]["root"]["children"][1]["text"] == "48,0 TPS"
    assert reads == [("/usage", SESSION)] * 4, reads
    return p.stdout, reads


def main():
    with tempfile.TemporaryDirectory(prefix="tps-finish-key-") as path:
        root = Path(path)
        arms = {}
        for arm, count in [("stock", 4), ("candidate", 6)]:
            src = root / arm
            targets = Path(os.environ.get("R65_TPS_TARGETS", root / "targets")).resolve()
            env = dict(os.environ, CARGO_TARGET_DIR=str(targets / arm), CARGO_INCREMENTAL="0", TZ="UTC")
            sp.run(["git","-c","advice.detachedHead=false","clone","-q","--no-checkout",str(Path(sys.argv[1]).resolve()),src],check=True)

            def run(*cmd):
                result = sp.run(cmd, cwd=src, env=env, capture_output=True)
                if result.returncode:
                    raise RuntimeError((cmd, result.stderr.decode(), result.stdout.decode()))
                return result.stdout

            patch = HERE / "source.patch"
            run("git","checkout","-q","--detach",BASE)
            assert run("git","rev-parse","HEAD").decode().strip() == BASE
            run("git","apply","--index","--check",patch)
            if arm == "candidate":
                run("git","apply","--whitespace=error",patch)
                run("git","apply","--reverse","--check",patch)
                run("git","diff","--check")
            run("cargo","fmt","--check","-p",PKG)
            for profile, flags in [("debug", []), ("release", ["--release"])]:
                output = run("cargo","test","--locked","-j1","-p",PKG,*flags).decode()
                summary = next(line for line in output.splitlines() if line.startswith("test result:"))
                assert f"ok. {count} passed; 0 failed;" in summary, summary
                print(arm, profile, summary.split("; finished in", 1)[0], flush=True)
            run("cargo","build","--release","--locked","-j1","-p",PKG)
            executable = targets / arm / "release" / "tps"
            wire = ordinary(executable, src, env)

            main_rs = src / PACKAGE / "src/main.rs"
            start = "fn main() {\n    run(Tps::default());\n}"
            source = main_rs.read_text()
            assert source.count(start) == 1
            main_rs.write_text(source.replace(start, (HERE / "probe.rs").read_text()))
            sampler = src / PACKAGE / "src/sample.rs"
            source = sampler.read_text()
            part = source.index("pub fn latest(")
            end = source.index("pub fn decimal(", part)
            seen = Counter()

            def measure(match):
                key = match.group(1)
                seen[key] += 1
                return f'crate::measured_at(request, "{key}")'

            probed = re.sub(r'\brequest\s*\.at\("(finished_at_ms|model)"\)', measure, source[part:end])
            assert seen == ({"finished_at_ms":3,"model":4} if arm == "stock" else {"finished_at_ms":1,"model":2}), seen
            sampler.write_text(source[:part] + probed + source[end:])
            run("cargo","build","--release","--locked","-j1","-p",PKG)
            results = run(executable,"outputs")
            counts = run(executable,"counts")
            assert all(run(executable,"counts") == counts for _ in range(4))
            arms[arm] = wire, results, counts

        stock, candidate = arms.values()
        assert stock[:2] == candidate[:2]
        for a, b in zip(stock[2].decode().splitlines(), candidate[2].decode().splitlines(), strict=True):
            a, b = a.split(), b.split()
            assert a[:3] == b[:3] and int(b[3]) < int(a[3]) and int(b[4]) <= int(a[4]), (a,b)
            assert a[5:] == b[5:], (a,b)
        print("synthetic HTTP receipts", stock[0][1])
        for label, content in [("ordinary protocol frames",stock[0][0]),("instrumented sampling outputs",stock[1])]:
            print(label, len(content.splitlines()), len(content), sha256(content).hexdigest())
        print("case, requests, selected, finish lookups, model-object lookups, alloc/realloc calls, requested bytes: 5 identical observations per arm")
        for arm, (_, _, counts) in arms.items():
            for line in counts.decode().splitlines():
                print(arm, line)


if __name__ == "__main__":
    main()
