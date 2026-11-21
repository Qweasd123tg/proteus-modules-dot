"""Run exact framed bytes and storage-refresh/reconnect tests in one Core build."""
import argparse
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

HERE = Path(__file__).resolve().parent
SRC = Path("crates/proteus-core/src")
SSE = SRC / "app_server/http/sse.rs"
p = argparse.ArgumentParser(description=__doc__)
p.add_argument("checkout", type=Path)
p.add_argument("target", type=Path)
args = p.parse_args()
target = args.target.resolve()
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
target.mkdir(parents=True, exist_ok=True)

with tempfile.TemporaryDirectory(prefix="proteus-r59-sse-") as d:
    work = Path(d)
    tree = work / "core"
    shutil.copytree(args.checkout, tree, ignore=shutil.ignore_patterns(".git", "target"))
    source = tree / SSE
    pad = source.read_text()
    # Guard the baseline expression copied to measure.rs.
    old = "Frame::data(encode_sse_output(&StdioOutput::Event {\n"
    selected = pad.split(old)[1:3]
    assert len(selected) == 2
    assert all("event: Box::new(AppServerEvent::SessionCatalogUpdated)" in block.split("})));",1)[0]
               for block in selected)
    subprocess.run(["git","apply","--check",HERE/"source.patch"], cwd=tree, check=True)
    subprocess.run(["git","apply",HERE/"source.patch"], cwd=tree, check=True)
    shutil.copyfile(HERE/"measure.rs",source.parent/"r59_sse_probe.rs")
    shutil.copyfile(tree/"crates/proteus-contracts/src/test_alloc.rs",tree/SRC/"r59_alloc.rs")
    with source.open("a", encoding="utf-8") as f:
        f.write('\n#[cfg(test)]\n#[path = "r59_sse_probe.rs"]\nmod r59_probe;\n')
    with (tree/SRC/"lib.rs").open("a", encoding="utf-8") as f:
        f.write("\n#[cfg(test)]\nmod r59_alloc;\n")
    frame = work/"frame.bin"
    command = ["cargo","test","--locked","--offline","-p","proteus-core","--lib","--",
               "r59_catalog_update_frame_is_exact_and_reused",
               "app_server::http::tests::sse::",
               "--nocapture"]
    run = subprocess.run(command, cwd=tree, env={**env,"R59_CATALOG_FRAME":str(frame)},
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT,text=True)
    (target/"r59-sse-catalog-frame.log").write_text(run.stdout)
    if run.returncode:
        raise RuntimeError(run.stdout)
    items = [l[l.index("r59 "):] for l in run.stdout.splitlines() if "r59 " in l]
    assert len(items) == 5, items
    for line in items:
        print(line)
    for line in run.stdout.splitlines():
        if (line.startswith("test ") and line.endswith(" ... ok")) or line.startswith("test result:"):
            print(line)
    assert "stored_summary_updates_notify_the_http_stream ... ok" in run.stdout
    encoded = frame.read_bytes()
    print(f"Exact SSE payload {len(encoded)} bytes, SHA256 {hashlib.sha256(encoded).hexdigest()}")
