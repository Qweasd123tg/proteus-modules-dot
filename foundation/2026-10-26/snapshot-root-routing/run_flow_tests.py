#!/usr/bin/env python3
"""Test the unchanged production pagination-flow module on the manifest's pinned base."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile


def blob_sha(data):
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("upstream", type=Path, help="exact Desktop checkout after pagination prerequisite")
    parser.add_argument("--rustc", default="rustc")
    args = parser.parse_args()
    upstream = args.upstream.resolve()
    bundle = Path(__file__).resolve().parent
    manifest = json.loads((bundle / "manifest.json").read_text())
    actual = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=upstream, text=True).strip()
    if actual != manifest["source_commit"]:
        raise SystemExit(f"Wrong base: {actual}; expected {manifest['source_commit']}")
    for relative, expected in manifest["stage_git_blobs"]["pagination_prerequisite"].items():
        path = Path(relative)
        if path.is_absolute() or ".." in path.parts or not path.parts:
            raise SystemExit(f"Unsafe source path: {relative}")
        source = upstream / path
        if expected is None:
            if source.exists():
                raise SystemExit(f"Expected absent source: {relative}")
        elif not source.is_file() or blob_sha(source.read_bytes()) != expected:
            raise SystemExit(f"Pagination-stage source mismatch: {relative}")

    source = upstream / "src/ui/chat/history_flow.rs"
    with tempfile.TemporaryDirectory(prefix="proteus-history-flow-") as directory:
        work = Path(directory)
        driver = work / "driver.rs"
        driver.write_text(
            f"#[path = {json.dumps(str(source), ensure_ascii=False)}]\nmod history_flow;\n"
        )
        binary = work / "history-flow-tests"
        subprocess.run(
            [args.rustc, "--edition=2024", "--crate-name", "proteus_history_flow_tests",
             "--test", str(driver), "-o", str(binary)],
            check=True,
        )
        subprocess.run([str(binary)], check=True)


if __name__ == "__main__":
    main()
