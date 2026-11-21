#!/usr/bin/env python3
"""Apply to the pinned tree, test, then profile both versions in one process."""
import argparse
import os
from pathlib import Path
import shutil
import subprocess as sp
import sys
import tempfile

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("repo", type=Path)
parser.add_argument("--compiler", type=Path,
                    help="optional Python wrapper for rustc with pinned dependency rlibs; run offline subset")
args = parser.parse_args()
base = "9469e3b12529d08b1f4a76882693e2065e842c51"
here = Path(__file__).resolve().parent
with tempfile.TemporaryDirectory(prefix="openai-item-", dir=os.environ.get("TMPDIR")) as t:
    work = Path(t).resolve()
    repo = work / "source"
    sp.run(["git", "clone", "--quiet", "--shared", "--no-checkout", args.repo.resolve(), repo], check=True)
    def run(*cmd):
        sp.run(cmd, cwd=repo, check=True)
    if args.compiler:
        run("git", "sparse-checkout", "set", "model/model-pack")
    run("git", "checkout", "-q", "--detach", base)
    api = repo / "model/model-pack/src/adapters/openai"
    target = api / "stream_state.rs"
    old = target.read_text()
    run("git", "apply", "--check", here / "candidate.patch")
    run("git", "apply", here / "candidate.patch")
    run("git", "diff", "--check")
    run("rustfmt", "--edition", "2024", "--check", target)
    # The original uses an identical sibling test-module name; don't register its tests twice.
    assert old.count("#[cfg(test)]\nmod tests;") == 1
    (api / "before.rs").write_text(old.replace("#[cfg(test)]\nmod tests;", ""))
    shutil.copyfile(here / "probe.rs", api / "probe.rs")

    if args.compiler:
        # Compile the supplied state, item decoder, completion and compaction logic directly.
        # Only HTTP response/status helpers and the subprocess model-host test require other crates.
        for filename, begin, end in [
            ("errors.rs","pub(super) async fn ensure_success", "pub(super) fn failure_from_error_value"),
            ("compaction.rs", "pub(crate) fn default_support", "pub(super) fn is_checkpoint"),
        ]:
            path = api / filename
            s = path.read_text(); path.write_text(s[:s.index(begin)] + s[s.index(end):])
        test = api / "stream_state/tests.rs"
        s = test.read_text()
        assert s.count("#[tokio::test]") == 1
        test.write_text(s.replace("#[tokio::test]", "#[cfg(any())]\n#[tokio::test]"))
        src = repo / "model/model-pack/src/adapters/suite.rs"
        src.write_text("#![allow(dead_code,unused_imports)]\npub(crate) use proteus_contracts::{domain,model_standard};\n"
                       "mod openai {mod errors; mod compaction; mod response; mod stream; mod before; mod stream_state; mod probe;}")
        exe = work / "suite"
        run(sys.executable,args.compiler.resolve(),"--test","-O",src,"-o",exe)
        run(exe,"--skip","probe::","--test-threads=1")
        run(exe,"openai::probe::parity_and_allocation","--nocapture","--test-threads=1")
    else:
        with (api.parent / "openai.rs").open("a") as dest:
            dest.write("\n#[cfg(test)] mod before;\n#[cfg(test)] mod probe;\n")
        # The project runner sets PROTEUS_TEST_HARNESS_ROOT for the bound-model integration case.
        for group in ("adapters::openai::stream_state::tests::", "adapters::openai::stream::tests::",
                      "adapters::openai::errors::tests::", "adapters::openai::probe::parity_and_allocation"):
            run(sys.executable, "scripts/test.py", "-p", "model-pack", "--lib", "--locked",
                "--release", group, "--", "--nocapture", "--test-threads=1")
