"""Shared helpers for isolated Rust builds. No downloads; use matching built rlibs."""
import subprocess


def git(repository, *arguments):
    return subprocess.check_output(["git", "-C", repository, *arguments], text=True)


def compile_stand(rustc, deps, directory, libraries, *, test=False):
    cmd = [
        str(rustc), "--edition=2024", "-C", "link-arg=-fuse-ld=lld",
        "-L", f"dependency={deps}", "-C", f"opt-level={0 if test else 2}",
    ]
    if test:
        cmd.extend(["--test", "-C", "debuginfo=0"])
    for name in libraries:
        artifacts = list(deps.glob(f"lib{name}-*.rlib"))
        if len(artifacts) != 1:
            raise SystemExit(f"Expected one matching {name} rlib in {deps}: {artifacts}")
        cmd.extend(["--extern", f"{name}={artifacts[0]}"])
    binary = directory / "stand"
    subprocess.run(cmd + [directory / "stand.rs", "-o", binary], check=True)
    return binary
