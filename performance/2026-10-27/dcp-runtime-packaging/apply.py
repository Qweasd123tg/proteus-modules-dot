#!/usr/bin/env python3
"""Materialize the reviewed DCP patchbundle in a fresh directory; never edit upstream."""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import tarfile
import tempfile

BASE = "0d9c5fd18f04e6e3a083351678065c5f72966792"
REPOSITORY = "https://github.com/Proteus-harness/Proteus-modules"

def sha256(data):
    return hashlib.sha256(data).hexdigest()

def git(source, *args):
    return subprocess.check_output(["git", "-C", str(source), *args])

def safe_path(value):
    path = PurePosixPath(value)
    if not value or path.is_absolute() or str(path) != value or any(part in ("", ".", "..") for part in value.split("/")):
        raise ValueError("noncanonical bundle path: " + repr(value))
    if not value.startswith("hook/dcp/") or value.endswith("/"):
        raise ValueError("bundle path is outside hook/dcp: " + value)
    return path

def validate(source, raw, expected_hash):
    if sha256(raw) != expected_hash:
        raise ValueError("whole bundle SHA-256 does not match the reviewed artifact")
    bundle = json.loads(raw)
    if bundle.get("schema") != 1 or bundle.get("sourceRepository") != REPOSITORY or bundle.get("sourceRevision") != BASE:
        raise ValueError("unsupported bundle identity")
    if git(source, "rev-parse", "HEAD").decode().strip() != BASE:
        raise ValueError("source HEAD must equal the full pinned baseline commit")
    if git(source, "status", "--porcelain=v1", "--untracked-files=all"):
        raise ValueError("source checkout must be clean; nothing will be modified")
    entries = {}
    for record in git(source, "ls-tree", "-r", "-z", "--full-tree", BASE).split(b"\0"):
        if not record:
            continue
        header, name = record.split(b"\t", 1)
        mode, kind, blob = header.decode().split()
        entries[name.decode()] = (mode, kind, blob)
    replacements = []
    seen = set()
    for item in bundle["files"]:
        value = item["path"]
        safe_path(value)
        if value in seen:
            raise ValueError("duplicate bundle file: " + value)
        seen.add(value)
        content = item["content"].encode("utf-8")
        if len(content) != item["utf8Bytes"] or sha256(content) != item["sha256"]:
            raise ValueError("candidate bytes do not match manifest: " + value)
        original = item["originalGitBlob"]
        entry = entries.get(value)
        if original is None:
            if entry is not None:
                raise ValueError("new candidate path exists in baseline: " + value)
        elif entry is None or entry[1:] != ("blob", original) or entry[0] not in ("100644", "100755"):
            raise ValueError("original Git blob does not match: " + value)
        replacements.append((value, content, original))
    if not replacements:
        raise ValueError("empty bundle")
    return bundle, replacements

def extract_archive(raw, destination):
    # git archive has no untrusted npm contents. Still reject links and traversal.
    with tarfile.open(fileobj=io.BytesIO(raw), mode="r:") as archive:
        for member in archive.getmembers():
            name = member.name.rstrip("/")
            path = PurePosixPath(name)
            if path.is_absolute() or str(path) != name or ".." in path.parts or name == ".":
                raise ValueError("invalid pinned archive member")
            target = destination.joinpath(*path.parts)
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
            elif member.isfile():
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.extractfile(member) as source, target.open("xb") as output:
                    shutil.copyfileobj(source, output)
                target.chmod(0o755 if member.mode & 0o111 else 0o644)
            else:
                raise ValueError("non-regular pinned archive member: " + name)

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path, help="clean baseline Git checkout")
    parser.add_argument("--bundle", required=True, type=Path)
    parser.add_argument("--sha256", required=True, help="reviewed whole source-bundle.json hash")
    parser.add_argument("--output", required=True, type=Path, help="new destination; candidate appears atomically at output/tree")
    args = parser.parse_args()
    if len(args.sha256) != 64 or any(c not in "0123456789abcdef" for c in args.sha256):
        raise ValueError("expected lowercase SHA-256")
    source = args.source.resolve(strict=True)
    output = args.output.resolve(strict=False)
    if output.is_relative_to(source) or source.is_relative_to(output):
        raise ValueError("source and output must not overlap")
    if output.exists() or output.is_symlink():
        raise ValueError("output already exists")
    raw = args.bundle.read_bytes()
    bundle, replacements = validate(source, raw, args.sha256)
    archive = git(source, "archive", "--format=tar", BASE)
    output.mkdir()  # Reserve a brand-new container exclusively; no existing data is replaced.
    stage = Path(tempfile.mkdtemp(prefix=".incomplete-", dir=output))
    try:
        extract_archive(archive, stage)
        for value, content, original in replacements:
            target = stage.joinpath(*PurePosixPath(value).parts)
            if original is not None:
                prior = target.read_bytes()
                git_blob = hashlib.sha1(b"blob " + str(len(prior)).encode() + b"\0" + prior).hexdigest()
                if git_blob != original:
                    raise ValueError("archive content does not match original blob: " + value)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
            if target.read_bytes() != content:
                raise ValueError("candidate write readback mismatch: " + value)
        receipt = {"schema": 1, "sourceRepository": REPOSITORY, "sourceRevision": BASE,
                   "bundleSha256": sha256(raw), "changedFiles": [
                       {key: item[key] for key in ("path", "originalGitBlob", "utf8Bytes", "sha256")}
                       for item in bundle["files"]],
                   "verification": "Source materialization only; no builds or tests executed."}
        (stage / ".dcp-packaging-apply.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
        os.rename(stage, output / "tree")
        print(json.dumps({"candidate": str(output / "tree"), "bundleSha256": sha256(raw)}))
    except BaseException:
        shutil.rmtree(stage, ignore_errors=True)
        # Keep the exclusively created output container as a visible failed attempt.
        raise

if __name__ == "__main__":
    main()
