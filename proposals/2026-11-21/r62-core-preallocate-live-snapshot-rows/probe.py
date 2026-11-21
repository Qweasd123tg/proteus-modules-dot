"""Compile exact stock/candidate TurnProgress plus native unit tests with real rlibs."""
import argparse
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

HERE = Path(__file__).resolve().parent
APP_SERVER = Path("crates/proteus-core/src/app_server")
ALLOC = Path("crates/proteus-contracts/src/test_alloc.rs")

p = argparse.ArgumentParser(description=__doc__)
p.add_argument("checkout", type=Path, help="clean exact Core checkout")
for name in ("contracts", "serde-json", "uuid"):
    p.add_argument(f"--{name}-rlib", type=Path, required=True)
a = p.parse_args()

with tempfile.TemporaryDirectory(prefix="proteus-r62-progress-") as temporary:
    root = Path(temporary)
    for side in ("stock", "candidate"):
        tree = root / side
        source = tree / APP_SERVER
        source.mkdir(parents=True)
        shutil.copyfile(a.checkout / APP_SERVER / "turn_progress.rs", source / "turn_progress.rs")
        shutil.copytree(a.checkout / APP_SERVER / "turn_progress", source / "turn_progress")
        if side == "candidate":
            subprocess.run(["git", "apply", "--check", HERE / "source.patch"], cwd=tree, check=True)
            subprocess.run(["git", "apply", HERE / "source.patch"], cwd=tree, check=True)
        # Attach a test-only helper inside the exact implementation so the same
        # deterministic states are available without adding a production seam.
        harness = root / f"{side}_harness"
        progress = harness / "progress"
        shutil.copytree(source / "turn_progress", progress)
        shutil.copyfile(source / "turn_progress.rs", progress / "mod.rs")
        (harness / "mod.rs").write_text(
            "#![allow(dead_code)]\nuse crate::transcript;\n"
            "mod progress;\npub use progress::fixture::State;\n",
            encoding="utf-8",
        )
        with (progress / "mod.rs").open("a", encoding="utf-8") as f:
            f.write("\n#[cfg(test)]\npub mod fixture;\n")
        shutil.copyfile(HERE / "fixture.rs", progress / "fixture.rs")
    shutil.copyfile(HERE / "measure.rs", root / "main.rs")
    shutil.copyfile(a.checkout / ALLOC, root / "test_alloc.rs")
    deps = a.contracts_rlib.resolve(strict=True).parent
    binary = root / "proof"
    command = [
        "rustc", "--edition=2024", "--test", "-C", "opt-level=2", "-C", "debuginfo=0",
        "-C", "codegen-units=1", "-C", "link-arg=-fuse-ld=lld", "-L", f"dependency={deps}",
        "-o", binary, "main.rs",
    ]
    for name, path in (
        ("proteus_contracts", a.contracts_rlib),
        ("serde_json", a.serde_json_rlib),
        ("uuid", a.uuid_rlib),
    ):
        path = path.resolve(strict=True)
        assert path.parent == deps, "all rlibs must be from the same locked Cargo dependency directory"
        command += ["--extern", f"{name}={path}"]
    subprocess.run(command, cwd=root, check=True)
    snapshot = root / "parity.frames"
    subprocess.run(
        [binary, "--nocapture", "--test-threads=1"], cwd=root, check=True,
        env={**os.environ, "R62_SNAPSHOT": str(snapshot)},
    )
    parity = snapshot.read_bytes()
    print(f"Byte-identical corpus ({len(parity)} framed bytes), SHA256 {hashlib.sha256(parity).hexdigest()}")
