"""Compile both exact summary functions against the same real Proteus contracts."""
from pathlib import Path
from tempfile import TemporaryDirectory
import subprocess
import sys

base = "32e56ecb4cc6da324c60dd6ae2da78f3b7e46e7f"
cache = Path("crates/proteus-core/src/core/session_store/remote/view/cache.rs")
here = Path(__file__).resolve().parent
repo, deps = (Path(x).resolve() for x in sys.argv[1:])
with TemporaryDirectory() as tmp:
    work = Path(tmp)
    src = work / cache
    src.parent.mkdir(parents=True)
    old = subprocess.check_output(["git", "-C", repo, "show", f"{base}:{cache}"], text=True)
    src.write_text(old)
    subprocess.run(["git", "init", "-q"], cwd=work, check=True)
    subprocess.run(["git", "apply", "--check", here/"source.patch"], cwd=work, check=True)
    subprocess.run(["git", "apply", "--whitespace=error", here/"source.patch"], cwd=work, check=True)
    for label, body in [("stock", old), ("candidate", src.read_text())]:
        mod = work/label
        mod.mkdir()
        exact = body[body.index("pub(super) fn summary("):]
        prefix = "use super::*;\n"
        if label == "candidate":
            (mod/"preview.rs").write_bytes((src.with_suffix("")/"preview.rs").read_bytes())
            prefix += "mod preview;\n"
        (mod/"mod.rs").write_text(prefix + exact)
    (work/"main.rs").write_bytes((here/"probe.rs").read_bytes())
    cmd = ["rustc", "--edition=2024", "-Copt-level=3", "-Cstrip=debuginfo",
           "-Clink-arg=-fuse-ld=lld", "--test", str(work/"main.rs"), "-L", f"dependency={deps}",
           "-o", str(work/"probe")]
    for lib in ["anyhow", "serde_json", "proteus_contracts"]:
        matches = list(deps.glob(f"lib{lib}-*.rlib"))
        if len(matches) != 1:
            sys.exit(f"need one compiled {lib} in {deps}; got {matches}")
        cmd.extend(["--extern", f"{lib}={matches[0]}"])
    subprocess.run(cmd, check=True)
    subprocess.run([work/"probe", "--test-threads=1", "--nocapture"], check=True)
