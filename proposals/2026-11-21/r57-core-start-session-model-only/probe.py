#!/usr/bin/env python3
"""Run the unchanged stock lifecycle implementation beside the real candidate."""
import argparse
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

P = argparse.ArgumentParser(description=__doc__)
for name in ("stock", "target", "worker", "reference"):
    P.add_argument(name, type=Path)
A = P.parse_args()
here = Path(__file__).resolve().parent
r = Path("crates/proteus-core/src/core/runtime")
stock = A.stock.resolve(strict=True)
base = (stock / r.with_suffix(".rs")).read_text()
pos = base.index("    pub async fn start_session(&self)")
end = base.index("    async fn persist_config_snapshot_for_session", pos)
same = (
    "use super::super::execution::ExecutionAdmissionSnapshot;\n\nimpl AgentRuntime {\n"
    + base[pos:end].replace(" fn start_session(", " fn r57_stock_start_session(")
      .replace("ensure_session_started", "r57_stock_ensure_session_started")
    + "}\n"
)
assert same == (here / "stock_lifecycle.rs").read_text(), "stock lifecycle source differs"
cache = os.environ.get("CARGO_HOME", str(Path.home() / ".cargo"))
with tempfile.TemporaryDirectory(prefix="r57-lifecycle-proof-") as directory:
    work = Path(directory)
    tree = work / "core"
    home = work / "synthetic-home"
    home.mkdir()
    temp = work / "tool-tmp"
    temp.mkdir()
    shutil.copytree(stock, tree, symlinks=True, ignore=shutil.ignore_patterns(".git", "target"))
    subprocess.run(["git","apply","--check",str(here / "source.patch")], cwd=tree, check=True)
    subprocess.run(["git","apply",str(here / "source.patch")], cwd=tree, check=True)
    for src, dst in (("tests_r57.rs","tests_r57.rs"),
                     ("stock_lifecycle.rs","r57_stock.rs"), ("alloc.rs","r57_alloc.rs")):
        shutil.copyfile(here / src, tree / r / "tests" / dst)
    with (tree / r / "tests.rs").open("a") as mod:
        mod.write("\nmod tests_r57;\n")
    env = {
        "PATH": os.environ["PATH"], "HOME": str(home), "TMPDIR": str(temp),
        "XDG_CONFIG_HOME": str(home), "CARGO_HOME": cache,
        "CARGO_TARGET_DIR": str(A.target.resolve()), "CARGO_BUILD_JOBS": "1",
        "CARGO_PROFILE_TEST_DEBUG": "0", "CARGO_PROFILE_DEV_DEBUG": "0",
        "CARGO_INCREMENTAL": "0", "RUST_TEST_THREADS": "1",
        "PROTEUS_TEST_REFERENCE_MODULE": str(A.reference.resolve(strict=True)),
        "PROTEUS_TEST_SESSION_STORAGE_MODULE": str(A.worker.resolve(strict=True)),
    }
    subprocess.run(
        ["cargo","test","--locked","--offline","-j1","-p","proteus-core","--lib","--",
         "r57_lifecycle","app_server::tests::startup::","app_server::http::tests::sse::",
         "core::runtime::tests::snapshot_atomicity::","--nocapture"],
        cwd=tree,env=env,check=True,
    )
