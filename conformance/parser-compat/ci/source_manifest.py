#!/usr/bin/env python3
"""Freeze the exact authored runner, fixtures and unmodified typed baseline copies."""
import hashlib
import json
from pathlib import Path

PACKAGE = Path(__file__).resolve().parent.parent


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def inputs():
    paths = [PACKAGE / name for name in ("Cargo.toml", "Cargo.lock", "rust-toolchain.toml",
                                         "FROZEN_BASELINE.json", "SOURCE_PINS.json")]
    for directory in ("src", "ci", "fixtures", ".cargo"):
        paths += [path for path in (PACKAGE / directory).rglob("*")
                  if path.is_file() and "__pycache__" not in path.parts]
    if (PACKAGE / "build.rs").exists():
        paths.append(PACKAGE / "build.rs")
    return sorted(paths)


def manifest():
    baseline = json.loads((PACKAGE / "FROZEN_BASELINE.json").read_text())
    if digest(PACKAGE / "fixtures/corpus.json") != baseline["corpus_sha256"]:
        raise ValueError("authored baseline corpus identity changed")
    for name, expected in baseline["exact_source_copies"].items():
        if digest(PACKAGE / name) != expected["sha256"]:
            raise ValueError("frozen actual typed baseline source changed")
    result = {}
    for path in inputs():
        if path.is_symlink():
            raise ValueError("symlink source input not accepted")
        result[str(path.relative_to(PACKAGE))] = digest(path)
    expected = {}
    for line in (PACKAGE / "CODE.sha256").read_text().splitlines():
        value, name = line.split("  ", 1)
        if name in expected:
            raise ValueError("duplicate source freeze entry")
        expected[name] = value
    if result != expected:
        raise ValueError("frozen source input set or bytes changed")
    return {"schema_version": 1, "sha256": result}


if __name__ == "__main__":
    print(json.dumps(manifest(), indent=2))
