"""Run actual baseline and patched disclosure projection in one release test executable.

Requires a clean pinned checkout, cargo, locked dependencies, Git and Python.
Builds a temporary copy, leaving the supplied checkout untouched.
"""
import hashlib
from pathlib import Path
import sys
import subprocess
import shutil
import tempfile
here = Path(__file__).resolve().parent
source = Path(sys.argv[1]).resolve()
temp = tempfile.TemporaryDirectory()
root = Path(temp.name) / "pkg"
shutil.copytree(source, root, ignore=shutil.ignore_patterns(".git", "target", "dist", "__pycache__"))
path = root / "packages/analysis/src/nodes.rs"
base = path.read_bytes()
assert hashlib.sha1(b"blob " + str(len(base)).encode() + b"\0" + base).hexdigest() == "9860c5ada746f55ac1bc717d9e2410d3b66856f4"
text = base.decode()
start, end = text.index("/// Lines as Python"), text.rindex("#[cfg(test)]")
baseline_module = "\n#[cfg(test)] mod baseline { use super::*;\n" + text[start:end] + "\n}"
try:
    subprocess.run(["git", "apply", "--check", here/"analysis-height.patch"],cwd=root,check=True)
    subprocess.run(["git", "apply", here/"analysis-height.patch"],cwd=root,check=True)
    with path.open("a") as f:
        f.write(baseline_module+"\n"+(here / "projection.rs.in").read_text())
    subprocess.run(["cargo","test","--offline","--locked","--release","-p","extension-analysis","actual_projection_pairs","--","--nocapture"],cwd=root,check=True)
finally:
    temp.cleanup()
