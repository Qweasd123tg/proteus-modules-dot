"""Run against an applied Core checkout and the deps dir from its focused Cargo test."""
from pathlib import Path
import subprocess
import sys

repo, deps, out = map(lambda s: Path(s).resolve(), sys.argv[1:])
out.mkdir(parents=True, exist_ok=True)
source = "crates/proteus-core/src/core/event_store.rs"
pin = "32e56ecb4cc6da324c60dd6ae2da78f3b7e46e7f"
(out / "before.rs").write_bytes(subprocess.check_output(["git", "-C", repo, "show", f"{pin}:{source}"]))
(out / "after.rs").write_bytes((repo / source).read_bytes())
program = (Path(__file__).parent / "probe.rs").read_text()
(out / "main.rs").write_text(program)
cmd = ["rustc", "--edition=2024", "-Copt-level=3", "-Cstrip=debuginfo", "-Clink-arg=-fuse-ld=lld",
       "-Awarnings", str(out / "main.rs"), "-L", f"dependency={deps}", "-o", str(out / "probe")]
for lib in ["proteus_contracts", "async_trait", "anyhow", "tokio", "serde_json"]:
    suffix = "so" if lib == "async_trait" else "rlib"
    found = list(deps.glob(f"lib{lib}-*.{suffix}"))
    if len(found) != 1:
        raise SystemExit(f"need one {lib} in {deps}, got {found}")
    cmd += ["--extern", f"{lib}={found[0]}"]
subprocess.run(cmd, check=True)
subprocess.run([out / "probe"], check=True)
