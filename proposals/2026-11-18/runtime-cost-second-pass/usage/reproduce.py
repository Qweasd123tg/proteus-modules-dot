"""Rust probes for the pinned Usage extension, in disposable workspaces.

Usage: python3 reproduce.py /path/to/Proteus-desktop-extensions
Requires Rust/Cargo on PATH and the pinned crates available to Cargo offline.
No source file in the supplied checkout is changed.
"""
from pathlib import Path
from hashlib import sha1
from tempfile import TemporaryDirectory
import os
import shutil
import subprocess
import sys

here = Path(__file__).resolve().parent
source = Path(sys.argv[1]).resolve()
manifest = [line.split("\t") for line in (here/"source-blobs.tsv").read_text().splitlines()]
def verify(contents, sha):
    assert sha1(b"blob " + str(len(contents)).encode() + b"\0" + contents).hexdigest() == sha
def cmd(args, wd, **env):
    subprocess.run(args, cwd=wd, env={**os.environ, **env}, check=True)
with TemporaryDirectory() as d:
    work = Path(d)
    base = work/"baseline"
    for sha, name in manifest:
        data = (source/name).read_bytes()
        verify(data, sha)
        out=base/name
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(data)
    candidate=work/"candidate"
    shutil.copytree(base, candidate)
    cmd(["git","apply","--check",here/"usage-by-model.patch"],candidate)
    cmd(["git","apply",here/"usage-by-model.patch"],candidate)
    common = ["cargo","test","--locked","--offline","-p","extension-usage"]
    for label,wd in [("old",base),("new",candidate)]:
        cmd(common, wd, CARGO_TARGET_DIR=str(work/f"target-std-{label}"))
    probe = candidate/"packages/usage/src"
    old = base/"packages/usage/src"
    shutil.copyfile(old/"report.rs",probe/"baseline_report.rs")
    orig = (old/"view.rs").read_text()
    old_import="use crate::report::{self, exact, money};"
    assert orig.count(old_import)==1
    (probe/"baseline_view.rs").write_text(orig.replace(old_import,"use crate::baseline_report::{self as report, exact, money};"))
    shutil.copyfile(here/"native_probe.rs.in",probe/"probe.rs")
    with (probe/"main.rs").open("a") as f:
        for name in ("baseline_report","baseline_view","probe"):
            f.write(f"\n#[cfg(test)] mod {name};\n")
    for instrument,selector in [(False,"probe::"),(True,"probe::paired_usage_cost")]:
        flags="--check-cfg=cfg(usage_alloc)"+(" --cfg usage_alloc" if instrument else "")
        cmd(common+["--release",selector,"--","--test-threads=1","--nocapture"], candidate,
            CARGO_TARGET_DIR=str(work/f"target-probe-{int(instrument)}"),RUSTFLAGS=flags)
