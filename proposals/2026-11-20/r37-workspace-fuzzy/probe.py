"""Check the exact search modules from a patched checkout (one local dependency set)."""
from pathlib import Path
import subprocess
import sys

base = "32e56ecb4cc6da324c60dd6ae2da78f3b7e46e7f"
repo, deps, out = [Path(p).resolve() for p in sys.argv[1:]]
src = Path("crates/proteus-core/src/app_server/http/workspace/search.rs")
http = (repo/src).parent.parent
out.mkdir(parents=True, exist_ok=True)
w = out/"workspace"
w.mkdir(exist_ok=True)
source = subprocess.check_output(["git", "-C", repo, "show", f"{base}:{src}"], text=True)
# Append a bridge only for the synthetic score-parity test; application-path
# measurements call the two original search() functions without this bridge.
def bridge(parse):
    return """
pub(crate) fn score_matrix(query: &str, paths: &[String]) -> Vec<Option<i64>> {
    """ + parse + """
    paths.iter().map(|path| score(&terms, path)).collect()
}
"""
before_parse = source[source.index("    let terms: Vec<Vec<char>>"):source.index("    let (candidates,")]
(w/"before.rs").write_text(source + bridge(before_parse))
(w/"after.rs").write_text((repo/src).read_text() + bridge("let terms = terms(query);"))
work = (http/"workspace.rs").read_text()
entry = work[work.index("const MAX_ENTRIES"):work.index("#[derive(Serialize)]\npub(super) struct WorkspaceListing")]
(w/"mod.rs").write_text("use serde::Serialize;\npub(crate) mod before;\npub(crate) mod after;\nmod git;\npub(crate) use after as search;\n"+entry)
for name in ["git.rs", "git"]:
    path = w/name
    if not path.exists():
        path.symlink_to(http/"workspace"/name)
upstream_test = (http/"tests/workspace_git.rs").read_text()
(out/"http_tests").mkdir(exist_ok=True)
(out/"http_tests/workspace_git.rs").write_text("use std::{fs, path::Path, process::Command};\n"+
    upstream_test[upstream_test.index("fn git("):upstream_test.index("fn changes(")]+
    upstream_test[upstream_test.index("fn search("):upstream_test.index("#[test]\nfn workspace_git_revisions_track")])
session = (http/"sessions.rs").read_text()
(out/"sessions.rs").write_text("use anyhow::Result;\n"+session[session.index("pub(super) fn percent_decode_query_value"):session.index("/// Compact read")])
(out/"main.rs").write_text((Path(__file__).parent/"probe.rs").read_text())
(out/"git_support.rs").write_text((repo/"crates/proteus-contracts/src/git_support.rs").read_text().split("#[cfg(test)]")[0])
cmd = ["rustc", "--edition=2024", "-Copt-level=3", "-Cstrip=debuginfo", "-Clink-arg=-fuse-ld=lld", "-Awarnings",
       "--test", str(out/"main.rs"), "-o", str(out/"probe"), "-L", f"dependency={deps}"]
for lib in ["anyhow", "serde", "serde_json", "libc", "tempfile"]:
    hits = list(deps.glob(f"lib{lib}-*.rlib"))
    if len(hits)!=1:
        sys.exit(f"Need one {lib} in {deps}; got {hits}")
    cmd += ["--extern", f"{lib}={hits[0]}"]
subprocess.run(cmd, check=True)
subprocess.run([out/"probe", "--nocapture", "--test-threads=1"], check=True)
