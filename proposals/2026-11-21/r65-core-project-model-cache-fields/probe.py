"""Run exact ProcessModel cache/getter bodies with real locked DTOs and a scripted client."""
import argparse
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

HERE = Path(__file__).resolve().parent
SOURCE = Path("crates/proteus-core/src/process_adapters/model.rs")
ALLOC = Path("crates/proteus-contracts/src/test_alloc.rs")

p = argparse.ArgumentParser(description=__doc__)
p.add_argument("checkout", type=Path, help="clean exact Core checkout")
for name in ("contracts", "serde-json", "anyhow"):
    p.add_argument(f"--{name}-rlib", type=Path, required=True)
a = p.parse_args()


def selected(source):
    start = source.index("    fn describe_model")
    end = source.index("\n}\n\n// A stream can", start)
    describe = source[start:end]
    start = source.index("    fn capabilities(&self, model:")
    end = source.index("\n    async fn catalog(", start)
    getters = source[start:end].replace(
        "    fn capabilities(", "    pub(super) fn capabilities(", 1
    ).replace(
        "    fn provider_hosted_tools(", "    pub(super) fn provider_hosted_tools(", 1
    )
    return describe + "\n" + getters


with tempfile.TemporaryDirectory(prefix="proteus-r65-model-") as temporary:
    root = Path(temporary)
    checkout = root / "patched"
    source = checkout / SOURCE
    source.parent.mkdir(parents=True)
    shutil.copyfile(a.checkout / SOURCE, source)
    old = source.read_text(encoding="utf-8")
    subprocess.run(["git", "apply", "--check", HERE / "source.patch"], cwd=checkout, check=True)
    subprocess.run(["git", "apply", HERE / "source.patch"], cwd=checkout, check=True)
    new = source.read_text(encoding="utf-8")
    for side, code in (("stock", old), ("candidate", new)):
        (root / f"{side}.rs").write_text(
            """use super::*;

pub(super) struct ProcessModel {
    pub(super) client: FixtureClient,
    pub(super) adapter_id: String,
    pub(super) descriptions: StdMutex<DescriptorMap>,
}

impl ProcessModel {
""" + selected(code) + "\n}\n",
            encoding="utf-8",
        )
    shutil.copyfile(HERE / "measure.rs", root / "main.rs")
    shutil.copyfile(a.checkout / ALLOC, root / "test_alloc.rs")
    deps = a.contracts_rlib.resolve(strict=True).parent
    proof = root / "proof"
    command = [
        "rustc", "--edition=2024", "--test", "-C", "opt-level=2", "-C", "debuginfo=0",
        "-C", "codegen-units=1", "-C", "link-arg=-fuse-ld=lld", "-L", f"dependency={deps}",
        "-o", proof, "main.rs",
    ]
    for name, path in (
        ("proteus_contracts", a.contracts_rlib),
        ("serde_json", a.serde_json_rlib),
        ("anyhow", a.anyhow_rlib),
    ):
        path = path.resolve(strict=True)
        assert path.parent == deps, "all rlibs must come from the same locked target"
        command += ["--extern", f"{name}={path}"]
    subprocess.run(command, cwd=root, check=True)
    snapshot = root / "parity.frames"
    subprocess.run(
        [proof, "--nocapture", "--test-threads=1"], cwd=root, check=True,
        env={**os.environ, "R65_SNAPSHOT": str(snapshot)},
    )
    data = snapshot.read_bytes()
    print(f"Byte-identical cache trace corpus ({len(data)} framed bytes), SHA256 {hashlib.sha256(data).hexdigest()}")
