#!/usr/bin/env python3
"""Count parent Rust allocation traffic during real git-tools calls."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import statistics
import subprocess as sp
import sys
import tempfile

HERE = Path(__file__).resolve().parent
BASE = "9469e3b12529d08b1f4a76882693e2065e842c51"
p = argparse.ArgumentParser(description=__doc__)
p.add_argument("repo", type=Path)
p.add_argument("--rounds", type=int, default=9)
args = p.parse_args()
if args.rounds < 3:
    p.error("use at least three pairs")
repo = args.repo.resolve()
arms = ("base", "candidate")
with tempfile.TemporaryDirectory(prefix="r47-git-tools-") as td:
    temp = Path(td)
    target = Path(os.environ.get("CARGO_TARGET_DIR", temp/"target")).resolve()
    env = {**os.environ, "CARGO_TARGET_DIR": str(target), "LC_ALL": "C",
           "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull}
    for key in ("GIT_CONFIG_COUNT", "GIT_CONFIG_PARAMETERS", "GIT_DIR", "GIT_WORK_TREE",
                "GIT_INDEX_FILE", "GIT_COMMON_DIR", "GIT_PREFIX"):
        env.pop(key, None)
    for arm in arms:
        tree = temp / arm
        sp.run(["git", "clone", "-q", "--shared", "--no-checkout", repo, tree], check=True)
        sp.run(["git", "checkout", "-q", "--detach", BASE], cwd=tree, check=True)
        if arm == "candidate":
            sp.run(["git", "apply", "--check", HERE/"candidate.patch"], cwd=tree, check=True)
            sp.run(["git", "apply", HERE/"candidate.patch"], cwd=tree, check=True)
        crate = tree/"tool/git-tools/src"
        shutil.copyfile(HERE/"probe.rs", crate/"r47_probe.rs")
        with (crate/"lib.rs").open("a") as f:
            f.write("\n#[cfg(test)]\nmod r47_probe;\n")
        cmd = ["cargo", "test", "--locked", "--release", "-p", "git-tools", "--lib", "--no-run",
               "--message-format=json"]
        proc = sp.run(cmd, cwd=tree, env=env, text=True, stdout=sp.PIPE)
        messages = [json.loads(row) for row in proc.stdout.splitlines()]
        if proc.returncode:
            for m in messages:
                if m.get("reason") == "compiler-message":
                    print(m["message"].get("rendered", ""), file=sys.stderr)
            proc.check_returncode()
        exes = [m["executable"] for m in messages if
                m.get("executable") and m["target"]["name"] == "git_tools"]
        assert len(exes) == 1, exes
        shutil.copy2(exes[0], temp/f"{arm}.exe")

    work = temp/"git-project"
    work.mkdir()
    outside = temp/"not-a-git-repo"
    outside.mkdir()
    def git(*argv):
        return sp.check_output(["git", *argv], cwd=work, env=env)
    git("init", "-q", "-b", "trunk")
    git("config", "core.autocrlf", "false")
    entries = {
        "large.txt": "".join(f"new {i:04} " + "x"*160 + "\n" for i in range(1800)).encode(),
        "small.txt": b"first\nsecond saved line\n",
        "cut.txt": "start\nbyte boundary 💡\n".encode(),
        "invalid.txt": b"start\nunderstood as text: \xff\n",
        "unchanged.txt": b"stable\n",
    }
    for path in entries:
        (work/path).write_bytes(entries[path] if path=="unchanged.txt" else b"start\n")
    git("add", "--", *entries)
    for path, data in entries.items():
        (work/path).write_bytes(data)
    def raw_diff(path):
        return git("diff", "--no-ext-diff", "--no-textconv", "--unified=3", "--", path)
    cut = raw_diff("cut.txt").index("💡".encode()) + 2

    def check(name, result, cap, raw):
        assert result["ok"] == (name != "not-a-repo"), result
        meta = result["metadata"]
        if raw is None:
            if name == "not-a-repo":
                assert meta["stdout_bytes"] == 0 and meta["stderr_bytes"] > 0, result
                assert "not a git repository" in result["output"], result
            else:
                assert name == "status" and "small.txt" in result["output"], result
            return
        assert meta["stdout_bytes"] == len(raw) and meta["stderr_bytes"] == 0, result
        assert meta["stdout_truncated"] == (len(raw)>cap), result
        expected = raw[:cap].decode("utf-8", errors="replace") if raw else "(no diff)"
        assert result["output"] == expected, name

    cap = 200 * 1024
    cases = (
        ("large-capped", "git_diff", work, {"path": "large.txt", "max_bytes": cap}, raw_diff("large.txt")),
        ("small", "git_diff", work, {"path": "small.txt"}, raw_diff("small.txt")),
        ("utf8-cut", "git_diff", work, {"path": "cut.txt", "max_bytes": cut}, raw_diff("cut.txt")),
        ("invalid-bytes", "git_diff", work, {"path": "invalid.txt"}, raw_diff("invalid.txt")),
        ("no-diff", "git_diff", work, {"path": "unchanged.txt"}, b""),
        ("status", "git_status", work, {}, None),
        ("not-a-repo", "git_status", outside, {}, None),
    )
    for label, tool, cwd, tool_args, raw in cases:
        out = temp/"result.json"
        invocation = {**env, "R47_CWD":str(cwd), "R47_NAME":tool,
                      "R47_ARGS":json.dumps(tool_args), "R47_OUT":str(out)}
        canonical = None
        samples = {a:[] for a in arms}
        for lap in range(-1, args.rounds):
            for a in (arms if lap%2==0 else arms[::-1]):
                log = sp.check_output([temp/f"{a}.exe", "r47_probe::measure_git_tool",
                                       "--exact", "--nocapture", "--test-threads=1"],
                                      env=invocation, text=True)
                m = re.search(r"R47 (\d+) (\d+) (\d+)",log)
                assert m, log
                raw_result=out.read_bytes()
                if canonical is None:
                    canonical=raw_result
                    check(label,json.loads(canonical),tool_args.get("max_bytes",65536),raw)
                assert raw_result==canonical,(label,a,lap)
                if lap>=0:
                    samples[a].append(tuple(map(int,m.groups())))
        print(f"{label}: identical reply ({len(canonical)} bytes), sha256 {hashlib.sha256(canonical).hexdigest()}")
        for a in arms:
            med=tuple(statistics.median(series) for series in zip(*samples[a]))
            print(f" {a} median requested bytes/alloc calls/ns {med}; raw {samples[a]}")
