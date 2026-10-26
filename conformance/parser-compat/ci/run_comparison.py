#!/usr/bin/env python3
"""Execute only fixed authored case IDs in the explicitly supplied Rust binary."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
PACKAGE = HERE.parent


def load(name):
    spec = importlib.util.spec_from_file_location(name, HERE / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


semantic = load("verify_observations")
budget_gate = load("verify_budgets")
capture = load("process_capture").capture


def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    binary = args.binary.resolve(strict=True)
    if not binary.is_file() or not os.access(binary, os.X_OK):
        parser.error("binary must name an executable file")
    if shutil.disk_usage(args.output.parent).free < 1024 ** 3 + 1024 ** 2:
        raise RuntimeError("insufficient disk reserve; no deletion attempted")
    args.output.mkdir(exist_ok=False)
    out = args.output.resolve(strict=True)
    children = out / "children"
    children.mkdir()
    home, workspace, temp = (out / name for name in ("home", "workspace", "tmp"))
    for path in (home, workspace, temp):
        path.mkdir()
    before_binary = digest(binary)
    corpus = semantic.decode((PACKAGE / "fixtures/corpus.json").read_text())
    envelopes = semantic.decode((PACKAGE / "fixtures/envelopes.json").read_text())
    required = semantic.decode((HERE / "required-cases.json").read_text())
    for name, fixture in (("semantic_ids", corpus), ("envelope_ids", envelopes)):
        ids = [case["id"] for case in fixture["cases"]]
        if ids != required[name] or len(ids) != len(set(ids)) or not all(
                type(value) is str and re.fullmatch(r"[a-z0-9_]{1,80}", value) for value in ids):
            raise RuntimeError("authored case identity/path contract changed")
    if required["parsers"] != list(semantic.PARSERS):
        raise RuntimeError("authored parser matrix changed")
    save(out / "inputs.json", {"schema_version": 1, "binary_sha256": before_binary,
         "per_child_timeout_seconds": 5, "capture_limit_bytes_per_pipe": 262144,
         "expected_children": 174, "source_fixture_counts": {"semantic": 38, "envelope": 7},
         "launch": "authored trusted binary; clear environment is not an OS sandbox",
         "started_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())})
    env = {"PATH": os.defpath, "HOME": str(home), "XDG_CONFIG_HOME": str(home), "TMPDIR": str(temp)}
    invocations = []

    def invoke(label, arguments):
        if shutil.disk_usage(out).free < 1024 ** 3 + 1024 ** 2:
            raise RuntimeError("disk reserve reached; comparison stopped")
        started = time.monotonic()
        child = subprocess.Popen([str(binary), *arguments], cwd=workspace, env=env,
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
        stdout, stderr, capture_error = capture(child, timeout=5, max_bytes=262144)
        (children / (label + ".stdout.json")).write_text(stdout)
        (children / (label + ".stderr.txt")).write_text(stderr)
        receipt = {"id": label, "arguments": arguments, "returncode": child.returncode,
                   "elapsed_seconds_diagnostic_only": time.monotonic() - started,
                   "capture_error": capture_error}
        save(children / (label + ".process.json"), receipt)
        invocations.append(receipt)
        if capture_error or child.returncode != 0:
            raise RuntimeError(f"authored child failed: {label}; see retained receipt")
        return semantic.decode(stdout)

    try:
        rows = []
        for engine in semantic.PARSERS:
            for case in corpus["cases"]:
                rows.append(invoke(engine + "__" + case["id"], [engine, case["id"]]))
        for case in envelopes["cases"]:
            rows.append(invoke("baseline_envelope__" + case["id"], ["baseline_envelope", case["id"]]))
        observations = semantic.verify(corpus, envelopes, rows)
        save(out / "semantic-observations.json", rows)
        save(out / "semantic-comparison.json", observations)
        budgets = []
        for kind in budget_gate.KINDS:
            modes = ("permissive", "restrictive", "comments_disabled") if kind == "comments" else ("permissive", "restrictive")
            for mode in modes:
                budgets.append(invoke("budget__" + kind + "__" + mode, ["saphyr_budget", kind, mode]))
        budget_result = budget_gate.verify(corpus, rows, budgets)
        save(out / "budget-observations.json", budgets)
        save(out / "budget-controls.json", budget_result)
        if len(invocations) != 174 or any(row["returncode"] != 0 or row["capture_error"] for row in invocations):
            raise RuntimeError("not all 174 exact children completed")
        if digest(binary) != before_binary:
            raise RuntimeError("binary changed during comparison")
        if any(list(path.iterdir()) for path in (home, workspace, temp)):
            raise RuntimeError("parser child wrote to its empty HOME/workspace/temp")
        save(out / "result.json", {"status": "passed_observation_and_control_integrity",
             "semantic_and_envelope_children": 159, "budget_children": 15,
             "binary_unchanged": True, "empty_directories_unchanged": True,
             "migration_acceptance": "not_granted", "incompatibilities": "retained in semantic-comparison.json",
             "unsupported_configurable_controls": budget_result["unsupported_configurable_controls"]})
    except BaseException as error:
        save(out / "result.json", {"status": "failed", "error": repr(error), "completed_children": len(invocations),
             "migration_acceptance": "not_granted"})
        raise
    finally:
        save(out / "invocations.json", invocations)


if __name__ == "__main__":
    main()
