#!/usr/bin/env python3
"""Apply a pinned review bundle in a fresh CI checkout; retain bounded evidence."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parent
REPOS = {
    "core": "https://github.com/Proteus-harness/Proteus-core.git",
    "desktop": "https://github.com/Proteus-harness/Proteus-desktop.git",
}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def safe_relative(value):
    path = Path(value)
    if path.is_absolute() or ".." in path.parts or not path.parts:
        raise ValueError(f"Unsafe relative path: {value}")
    return path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", choices=REPOS)
    parser.add_argument("--work-dir", type=Path, required=True)
    parser.add_argument("--evidence-dir", type=Path, required=True)
    args = parser.parse_args()
    work = args.work_dir.resolve()
    evidence_dir = args.evidence_dir.resolve()
    if work.exists():
        raise SystemExit("Fresh absent --work-dir required; existing data is never removed")
    evidence_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = ROOT / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    spec = manifest["targets"][args.target]
    if spec["repository"] != REPOS[args.target] or not re.fullmatch(r"[0-9a-f]{40}", spec["commit"]):
        raise SystemExit("Unexpected source identity")
    result = {
        "schema": 1,
        "target": args.target,
        "bundle_commit": os.environ.get("GITHUB_SHA"),
        "workflow_run_id": os.environ.get("GITHUB_RUN_ID"),
        "source_repository": spec["repository"],
        "source_commit": spec["commit"],
        "manifest_sha256": digest(manifest_path),
        "commands": [],
        "status": "running",
        "claims": "Targeted regression evidence only; not native GUI, portable delivery or speed measurement",
    }
    env = os.environ.copy()
    env.update({"CARGO_BUILD_JOBS": "2", "CARGO_INCREMENTAL": "0", "RUST_TEST_THREADS": "4", "PYTHONDONTWRITEBYTECODE": "1", "GIT_TERMINAL_PROMPT": "0"})

    def save():
        (evidence_dir / "result.json").write_text(json.dumps(result, indent=2) + "\n")

    def run(command, cwd=None, *, expected_failed=(), required_passed=()):
        command = [str(arg).replace("{source}", str(work)).replace("{bundle}", str(ROOT)) for arg in command]
        print("+ " + " ".join(map(str, command)), flush=True)
        start = time.monotonic()
        proc = subprocess.Popen(list(map(str, command)), cwd=cwd, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        tail = b""
        while True:
            chunk = proc.stdout.read(4096)
            if not chunk:
                break
            sys.stdout.buffer.write(chunk)
            sys.stdout.buffer.flush()
            tail = (tail + chunk)[-65536:]
        code = proc.wait()
        row = {"argv": list(map(str, command)), "exit_code": code, "elapsed_seconds": round(time.monotonic() - start, 3), "log_tail": tail.decode(errors="replace")}
        result["commands"].append(row)
        output = tail.decode(errors="replace")
        observed_failed = re.findall(r"^test (\S+) \.{3} FAILED$", output, re.MULTILINE)
        observed_passed = re.findall(r"^test (\S+) \.{3} ok$", output, re.MULTILINE)
        row["observed_failed_tests"] = observed_failed
        row["observed_passed_tests"] = observed_passed
        save()
        if expected_failed:
            if code == 0 or sorted(observed_failed) != sorted(expected_failed):
                raise ValueError(f"Expected only named behavioral failures {expected_failed}; got exit {code}, failures {observed_failed}")
            if "test result: FAILED." not in output or "could not compile" in output:
                raise ValueError("Baseline did not reach an ordinary test assertion failure")
            row["status"] = "expected_regression_failure"
        elif code:
            raise subprocess.CalledProcessError(code, command)
        elif required_passed and not set(required_passed).issubset(observed_passed):
            raise ValueError(f"Required behavioral tests absent from passed evidence: {set(required_passed) - set(observed_passed)}")
        else:
            row["status"] = "success"
        save()
        return output.strip()

    save()
    try:
        for relative, expected in manifest["sha256"].items():
            path = ROOT / safe_relative(relative)
            if digest(path) != expected:
                raise ValueError(f"Bundle hash mismatch: {relative}")
        run(["rustc", "+1.95.0", "--version", "--verbose"])
        run(["python3", "--version"])
        run(["git", "--version"])
        run(["git", "init", work])
        run(["git", "remote", "add", "origin", spec["repository"]], work)
        run(["git", "-c", "credential.helper=", "fetch", "--depth=1", "origin", spec["commit"]], work)
        run(["git", "checkout", "--detach", "FETCH_HEAD"], work)
        observed = run(["git", "rev-parse", "HEAD"], work)
        if observed != spec["commit"]:
            raise ValueError("Checked out unexpected source commit")
        result["source_tree"] = run(["git", "rev-parse", "HEAD^{tree}"], work)
        result["original_git_blob"] = {}
        for relative, expected in spec["original_git_blob"].items():
            observed_blob = run(["git", "hash-object", work / safe_relative(relative)], work)
            result["original_git_blob"][relative] = observed_blob
            if observed_blob != expected:
                raise ValueError(f"Pinned upstream file hash mismatch: {relative}")
        def apply_patches(paths):
            for relative in paths:
                patch = ROOT / safe_relative(relative)
                run(["git", "apply", "--check", "--index", patch], work)
                run(["git", "apply", "--index", patch], work)
        apply_patches(spec["test_patches"])
        result["baseline_test_tree"] = run(["git", "write-tree"], work)
        baseline = spec.get("baseline")
        if baseline:
            if not baseline["expected_failed_tests"]:
                raise ValueError("Baseline must name actual behavioral failures")
            run(baseline["argv"], work, expected_failed=baseline["expected_failed_tests"])
            run(["git", "diff", "--exit-code"], work)
        else:
            result["baseline_not_run"] = spec["baseline_not_run_reason"]
        apply_patches(spec["fix_patches"])
        changed = run(["git", "diff", "--cached", "--name-only"], work).splitlines()
        if sorted(changed) != sorted(spec["changed_files"]):
            raise ValueError(f"Unexpected changed source paths: {changed}")
        result["patched_tree"] = run(["git", "write-tree"], work)
        result["patched_sha256"] = {p: digest(work / safe_relative(p)) for p in changed}
        run(["git", "diff", "--cached", "--check"], work)
        for check in spec["checks"]:
            run(check["argv"], work, required_passed=check.get("required_passed_tests", ()))
        run(["git", "diff", "--exit-code"], work)
        if not any(check.get("required_passed_tests") for check in spec["checks"]):
            raise ValueError("At least one named passing behavioral regression is required")
        result["status"] = "success"
    except Exception as exc:
        result["status"] = "failure"
        result["error"] = f"{type(exc).__name__}: {exc}"
        raise
    finally:
        save()


if __name__ == "__main__":
    main()
