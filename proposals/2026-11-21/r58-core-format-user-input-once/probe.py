"""Compare exact answer formatting and run real request_user_input smoke tests."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

HERE = Path(__file__).resolve().parent
SRC = Path("crates/proteus-core/src")
FORMATTER = SRC / "tools/request_user_input.rs"
p = argparse.ArgumentParser(description=__doc__)
p.add_argument("checkout", type=Path)
p.add_argument("target", type=Path)
args = p.parse_args()
target = args.target.resolve()
target.mkdir(parents=True, exist_ok=True)
env = dict(os.environ, CARGO_TARGET_DIR=str(target))
for key, value in {"CARGO_BUILD_JOBS":"1", "CARGO_PROFILE_TEST_DEBUG":"0",
                   "CARGO_PROFILE_DEV_DEBUG":"0", "CARGO_INCREMENTAL":"0",
                   "RUST_TEST_THREADS":"1"}.items():
    env.setdefault(key, value)
for key in ("PROTEUS_TEST_REFERENCE_MODULE", "PROTEUS_TEST_SESSION_STORAGE_MODULE"):
    path = env.get(key)
    if not path or not Path(path).is_file() or not os.access(path, os.X_OK):
        p.error(f"set {key} to the appropriate local Core process fixture executable")
    env[key] = str(Path(path).resolve())

with tempfile.TemporaryDirectory(prefix="proteus-r58-answer-") as d:
    work = Path(d)
    tree = work / "core"
    shutil.copytree(args.checkout, tree, ignore=shutil.ignore_patterns(".git", "target"))
    source = tree / FORMATTER
    stock = source.read_text()
    low = stock.index("fn format_user_input_response(")
    high = stock.index("\n#[cfg(test)]", low)
    body = stock[low:high].replace("fn format_user_input_response(", "fn stock_format_user_input_response(", 1)
    subprocess.run(["git","apply","--check",HERE/"source.patch"], cwd=tree, check=True)
    subprocess.run(["git","apply",HERE/"source.patch"], cwd=tree, check=True)
    shutil.copyfile(HERE/"measure.rs",source.parent/"r58_answer_probe.rs")
    shutil.copyfile(tree/"crates/proteus-contracts/src/test_alloc.rs",tree/SRC/"r58_alloc.rs")
    with source.open("a", encoding="utf-8") as f:
        f.write("\n#[cfg(test)]\n"+body)
        f.write('\n#[cfg(test)]\n#[path = "r58_answer_probe.rs"]\nmod r58_probe;\n')
    with (tree/SRC/"lib.rs").open("a", encoding="utf-8") as f:
        f.write("\n#[cfg(test)]\nmod r58_alloc;\n")
    snap = work/"results.json"
    command = ["cargo","test","--locked","--offline","-p","proteus-core","--lib","--",
               "tools::request_user_input::",
               "app_server::user_inputs::tests::",
               "route_send_user_input_loop_completes_after_http_response",
               "--nocapture"]
    run = subprocess.run(command, cwd=tree, env={**env,"R58_ANSWER_SNAPSHOT":str(snap)},
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    (target/"r58-answer-format.log").write_text(run.stdout)
    if run.returncode:
        raise RuntimeError(run.stdout)
    items = [l[l.index("r58 "):] for l in run.stdout.splitlines() if "r58 " in l]
    assert len(items) == 8, items
    for line in items:
        print(line)
    for line in run.stdout.splitlines():
        if (line.startswith("test ") and line.endswith(" ... ok")) or line.startswith("test result:"):
            print(line)
    assert "route_send_user_input_loop_completes_after_http_response ... ok" in run.stdout
    data = snap.read_bytes()
    assert len(json.loads(data)) == 1088
    print(f"1,088 byte-identical formatter outputs ({len(data)} serialized bytes), SHA256 {hashlib.sha256(data).hexdigest()}")
