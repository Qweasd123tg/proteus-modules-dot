"""Run production cold-render tests before/after the source-only patch."""
from pathlib import Path
import argparse
import os
import re
import shutil
import subprocess
import tempfile

SHA = "32e56ecb4cc6da324c60dd6ae2da78f3b7e46e7f"
SRC = Path("crates/proteus-core/src")
TEST_ALLOC = Path("crates/proteus-contracts/src/test_alloc.rs")
HERE = Path(__file__).resolve().parent

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("checkout", type=Path,
                    help=f"clean checkout/archive of Proteus-core@{SHA}")
parser.add_argument("target", type=Path, help="Cargo target directory, shared between runs")
args = parser.parse_args()
target = str(args.target.resolve())
env = os.environ.copy()
env["CARGO_TARGET_DIR"] = target
env.setdefault("CARGO_BUILD_JOBS", "2")
env.setdefault("CARGO_PROFILE_TEST_DEBUG", "0")
env.setdefault("CARGO_INCREMENTAL", "0")
env.setdefault("RUST_TEST_THREADS", "1")

def paste(path, text):
    with path.open("a", encoding="utf-8") as handle:
        handle.write(text)

def run_suite(tree, label, log):
    local_env = dict(env)
    local_env["PROTEUS_TRANSCRIPT_PROBE_OUTPUT"] = str(tree / f"{label}.json")
    cmd = ["cargo", "test", "--locked", "--offline", "-p", "proteus-core", "--lib",
           "app_server::transcript::", "--", "--nocapture"]
    result = subprocess.run(cmd, cwd=tree, env=local_env,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    log.write_text(result.stdout, encoding="utf-8")
    print(label, log, flush=True)
    if result.returncode:
        raise RuntimeError(result.stdout)
    rows = {}
    for line in result.stdout.splitlines():
        m = re.search(r"measure kind=(\w+) messages=(\d+) rows=(\d+) calls=(\d+) bytes=(\d+)", line)
        if m:
            kind, count, n, calls, size = m.groups()
            rows[kind, int(count)] = tuple(map(int, (n, calls, size)))
        if line.startswith("test result:"):
            print(line)
    assert len(rows) == 7, rows
    return rows, Path(local_env["PROTEUS_TRANSCRIPT_PROBE_OUTPUT"]).read_bytes()

target = Path(target)
target.mkdir(parents=True, exist_ok=True)
with tempfile.TemporaryDirectory(prefix="proteus-r46-core-") as temp:
    tree = Path(temp) / "core"
    shutil.copytree(args.checkout, tree, ignore=shutil.ignore_patterns(".git", "target"))
    subprocess.run(["git", "apply", "--check", HERE / "source.patch"], cwd=tree, check=True)
    journal = tree / SRC / "app_server/transcript/journal"
    (journal / "source").mkdir(exist_ok=True)
    shutil.copyfile(HERE / "measure.rs", journal / "source/measure.rs")
    paste(journal / "source.rs", "\n#[cfg(test)]\nmod measure;\n")
    shutil.copyfile(tree / TEST_ALLOC, tree / SRC / "r46_alloc.rs")
    paste(tree / SRC / "lib.rs", "\n#[cfg(test)]\nmod r46_alloc;\n")

    a, baseline = run_suite(tree, "baseline", target / "r46-stock.log")
    subprocess.run(["git", "apply", HERE / "source.patch"], cwd=tree, check=True)
    b, candidate = run_suite(tree, "candidate", target / "r46-candidate.log")
    assert baseline == candidate, "serialized transcript mismatch"
    print("Byte-for-byte equality for all seven fixture transcripts")
    for (kind, count), (rows, before_calls, before_bytes) in a.items():
        after_rows, after_calls, after_bytes = b[kind, count]
        assert rows == after_rows
        expected_calls_saved = (2 if kind == "single" else 1) * count
        assert before_calls - after_calls == expected_calls_saved
        assert before_bytes >= after_bytes
        print(f"{kind:10} {count:4} messages {rows:4} rows; calls "
              f"{before_calls}->{after_calls}; requested bytes {before_bytes}->{after_bytes}")
