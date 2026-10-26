#!/usr/bin/env python3
"""Hash authored executable inputs, rejecting a changed frozen module input."""
import hashlib
import json
from pathlib import Path
import sys

PACKAGE = Path(__file__).resolve().parent.parent


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def cargo_inputs(root):
    paths = [root / name for name in ("Cargo.toml", "Cargo.lock", "rust-toolchain.toml")]
    paths += [path for name in ("src", "tests", "examples", "benches")
              for path in (root / name).rglob("*.rs")]
    paths += [path for path in (root / ".cargo").rglob("*") if path.is_file()]
    if (root / "build.rs").exists():
        paths.append(root / "build.rs")
    return sorted(paths)


def read_hashes(path):
    result = {}
    for line in path.read_text().splitlines():
        sha, name = line.split("  ", 1)
        if name in result or Path(name).is_absolute() or ".." in Path(name).parts:
            raise ValueError("invalid source freeze entry")
        result[name] = sha
    return result


def hashes(root, paths):
    result = {}
    for path in paths:
        if path.is_symlink() or not path.is_file():
            raise ValueError(f"not a regular source input: {path.name}")
        result[str(path.relative_to(root))] = digest(path)
    return result


def manifest(module):
    paths = cargo_inputs(PACKAGE) + [PACKAGE / "scenarios.json"]
    paths += sorted(path for path in (PACKAGE / "ci").rglob("*")
                    if path.is_file() and "__pycache__" not in path.parts)
    module_hashes = hashes(module, cargo_inputs(module))
    if module_hashes != read_hashes(PACKAGE / "ci/portable-module.sha256"):
        raise ValueError("frozen portable module source input set or bytes changed")
    harness_hashes = hashes(PACKAGE, paths)
    if harness_hashes != read_hashes(PACKAGE / "CODE.sha256"):
        raise ValueError("frozen harness source input set or bytes changed")
    return {"schema_version": 1, "harness": harness_hashes,
            "portable_module": module_hashes}


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: source_manifest.py PORTABLE_MODULE_PACKAGE")
    print(json.dumps(manifest(Path(sys.argv[1]).resolve(strict=True)), indent=2))
