#!/usr/bin/env python3
"""Exact A/B comparison of Analysis package tests, normal frames and allocator requests."""
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
PKG = "extension-analysis"
PACKAGE = Path("packages/analysis")
SESSION = "/session"
CONTEXT = "analysis-fixture"


def ordinary(exe, src, env):
    features = json.loads((src / PACKAGE / "extension.json").read_text())["required_features"]
    spec = importlib.util.spec_from_file_location("wire_fixture",src/"tests/wire.py")
    wire = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(wire)
    fixture = wire.analysis
    catalogs = []
    for shape in ["unicode", "missing", "structured"]:
        data = fixture()
        data["selected"]["task"]["cwd"] = "/analysis-panel-fixture"
        result = data["selected"]["steps"][2]["data"]["result"]
        answer = data["selected"]["output"]
        if shape == "unicode":
            result["output"] = 'Строка "A" \r\n🦀 второй ряд\n' * 100
            answer["text"] = "Итог \u2028 последняя строка\n" * 40
            tool_text, tool_lang = result["output"], "text"
            answer_text, answer_lang = answer["text"], "text"
        elif shape == "missing":
            del result["output"]
            answer["text"] = ""
            tool_text, tool_lang = "—", "text"
            answer_text, answer_lang = "Итоговый ответ не записан.", "text"
        else:
            result["output"] = None
            answer["text"] = {"z": "строка", "a": [True, None]}
            tool_text, tool_lang = "null", "json"
            answer_text, answer_lang = json.dumps(answer["text"], ensure_ascii=False, indent=2), "json"
        wire.analysis = lambda: data
        wire.READS.clear()

        def run(port):
            frames = [{"type": "hello", "protocol": 4, "features": features,
                       "workspace": "/analysis-panel-fixture",
                       "server": {"origin": f"http://127.0.0.1:{port}", "token": "fixture"}},
                      {"type": "render", "context": CONTEXT, "session_dir": SESSION, "view": "page", "surface": "page"}]
            actions = [("step", 3), ("step", 3), ("step", {"id": 3}), ("kind", "tool"), ("query", "fixture")]
            frames.extend({"type": "action", "view":"page", "sequence": i, "action": name, "value": value}
                          for i, (name, value) in enumerate(actions, 1))
            frames.extend([{"type":"close","view":"page"},
                           {"type": "render", "context": CONTEXT, "session_dir": SESSION, "view": "page", "surface": "page"}])
            encoded = b"".join(json.dumps(frame).encode() + b"\n" for frame in frames)
            return sp.run([exe], input=encoded, cwd=src / PACKAGE, env=env,
                          capture_output=True, check=True, timeout=20)

        with http.server.ThreadingHTTPServer(("127.0.0.1",0), wire.Api) as server:
            runner = threading.Thread(target=server.serve_forever, kwargs={"poll_interval":0.025}, daemon=True)
            runner.start()
            try:
                p = run(server.server_port)
            finally:
                server.shutdown()
                runner.join()
        assert not p.stderr, p.stderr
        assert wire.READS[0:2] == [("/analysis", SESSION), ("/sessions", SESSION)], wire.READS
        assert [r for r in wire.READS if r[0] == "/analysis"] == [("/analysis", SESSION)] * 2, wire.READS
        assert set(wire.READS) == {("/analysis", SESSION), ("/sessions", SESSION)} and not wire.WRITES
        rows = [json.loads(line) for line in p.stdout.splitlines()]
        assert [row["sequence"] for row in rows] == [0, 1, 2, 3, 4, 5, 0], rows
        for i,row in enumerate(rows):
            assert row["type"] == "view"
            nodes = {node.get("id"): node for node in wire.walk(row["root"])}
            summary = nodes["turn:turn-10:output"]
            summary_code = summary["children"][0]
            assert summary["open"] and (summary_code["text"], summary_code["language"]) == (answer_text, answer_lang)
            if i in (1, 3, 4, 5, 6):
                output = nodes["3:output"]
                code = output["children"][0]
                assert output["open"] and (code["text"], code["language"]) == (tool_text, tool_lang)
                assert code.get("wrap", False) == (tool_lang == "text")
            else:
                assert "3:output" not in nodes
        catalogs.append((p.stdout, wire.READS.copy()))
    return b"".join(raw for raw,_ in catalogs), [reads for _,reads in catalogs]


def main():
    with tempfile.TemporaryDirectory(prefix="analysis-borrowed-output-") as path:
        root = Path(path)
        arms = {}
        for arm, count in [("stock", 12), ("candidate", 13)]:
            src = root / arm
            targets = Path(os.environ.get("R54_ANALYSIS_TARGETS", root / "targets")).resolve()
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
                output = run("cargo", "test", "--locked", "-p", PKG, *flags).decode()
                summary = next(line for line in output.splitlines() if line.startswith("test result:"))
                assert f"ok. {count} passed; 0 failed;" in summary, summary
                print(arm, profile, summary, flush=True)
            run("cargo", "build", "--release", "--locked", "-p", PKG)
            executable = targets / arm / "release" / "analysis"
            wire = ordinary(executable, src, env)
            main_rs = src / PACKAGE / "src/main.rs"
            start = "fn main() {\n    run(Analysis::default());\n}"
            source = main_rs.read_text()
            assert source.count(start) == 1
            main_rs.write_text(source.replace(start, (HERE / "probe.rs").read_text()))
            run("cargo", "build", "--release", "--locked", "-p", PKG)
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
