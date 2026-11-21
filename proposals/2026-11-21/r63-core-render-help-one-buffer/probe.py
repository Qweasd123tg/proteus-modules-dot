"""Compile the exact stock and patched /help arms using real Contracts types."""
import argparse
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

HERE = Path(__file__).resolve().parent
SOURCE = Path("crates/proteus-core/src/app_server/commands.rs")
ALLOC = Path("crates/proteus-contracts/src/test_alloc.rs")

p = argparse.ArgumentParser(description=__doc__)
p.add_argument("checkout", type=Path, help="clean exact upstream Core checkout")
p.add_argument("--contracts-rlib", type=Path, required=True)
a = p.parse_args()


def arm(source):
    start = source.index('            "help" =>')
    end = source.index('            "status" =>', start)
    return source[start:end]


def builtins(source):
    start = source.index("const BUILTINS:")
    end = source.index("\nimpl AppServerHandle", start)
    return source[start:end]


with tempfile.TemporaryDirectory(prefix="proteus-r63-help-") as temporary:
    root = Path(temporary)
    tree = root / "candidate"
    source = tree / SOURCE
    source.parent.mkdir(parents=True)
    shutil.copyfile(a.checkout / SOURCE, source)
    old = source.read_text(encoding="utf-8")
    subprocess.run(["git", "apply", "--check", HERE / "source.patch"], cwd=tree, check=True)
    subprocess.run(["git", "apply", HERE / "source.patch"], cwd=tree, check=True)
    new = source.read_text(encoding="utf-8")
    assert builtins(old) == builtins(new)
    helper = new[new.index("fn render_command_help("):]
    generated = "use proteus_contracts::app_protocol::commands::UserCommand;\n"
    generated += builtins(old).replace("const BUILTINS:", "pub(super) const BUILTINS:", 1)
    generated += helper
    for name, text in (("stock", old), ("candidate", new)):
        generated += (
            f"\npub(super) fn {name}(catalog: &[UserCommand]) -> String {{\n"
            '    match "help" {\n' + arm(text) + "        _ => unreachable!(),\n    }\n}\n"
        )
    (root / "implementations.rs").write_text(generated, encoding="utf-8")
    shutil.copyfile(HERE / "measure.rs", root / "main.rs")
    shutil.copyfile(a.checkout / ALLOC, root / "test_alloc.rs")
    contracts = a.contracts_rlib.resolve(strict=True)
    proof = root / "proof"
    subprocess.run(
        [
            "rustc", "--edition=2024", "--test", "-C", "opt-level=2", "-C", "debuginfo=0",
            "-C", "codegen-units=1", "-C", "link-arg=-fuse-ld=lld", "-L",
            f"dependency={contracts.parent}", "--extern", f"proteus_contracts={contracts}",
            "-o", proof, "main.rs",
        ],
        cwd=root,
        check=True,
    )
    snapshot = root / "parity.frames"
    subprocess.run(
        [proof, "--nocapture", "--test-threads=1"],
        cwd=root,
        check=True,
        env={**os.environ, "R63_SNAPSHOT": str(snapshot)},
    )
    payload = snapshot.read_bytes()
    print(f"Byte-identical corpus ({len(payload)} framed bytes), SHA256 {hashlib.sha256(payload).hexdigest()}")
