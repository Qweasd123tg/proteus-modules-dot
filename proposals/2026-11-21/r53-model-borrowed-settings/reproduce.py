#!/usr/bin/env python3
"""Compare exact pre/post Model package tests, ordinary frames and allocations."""
from copy import deepcopy
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess as sp
import sys
import tempfile

BASE = "892f627570369ed60d7205eb0d351c753ec4305f"
HERE = Path(__file__).resolve().parent
PKG = "extension-model"
PACKAGE = Path("packages/model")
SESSION = "/model-fixture-session"
CONTEXT = "model-fixture"


def ordinary(exe, src, env):
    features = json.loads((src / PACKAGE / "extension.json").read_text())["required_features"]
    hello = {"type": "hello", "protocol": 4, "features": features, "workspace": "/model-panel-fixture"}

    def select(key, chosen, options):
        return {"id": key, "name": key, "control": {"type": "select", "value": chosen, "options": options}}

    def option(value, name):
        return {"value": value, "name": name}

    config = {
        "profile": "fixture",
        "model": {"name": "one"},
        "model_options": [{"name": "one", "provider": "A", "default_reasoning_effort": "high"}, {"name": "two", "provider": "B"}],
        "session_settings": [
            select("model", "one", [option("one", "One"), option("two", "Two")]),
            select("reasoning_effort", "_default", [
                option("_default", "Profile"), option("effort:low", "First low"),
                option("effort:low", "Ignored low"), option({"invalid": True}, "Ignored object"),
                option("effort:high", "First high"),
            ]),
            select("provider/style", "short", [option("short", "Кратко"), option("long", "Подробно")]),
            {"id": "slider", "control": {"type": "slider", "value": 1}},
        ],
    }

    def snapshot(state):
        return {"type": "session_snapshot", "context": CONTEXT, "session_dir": SESSION, "state": {"config": state}}

    def render(view, session=SESSION):
        return {"type": "render", "context": CONTEXT, "session_dir": session, "view": view, "surface": view}

    def action(view, seq, name, value=None):
        return {"type": "action", "view": view, "sequence": seq, "action": name, "value": value}

    def ack(id, state):
        return {"type": "command_result", "context": CONTEXT, "session_dir": SESSION, "id": id, "config": state}

    def close(view):
        return {"type": "close", "view": view}

    def run(frames):
        encoded = b"".join(json.dumps(x).encode() + b"\n" for x in frames)
        p = sp.run([exe], input=encoded, cwd=src / PACKAGE, env=env, capture_output=True, check=True, timeout=15)
        assert not p.stderr, p.stderr
        return p.stdout, [json.loads(line) for line in p.stdout.splitlines()]

    accepted = deepcopy(config)
    accepted["session_settings"][1]["control"]["value"] = "effort:low"
    unavailable = dict(config, model_catalog_error="Synthetic catalog unavailable")
    a, rows = run([
        hello, snapshot(config), render("popup"), action("popup", 1, "effort", 0),
        action("popup", 2, "effort", 0), ack("setting-1", accepted),
        action("popup", 3, "effort_reset"), ack("setting-2", config),
        action("popup", 4, "setting:provider/style", "long"),
        action("popup", 5, "models"), action("popup", 6, "escape"), snapshot(unavailable),
        close("popup"), render("badge"), close("badge"),
    ])
    by_type = lambda name: [row for row in rows if row["type"] == name]
    writes = by_type("set_session")
    assert [w["setting"] for w in writes] == [
        {"id": "reasoning_effort", "value": "effort:low"},
        {"id": "reasoning_effort", "value": "_default"},
        {"id": "provider/style", "value": "long"},
    ], writes
    assert all(w["session_dir"] == SESSION and w["context"] == CONTEXT and w["view"] == "popup" for w in writes)
    views = by_type("view")
    assert [v["sequence"] for v in views] == [0, 1, 2, 2, 3, 3, 4, 5, 6, 6], views
    assert [v["root"]["transition"] for v in views] == ["summary"] * 7 + ["models", "summary", "catalog-error"]
    for i, expected in enumerate([1, 0, 0, 0, 1, 1, 1]):
        steps = next(node for node in views[i]["root"]["children"] if node["type"] == "steps")
        assert steps["options"] == ["First low", "First high"] and steps["selected"] == expected, steps
    select_long = next(node for node in views[6]["root"]["children"] if node["type"] == "select")
    assert [option["selected"] for option in select_long["options"]] == [False, True]
    assert len(by_type("badge")) == 1
    assert "Synthetic catalog unavailable" in str(views[-1])

    b, preview = run([
        hello, render("preview", None), action("preview", 1, "effort", 0),
        action("preview", 2, "effort", 1), action("preview", 3, "effort_reset"),
        action("preview", 4, "effort", 99), close("preview"),
    ])
    assert len(preview) == 5 and all(row["type"] == "view" for row in preview), preview
    assert [
        next(node["selected"] for node in row["root"]["children"] if node["type"] == "steps") for row in preview
    ] == [1, 0, 1, 1, 1], preview
    return a + b


def main():
    with tempfile.TemporaryDirectory(prefix="model-borrowed-settings-") as path:
        root = Path(path)
        arms = {}
        for arm, count in [("stock", 10), ("candidate", 11)]:
            src = root / arm
            targets = Path(os.environ.get("R53_MODEL_TARGETS", root / "targets")).resolve()
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
            executable = targets / arm / "release" / "model"
            wire = ordinary(executable, src, env)
            main_rs = src / PACKAGE / "src/main.rs"
            start = "fn main() {\n    run(Model::default());\n}"
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
        for label, content in [("ordinary protocol frames", a[0]), ("instrumented trees and labels", a[1])]:
            print(label, len(content.splitlines()), len(content), sha256(content).hexdigest())
        print("allocator calls, requested bytes and output count/bytes: 5 identical observations per arm")
        for arm, (_, _, counts) in arms.items():
            for line in counts.decode().splitlines():
                print(arm, line)


if __name__ == "__main__":
    main()
