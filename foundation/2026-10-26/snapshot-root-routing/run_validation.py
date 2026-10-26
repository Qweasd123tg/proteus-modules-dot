#!/usr/bin/env python3
"""Validate the reviewed, pinned snapshot-root composition on a fresh CI runner."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import selectors
import signal
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[2]
SOURCE_REPOSITORY = "https://github.com/Proteus-harness/Proteus-desktop.git"
SOURCE_COMMIT = "5748ac04f78eaffa1f4ea6102bd349ca61412e8d"
EXTENSIONS_REPOSITORY = "https://github.com/Proteus-harness/Proteus-desktop-extensions.git"
EXTENSIONS_COMMIT = "3361fc1650c4ac6f167c3e48a0fba8980a5c9038"


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def relative(value):
    path = Path(value)
    if path.is_absolute() or ".." in path.parts or not path.parts:
        raise ValueError(f"Unsafe relative path: {value}")
    return path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work-dir", type=Path, required=True)
    parser.add_argument("--evidence-dir", type=Path, required=True)
    args = parser.parse_args()
    work = args.work_dir.resolve()
    evidence = args.evidence_dir.resolve()
    if work.exists():
        raise SystemExit("Fresh absent --work-dir required; existing data is never removed")
    evidence.mkdir(parents=True, exist_ok=True)
    manifest = json.loads((ROOT / "manifest.json").read_text())
    if (manifest["source_repository"], manifest["source_commit"]) != (SOURCE_REPOSITORY, SOURCE_COMMIT):
        raise SystemExit("Unexpected source identity")
    result = {
        "schema": 1,
        "bundle_commit": os.environ.get("GITHUB_SHA"),
        "workflow_run_id": os.environ.get("GITHUB_RUN_ID"),
        "source_repository": SOURCE_REPOSITORY,
        "source_commit": SOURCE_COMMIT,
        "manifest_sha256": sha256(ROOT / "manifest.json"),
        "baseline_definition": manifest["baseline_definition"],
        "commands": [],
        "stages": {},
        "status": "running",
        "claims": "Targeted composed-source routing regressions only; not pristine-upstream red, native GUI, portable delivery, or measured speed",
    }
    env = os.environ.copy()
    env.update({
        "CARGO_BUILD_JOBS": "2", "CARGO_INCREMENTAL": "0",
        "RUST_TEST_THREADS": "4", "PYTHONDONTWRITEBYTECODE": "1",
        "GIT_TERMINAL_PROMPT": "0", "RUSTUP_TOOLCHAIN": "1.95.0",
    })
    # The pinned fixture is supplied explicitly below, never selected by a sibling checkout.
    for key in ("PROTEUS_HARNESS_SOURCE", "PROTEUS_MODULES_SOURCE",
                "PROTEUS_EXTENSIONS_SOURCE", "PROTEUS_TEST_EXTENSIONS_SOURCE"):
        env.pop(key, None)

    def save():
        (evidence / "result.json").write_text(json.dumps(result, indent=2) + "\n")

    def run(command, cwd=None, *, expected_failed=(), required_passed=(), assertion_markers=(), timeout_seconds=300):
        command = [str(arg).replace("{source}", str(work)).replace("{bundle}", str(ROOT)).replace("{repo}", str(REPO)) for arg in command]
        print("+ " + " ".join(command), flush=True)
        started = time.monotonic()
        proc = subprocess.Popen(command, cwd=cwd, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, start_new_session=True)
        timed_out = False
        deadline = started + timeout_seconds

        def stop_process_group():
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass

        os.set_blocking(proc.stdout.fileno(), False)
        selector = selectors.DefaultSelector()
        selector.register(proc.stdout, selectors.EVENT_READ)
        tail = b""
        pending = ""
        failed, passed, markers = set(), set(), set()
        failed_summary = False
        compilation_error = False

        def observe(line):
            nonlocal failed_summary, compilation_error
            match = re.fullmatch(r"test (\S{1,400}) \.{3} (ok|FAILED)", line)
            if match:
                target = passed if match.group(2) == "ok" else failed
                if len(target) >= 10000:
                    raise ValueError("Unexpectedly many test names; refusing unbounded evidence")
                target.add(match.group(1))
            failed_summary |= line.startswith("test result: FAILED.")
            compilation_error |= "could not compile" in line
            for marker in assertion_markers:
                if marker in line:
                    markers.add(marker)

        try:
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    timed_out = True
                    stop_process_group()
                    break
                if not selector.select(min(1.0, remaining)):
                    continue
                chunk = os.read(proc.stdout.fileno(), 4096)
                if not chunk:
                    break
                sys.stdout.buffer.write(chunk)
                sys.stdout.buffer.flush()
                tail = (tail + chunk)[-65536:]
                lines = (pending + chunk.decode(errors="replace")).split("\n")
                pending = lines.pop()[-16384:]
                for line in lines:
                    observe(line.rstrip("\r"))
            observe(pending)
            code = proc.wait(timeout=10)
        finally:
            selector.close()
            proc.stdout.close()
            if proc.poll() is None:
                stop_process_group()
                proc.wait(timeout=10)
        row = {
            "argv": command, "exit_code": code, "timed_out": timed_out,
            "elapsed_seconds": round(time.monotonic() - started, 3), "timeout_seconds": timeout_seconds,
            "log_tail": tail.decode(errors="replace"),
            "observed_failed_tests": sorted(failed),
            "observed_passed_tests": sorted(passed),
            "observed_assertion_markers": sorted(markers),
        }
        result["commands"].append(row)
        save()
        if timed_out:
            raise TimeoutError(f"Command exceeded its {timeout_seconds}-second process-group watchdog")
        if expected_failed:
            if code != 101 or failed != set(expected_failed) or failed & passed:
                raise ValueError(f"Expected only named cargo behavioral failures {expected_failed}; got exit {code}, failures {sorted(failed)}")
            if not failed_summary or compilation_error or markers != set(assertion_markers):
                raise ValueError("Baseline did not reach every reviewed routing assertion failure")
            if not assertion_markers:
                raise ValueError("Baseline must name reviewed routing assertion messages")
            row["status"] = "expected_regression_failure"
        elif code:
            raise subprocess.CalledProcessError(code, command)
        else:
            row["status"] = "success"
        if not set(required_passed).issubset(passed):
            raise ValueError(f"Required tests absent from PASS evidence: {set(required_passed) - passed}")
        save()
        return tail.decode(errors="replace").strip()

    def fetch(repository, commit, destination):
        run(["git", "init", destination])
        run(["git", "remote", "add", "origin", repository], destination)
        run(["git", "-c", "credential.helper=", "fetch", "--depth=1", "origin", commit], destination)
        run(["git", "checkout", "--detach", "FETCH_HEAD"], destination)
        if run(["git", "rev-parse", "HEAD"], destination) != commit:
            raise ValueError("Checked out unexpected source commit")

    def verify_blobs(expected):
        observed = {}
        for path, blob in expected.items():
            file = work / relative(path)
            if blob is None:
                if file.exists():
                    raise ValueError(f"Expected absent source path: {path}")
                observed[path] = None
                continue
            actual = run(["git", "hash-object", file], work)
            if actual != blob:
                raise ValueError(f"Source blob mismatch: {path}")
            observed[path] = actual
        return observed

    def stage(name, expected):
        result["stages"][name] = {
            "tree": run(["git", "write-tree"], work),
            "git_blobs": verify_blobs(expected),
        }
        save()

    def apply(paths):
        for path in paths:
            patch = REPO / relative(path)
            run(["git", "apply", "--check", "--index", patch], work)
            run(["git", "apply", "--index", patch], work)
            run(["git", "diff", "--cached", "--check"], work)

    save()
    try:
        for path, expected in manifest["sha256"].items():
            if sha256(REPO / relative(path)) != expected:
                raise ValueError(f"Bundle checksum mismatch: {path}")
        run(["rustc", "+1.95.0", "--version", "--verbose"])
        run(["python3", "--version"])
        run(["git", "--version"])
        fetch(SOURCE_REPOSITORY, SOURCE_COMMIT, work)
        stage("upstream", manifest["stage_git_blobs"]["upstream"])
        apply(manifest["prerequisite_patches"])
        stage("pagination_prerequisite", manifest["stage_git_blobs"]["pagination_prerequisite"])
        for check in manifest["prerequisite_checks"]:
            run(check["argv"], work, required_passed=check.get("required_passed_tests", ()), timeout_seconds=check.get("timeout_seconds", 300))
        extensions = work / "build/sources/extensions"
        fetch(EXTENSIONS_REPOSITORY, EXTENSIONS_COMMIT, extensions)
        env["PROTEUS_EXTENSIONS_SOURCE"] = str(extensions)
        result["extensions_source"] = {
            "repository": EXTENSIONS_REPOSITORY, "commit": EXTENSIONS_COMMIT,
            "tree": run(["git", "rev-parse", "HEAD^{tree}"], extensions),
        }
        apply(manifest["test_refactor_patches"])
        stage("baseline_test_refactor", manifest["stage_git_blobs"]["baseline_test_refactor"])
        baseline = manifest["baseline"]
        run(baseline["argv"], work,
            expected_failed=baseline["expected_failed_tests"],
            required_passed=baseline["required_passed_tests"],
            assertion_markers=baseline["assertion_markers"], timeout_seconds=baseline["timeout_seconds"])
        run(["git", "diff", "--exit-code"], work)
        apply(manifest["fix_patches"])
        stage("fixed_composition", manifest["stage_git_blobs"]["fixed_composition"])
        changed = run(["git", "diff", "--cached", "--name-only"], work).splitlines()
        if sorted(changed) != sorted(manifest["changed_files"]):
            raise ValueError(f"Unexpected source changes: {changed}")
        for check in manifest["checks"]:
            run(check["argv"], work, required_passed=check.get("required_passed_tests", ()), timeout_seconds=check.get("timeout_seconds", 300))
        run(["git", "diff", "--exit-code"], work)
        if not any(check.get("required_passed_tests") for check in manifest["checks"]):
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
