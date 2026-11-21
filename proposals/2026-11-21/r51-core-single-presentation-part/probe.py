"""Compare exact canonical text and reasoning output and allocations on clean Core."""
import argparse
import contextlib
import hashlib
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

HERE = Path(__file__).resolve().parent
SRC = Path("crates/proteus-contracts/src/model_standard")
p = argparse.ArgumentParser(description=__doc__)
p.add_argument("checkout", type=Path)
p.add_argument("cargo_target", type=Path)
p.add_argument("--in-owned-scratch-tree", action="store_true",
               help="instrument a disposable copy in place instead of making a temporary copy")
p.add_argument("--check-existing", action="store_true",
               help="verify completed probe outputs from a previous disposable-tree run")
args = p.parse_args()
target = args.cargo_target.resolve()
target.mkdir(parents=True, exist_ok=True)
env = dict(os.environ, CARGO_TARGET_DIR=str(target))
for k, v in {"CARGO_BUILD_JOBS": "1", "CARGO_PROFILE_TEST_DEBUG": "0",
             "CARGO_INCREMENTAL": "0", "RUST_TEST_THREADS": "1"}.items():
    env.setdefault(k, v)

def suite(tree, label):
    dest = tree / f"r51-{label}.json"
    cmd = ["cargo", "test", "--locked", "--offline", "-p", "proteus-contracts",
           "--lib", "--", "--nocapture"]
    log = subprocess.run(cmd, cwd=tree,
                         env={**env, "R51_PRESENTATION_SNAPSHOT": str(dest)},
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    (target / f"r51-contracts-{label}.log").write_text(log.stdout)
    if log.returncode:
        raise RuntimeError(log.stdout)
    return result(tree, label)

def result(tree, label):
    log = (target / f"r51-contracts-{label}.log").read_text()
    print(label, next(line for line in log.splitlines()
                      if line.startswith("test result: ok.")), flush=True)
    rows = {n: tuple(map(int, counts)) for n, *counts in re.findall(
        r"r51 (\w+) display=(\d+) (\d+) thought=(\d+) (\d+)", log)}
    assert len(rows) == 11, rows
    return rows, (tree / f"r51-{label}.json").read_bytes()

def compare(first, second):
    base, a = first
    cand, b = second
    assert a == b, "Serialized presentation output mismatch"
    print(f"3,136 fixtures; exact serialized parity: {len(a)} bytes; SHA256 {hashlib.sha256(a).hexdigest()}")
    affected = {"single_text": (1,0), "single_reasoning": (0,1), "single_summary": (0,1),
                "mixed_single": (1,1), "text_64k": (1,0), "text_2": (0,1), "thought_3": (1,0)}
    for mode, (d0, db0, t0, tb0) in base.items():
        d1, db1, t1, tb1 = cand[mode]
        dd, td = affected.get(mode, (0,0))
        assert (d0-d1, t0-t1) == (dd, td), (mode, d0, d1, t0, t1)
        assert db1 < db0 if dd else db1 == db0
        assert tb1 < tb0 if td else tb1 == tb0
        print(f"{mode}: display calls {d0}->{d1}, bytes {db0}->{db1}; "
              f"reasoning calls {t0}->{t1}, bytes {tb0}->{tb1}")

if args.check_existing:
    compare(result(args.checkout, "baseline"), result(args.checkout, "candidate"))
    raise SystemExit(0)

scratch = (contextlib.nullcontext(None) if args.in_owned_scratch_tree
           else tempfile.TemporaryDirectory(prefix="proteus-r51-"))
with scratch as temp:
    if temp is None:
        tree = args.checkout.resolve()
    else:
        tree = Path(temp) / "core"
        shutil.copytree(args.checkout, tree, ignore=shutil.ignore_patterns(".git", "target"))
    subprocess.run(["git", "apply", "--check", HERE / "source.patch"], cwd=tree, check=True)
    shutil.copyfile(HERE / "measure.rs", tree / SRC / "content_part_probe.rs")
    with (tree / SRC / "content_part.rs").open("a", encoding="utf-8") as f:
        f.write('\n#[cfg(test)]\n#[path = "content_part_probe.rs"]\nmod r51_probe;\n')
    first = suite(tree, "baseline")
    subprocess.run(["git", "apply", HERE / "source.patch"], cwd=tree, check=True)
    compare(first, suite(tree, "candidate"))
