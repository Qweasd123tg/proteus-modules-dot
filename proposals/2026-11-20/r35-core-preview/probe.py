"""Compile the unchanged full summary bodies against the same exact crates.
Usage after applying the patch and building proteus-core --lib:
  python3 probe.py CHECKOUT CARGO_TARGET_DIR/debug/deps OUTPUT_DIR
"""
from pathlib import Path
import subprocess
import sys

repo, deps, out = (Path(x).resolve() for x in sys.argv[1:])
out.mkdir(parents=True, exist_ok=True)
here = Path(__file__).resolve().parent
base = "048378da7cbe890d8bf8a0152e55eb28ecb5013d"
path = "crates/proteus-core/src/core/session_store/remote/view/cache.rs"
stock = subprocess.check_output(["git", "-C", str(repo), "show", f"{base}:{path}"], text=True)
candidate = (repo / path).read_text()

def body(text, name):
    start = text.index(name)
    return text[start:text.index("\n}", start) + 2]

src = (here / "probe.rs").read_text()
for name, source in [("stock", stock), ("candidate", candidate)]:
    extract = [body(source, "fn preview_excerpt(")] if name == "candidate" else []
    extract.append(body(source, "pub(super) fn summary("))
    src += f"\nmod {name} {{ use super::*;\n" + "\n".join(extract) + "\n}\n"
(out / "main.rs").write_text(src)
cmd = ["rustc", "--edition=2024", "-Copt-level=3", "-Cdebuginfo=0", "-Clink-arg=-fuse-ld=lld",
       str(out / "main.rs"), "-L", f"dependency={deps}", "-o", str(out / "probe")]
for lib in ["proteus_contracts", "anyhow"]:
    libs = list(deps.glob(f"lib{lib}-*.rlib"))
    if len(libs) != 1:
        raise SystemExit(f"Expected exactly one pinned {lib} rlib in {deps}: {libs}")
    cmd += ["--extern", f"{lib}={libs[0]}"]
subprocess.run(cmd, check=True)
subprocess.run([str(out / "probe")], check=True)
