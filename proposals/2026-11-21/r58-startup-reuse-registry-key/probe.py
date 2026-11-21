#!/usr/bin/env python3
"""Pair actual stock and candidate HTTP state registration in one test executable."""
import argparse
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

p = argparse.ArgumentParser(description=__doc__)
for name in ("stock", "target", "worker", "reference"):
    p.add_argument(name, type=Path)
a = p.parse_args()
here = Path(__file__).resolve().parent
stock = a.stock.resolve(strict=True)
rel = Path("crates/proteus-core/src/app_server/http")
s = (stock / rel / "state.rs").read_text()
names = (
    ("    pub(super) async fn new_for_workspace(", "    pub(super) fn subscribe_activity"),
    ("    pub(super) async fn remember_server(", "    /// Resolve caller spelling"),
    ("    fn watch_server(", "\n}\n\nfn app_event_affects_session_activity"),
)
stock_impl = "impl HttpAppState {\n"
for start, stop in names:
    i = s.index(start)
    stock_impl += s[i:s.index(stop, i)]
stock_impl += "\n}\n"
for method in ("new_for_workspace", "remember_server", "watch_server"):
    stock_impl = stock_impl.replace(method + "(", "stock_" + method + "(")
assert stock_impl == (here / "stock_watcher.rs").read_text()
cache = os.environ.get("CARGO_HOME", str(Path.home() / ".cargo"))
with tempfile.TemporaryDirectory(prefix="r58-watcher-proof-") as d:
    root = Path(d)
    tree, home, temp = (root / "core", root / "synthetic-home", root / "tool-tmp")
    home.mkdir()
    temp.mkdir()
    shutil.copytree(stock, tree, symlinks=True, ignore=shutil.ignore_patterns(".git", "target"))
    subprocess.run(["git", "apply", "--check", str(here / "source.patch")], cwd=tree, check=True)
    subprocess.run(["git", "apply", str(here / "source.patch")], cwd=tree, check=True)
    for src, dst in (("test_watcher.rs", "r58_test_watcher.rs"), ("stock_watcher.rs", "r58_stock_watcher.rs")):
        shutil.copyfile(here / src, tree / rel / dst)
    p = tree / rel / "state.rs"
    content = p.read_text()
    mark = "pub(super) fn session_key(session_dir: PathBuf) -> PathBuf {\n"
    assert content.count(mark) == 1
    count = "    #[cfg(test)]\n    R58_KEY_OBSERVATIONS.with(|count| count.set(count.get() + 1));\n"
    content = content.replace(mark, mark + count)
    content += '''
#[cfg(test)]
std::thread_local! {
    static R58_KEY_OBSERVATIONS: std::cell::Cell<usize> = const { std::cell::Cell::new(0) };
}

#[cfg(test)]
#[path = "r58_test_watcher.rs"]
mod r58_test_watcher;
'''
    p.write_text(content)
    env = {
        "PATH": os.environ["PATH"], "HOME": str(home), "TMPDIR": str(temp),
        "XDG_CONFIG_HOME": str(home), "CARGO_HOME": cache,
        "CARGO_TARGET_DIR": str(a.target.resolve()), "CARGO_BUILD_JOBS": "1",
        "CARGO_PROFILE_TEST_DEBUG": "0", "CARGO_PROFILE_DEV_DEBUG": "0",
        "CARGO_INCREMENTAL": "0", "RUST_TEST_THREADS": "1",
        "PROTEUS_TEST_REFERENCE_MODULE": str(a.reference.resolve(strict=True)),
        "PROTEUS_TEST_SESSION_STORAGE_MODULE": str(a.worker.resolve(strict=True)),
    }
    subprocess.run(["cargo", "test", "--locked", "--offline", "-j1", "-p", "proteus-core", "--lib",
                    "--", "r58_watcher_", "app_server::http::tests::addressing::", "app_server::http::tests::live::",
                    "app_server::http::tests::sse::", "--nocapture"],
                    cwd=tree, env=env, check=True)
