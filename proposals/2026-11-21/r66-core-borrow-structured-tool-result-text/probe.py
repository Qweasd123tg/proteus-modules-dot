"""Compile both full tool DTO modules against the exact stock Contracts dependencies."""
import argparse
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

HERE = Path(__file__).resolve().parent
SOURCE = Path("crates/proteus-contracts/src/domain/tool.rs")
ALLOC = Path("crates/proteus-contracts/src/test_alloc.rs")

p = argparse.ArgumentParser(description=__doc__)
p.add_argument("checkout", type=Path)
for name in ("contracts", "serde", "serde-json"):
    p.add_argument(f"--{name}-rlib", type=Path, required=True)
a = p.parse_args()

with tempfile.TemporaryDirectory(prefix="proteus-r66-tooltext-") as temporary:
    root = Path(temporary)
    checkout = root / "patched"
    source = checkout / SOURCE
    source.parent.mkdir(parents=True)
    shutil.copyfile(a.checkout / SOURCE, source)
    shutil.copyfile(source, root / "stock.rs")
    subprocess.run(["git", "apply", "--check", HERE / "source.patch"], cwd=checkout, check=True)
    subprocess.run(["git", "apply", HERE / "source.patch"], cwd=checkout, check=True)
    shutil.copyfile(source, root / "candidate.rs")
    shutil.copyfile(a.checkout / ALLOC, root / "test_alloc.rs")
    shutil.copyfile(HERE / "measure.rs", root / "main.rs")
    deps = a.contracts_rlib.resolve(strict=True).parent
    proof = root / "proof"
    command = [
        "rustc", "--edition=2024", "--test", "-C", "opt-level=2", "-C", "debuginfo=0",
        "-C", "codegen-units=1", "-C", "link-arg=-fuse-ld=lld", "-L", f"dependency={deps}",
        "-o", proof, "main.rs",
    ]
    for name, path in (
        ("proteus_contracts", a.contracts_rlib),
        ("serde", a.serde_rlib),
        ("serde_json", a.serde_json_rlib),
    ):
        path = path.resolve(strict=True)
        assert path.parent == deps, "all rlibs must come from the same locked target"
        command += ["--extern", f"{name}={path}"]
    subprocess.run(command, cwd=root, check=True)
    snapshot = root / "parity.frames"
    subprocess.run(
        [proof, "--nocapture", "--test-threads=1"], cwd=root, check=True,
        env={**os.environ, "R66_SNAPSHOT": str(snapshot)},
    )
    data = snapshot.read_bytes()
    print(f"Byte-identical corpus ({len(data)} framed bytes), SHA256 {hashlib.sha256(data).hexdigest()}")
