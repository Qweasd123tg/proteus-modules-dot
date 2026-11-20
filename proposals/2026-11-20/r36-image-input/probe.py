"""Compare exact checked-in prepare + local-admit code using a common contracts build."""
from pathlib import Path
import subprocess
import sys

repo, deps, out = (Path(s).resolve() for s in sys.argv[1:])
out.mkdir(parents=True, exist_ok=True)
path = "crates/proteus-core/src/core/runtime/images.rs"
pin = "32e56ecb4cc6da324c60dd6ae2da78f3b7e46e7f"
stock = subprocess.check_output(["git","-C",repo,"show",f"{pin}:{path}"], text=True)
for arm, data in [("before", stock), ("after", (repo / path).read_text())]:
    # Keep all actual types and both real functions, ending before the remote backend.
    src = data[:data.index("    pub(super) async fn admit_to_session(")] + "}\n"
    (out / f"{arm}.rs").write_text(src)
(out / "main.rs").write_bytes((Path(__file__).parent / "probe.rs").read_bytes())
args = ["rustc","--edition=2024","-Copt-level=3","-Cstrip=debuginfo","-Clink-arg=-fuse-ld=lld",
        "-Awarnings",str(out/"main.rs"),"-L",f"dependency={deps}","-o",str(out/"probe")]
for lib in ["anyhow", "proteus_contracts", "ring", "uuid", "tempfile"]:
    paths=list(deps.glob(f"lib{lib}-*.rlib"))
    if len(paths)!=1: raise SystemExit(f"Need exactly one {lib} rlib; got {paths}")
    args.extend(["--extern",f"{lib}={paths[0]}"])
subprocess.run(args, check=True)
subprocess.run([out/"probe"],check=True)
