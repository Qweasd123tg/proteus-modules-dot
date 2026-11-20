#!/usr/bin/env python3
"""Compare the two unmodified search_roots functions; requires rustc, git, a patched source tree."""
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory

repo = Path(sys.argv[1]).resolve()
base = sys.argv[2]
path = "context_provider/rg-search/src/lib.rs"
old = subprocess.check_output(["git","show",f"{base}:{path}"], cwd=repo, text=True)
new = (repo/path).read_text()
def roots(s):
    return s[s.index("fn search_roots("):s.index("fn suffix_glob(")]
def arm(name, src):
    return 'mod '+name+' { use super::*;\n'+roots(src).replace("fn search_roots(", "pub(super) fn search_roots(", 1)+'}\n'
with TemporaryDirectory() as d:
    p = Path(d)
    harness = Path(__file__).with_name("probe.rs").read_text()
    (p/"main.rs").write_text(arm("stock", old)+arm("candidate",new)+harness)
    subprocess.run(["rustc","--edition","2024","-O",str(p/"main.rs"),"-o",str(p/"probe")],check=True)
    subprocess.run([str(p/"probe"),str(p/"fs")], check=True)
