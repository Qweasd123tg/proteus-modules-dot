#!/usr/bin/env python3
"""Compare optimized builds on real patch verify+apply, using only temporary checkouts."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import statistics
import subprocess as sp
import tempfile

BASE = "9469e3b12529d08b1f4a76882693e2065e842c51"
HERE = Path(__file__).resolve().parent
p = argparse.ArgumentParser(description=__doc__)
p.add_argument("repo", type=Path)
p.add_argument("--local-compiler", type=Path, help="optional rustc wrapper using pinned cached dependencies: LIB_RS OUTPUT")
p.add_argument("--rounds", type=int, default=8)
args = p.parse_args()
if args.rounds < 2:
    p.error("--rounds must be >= 2")
repo = args.repo.resolve()
arms = ("base", "candidate")
timings = {a: {} for a in arms}
with tempfile.TemporaryDirectory(prefix="r44-patch-") as td:
    temp = Path(td)
    fixture = temp/"workspace"
    fixture.mkdir()
    env = {**os.environ, "CODEX_PATCH_FIXTURE": str(fixture)}
    target = Path(env.get("CARGO_TARGET_DIR", temp/"target")).resolve()
    for arm in arms:
        tree = temp/f"src-{arm}"
        sp.run(["git", "clone", "-q", "--shared", "--no-checkout", repo, tree], check=True)
        if args.local_compiler:
            sp.run(["git", "sparse-checkout", "set", "tool/codex-patch"], cwd=tree, check=True)
        sp.run(["git", "checkout", "-q", "--detach", BASE], cwd=tree, check=True)
        if arm == "candidate":
            sp.run(["git", "apply", "--check", HERE/"candidate.patch"], cwd=tree, check=True)
            sp.run(["git", "apply", HERE/"candidate.patch"], cwd=tree, check=True)
        src = tree/"tool/codex-patch/src"
        (src/"tests").mkdir(exist_ok=True)
        shutil.copyfile(HERE/"probe.rs", src/"tests/r44_probe.rs")
        with (src/"tests.rs").open("a") as f:
            f.write("\nmod r44_probe;\n")
        exe = temp/f"exe-{arm}"
        if args.local_compiler:
            sp.run([args.local_compiler.resolve(), src/"lib.rs", exe], check=True)
        else:
            cmd = ["cargo","test","--release","--locked","-p","codex-patch","--lib","--no-run","--message-format=json"]
            lines = sp.check_output(cmd, cwd=tree, env={**env, "CARGO_TARGET_DIR": str(target/f"r44-{arm}")}, text=True).splitlines()
            artifacts = [v["executable"] for v in map(json.loads,lines)
                         if v.get("executable") and v["target"]["name"] == "codex_patch"]
            assert len(artifacts) == 1, artifacts
            shutil.copy2(artifacts[0], exe)
        (temp/arm).mkdir()
    for arm in arms:
        env["CODEX_PATCH_OUTPUT"] = str(temp/arm)
        sp.run([temp/f"exe-{arm}", "tests::r44_probe::differential_small_hunks", "--exact"], env=env, check=True, stdout=sp.DEVNULL)
    records = (temp/"base/small.jsonl").read_bytes()
    assert records == (temp/"candidate/small.jsonl").read_bytes()
    assert records.count(b"\n") == 6272
    ok = sum("Ok" in json.loads(rec) for rec in records.splitlines())
    print(f"two-hunk parity: {ok} ok, {6272-ok} errors; identical {hashlib.sha256(records).hexdigest()}")
    for lap in range(-1, args.rounds):
        for arm in (arms if lap % 2 == 0 else arms[::-1]):
            env["CODEX_PATCH_OUTPUT"] = str(temp/arm)
            log = sp.check_output([temp/f"exe-{arm}", "tests::r44_probe::measure_apply_patch", "--exact",
                                   "--nocapture","--test-threads=1"], env=env, text=True)
            rows = [s.split("R44 ",1)[1].split() for s in log.splitlines() if "R44 " in s]
            assert len(rows) == len({r[0] for r in rows}) == 5, rows
            if lap >= 0:
                for label, ns in rows:
                    timings[arm].setdefault(label,[]).append(int(ns))
    for label in timings["base"]:
        a = (temp/"base"/label).read_bytes()
        assert a == (temp/"candidate"/label).read_bytes()
        samples = [timings[arm][label] for arm in arms]
        med = [statistics.median(s)/1e6 for s in samples]
        print(f"{label}: median ms {med[0]:.3f} -> {med[1]:.3f}; sha256 {hashlib.sha256(a).hexdigest()}")
        for arm, s in zip(arms,samples):
            print(arm, "ns", *s)
