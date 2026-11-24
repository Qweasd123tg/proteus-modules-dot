"""Verify pinned inputs, apply/reverse, and run exact Rust source-lift for both images.rs variants."""
import hashlib
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

packet = Path(__file__).resolve().parent
source, rustc, rustfmt = map(lambda arg: Path(arg).resolve(), sys.argv[1:])
pinned = {
    "src/ui/chat/images.rs": "3d96d0f49276cdfed2a2f64815421603207b7422",
    "src/ui/chat/images/cache.rs": "f768237b865a0d3cf9b7592f2e26f69eb8071303",
    "src/ui/chat/images/tests.rs": "b85968c56f0377240bfaae1390114a8b3e0b327d",
}
posthash = "ae7614e1fd09bef397fa06744b550fbbcac7572b"
rel = "src/ui/chat/images.rs"
patch = packet / "source.patch"

def git_hash(data):
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()

def run(*command, cwd=None):
    return subprocess.check_output(list(map(str, command)), text=True, cwd=cwd).strip()

version = run(rustc, "--version")
assert "rustc 1.95.0 " in version, version
print(version)
for name, sha in pinned.items():
    actual = git_hash((source / name).read_bytes())
    assert actual == sha, (name, sha, actual)
    print(f"{actual} stock {name}")

with tempfile.TemporaryDirectory(prefix="proteus-image-key-proof-") as scratch:
    work = Path(scratch)
    dst = work / rel
    dst.parent.mkdir(parents=True)
    shutil.copyfile(source / rel, dst)
    run("git", "apply", "--check", patch, cwd=work)
    run("git", "apply", patch, cwd=work)
    assert git_hash(dst.read_bytes()) == posthash
    run(rustfmt, "--check", "--edition", "2024", "--config", "skip_children=true", dst)
    run("git", "apply", "--reverse", "--check", patch, cwd=work)
    print(f"{posthash} applied and rustfmt-checked postimage")
    matrices = {
        "stock": ["128 5568", "4 218"],
        "post": ["0 0", "2 131"],
    }
    for name, prod in (("stock", source / rel), ("post", dst)):
        lift = work / f"{name}.rs"
        run(sys.executable, packet / "lift.py", prod, source / "src/ui/chat/images/cache.rs",
            source / "src/ui/chat/images/tests.rs", packet / "cases.rs", lift)
        for profile in (0, 3):
            binary = work / f"{name}-{profile}"
            run(rustc, "--edition=2024", "-C", f"opt-level={profile}", lift, "-o", binary)
            result = run(binary, name)
            assert result.startswith("pass path, stale ownership and ticket")
            observed = [line.split(" ", 2)[-1] for line in result.splitlines() if line.startswith("alloc ")]
            print(f"{name} opt-level={profile}\n{result}")
            assert observed == matrices[name], (name, observed)
    run("git", "apply", "--reverse", patch, cwd=work)
    assert dst.read_bytes() == (source / rel).read_bytes()
    print("reverse: exact stock bytes")
