#!/usr/bin/env python3
"""Reconstruct exact selected-package candidate and run Python-only controls."""
import argparse
import ast
from contextlib import ExitStack
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import sys
import tempfile
import tomllib
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
REPOSITORY = "Proteus-harness/Proteus-desktop-extensions"
REVISION = "3361fc1650c4ac6f167c3e48a0fba8980a5c9038"
BASELINE_FILES = ["package.py", "README.md"]
CANDIDATE_FILES = {"package.py", "README.md", "tests/test_package_selection.py"}
HUNK = re.compile(r"@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@(?:.*)\n$")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def apply_exact(files, diff):
    """Apply only exact LF unified hunks; no fuzz, offsets, subprocess or paths."""
    require(set(files) == set(BASELINE_FILES), "unexpected baseline paths")
    files = dict(files)
    lines = diff.splitlines(keepends=True)
    changed = set()
    i = 0
    while i < len(lines):
        require(lines[i].startswith("--- "), "expected old file header")
        old = lines[i][4:].rstrip("\n")
        i += 1
        require(i < len(lines) and lines[i].startswith("+++ b/"), "expected new file header")
        name = lines[i][6:].rstrip("\n")
        require(name in CANDIDATE_FILES, "unexpected patch path")
        require(name not in changed, "duplicate patch file")
        changed.add(name)
        i += 1
        require(old == "/dev/null" or old == "a/" + name, "rename or invalid old path")
        require((old == "/dev/null") == (name not in files), "unexpected baseline existence")
        source = files.get(name, "").splitlines(keepends=True)
        result = []
        cursor = 0
        hunks = 0
        while i < len(lines) and lines[i].startswith("@@ "):
            match = HUNK.fullmatch(lines[i])
            require(match is not None, "invalid hunk header")
            old_line, old_count, new_line, new_count = match.groups()
            old_count = int(old_count) if old_count is not None else 1
            new_count = int(new_count) if new_count is not None else 1
            start = int(old_line) - (1 if old_count else 0)
            require(cursor <= start <= len(source), "invalid or overlapping hunk offset")
            result.extend(source[cursor:start])
            cursor = start
            require(len(result) == int(new_line) - (1 if new_count else 0), "new hunk offset mismatch")
            seen_old = seen_new = 0
            i += 1
            while seen_old < old_count or seen_new < new_count:
                require(i < len(lines), "truncated hunk")
                line = lines[i]
                require(line and line[0] in " +-", "invalid hunk line")
                body = line[1:]
                if line[0] in " -":
                    require(cursor < len(source) and source[cursor] == body, "patch context mismatch")
                    cursor += 1
                    seen_old += 1
                if line[0] in " +":
                    result.append(body)
                    seen_new += 1
                require(seen_old <= old_count and seen_new <= new_count, "hunk count overflow")
                i += 1
            hunks += 1
        require(hunks > 0, "file without hunks")
        result.extend(source[cursor:])
        files[name] = "".join(result)
    require(changed == CANDIDATE_FILES, "incomplete patch")
    return files


def load_candidate():
    manifest = json.loads((HERE / "manifest.json").read_text())
    require(manifest["baseline_files"] == BASELINE_FILES, "unexpected baseline paths")
    require(set(manifest["candidate_sha256"]) == CANDIDATE_FILES, "unexpected candidate paths")
    source_bytes = (HERE / "source-bundle.json").read_bytes()
    patch_bytes = (HERE / "extension-selective-packaging.patch").read_bytes()
    require(sha256(source_bytes) == manifest["source_bundle_sha256"], "source bundle digest mismatch")
    require(sha256(patch_bytes) == manifest["patch_sha256"], "patch digest mismatch")
    source = json.loads(source_bytes)
    for value in (source, manifest):
        require(value["schema"] == 1, "unsupported schema")
        require(value["repository"] == REPOSITORY and value["revision"] == REVISION, "upstream pin mismatch")
    for name, item in source["files"].items():
        data = item["content"].encode()
        require(sha256(data) == item["sha256"], f"source digest mismatch: {name}")
        blob = hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()
        require(blob == item["git_blob_sha"], f"Git blob mismatch: {name}")
    workspace = tomllib.loads(source["files"]["Cargo.toml"]["content"])
    require(workspace["workspace"]["members"] == ["sdk", "packages/*"], "workspace layout drift")
    ids = sorted({name.split("/")[1] for name in source["files"] if name.startswith("packages/")})
    require(ids == manifest["package_ids"] and len(ids) == 11, "package inventory mismatch")
    for name in ids:
        cargo = tomllib.loads(source["files"][f"packages/{name}/Cargo.toml"]["content"])
        extension = json.loads(source["files"][f"packages/{name}/extension.json"]["content"])
        require(cargo["package"]["name"] == f"extension-{name}", "Cargo package naming drift")
        require([target["name"] for target in cargo["bin"]] == [name], "Cargo bin identity drift")
        require(extension["id"] == name and extension["command"] == [f"bin/{name}"] and extension["protocol"] == 3,
                "extension manifest drift")
    original = {name: source["files"][name]["content"] for name in manifest["baseline_files"]}
    candidate = apply_exact(original, patch_bytes.decode())
    require(set(candidate) == CANDIDATE_FILES, "candidate inventory mismatch")
    for name, text in candidate.items():
        require(sha256(text.encode()) == manifest["candidate_sha256"][name], f"candidate digest mismatch: {name}")
    before = ast.parse(original["package.py"])
    after = ast.parse(candidate["package.py"])
    for name in ("binaries", "place", "assemble", "develop"):
        nodes = [next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == name)
                 for tree in (before, after)]
        require(ast.dump(nodes[0]) == ast.dump(nodes[1]), f"legacy helper changed: {name}")
    return candidate, manifest


def denied(*args, **kwargs):
    raise AssertionError("real subprocess/network forbidden in selected-package qualification")


def run_controls(candidate, manifest):
    require(set(candidate) == CANDIDATE_FILES, "unexpected candidate paths")
    with tempfile.TemporaryDirectory(prefix="proteus-selected-package-") as directory:
        root = Path(directory)
        for name, text in candidate.items():
            target = root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text)
        with ExitStack() as stack:
            stack.enter_context(patch.dict(os.environ, {"CANDIDATE_PACKAGE": str(root / "package.py")}))
            for name in ("run", "Popen", "call", "check_call", "check_output"):
                stack.enter_context(patch.object(subprocess, name, denied))
            stack.enter_context(patch.object(os, "system", denied))
            stack.enter_context(patch.object(socket, "create_connection", denied))
            for name in ("connect", "connect_ex"):
                stack.enter_context(patch.object(socket.socket, name, denied))
            spec = importlib.util.spec_from_file_location("selected_package_bound_tests", root / "tests/test_package_selection.py")
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            names = unittest.defaultTestLoader.getTestCaseNames(module.SelectedPackageReview)
            require(names == manifest["test_names"], "test inventory mismatch")
            suite = unittest.defaultTestLoader.loadTestsFromTestCase(module.SelectedPackageReview)
            output = io.StringIO()
            result = unittest.TextTestRunner(stream=output, verbosity=2).run(suite)
        return result, output.getvalue()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    candidate, manifest = load_candidate()
    result, log = run_controls(candidate, manifest)
    sys.stdout.write(log)
    report = {"schema": 1, "repository": REPOSITORY, "revision": REVISION,
              "candidate_sha256": manifest["candidate_sha256"], "patch_sha256": manifest["patch_sha256"],
              "tests_run": result.testsRun, "tests_successful": result.wasSuccessful(),
              "legacy_helpers_ast_identical": True, "real_cargo_or_product_execution": False,
              "qualification": manifest["qualification"]}
    if args.output:
        args.output.mkdir(parents=True, exist_ok=True)
        (args.output / "tests.log").write_text(log)
        (args.output / "result.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, sort_keys=True))
    return 0 if result.wasSuccessful() and result.testsRun == len(manifest["test_names"]) else 1


if __name__ == "__main__":
    raise SystemExit(main())
