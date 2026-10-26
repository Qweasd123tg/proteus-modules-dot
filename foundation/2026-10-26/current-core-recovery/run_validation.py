#!/usr/bin/env python3
"""Qualify immutable recovery patches against a pinned current Core checkout."""
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
BUNDLE = ROOT.parents[2]
SOURCE = "https://github.com/Proteus-harness/Proteus-core.git"
FIXTURE = "https://github.com/Proteus-harness/Proteus-modules.git"
PUBLICATION = "https://github.com/Qweasd123tg/proteus-modules-dot.git"
BASELINE = "app_server::http::tests::session_reads::paged_snapshot_full_history_and_revision_checked_pages_agree"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def relative(value):
    path = Path(value)
    if not path.parts or path.is_absolute() or ".." in path.parts:
        raise ValueError(f"Unsafe relative path: {value}")
    return path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work-dir", type=Path, required=True)
    parser.add_argument("--evidence-dir", type=Path, required=True)
    args = parser.parse_args()
    if not __debug__:
        raise SystemExit("Python optimization must be disabled: identity gates use assertions")
    work, evidence = args.work_dir.resolve(), args.evidence_dir.resolve()
    if work.exists() or evidence.exists():
        raise SystemExit("Fresh absent work and evidence directories required; no data is removed")
    if work == evidence or work in evidence.parents or evidence in work.parents:
        raise SystemExit("Work and evidence directories must be disjoint")
    spec_path = ROOT / "manifest.json"
    spec = json.loads(spec_path.read_text())
    assert spec["core"]["repository"] == SOURCE
    assert spec["fixture"]["repository"] == FIXTURE
    assert spec["patch_source"]["repository"] == PUBLICATION
    for key in ("core", "fixture", "patch_source"):
        assert re.fullmatch(r"[0-9a-f]{40}", spec[key]["commit"])
    assert spec["schema"] == 1 and spec["toolchain"] == "1.95.0"
    work.mkdir(parents=True)
    evidence.mkdir(parents=True)
    result = {
        "schema": 1,
        "bundle_commit": os.environ.get("GITHUB_SHA"),
        "workflow_run_id": os.environ.get("GITHUB_RUN_ID"),
        "workflow_run_attempt": os.environ.get("GITHUB_RUN_ATTEMPT"),
        "manifest_sha256": digest(spec_path),
        "runner_sha256": digest(Path(__file__)),
        "status": "running",
        "commands": [],
        "claims": "Pinned current-Core recovery regression only; no timing, native GUI, portable or release qualification",
    }
    env = os.environ.copy()
    for key in ("PROTEUS_TEST_REFERENCE_MODULE", "PROTEUS_TEST_DCP_MODULE",
                "PROTEUS_MODULES_SOURCE", "PROTEUS_CONFIG_PATH", "RUSTFLAGS",
                "CARGO_ENCODED_RUSTFLAGS", "RUSTC_WRAPPER", "RUSTC_WORKSPACE_WRAPPER"):
        env.pop(key, None)
    env.update({
        "RUSTUP_TOOLCHAIN": "1.95.0", "CARGO_BUILD_JOBS": "2",
        "CARGO_INCREMENTAL": "0", "RUST_TEST_THREADS": "4",
        "PYTHONDONTWRITEBYTECODE": "1", "GIT_TERMINAL_PROMPT": "0",
        "CARGO_TERM_COLOR": "never",
    })

    def save():
        (evidence / "result.json").write_text(json.dumps(result, indent=2) + "\n")

    def run(argv, cwd=None, *, expected_failure=False, timeout_seconds=300):
        argv = list(map(str, argv))
        print("+ " + " ".join(argv), flush=True)
        deadline = time.monotonic() + timeout_seconds
        proc = subprocess.Popen(argv, cwd=cwd, env=env, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, start_new_session=True)
        timed_out = False
        control_error = None
        code = None
        tail, pending = b"", ""
        passed, failed, listed, success_counts = [], [], [], []
        markers = set()
        expected_markers = {
            "crates/proteus-core/src/app_server/http/tests/session_reads.rs:63:",
            "history revision changed; retry reading history",
            "test result: FAILED. 0 passed; 1 failed; 0 ignored;",
        }
        compilation_error = False

        def stop():
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass

        def append_bounded(target, value):
            if len(target) >= 10000:
                raise ValueError("Unexpectedly many test names; refusing unbounded evidence")
            target.append(value)

        def observe(line):
            nonlocal compilation_error
            match = re.fullmatch(r"test (app_server::\S{1,400}) \.\.\. (ok|FAILED)", line)
            if match:
                append_bounded(passed if match[2] == "ok" else failed, match[1])
            match = re.fullmatch(r"(app_server::\S{1,400}): test", line)
            if match:
                append_bounded(listed, match[1])
            match = re.match(r"test result: ok\. (\d+) passed; 0 failed; 0 ignored;", line)
            if match:
                append_bounded(success_counts, int(match[1]))
            compilation_error |= "could not compile" in line
            for marker in expected_markers:
                if marker in line:
                    markers.add(marker)

        os.set_blocking(proc.stdout.fileno(), False)
        selector = selectors.DefaultSelector()
        selector.register(proc.stdout, selectors.EVENT_READ)
        try:
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    timed_out = True
                    stop()
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
            observe(pending.rstrip("\r"))
            code = proc.wait(timeout=10)
        except BaseException as exc:
            control_error = exc
        finally:
            selector.close()
            proc.stdout.close()
            if proc.poll() is None or control_error is not None:
                stop()
            try:
                code = proc.wait(timeout=10)
            except subprocess.TimeoutExpired as exc:
                control_error = exc
        row = {"argv": argv, "exit_code": code, "timed_out": timed_out,
               "timeout_seconds": timeout_seconds, "log_tail": tail.decode(errors="replace"),
               "passed_tests": passed, "failed_tests": failed, "listed_tests": listed,
               "success_counts": success_counts, "assertion_markers": sorted(markers)}
        if control_error is not None:
            row["control_error"] = f"{type(control_error).__name__}: {control_error}"
        result["commands"].append(row)
        save()
        if control_error is not None:
            raise control_error
        if timed_out:
            raise TimeoutError("Command exceeded its process-group watchdog")
        if expected_failure:
            if not (code == 101 and failed == [BASELINE] and not passed
                    and markers == expected_markers and not compilation_error):
                raise ValueError("Baseline did not reproduce the named missing-index behavioral failure")
            row["status"] = "expected_missing_index_failure"
        elif code:
            raise subprocess.CalledProcessError(code, argv)
        elif failed or compilation_error:
            raise ValueError("A zero exit code cannot override observed failure")
        else:
            row["status"] = "success"
        save()
        return row

    def output(argv, cwd=None):
        return run(argv, cwd)["log_tail"].strip()

    def checkout(identity, directory):
        run(["git", "init", directory])
        run(["git", "remote", "add", "origin", identity["repository"]], directory)
        run(["git", "-c", "credential.helper=", "fetch", "--depth=1",
             "origin", identity["commit"]], directory)
        run(["git", "checkout", "--detach", "FETCH_HEAD"], directory)
        assert output(["git", "rev-parse", "HEAD"], directory) == identity["commit"]
        tree = output(["git", "rev-parse", "HEAD^{tree}"], directory)
        assert tree == identity["tree"], (directory, tree)
        return {"commit": identity["commit"], "tree": tree}

    def assert_clean(directory):
        assert output(["git", "status", "--porcelain", "--untracked-files=no"], directory) == ""

    save()
    try:
        assert result["runner_sha256"] == spec["runner_sha256"]
        assert output(["git", "rev-parse", "HEAD"], BUNDLE) == result["bundle_commit"]
        version = output(["rustc", "--version", "--verbose"])
        assert version.startswith("rustc 1.95.0 ")
        run(["python3", "--version"])
        run(["git", "--version"])
        core, fixture = work / "core", work / "reference-modules"
        result["core"] = checkout(spec["core"], core)
        result["fixture"] = checkout(spec["fixture"], fixture)
        repositories = json.loads((core / "repositories.json").read_text())
        assert repositories["modules"]["url"] == FIXTURE
        assert repositories["modules"]["rev"] == spec["fixture"]["commit"]
        env["PROTEUS_MODULES_SOURCE"] = str(fixture)
        patch_source = spec["patch_source"]
        run(["git", "-c", "credential.helper=", "fetch", "--depth=1",
             patch_source["repository"], patch_source["commit"]], BUNDLE)
        assert output(["git", "rev-parse", patch_source["commit"] + "^{tree}"], BUNDLE) == patch_source["tree"]
        patches = []
        result["patches"] = []
        for item in patch_source["patches"]:
            path = relative(item["path"])
            data = run(["git", "show", patch_source["commit"] + ":" + path.as_posix()],
                       BUNDLE)["log_tail"].encode()
            assert hashlib.sha256(data).hexdigest() == item["sha256"]
            header = f"blob {len(data)}\0".encode()
            assert hashlib.sha1(header + data).hexdigest() == item["git_blob"]
            destination = work / path.name
            destination.write_bytes(data)
            patches.append(destination)
            result["patches"].append(item)
        assert len(patches) == 2
        for path, expected in spec["original_git_blob"].items():
            assert output(["git", "hash-object", core / relative(path)], core) == expected

        def apply(path):
            run(["git", "apply", "--check", "--index", path], core)
            run(["git", "apply", "--index", path], core)
            run(["git", "diff", "--cached", "--check"], core)

        apply(patches[0])
        result["baseline_test_tree"] = output(["git", "write-tree"], core)
        assert result["baseline_test_tree"] == spec["baseline_test_tree"]
        run(["python3", "scripts/test.py", "-p", "proteus-core", "--lib",
             BASELINE, "--", "--exact"], core, expected_failure=True, timeout_seconds=2700)
        run(["git", "diff", "--exit-code"], core)
        assert_clean(fixture)
        apply(patches[1])
        changed = output(["git", "diff", "--cached", "--name-only"], core).splitlines()
        assert sorted(changed) == sorted(spec["patched_files"])
        result["patched_tree"] = output(["git", "write-tree"], core)
        assert result["patched_tree"] == spec["patched_tree"]
        for path, identity in spec["patched_files"].items():
            assert digest(core / relative(path)) == identity["sha256"]
            assert output(["git", "hash-object", core / relative(path)], core) == identity["git_blob"]

        command = ["python3", "scripts/test.py", "-p", "proteus-core", "--lib", "app_server::"]
        discovered = run(command + ["--", "--list"], core, timeout_seconds=600)["listed_tests"]
        assert discovered and len(discovered) == len(set(discovered))
        assert set(spec["required_passed_tests"]).issubset(discovered)
        result["discovered_app_server_tests"] = discovered
        row = run(command, core, timeout_seconds=1200)
        assert not row["failed_tests"] and sorted(row["passed_tests"]) == sorted(discovered)
        assert row["success_counts"] == [len(discovered)]
        result["passed_app_server_count"] = len(discovered)
        run(["cargo", "fmt", "--all", "--", "--check"], core)
        run(["git", "diff", "--exit-code"], core)
        assert output(["git", "write-tree"], core) == spec["patched_tree"]
        assert_clean(fixture)
        result["status"] = "success"
    except BaseException as exc:
        result["status"] = "failure"
        result["error"] = f"{type(exc).__name__}: {exc}"
        raise
    finally:
        save()


if __name__ == "__main__":
    main()
