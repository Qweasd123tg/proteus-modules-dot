"""Test baseline and candidate ACP inbound prompt projection in one disposable Core tree."""
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
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("checkout", type=Path)
parser.add_argument("target", type=Path)
parser.add_argument("--in-owned-scratch-tree", action="store_true",
                    help="instrument this disposable tree in place rather than copying it")
args = parser.parse_args()
target = args.target.resolve()
target.mkdir(parents=True, exist_ok=True)
env = os.environ.copy()
env["CARGO_TARGET_DIR"] = str(target)
env.setdefault("CARGO_BUILD_JOBS", "2")
env.setdefault("CARGO_PROFILE_TEST_DEBUG", "0")
env.setdefault("CARGO_INCREMENTAL", "0")
env.setdefault("RUST_TEST_THREADS", "1")

def add(path, text):
    with path.open("a", encoding="utf-8") as f:
        f.write(text)

def suite(tree, label):
    dest = tree / f"r49-{label}.json"
    cmd = ["cargo", "test", "--locked", "--offline", "-p", "proteus-core", "--lib",
           "app_server::acp::", "--", "--nocapture", "--skip",
           "protocol_prompt_stays_reserved_after_runtime_has_settled"]
    run = subprocess.run(cmd, cwd=tree, env={**env, "R49_ACP_SNAPSHOT": str(dest)},
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    (target / f"r49-acp-prompt-{label}.log").write_text(run.stdout)
    if run.returncode:
        raise RuntimeError(run.stdout)
    print(label, next(line for line in run.stdout.splitlines() if line.startswith("test result:")), flush=True)
    rows = {name: (int(c),int(b)) for name,c,b in re.findall(
            r"r49 case=(\w+) calls=(\d+) bytes=(\d+)", run.stdout)}
    assert len(rows) == 14, rows
    return rows, dest.read_bytes()

scratch = (contextlib.nullcontext(None) if args.in_owned_scratch_tree
           else tempfile.TemporaryDirectory(prefix="core-r49-acp-"))
with scratch as temp:
    if temp is None:
        tree = args.checkout.resolve()
    else:
        tree = Path(temp) / "core"
        shutil.copytree(args.checkout, tree, ignore=shutil.ignore_patterns(".git", "target"))
    subprocess.run(["git", "apply", "--check", HERE / "source.patch"], cwd=tree, check=True)
    src = tree / "crates/proteus-core/src"
    shutil.copyfile(tree / "crates/proteus-contracts/src/test_alloc.rs", src / "r49_alloc.rs")
    add(src / "lib.rs", "\n#[cfg(test)]\nmod r49_alloc;\n")
    tests = src / "app_server/acp/tests"
    shutil.copyfile(HERE / "measure.rs", tests / "r49_probe.rs")
    add(tests.with_suffix(".rs"), "\nmod r49_probe;\n")
    base, old = suite(tree, "baseline")
    subprocess.run(["git", "apply", HERE / "source.patch"], cwd=tree, check=True)
    cand, new = suite(tree, "candidate")
    assert old == new, "wire output or errors changed between baseline and candidate"
    print(f"All serialized text / error snapshots match byte-for-byte ({len(new)} bytes; SHA256 {hashlib.sha256(new).hexdigest()}).")
    for case, (calls, size) in base.items():
        calls2, size2 = cand[case]
        if case.startswith("single_") or case == "annotations":
            assert calls2 < calls and size2 < size, (case, calls, calls2, size, size2)
        else:
            assert (calls2, size2) == (calls, size), (case, calls, calls2, size, size2)
        print(f"{case}: calls {calls}->{calls2}, bytes {size}->{size2}")
