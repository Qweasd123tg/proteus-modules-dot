"""Compare exact estimate metadata decoding and allocations on clean Core."""
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
    dest = tree / f"r53-{label}.json"
    cmd = ["cargo", "test", "--locked", "--offline", "-p", "proteus-contracts",
           "--lib", "--", "--nocapture"]
    log = subprocess.run(cmd, cwd=tree,
                         env={**env, "R53_ESTIMATE_SNAPSHOT": str(dest)},
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    (target / f"r53-contracts-{label}.log").write_text(log.stdout)
    if log.returncode:
        raise RuntimeError(log.stdout)
    return result(tree, label)

def result(tree, label):
    log = (target / f"r53-contracts-{label}.log").read_text()
    print(label, next(line for line in log.splitlines()
                      if line.startswith("test result: ok.")), flush=True)
    rows = {n: (int(c), int(b)) for n,c,b in re.findall(
        r"r53 (\w+): calls=(\d+) bytes=(\d+)", log)}
    assert len(rows) == 19, rows
    return rows, (tree / f"r53-{label}.json").read_bytes()

def compare(first, second):
    base, a = first
    cand, b = second
    assert a == b, "serialized estimates or rejected inputs changed"
    print(f"1,315 fixtures; exact serialized parity: {len(a)} bytes; SHA256 {hashlib.sha256(a).hexdigest()}")
    for mode,(c0,b0) in base.items():
        c1,b1 = cand[mode]
        if mode in {"missing","scalar_metadata","null_estimate","missing_parts"}:
            assert (c0,b0) == (c1,b1), (mode,c0,c1,b0,b1)
        else:
            assert c1 < c0 and b1 < b0, (mode,c0,c1,b0,b1)
        print(f"{mode}: calls {c0}->{c1}, bytes {b0}->{b1}")

if args.check_existing:
    compare(result(args.checkout, "baseline"), result(args.checkout, "candidate"))
    raise SystemExit(0)

scratch = (contextlib.nullcontext(None) if args.in_owned_scratch_tree
           else tempfile.TemporaryDirectory(prefix="proteus-r53-"))
with scratch as temp:
    if temp is None:
        tree = args.checkout.resolve()
    else:
        tree = Path(temp) / "core"
        shutil.copytree(args.checkout, tree, ignore=shutil.ignore_patterns(".git", "target"))
    subprocess.run(["git", "apply", "--check", HERE / "source.patch"], cwd=tree, check=True)
    shutil.copyfile(HERE / "measure.rs", tree / SRC / "estimate_r53_probe.rs")
    with (tree / SRC / "input_estimates.rs").open("a", encoding="utf-8") as f:
        f.write('\n#[cfg(test)]\n#[path = "estimate_r53_probe.rs"]\nmod r53_probe;\n')
    first = suite(tree, "baseline")
    subprocess.run(["git", "apply", HERE / "source.patch"], cwd=tree, check=True)
    compare(first, suite(tree, "candidate"))
