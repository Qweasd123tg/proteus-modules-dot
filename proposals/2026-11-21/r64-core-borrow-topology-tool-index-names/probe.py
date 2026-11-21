"""Compile both exact topology tool projection modules against real stock Core and Contracts."""
import argparse
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

HERE = Path(__file__).resolve().parent
SOURCE = Path("crates/proteus-core/src/core/topology/tools.rs")
CLASSIFY = Path("crates/proteus-core/src/core/agent_control/mod.rs")
ALLOC = Path("crates/proteus-contracts/src/test_alloc.rs")

p = argparse.ArgumentParser(description=__doc__)
p.add_argument("checkout", type=Path, help="clean exact upstream Core checkout")
for name in ("core", "contracts", "serde-json"):
    p.add_argument(f"--{name}-rlib", type=Path, required=True)
p.add_argument("--native-dir", type=Path, required=True)
a = p.parse_args()

with tempfile.TemporaryDirectory(prefix="proteus-r64-topology-") as temporary:
    root = Path(temporary)
    checkout = root / "candidate"
    source = checkout / SOURCE
    source.parent.mkdir(parents=True)
    shutil.copyfile(a.checkout / SOURCE, source)
    shutil.copyfile(source, root / "stock.rs")
    subprocess.run(["git", "apply", "--check", HERE / "source.patch"], cwd=checkout, check=True)
    subprocess.run(["git", "apply", HERE / "source.patch"], cwd=checkout, check=True)
    shutil.copyfile(source, root / "candidate.rs")
    # Compile the actual private helper unchanged, rather than mock provenance.
    classification = (a.checkout / CLASSIFY).read_text(encoding="utf-8")
    start = classification.index("const TASK_SOURCE:")
    end = classification.index("\n///", start)
    (root / "ownership.rs").write_text(classification[start:end], encoding="utf-8")
    shutil.copyfile(HERE / "measure.rs", root / "main.rs")
    shutil.copyfile(a.checkout / ALLOC, root / "test_alloc.rs")
    deps = a.core_rlib.resolve(strict=True).parent
    binary = root / "proof"
    command = [
        "rustc", "--edition=2024", "--test", "-C", "opt-level=2", "-C", "debuginfo=0",
        "-C", "codegen-units=1", "-C", "link-arg=-fuse-ld=lld",
        "-L", f"dependency={deps}", "-L", f"native={a.native_dir.resolve(strict=True)}",
        "-o", binary, "main.rs",
    ]
    for name, path in (
        ("proteus_core", a.core_rlib),
        ("proteus_contracts", a.contracts_rlib),
        ("serde_json", a.serde_json_rlib),
    ):
        path = path.resolve(strict=True)
        assert path.parent == deps, "all artifacts must come from the same locked Core target"
        command += ["--extern", f"{name}={path}"]
    subprocess.run(command, cwd=root, check=True)
    snapshot = root / "parity.frames"
    subprocess.run(
        [binary, "--nocapture", "--test-threads=1"], cwd=root, check=True,
        env={**os.environ, "R64_SNAPSHOT": str(snapshot)},
    )
    parity = snapshot.read_bytes()
    print(f"Byte-identical corpus ({len(parity)} framed bytes), SHA256 {hashlib.sha256(parity).hexdigest()}")
