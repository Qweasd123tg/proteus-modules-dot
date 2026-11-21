"""Run paired registered-tool projection and real config-route tests."""
import argparse
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

HERE = Path(__file__).resolve().parent
SRC = Path("crates/proteus-core/src")
ALLOC = Path("crates/proteus-contracts/src/test_alloc.rs")
SUMMARY = SRC/"app_server/config_summary.rs"
p = argparse.ArgumentParser(description=__doc__)
p.add_argument("checkout", type=Path)
p.add_argument("target", type=Path)
args = p.parse_args()
env = dict(os.environ, CARGO_TARGET_DIR=str(args.target.resolve()))
for k, v in {"CARGO_BUILD_JOBS": "2", "CARGO_PROFILE_TEST_DEBUG": "0",
             "CARGO_INCREMENTAL": "0", "RUST_TEST_THREADS": "1"}.items():
    env.setdefault(k, v)
target = Path(env["CARGO_TARGET_DIR"])
target.mkdir(parents=True, exist_ok=True)

with tempfile.TemporaryDirectory(prefix="proteus-r54-summary-") as temp:
    root = Path(temp)
    tree = root / "core"
    shutil.copytree(args.checkout, tree, ignore=shutil.ignore_patterns(".git", "target"))
    src = tree/SUMMARY
    stock = src.read_text()
    low = stock.index("            registered_tools: tools")
    high = stock.index("\n            components:", low)
    projection = stock[low:high].split(": ", 1)[1].rstrip().removesuffix(",")
    stock = (
        "fn stock_registered_tool_summaries(\n"
        "    tools: &[(ToolSource, crate::domain::ToolSpec)],\n"
        ") -> Vec<ConfigTool> {\n" + projection + "\n}\n"
    )
    subprocess.run(["git", "apply", "--check", HERE/"source.patch"], cwd=tree, check=True)
    subprocess.run(["git", "apply", HERE/"source.patch"], cwd=tree, check=True)
    with src.open("a", encoding="utf-8") as f:
        f.write("\n#[cfg(test)]\n"+stock)
        f.write('\n#[cfg(test)]\n#[path = "r54_summary_probe.rs"]\nmod r54_summary_probe;\n')
    shutil.copyfile(HERE/"measure.rs", src.parent/"r54_summary_probe.rs")
    shutil.copyfile(tree/ALLOC, tree/SRC/"r54_alloc.rs")
    with (tree/SRC/"lib.rs").open("a", encoding="utf-8") as f:
        f.write("\n#[cfg(test)]\nmod r54_alloc;\n")
    snap = root/"snapshot.json"
    command = ["cargo","test","--locked","--offline","-p","proteus-core","--lib","--",
               "app_server::config_summary::r54_summary_probe::",
               "app_server::http::tests::config::",
               "app_server::tests::reload_tools_rebuilds_registry_from_config_path_and_emits_event",
               "app_server::tests::app_server_remember_uses_a_process_tool_without_a_turn",
               "--nocapture"]
    run = subprocess.run(command, cwd=tree, env={**env,"R54_SUMMARY_PROBE_SNAPSHOT":str(snap)},
                         stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
    (target/"r54-config-summary.log").write_text(run.stdout)
    if run.returncode:
        raise RuntimeError(run.stdout)
    stats = [line[line.index("r54 "):] for line in run.stdout.splitlines() if "r54 " in line]
    assert len(stats) == 7, stats
    for line in stats:
        print(line)
    for line in run.stdout.splitlines():
        if line.startswith("test app_server::") and line.endswith(" ... ok"):
            print(line)
        if line.startswith("test result:"):
            print(line)
    for name in ("route_config_builder_persists_settings_and_reloads_runtime",
                 "reload_tools_rebuilds_registry_from_config_path_and_emits_event",
                 "app_server_remember_uses_a_process_tool_without_a_turn"):
        assert f"{name} ... ok" in run.stdout
    data = snap.read_bytes()
    labels = __import__("json").loads(data)
    assert len(labels) == 7
    print(f"{len(labels)} registered-tool JSON lists byte-identical; SHA256 {hashlib.sha256(data).hexdigest()}")
