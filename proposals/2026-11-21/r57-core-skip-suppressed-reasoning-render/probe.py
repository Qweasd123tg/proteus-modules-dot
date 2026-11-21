"""Exercise exact stock and patched present_stream with one real Core test build."""
import argparse
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

HERE = Path(__file__).resolve().parent
SRC = Path("crates/proteus-core/src")
F = SRC / "core/bound_model/presentation.rs"
p = argparse.ArgumentParser(description=__doc__)
p.add_argument("checkout", type=Path)
p.add_argument("target", type=Path)
a = p.parse_args()
env = dict(os.environ, CARGO_TARGET_DIR=str(a.target.resolve()))
for key,val in {"CARGO_BUILD_JOBS":"1", "CARGO_PROFILE_TEST_DEBUG":"0",
                "CARGO_PROFILE_DEV_DEBUG":"0", "CARGO_INCREMENTAL":"0",
                "RUST_TEST_THREADS":"1"}.items():
    env.setdefault(key,val)
for key in ("PROTEUS_TEST_REFERENCE_MODULE", "PROTEUS_TEST_SESSION_STORAGE_MODULE"):
    fixture = env.get(key)
    if not fixture or not Path(fixture).is_file() or not os.access(fixture, os.X_OK):
        p.error(f"set {key} to the appropriate Core process fixture executable")
    env[key] = str(Path(fixture).resolve())
target = a.target.resolve()
target.mkdir(parents=True, exist_ok=True)

with tempfile.TemporaryDirectory(prefix="proteus-r57-presentation-") as d:
    root = Path(d)
    tree = root / "core"
    shutil.copytree(a.checkout, tree, ignore=shutil.ignore_patterns(".git", "target"))
    src = tree / F
    stock = src.read_text()
    low = stock.index("pub(super) fn present_stream(")
    high = stock.index("#[derive(Default)]", low)
    body = stock[low:high].replace("pub(super) fn present_stream(", "fn stock_present_stream(")
    body = body.replace(".emit_message(", ".stock_emit_message(")
    impl = stock[stock.index("impl ModelExecutionBinding {", high):]
    impl = impl.replace("async fn emit_message(", "async fn stock_emit_message(", 1)
    subprocess.run(["git","apply","--check",HERE/"source.patch"], cwd=tree, check=True)
    subprocess.run(["git","apply",HERE/"source.patch"], cwd=tree, check=True)
    with src.open("a", encoding="utf-8") as f:
        f.write("\n#[cfg(test)]\n"+body+"\n#[cfg(test)]\n"+impl)
        f.write('\n#[cfg(test)]\n#[path = "r57_presentation_probe.rs"]\nmod r57_probe;\n')
    shutil.copyfile(HERE/"measure.rs",src.parent/"r57_presentation_probe.rs")
    shutil.copyfile(tree/"crates/proteus-contracts/src/test_alloc.rs",tree/SRC/"r57_alloc.rs")
    with (tree/SRC/"lib.rs").open("a", encoding="utf-8") as f:
        f.write("\n#[cfg(test)]\nmod r57_alloc;\n")
    snap = root/"outputs.json"
    command = ["cargo","test","--locked","--offline","-p","proteus-core","--lib","--",
               "r57_paired_presentation_preserves_complete_stream_and_events",
               "app_server::acp::tests::reasoning_presentation::",
               "core::bound_model::tests::failure_progress::",
               "--nocapture"]
    run = subprocess.run(command, cwd=tree, env={**env,"R57_PRESENTATION_SNAPSHOT":str(snap)},
                         stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
    (target/"r57-presentation.log").write_text(run.stdout)
    if run.returncode:
        raise RuntimeError(run.stdout)
    results = [line[line.index("r57 "):] for line in run.stdout.splitlines() if "r57 " in line]
    assert len(results) == 11
    for line in results:
        print(line)
    for line in run.stdout.splitlines():
        if (line.startswith("test ") and line.endswith(" ... ok")) or line.startswith("test result:"):
            print(line)
    assert "anonymous_progress_is_not_republished_as_identified_completed_thoughts ... ok" in run.stdout
    assert snap.stat().st_size > 65536
    print(f"11 paired serialized canonical streams and delivered typed event arrays are byte-identical ({snap.stat().st_size} bytes across fixture outputs).")
