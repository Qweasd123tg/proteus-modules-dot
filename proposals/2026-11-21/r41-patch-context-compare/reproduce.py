#!/usr/bin/env python3
"""Compare actual Codex patch verification/application, file bytes and replies on both revisions."""
import argparse
import hashlib
import os
from pathlib import Path
import shutil
import subprocess as sp
import tempfile

base = "9469e3b12529d08b1f4a76882693e2065e842c51"
here = Path(__file__).resolve().parent
p = argparse.ArgumentParser(description=__doc__)
p.add_argument("repository", type=Path)
p.add_argument("--local-compiler", type=Path, help="optional rustc wrapper with cached dependencies: LIB_RS OUT")
args = p.parse_args()
repo = args.repository.resolve()
with tempfile.TemporaryDirectory(prefix="codex-patch-parity-") as td:
    root = Path(td)
    fixture = root / "workspace"
    fixture.mkdir()
    env = {**os.environ, "CODEX_PATCH_FIXTURE": str(fixture)}
    env.setdefault("CARGO_TARGET_DIR", str(root / "target"))
    results = {}
    for arm in ("base", "candidate"):
        tree = root / "src"
        sp.run(["git", "clone", "-q", "--shared", "--no-checkout", repo, tree], check=True)
        if args.local_compiler:
            sp.run(["git", "sparse-checkout", "set", "tool/codex-patch"], cwd=tree, check=True)
        sp.run(["git", "checkout", "-q", "--detach", base], cwd=tree, check=True)
        if arm == "candidate":
            sp.run(["git", "apply", "--check", here / "candidate.patch"], cwd=tree, check=True)
            sp.run(["git", "apply", here / "candidate.patch"], cwd=tree, check=True)
        src = tree / "tool/codex-patch/src"
        tests = src / "tests"
        tests.mkdir(exist_ok=True)
        shutil.copyfile(here / "probe.rs", tests / "r41_probe.rs")
        with (src / "tests.rs").open("a") as f:
            f.write("\nmod r41_probe;\n")
        if args.local_compiler:
            exe = root / "test-bin"
            sp.run([args.local_compiler.resolve(), src / "lib.rs", exe], check=True)
            cmd = [exe]
        else:
            cmd = ["cargo", "test", "--release", "--locked", "-p", "codex-patch", "--lib", "--"]
        (root / arm).mkdir()
        env["CODEX_PATCH_OUTPUT"] = str(root / arm)
        log = sp.check_output([*cmd, "tests::r41_probe::compare_apply_patch", "--exact", "--nocapture", "--test-threads=1"], cwd=tree, env=env, text=True)
        counts = {}
        for row in log.splitlines():
            if "COUNT " in row:
                label, repeat, calls, size = row.split("COUNT ",1)[1].split()
                assert int(repeat) == len(counts.setdefault(label, []))
                counts[label].append((int(calls),int(size)))
        assert len(counts) == 9 and all(len(v) == 3 and len(set(v)) == 1 for v in counts.values())
        results[arm] = {k:v[0] for k,v in counts.items()}
        shutil.rmtree(tree)
    for label, before in results["base"].items():
        after = results["candidate"][label]
        for suffix in ("file", "result"):
            a = (root / "base" / f"{label}.{suffix}").read_bytes()
            b = (root / "candidate" / f"{label}.{suffix}").read_bytes()
            assert a == b, (label, suffix)
            if suffix == "file":
                digest = hashlib.sha256(b).hexdigest()
        if label in ("exact", "rstrip", "strict_precedence"):
            assert before == after, label
        else:
            assert before[0] > after[0] and before[1] > after[1], label
        print(f"{label}: allocations {before[0]} -> {after[0]}; requested bytes {before[1]} -> {after[1]}; file sha256 {digest}; Result bytes identical")
