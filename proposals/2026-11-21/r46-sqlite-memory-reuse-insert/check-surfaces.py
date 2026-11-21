#!/usr/bin/env python3
"""Run identical supplemental export, external WAL and metadata tests on both trees."""
import argparse, os, shutil, subprocess as sp, tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
BASE = "9469e3b12529d08b1f4a76882693e2065e842c51"
p = argparse.ArgumentParser(description=__doc__)
p.add_argument("repo", type=Path)
args = p.parse_args()
with tempfile.TemporaryDirectory(prefix="r46-sqlite-surfaces-") as td:
    t = Path(td)
    for arm in ("base", "candidate"):
        print(f"--- {arm} ---", flush=True)
        tree = t / arm
        sp.run(["git", "clone", "-q", "--shared", "--no-checkout", args.repo.resolve(), tree], check=True)
        sp.run(["git", "checkout", "--detach", "-q", BASE], cwd=tree, check=True)
        if arm == "candidate":
            sp.run(["git", "apply", HERE / "candidate.patch"], cwd=tree, check=True)
        crate = tree / "context_provider/sqlite-memory/src"
        shutil.copyfile(HERE / "surface-probe.rs", crate / "tests/r46_surface_probe.rs")
        path = crate / "lib.rs"
        original = path.read_text()
        assert original.count("    mod recall;") == 1
        path.write_text(original.replace("    mod recall;", "    mod recall;\n    mod r46_surface_probe;"))
        sp.run(
            ["cargo", "test", "--locked", "-p", "sqlite-memory", "--lib", "tests::r46_surface_probe"],
            cwd=tree, check=True, env={**os.environ, "CARGO_TARGET_DIR": os.environ.get("CARGO_TARGET_DIR", str(t / "target"))},
        )
