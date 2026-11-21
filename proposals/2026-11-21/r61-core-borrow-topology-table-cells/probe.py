"""Compile both complete topology renderer trees against a real Core Contracts artifact."""
import argparse
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

HERE = Path(__file__).resolve().parent
RENDER_DIR = Path("crates/proteus-core/src/core")
CONTRACT_ALLOC = Path("crates/proteus-contracts/src/test_alloc.rs")

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("checkout", type=Path, help="clean exact upstream archive")
parser.add_argument("--contracts-rlib", type=Path, required=True)
args = parser.parse_args()

with tempfile.TemporaryDirectory(prefix="proteus-r61-topology-") as temporary:
    root = Path(temporary)
    stock = root / "stock"
    tree = root / "candidate"
    stock.mkdir()
    shutil.copyfile(args.checkout / RENDER_DIR / "topology_render.rs", stock / "mod.rs")
    shutil.copytree(args.checkout / RENDER_DIR / "topology_render", stock, dirs_exist_ok=True)
    render = tree / RENDER_DIR
    render.mkdir(parents=True)
    shutil.copyfile(args.checkout / RENDER_DIR / "topology_render.rs", render / "topology_render.rs")
    shutil.copytree(args.checkout / RENDER_DIR / "topology_render", render / "topology_render")
    subprocess.run(["git", "apply", "--check", HERE / "source.patch"], cwd=tree, check=True)
    subprocess.run(["git", "apply", HERE / "source.patch"], cwd=tree, check=True)
    shutil.copyfile(render / "topology_render.rs", render / "topology_render/mod.rs")
    shutil.copyfile(HERE / "measure.rs", root / "main.rs")
    shutil.copyfile(args.checkout / CONTRACT_ALLOC, root / "test_alloc.rs")
    contracts = args.contracts_rlib.resolve(strict=True)
    binary = root / "proof"
    subprocess.run(
        [
            "rustc", "--edition=2024", "--test", "-C", "opt-level=2",
            "-C", "debuginfo=0", "-C", "codegen-units=1", "-C", "link-arg=-fuse-ld=lld",
            "-L", f"dependency={contracts.parent}", "--extern", f"proteus_contracts={contracts}",
            "-o", binary, "main.rs",
        ],
        cwd=root,
        check=True,
    )
    snapshot = root / "parity.frames"
    subprocess.run(
        [binary, "--nocapture", "--test-threads=1"],
        cwd=root,
        env={**os.environ, "R61_SNAPSHOT": str(snapshot)},
        check=True,
    )
    parity = snapshot.read_bytes()
    print(f"Byte-identical corpus ({len(parity)} framed bytes), SHA256 {hashlib.sha256(parity).hexdigest()}")
