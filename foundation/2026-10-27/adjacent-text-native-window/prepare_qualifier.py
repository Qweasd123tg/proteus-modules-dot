#!/usr/bin/env python3
"""Validate exact harness bytes; adapt only the isolated PR30 controller's npm audit environment."""
import argparse
import ast
import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[2]
RUNNER = "foundation/2026-10-27/adjacent-text-portable-fast/run_qualification.py"
MANIFEST = "foundation/2026-10-27/adjacent-text-portable-fast/manifest.json"
PIN = "cc69f8140c8cc9966356e7152b3a47594f672a65"
RUNNER_SHA = "7e9292d96f456938d943ac6e07b8db0431ffa6db3f13e9f5a4fa76e458c0033c"

def digest(data):
    return hashlib.sha256(data).hexdigest()

def insist(value,message):
    if not value:
        raise ValueError(message)

def adapted(source):
    before = '"npm_config_cache": str(work / "npm-cache"), "TMPDIR": str(work / "tmp"),'
    after = '"npm_config_cache": str(work / "npm-cache"), "TMPDIR": str(work / "tmp"),\n        "npm_config_audit": "false",'
    receipt_before = '"PROTEUS_MODULES_SOURCE", "PROTEUS_EXTENSIONS_SOURCE")'
    receipt_after = '"PROTEUS_MODULES_SOURCE", "PROTEUS_EXTENSIONS_SOURCE", "npm_config_audit")'
    insist(source.count(before) == 1 and source.count(receipt_before) == 1,
           "Qualifier adaptation anchors changed")
    output = source.replace(before,after).replace(receipt_before,receipt_after)
    ast.parse(output)
    return output

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qualifier-root",type=Path,required=True)
    parser.add_argument("--receipt",type=Path,required=True)
    args = parser.parse_args()
    own = json.loads((ROOT/"manifest.json").read_text())
    for relative,expected in own["sha256"].items():
        path = (REPO/relative).resolve()
        insist(path.is_relative_to(REPO) and path.is_file(),"Unsafe harness manifest path")
        insist(digest(path.read_bytes()) == expected,"Harness bytes differ: "+relative)
    qualifier = args.qualifier_root.resolve()
    head = subprocess.run(["git","-C",str(qualifier),"rev-parse","HEAD"],check=True,
                          capture_output=True,text=True,timeout=10).stdout.strip()
    insist(head == PIN,"Wrong original PR30 qualifier checkout")
    clean = subprocess.run(["git","-C",str(qualifier),"status","--porcelain"],check=True,
                           capture_output=True,text=True,timeout=10).stdout
    insist(not clean,"Original qualifier checkout is not clean")
    manifest_path = qualifier/MANIFEST
    old_manifest_bytes = manifest_path.read_bytes()
    old = json.loads(old_manifest_bytes)
    insist(digest(old_manifest_bytes) == own["qualifier_manifest_sha256"],
           "Original qualifier manifest identity changed")
    for relative,expected in old["sha256"].items():
        path = (qualifier/relative).resolve()
        insist(path.is_relative_to(qualifier) and digest(path.read_bytes()) == expected,
               "Original PR30 qualifier bytes differ: "+relative)
    runner = qualifier/RUNNER
    original = runner.read_bytes()
    insist(digest(original) == RUNNER_SHA,"Original qualifier runner changed")
    replacement = adapted(original.decode()).encode()
    runner.write_bytes(replacement)
    old["sha256"][RUNNER] = digest(replacement)
    updated_manifest_bytes = (json.dumps(old,indent=2)+"\n").encode()
    manifest_path.write_bytes(updated_manifest_bytes)
    changed = subprocess.run(["git","-C",str(qualifier),"diff","--name-only"],check=True,
                             capture_output=True,text=True,timeout=10).stdout.splitlines()
    insist(set(changed) == {RUNNER,MANIFEST},"Adaptation changed more than copied controller/manifest")
    result = {"schema":1,"status":"passed","original_qualifier_commit":PIN,
              "original_runner_sha256":digest(original),"adapted_runner_sha256":digest(replacement),
              "original_manifest_sha256":digest(old_manifest_bytes),
              "adapted_manifest_sha256":digest(updated_manifest_bytes),
              "changed_paths":changed,"constructed_environment":{"npm_config_audit":"false"},
              "receipt_key_added":"effective_build_env.npm_config_audit",
              "scope":"Harness-local qualifier adaptation only; product sources, locks and scripts unchanged",
              "reason":"Automatic npm Bulk Advisory POST is not authorized; this is not an advisory audit"}
    args.receipt.parent.mkdir(parents=True,exist_ok=True)
    args.receipt.write_text(json.dumps(result,indent=2)+"\n")

if __name__ == "__main__":
    main()
