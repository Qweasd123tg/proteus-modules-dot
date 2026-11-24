"""Verify input identities, isolated patch scope, and the lifted behavior in two profiles."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

sys.dont_write_bytecode = True
from lift import lift, history

packet = Path(__file__).resolve().parent
pins = json.loads((packet / "SOURCE-PROVENANCE.json").read_text())
post = "72083028e592d9f7e981a67e800a6367438251a0"


def run(*command, cwd=None, env=None):
    r = subprocess.run(
        list(map(str, command)), text=True, cwd=cwd, env=env,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
    )
    if r.returncode:
        print(r.stdout, end="", flush=True)
        r.check_returncode()
    return r.stdout.strip()


def main():
    source, vendor, toolchain = map(lambda p: Path(p).resolve(), sys.argv[1:])
    env = {**os.environ, "PATH": f"{toolchain}{os.pathsep}{os.environ.get('PATH', '')}",
           "RUSTC": str(toolchain / "rustc"), "RUSTFLAGS": ""}
    version = run(toolchain / "rustc", "--version")
    assert "rustc 1.95.0 " in version
    print(version, flush=True)
    for path, spec in pins["source"].items():
        b = (source / path).read_bytes()
        got = hashlib.sha1(b"blob " + str(len(b)).encode() + b"\0" + b).hexdigest()
        assert got == spec["git_blob"], (path, got)
        print(f"{got} {path}", flush=True)
    with tempfile.TemporaryDirectory(prefix="proteus-disclosures-proof-") as scratch:
        dest = Path(scratch)
        native = dest / "native"
        for path in pins["source"]:
            target = native / path
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source / path, target)
            target.chmod(0o644)
        patch = packet / "source.patch"
        assert run("git", "apply", "--numstat", patch).split() == ["7", "0", str(history)]
        run("git", "apply", "--check", patch, cwd=native)
        run("git", "apply", patch, cwd=native)
        assert run("git", "hash-object", history, cwd=native) == post
        run(toolchain / "rustfmt", "--check", "--edition", "2024",
            "--config", "skip_children=true", native / history)
        print(f"{post} postimage; 7 added lines; rustfmt check passed", flush=True)
        lift(source, native, packet, dest / "src")
        run("git", "apply", "--reverse", "--check", patch, cwd=native)
        run("git", "apply", "--reverse", patch, cwd=native)
        assert all((native / path).read_bytes() == (source / path).read_bytes()
                   for path in pins["source"])
        print("Reverse application restores every pinned input byte", flush=True)
        for name in ("Cargo.toml", "Cargo.lock"):
            shutil.copyfile(packet / name, dest / name)
        (dest / ".cargo").mkdir()
        (dest / ".cargo" / "config.toml").write_text(
            f'[source.crates-io]\nreplace-with = "offline"\n'
            f'[source.offline]\ndirectory = {json.dumps(str(vendor))}\n'
        )
        env["CARGO_HOME"] = str(dest / "cargo-home")
        for profile in ([], ["--release"]):
            print("Release build" if profile else "Debug build", flush=True)
            output = run(toolchain / "cargo", "test", "--offline", "--locked", *profile, "--",
                         "--nocapture", "--test-threads=1", cwd=dest, env=env)
            assert "7 passed; 0 failed" in output
            print(output, flush=True)


if __name__ == "__main__":
    main()
