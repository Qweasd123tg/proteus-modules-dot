#!/usr/bin/env python3
"""Reproduce without modifying the input checkout. Requires Rust 1.95, git, tar."""
import argparse
import pathlib
import shutil
import subprocess
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
BASE = "9469e3b12529d08b1f4a76882693e2065e842c51"
BUDGET = "context/context-pack/src/budget.rs"

parser = argparse.ArgumentParser()
parser.add_argument("checkout", type=pathlib.Path)
parser.add_argument("--cached-rustc", nargs="+", metavar="RUSTC_ARG",
                    help="compiler-argument file (one argument per line); uses already-built locked deps, no Cargo build")
args = parser.parse_args()
repo = args.checkout.resolve()
with tempfile.TemporaryDirectory(prefix="context-budget-") as raw:
    dest = pathlib.Path(raw)
    with (dest / "tree.tar").open("wb") as out:
        subprocess.run(["git", "-C", repo, "archive", BASE], stdout=out, check=True)
    subprocess.run(["tar", "-xf", "tree.tar"], cwd=dest, check=True)
    crate = dest / "context/context-pack"
    tests = crate / "tests"
    tests.mkdir(exist_ok=True)
    generated = tests / "probe-fixtures"
    generated.mkdir()
    shutil.copyfile(dest / BUDGET, generated / "budget-before.rs")
    subprocess.run(["git", "apply", HERE / "source.patch"], cwd=dest, check=True)
    shutil.copyfile(dest / BUDGET, generated / "budget-after.rs")
    (tests / "budget_probe.rs").write_text((HERE / "probe.rs").read_text().replace(
        '#[path = "budget-', '#[path = "probe-fixtures/budget-'))
    if args.cached_rustc:
        flags = [arg for f in args.cached_rustc for arg in pathlib.Path(f).read_text().splitlines()]
        for source, name, opt in [(crate / "src/lib.rs", "context_pack", []),
                                  (tests / "budget_probe.rs", "budget_probe", ["-O"])]:
            subprocess.run(["rustc", "--edition=2024", "--test", "--crate-name", name, *opt,
                            *flags, source, "-o", dest / name], cwd=dest, check=True)
            subprocess.run([dest / name, "--nocapture", "--test-threads=1"], cwd=dest, check=True)
    else:
        subprocess.run(["cargo", "test", "--locked", "--release", "-p", "context-pack",
                        "--lib", "--test", "budget_probe", "--", "--nocapture", "--test-threads=1"],
                       cwd=dest, check=True)
