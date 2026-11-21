#!/usr/bin/env python3
"""Compare the real read_many_files JSON handler at both revisions. Requires Git and Rust."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess as sp
import tempfile

here = Path(__file__).resolve().parent
base = "9469e3b12529d08b1f4a76882693e2065e842c51"
p = argparse.ArgumentParser(description=__doc__)
p.add_argument("repository", type=Path)
p.add_argument("--local-compiler", type=Path, help="optional cached rustc wrapper: LIB_RS OUT")
args = p.parse_args()
repo = args.repository.resolve()
with tempfile.TemporaryDirectory(prefix="numbered-read-") as tmp:
    root = Path(tmp)
    (root / "workspace").mkdir()
    env = {**os.environ, "READ_MANY_WORKSPACE": str(root / "workspace")}
    env.setdefault("CARGO_TARGET_DIR", str(root / "target"))
    results = {}
    for arm in ("stock", "new"):
        tree = root / arm
        sp.run(["git", "clone", "-q", "--shared", "--no-checkout", repo, tree], check=True)
        sp.run(["git", "checkout", "-q", "--detach", base], cwd=tree, check=True)
        if arm == "new":
            sp.run(["git", "apply", "--check", here / "candidate.patch"], cwd=tree, check=True)
            sp.run(["git", "apply", here / "candidate.patch"], cwd=tree, check=True)
        src = tree / "tool/file-tools/src"
        shutil.copyfile(here / "probe.rs", src / "tests/r40_probe.rs")
        with (src / "tests.rs").open("a") as f:
            f.write("\nmod r40_probe;\n")
        if args.local_compiler:
            exe = root / "test-bin"
            sp.run([args.local_compiler.resolve(), src / "lib.rs", exe], check=True)
            cmd = [exe]
        else:
            cmd = ["cargo", "test", "--locked", "--release", "-p", "file-tools", "--lib", "--"]
        out = sp.check_output([*cmd, "tests::r40_probe::compare_read_many", "--exact",
                               "--test-threads=1", "--nocapture"], cwd=tree, env=env)
        wires, counts = {}, {}
        # The Rust test harness prefixes the test name to its first print.
        for row in out.splitlines():
            if b"COUNT " in row:
                label, repeat, n, size = row.split(b"COUNT ", 1)[1].decode().split()
                counts.setdefault(label, []).append((int(n), int(size)))
            if row.startswith(b"WIRE "):
                _, label, wire = row.split(b" ", 2)
                # Only the temp path in the intentionally invalid-file error is variable.
                wires[label.decode()] = wire.replace(str(root / "workspace").encode(), b"<fixture>")
        results[arm] = counts, wires
        shutil.rmtree(tree)
    stock, new = results["stock"], results["new"]
    assert len(stock[0]) == 8 and stock[1] == new[1] and len(stock[1]) == 8
    for label, wire in stock[1].items():
        a, b = stock[0][label], new[0][label]
        assert len(a) == len(b) == 3 and len(set(a)) == len(set(b)) == 1, (label,a,b)
        if label in ("short_lines", "budget_cut"):
            assert a[0][0] > b[0][0] and a[0][1] > b[0][1], label
        if label in ("bad_utf8", "unnumbered"):
            assert a == b, label
        reply = json.loads(wire)
        print(label, *a[0], "->", *b[0], "wire_bytes",len(wire),"sha256",hashlib.sha256(wire).hexdigest(),
              "returned", len(reply["output"].encode()))
