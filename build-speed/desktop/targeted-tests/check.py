#!/usr/bin/env python3
"""Verify the pinned runner patch and exercise it with entirely fake dependencies."""
import argparse
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


HERE = Path(__file__).resolve().parent


def bounded(path):
    raw = path.read_bytes()
    if len(raw) > 64 * 1024:
        raise ValueError("Runner input exceeds 64 KiB: " + str(path))
    return raw


def sha256(raw):
    return hashlib.sha256(raw).hexdigest()


def check(output):
    receipt = {
        "status": "FAIL",
        "scope": "Pinned Desktop runner patch and synthetic subprocess controls only",
        "rust_tests": "NOT_RUN", "extensions": "NOT_RUN", "workspace_gate": "NOT_RUN",
        "speedup": "NOT_MEASURED",
        "delivery_commit": os.environ.get("GITHUB_SHA"),
        "run_id": os.environ.get("GITHUB_RUN_ID"),
        "run_attempt": os.environ.get("GITHUB_RUN_ATTEMPT"),
        "workflow_ref": os.environ.get("GITHUB_WORKFLOW_REF"),
        "controller_sha256": sha256(bounded(Path(__file__))),
    }
    try:
        identity_bytes = bounded(HERE / "source-identity.json")
        identity = json.loads(identity_bytes)
        receipt["source_identity_sha256"] = sha256(identity_bytes)
        receipt["upstream_repository"] = identity["repository"]
        receipt["upstream_commit"] = identity["commit"]
        if identity["schema"] != 1:
            raise ValueError("Unsupported identity schema")
        original = bounded(HERE / "upstream/test.py")
        preimage = next(row for row in identity["files"] if row["path"] == "scripts/test.py")
        blob = hashlib.sha1(b"blob " + str(len(original)).encode() + b"\0" + original).hexdigest()
        if len(original) != preimage["size"] or blob != preimage["sha"]:
            raise ValueError("Pinned upstream launcher preimage differs")
        receipt["preimage_git_blob"] = blob
        patch = HERE / "desktop-headless-test-selection.patch"
        if identity["patch"]["path"] != patch.name or sha256(bounded(patch)) != identity["patch"]["sha256"]:
            raise ValueError("Reviewed patch bytes differ")
        receipt["patch_sha256"] = identity["patch"]["sha256"]
        if identity["candidate"]["path"] != "scripts/test.py":
            raise ValueError("Unexpected candidate path")
        with tempfile.TemporaryDirectory(prefix="proteus-runner-controls-") as temporary:
            root = Path(temporary)
            candidate = root / "scripts/test.py"
            candidate.parent.mkdir()
            candidate.write_bytes(original)
            env = {"PATH": os.environ.get("PATH", ""), "LC_ALL": "C",
                   "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull,
                   "GIT_TERMINAL_PROMPT": "0"}
            for options in (["--check"], []):
                subprocess.run(["git", "apply", *options, "--whitespace=error", str(patch)],
                               cwd=root, env=env, check=True, capture_output=True, timeout=10)
            candidate_hash = sha256(bounded(candidate))
            if candidate_hash != identity["candidate"]["sha256"]:
                raise ValueError("Applied candidate bytes differ")
            receipt["candidate_sha256"] = candidate_hash
            driver = HERE / "test_runner_selection.py"
            receipt["controls_sha256"] = sha256(bounded(driver))
            spec = importlib.util.spec_from_file_location("runner_selection_controls", driver)
            controls = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(controls)
            controls.RUNNER_PATH = candidate
            suite = unittest.defaultTestLoader.loadTestsFromModule(controls)
            log = io.StringIO()
            result = unittest.TextTestRunner(stream=log, verbosity=2).run(suite)
            sys.stderr.write(log.getvalue())
            receipt.update(tests_run=result.testsRun, failures=len(result.failures),
                           errors=len(result.errors), skipped=len(result.skipped))
            if (not result.wasSuccessful() or result.skipped or result.expectedFailures
                    or result.testsRun != identity["expected_controls"]):
                raise ValueError("Runner controls did not complete as a full pass")
            receipt["status"] = "PASS"
    except Exception as error:
        receipt["error"] = type(error).__name__ + ": " + str(error)
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt, indent=2))
    return 0 if receipt["status"] == "PASS" else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="Optional small JSON receipt")
    raise SystemExit(check(parser.parse_args().output))
