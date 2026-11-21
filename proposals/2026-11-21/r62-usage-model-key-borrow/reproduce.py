#!/usr/bin/env python3
"""Exact Usage package A/B tests, ordinary protocol and scoped selector counters."""
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
PKG = "extension-usage"
PACKAGE = Path("packages/usage")
SESSION = "/session"
CONTEXT = "usage-model-fixture"


def ordinary(exe, src, env):
    features = json.loads((src / PACKAGE / "extension.json").read_text())["required_features"]
    spec = importlib.util.spec_from_file_location("wire_fixture", src / "tests/wire.py")
    wire = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(wire)
    models = [{"provider":"fixture/proxy","model":"地"},{"provider":"fixture","model":"proxy/地"},
              {"provider":"fixture","model":"other"},None]
    data = wire.usage()
    template=data["requests"][0]
    data["requests"]=[dict(template,exchange_id=f"req-{i}",turn_id=f"turn-{i%3}",model=models[i%4],
                           started_at_ms=i*1000,finished_at_ms=i*1000+100) for i in range(67)]
    data["latest_turn_id"]="turn-1"
    wire.usage = lambda: data
    class Api(wire.Api):
        def log_message(self, *args):
            pass
    with http.server.ThreadingHTTPServer(("127.0.0.1",0), Api) as server:
        thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval":0.025}, daemon=True)
        thread.start()
        try:
            inputs = [
                {"type":"hello","protocol":4,"features":features,"workspace":"/usage-panel-fixture",
                 "server":{"origin":f"http://127.0.0.1:{server.server_port}","token":"fixture"}},
                {"type":"render","context":CONTEXT,"session_dir":SESSION,"view":"usage","surface":"page"},
            ]
            for seq,(action,value) in enumerate([
                ("model","fixture/proxy/地"),("page",1),("period","latest"),("model","/"),
                ("model","unknown"),("period","all"),("model",None),
            ],1):
                inputs.append({"type":"action","view":"usage","action":action,"sequence":seq,"value":value})
            inputs.append({"type":"close","view":"usage"})
            wire_input = b"".join(json.dumps(msg).encode() + b"\n" for msg in inputs)
            p = sp.run([exe], input=wire_input, cwd=src / PACKAGE, env=env, capture_output=True, check=True, timeout=15)
        finally:
            server.shutdown()
            thread.join()
    assert not p.stderr, p.stderr
    frames = [json.loads(line) for line in p.stdout.splitlines()]
    assert [r["sequence"] for r in frames] == list(range(8))
    assert all(r["view"] == "usage" and r["type"] == "view" for r in frames)
    for row,(expected,key) in zip(frames, [(67,None),(34,"fixture/proxy/地"),(34,"fixture/proxy/地"),
                                          (12,"fixture/proxy/地"),(5,"/"),(22,None),(67,None),(67,None)]):
        nodes = list(wire.walk(row["root"]))
        picker = next(n for n in nodes if n.get("id") == "model")
        assert [option["value"] for option in picker["options"]] == [None,"fixture/proxy/地","fixture/other","/"]
        assert [option["value"] for option in picker["options"] if option["selected"]] == [key]
        assert any(n.get("text") == f"Запросы: {expected} из {expected}" for n in nodes), [n.get("text") for n in nodes]
    assert wire.READS == [("/sessions",SESSION),("/usage",SESSION)] and not wire.WRITES
    return p.stdout, wire.READS


def main():
    with tempfile.TemporaryDirectory(prefix="usage-model-key-") as path:
        root = Path(path)
        arms = {}
        for arm, count in [("stock", 12), ("candidate", 13)]:
            src = root / arm
            targets = Path(os.environ.get("R62_USAGE_TARGETS", root / "targets")).resolve()
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
            executable = targets / arm / "release" / "usage"
            wire = ordinary(executable, src, env)
            main_rs = src / PACKAGE / "src/main.rs"
            start = "fn main() {\n    run(Usage::default());\n}"
            source = main_rs.read_text()
            assert source.count(start) == 1
            main_rs.write_text(source.replace(start, (HERE / "probe.rs").read_text()))
            # Measure the same selector projection directly in each version,
            # without guessing its stock implementation or including widgets.
            view_rs = src / PACKAGE / "src/view.rs"
            view_source = view_rs.read_text()
            start_at = "    let turns = report::turn_ids(snapshot);\n"
            end_at = "    if state\n"
            start_idx = view_source.index(start_at) + len(start_at)
            end_idx = view_source.index(end_at, start_idx)
            selector = view_source[start_idx:end_idx]
            view_rs.write_text(view_source + "\npub fn model_options_probe(requests: &[Value]) -> Vec<String> {\n"
                               + selector + "    models\n}\n")
            run("cargo", "build", "--release", "--locked", "-j1", "-p", PKG)
            views = run(executable, "wire")
            counts = run(executable, "counts")
            assert all(run(executable, "counts") == counts for _ in range(4))
            arms[arm] = wire, views, counts

        a, b = arms.values()
        assert a[:2] == b[:2]
        print("synthetic HTTP read receipts", a[0][1])
        for label, content in [("ordinary protocol frames", a[0][0]), ("instrumented projections and trees", a[1])]:
            print(label, len(content.splitlines()), len(content), sha256(content).hexdigest())
        print("allocator calls and requested bytes: 5 identical observations per arm")
        for arm, (_, _, counts) in arms.items():
            for line in counts.decode().splitlines():
                print(arm, line)


if __name__ == "__main__":
    main()
