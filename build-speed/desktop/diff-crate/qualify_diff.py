#!/usr/bin/env python3
"""Qualify only the pinned extracted diff library in a disposable checkout."""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import selectors
import shutil
import signal
import subprocess
import time
import tomllib
from urllib.parse import unquote, urlsplit

HERE = Path(__file__).resolve().parent
LOG_LIMIT = 8 * 1024 * 1024
ADMISSION_FREE = 8 * 1024**3
LOW_WATER_FREE = 2 * 1024**3
ARTIFACT_LIMIT = 64
RECEIPT_LIMIT = 256 * 1024


def sha256(path, limit=16 * 1024 * 1024):
    if path.stat().st_size > limit:
        raise ValueError(f"File exceeds qualification size cap: {path.name}")
    digest = hashlib.sha256()
    total = 0
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            total += len(block)
            if total > limit:
                raise ValueError(f"Growing file exceeds qualification size cap: {path.name}")
            digest.update(block)
    return digest.hexdigest()


def package_key(value, source, expected):
    origin, separator, identity = value.rpartition("#")
    name, at, version = identity.rpartition("@")
    if not separator or not at:
        raise ValueError(f"Unrecognized Cargo package ID: {value}")
    if name == "proteus-diff":
        if version != expected["package_version"] or not origin.startswith("path+file://"):
            raise ValueError(f"Unexpected local package: {value}")
        url = urlsplit(origin.removeprefix("path+"))
        if url.netloc or PurePosixPath(unquote(url.path)) != PurePosixPath(source) / "crates/diff":
            raise ValueError(f"Unexpected diff source: {value}")
    else:
        package = expected["registry_packages"].get(name)
        if package is None or version != package["version"] or origin != package["source"]:
            raise ValueError(f"Package outside the audited serde closure: {value}")
    return name


def inspect_output(output, source, target, expected):
    wanted = set(expected["test_names"])
    observed = []
    summaries = []
    packages = set()
    artifacts = []
    test_executables = []
    finished = []
    execution_headers = []
    count_headers = []
    for line in output.splitlines():
        if line.startswith("{"):
            message = json.loads(line)
            reason = message.get("reason")
            if reason in ("compiler-artifact", "compiler-message", "build-script-executed"):
                name = package_key(message["package_id"], source, expected)
                if reason == "compiler-message" and message["message"]["level"] == "error":
                    raise ValueError("Cargo emitted a compiler error")
                if reason == "build-script-executed" and name == "proteus-diff":
                    raise ValueError("The diff crate must not run a build script")
                if reason != "compiler-artifact":
                    continue
                packages.add(name)
                kind = message["target"]["kind"]
                if name == "proteus-diff":
                    if kind != ["lib"] or message["target"]["name"] != "proteus_diff":
                        raise ValueError("Unexpected diff target")
                    if PurePosixPath(message["target"]["src_path"]) != PurePosixPath(source) / "crates/diff/src/lib.rs":
                        raise ValueError("Unexpected diff target source")
                    if message["profile"]["test"]:
                        executable = PurePosixPath(message["executable"])
                        if not executable.is_absolute() or ".." in executable.parts or not executable.is_relative_to(PurePosixPath(target)):
                            raise ValueError("Test executable is outside the fresh target directory")
                        test_executables.append(str(executable))
                elif kind not in (["lib"], ["proc-macro"], ["custom-build"]):
                    raise ValueError("Unexpected dependency target kind")
                if len(artifacts) >= ARTIFACT_LIMIT:
                    raise ValueError("Too many compiler artifacts for this pure closure")
                artifacts.append({
                    "package_id": message["package_id"],
                    "target": message["target"]["name"],
                    "kind": kind,
                    "features": sorted(message["features"]),
                    "profile": message["profile"],
                    "fresh": message["fresh"],
                })
            elif reason == "build-finished":
                finished.append(message["success"])
            elif reason is not None:
                raise ValueError(f"Unexpected Cargo JSON reason: {reason}")
            else:
                raise ValueError("Unrecognized JSON in Cargo output")
        elif line.strip().startswith("Running unittests "):
            match = re.fullmatch(r"Running unittests (.+) \((.+)\)", line.strip())
            if match is None or match.group(1) not in (
                "src/lib.rs", "crates/diff/src/lib.rs",
                str(PurePosixPath(source) / "crates/diff/src/lib.rs"),
            ):
                raise ValueError("Unexpected unit-test execution header")
            path = PurePosixPath(match.group(2))
            if ".." in path.parts:
                raise ValueError("Noncanonical executable path in execution header")
            execution_headers.append(str(path if path.is_absolute() else PurePosixPath(source) / path))
        elif line.startswith("running "):
            count_headers.append(line)
        elif line.startswith("test "):
            match = re.fullmatch(r"test (tests::[a-z0-9_]+) \.\.\. ok", line)
            if match:
                observed.append(match.group(1))
            elif line.startswith("test result:"):
                summaries.append(line)
            else:
                raise ValueError(f"Unexpected test outcome: {line}")
    expected_summary = r"test result: ok\. 8 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in [0-9.]+s"
    if len(summaries) != 1 or re.fullmatch(expected_summary, summaries[0]) is None:
        raise ValueError("Missing or incomplete eight-test success summary")
    if len(observed) != 8 or len(set(observed)) != 8 or set(observed) != wanted:
        raise ValueError("Test identities differ from the eight preserved tests")
    if packages != {"proteus-diff", *expected["registry_packages"]}:
        raise ValueError("Artifact package set differs from the audited closure")
    if finished != [True] or len(test_executables) != 1:
        raise ValueError("Expected one successful build and one library test executable")
    if execution_headers != test_executables or count_headers != ["running 8 tests"]:
        raise ValueError("Test execution/count header does not bind the reported executable")
    return {
        "test_names": sorted(observed),
        "test_executable": test_executables[0],
        "artifacts": artifacts,
        "summary": summaries[0],
    }


class CommandLimit(RuntimeError):
    def __init__(self, reason, output):
        super().__init__(f"Qualification process stopped: {reason}")
        self.reason = reason
        self.output = output


def command(argv, cwd, env=None, timeout=60):
    """Bounded Linux process group; retain at most LOG_LIMIT raw output bytes."""
    process = subprocess.Popen(
        argv, cwd=cwd, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        start_new_session=True, bufsize=0,
    )
    selector = selectors.DefaultSelector()
    selector.register(process.stdout, selectors.EVENT_READ)
    captured = bytearray()
    started = time.monotonic()
    try:
        while selector.get_map() or process.poll() is None:
            if time.monotonic() - started >= timeout:
                raise CommandLimit("timeout", bytes(captured))
            if shutil.disk_usage(cwd).free < LOW_WATER_FREE:
                raise CommandLimit("disk_low_water", bytes(captured))
            for key, _ in selector.select(timeout=0.25):
                block = os.read(key.fileobj.fileno(), 64 * 1024)
                if not block:
                    selector.unregister(key.fileobj)
                    continue
                room = LOG_LIMIT - len(captured)
                captured.extend(block[:room])
                if len(block) > room:
                    raise CommandLimit("output_limit", bytes(captured))
        return subprocess.CompletedProcess(argv, process.wait(), bytes(captured))
    finally:
        # Kill the entire group even if its leader exited but descendants remain.
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired as error:
            raise CommandLimit("process_reap_timeout", bytes(captured)) from error
        finally:
            selector.close()
            process.stdout.close()


def require_git(source, *args):
    result = command(["git", "-C", str(source), *args], source)
    if result.returncode:
        raise RuntimeError(f"git {' '.join(args)} failed: {result.stdout[-4000:]!r}")
    return result.stdout.decode("utf-8").strip()


def verify_overlay(source, expected):
    for relative, record in expected["files"].items():
        path = source / relative
        if record["mode"] == "120000":
            if not path.is_symlink() or os.readlink(path) != "../../LICENSE-GPL":
                raise ValueError("GPL license must remain the exact relative symlink")
            data = os.readlink(path).encode("utf-8")
        else:
            if path.is_symlink() or not path.is_file():
                raise ValueError(f"Expected ordinary source file: {relative}")
            if path.stat().st_size > 1024 * 1024:
                raise ValueError(f"Source file exceeds 1 MiB cap: {relative}")
            data = path.read_bytes()
        if hashlib.sha256(data).hexdigest() != record["sha256"]:
            raise ValueError(f"Source hash mismatch: {relative}")
    if any((source / path).exists() for path in expected["deletes"]):
        raise ValueError("Old parser paths remain")
    manifest = tomllib.loads((source / "crates/diff/Cargo.toml").read_text())
    if set(manifest) != {"package", "dependencies"} or manifest["dependencies"] != {
        "serde": {"version": "1", "features": ["derive"]}
    }:
        raise ValueError("Diff manifest acquired an unaudited dependency or target section")
    if (source / "crates/diff/build.rs").exists():
        raise ValueError("Unexpected diff build script")
    root = tomllib.loads((source / "Cargo.toml").read_text())
    if root["workspace"]["default-members"] != [".", "crates/diff"]:
        raise ValueError("Default test coverage changed")
    if root["profile"]["release"] != {
        "opt-level": 3, "lto": "thin", "codegen-units": 1, "strip": True
    }:
        raise ValueError("Shipping release profile changed")


def qualify(source, output):
    expected_path = HERE / "expected.json"
    expected = json.loads(expected_path.read_text())
    source = source.resolve(strict=True)
    output = output.resolve()
    if output.is_relative_to(source) or source.is_relative_to(output):
        raise ValueError("Output and disposable source checkout must be disjoint")
    output.mkdir(parents=True, exist_ok=False)
    receipt = {
        "status": "FAIL", "scope": "proteus-diff library only",
        "shipping_native_ui_packaging": "NOT_RUN", "shipping_performance": "NOT_MEASURED",
        "delivery_commit": os.environ.get("GITHUB_SHA"),
        "run_id": os.environ.get("GITHUB_RUN_ID"),
        "run_attempt": os.environ.get("GITHUB_RUN_ATTEMPT"),
        "workflow_ref": os.environ.get("GITHUB_WORKFLOW_REF"),
        "job": os.environ.get("GITHUB_JOB"),
        "controller_sha256": sha256(Path(__file__)),
        "expected_sha256": sha256(expected_path),
        "source": expected["source"],
    }
    start = time.monotonic()
    try:
        receipt["phase"] = "disk_admission"
        if source.stat().st_dev != output.stat().st_dev:
            raise ValueError("Source and evidence must share the monitored filesystem")
        receipt["disk_admission_free_bytes"] = shutil.disk_usage(output).free
        if receipt["disk_admission_free_bytes"] < ADMISSION_FREE:
            raise CommandLimit("disk_admission", b"")
        receipt["phase"] = "source_preflight"
        if require_git(source, "rev-parse", "HEAD") != expected["source"]["commit"]:
            raise ValueError("Wrong source commit")
        if require_git(source, "rev-parse", "HEAD^{tree}") != expected["source"]["tree"]:
            raise ValueError("Wrong source tree")
        if require_git(source, "status", "--porcelain=v1", "--untracked-files=all"):
            raise ValueError("Disposable checkout is not clean")
        patch = HERE / "extract-diff-crate.patch"
        if sha256(patch) != expected["patch_sha256"]:
            raise ValueError("Wrong patch bytes")
        receipt["phase"] = "apply_reviewed_patch"
        require_git(source, "apply", "--check", str(patch))
        require_git(source, "apply", "--index", str(patch))
        if require_git(source, "write-tree") != expected["source"]["candidate_tree"]:
            raise ValueError("Patched Git tree differs from the reviewed candidate")
        require_git(source, "diff", "--exit-code")
        verify_overlay(source, expected)
        receipt["patch_sha256"] = expected["patch_sha256"]
        receipt["source_verified"] = True
        forbidden = {
            "RUSTC", "RUSTC_WRAPPER", "RUSTC_WORKSPACE_WRAPPER", "RUSTFLAGS",
            "CARGO_ENCODED_RUSTFLAGS", "CARGO_BUILD_TARGET",
        }
        if forbidden.intersection(os.environ) or any(k.startswith("CARGO_PROFILE_") for k in os.environ):
            raise ValueError("Compiler/profile overrides are outside this qualification")
        target = output / "target"
        target.mkdir()
        env = os.environ.copy()
        env["CARGO_TARGET_DIR"] = str(target)
        receipt["phase"] = "pinned_toolchain"
        compiler = command(["rustc", f"+{expected['toolchain']}", "--version", "--verbose"], source, env)
        if compiler.returncode:
            raise RuntimeError(compiler.stdout[-4000:].decode("utf-8", errors="replace"))
        receipt["rustc"] = compiler.stdout.decode("utf-8")
        argv = [
            "cargo", f"+{expected['toolchain']}", "test", "--locked",
            "-p", "proteus-diff", "--lib", "--jobs", "2", "--color", "never",
            "--message-format=json", "--", "--test-threads=4", "--color", "never",
        ]
        receipt["argv"] = argv
        receipt["phase"] = "pure_cargo_test"
        cargo_start = time.monotonic()
        try:
            result = command(argv, source, env, timeout=900)
            log = result.stdout
            receipt["cargo_exit_code"] = result.returncode
        except CommandLimit as error:
            (output / "cargo.log").write_bytes(error.output)
            error.log_name = "cargo.log"
            receipt["cargo_log_sha256"] = sha256(output / "cargo.log")
            raise
        finally:
            receipt["cargo_wall_seconds"] = time.monotonic() - cargo_start
        (output / "cargo.log").write_bytes(log)
        receipt["cargo_log_sha256"] = sha256(output / "cargo.log")
        if result.returncode:
            raise RuntimeError(f"Pure crate Cargo test failed with exit code {result.returncode}")
        receipt["phase"] = "selected_graph_and_test_evidence"
        observation = inspect_output(log.decode("utf-8"), source, target, expected)
        executable = Path(observation["test_executable"]).resolve(strict=True)
        if not executable.is_relative_to(target):
            raise ValueError("Resolved test executable escapes the fresh target directory")
        observation["test_executable_sha256"] = sha256(executable, limit=64 * 1024 * 1024)
        observation["test_executable_bytes"] = executable.stat().st_size
        receipt["phase"] = "post_test_source_identity"
        if require_git(source, "write-tree") != expected["source"]["candidate_tree"]:
            raise ValueError("Source index tree changed during qualification")
        verify_overlay(source, expected)
        require_git(source, "diff", "--exit-code")
        receipt.update(observation)
        receipt["status"] = "PASS"
        receipt["phase"] = "complete"
    except Exception as error:
        receipt["failure_stage"] = receipt.get("phase", "initialization")
        receipt["error_type"] = type(error).__name__
        receipt["error"] = str(error)[:4000]
        if isinstance(error, CommandLimit):
            receipt["resource_limit"] = error.reason
            log_name = getattr(error, "log_name", "command-partial.log")
            (output / log_name).write_bytes(error.output)
            receipt["partial_log"] = log_name
            receipt["partial_log_sha256"] = sha256(output / log_name)
    finally:
        receipt["wall_seconds"] = time.monotonic() - start
        serialized = json.dumps(receipt, indent=2, ensure_ascii=False) + "\n"
        if len(serialized.encode("utf-8")) > RECEIPT_LIMIT:
            receipt = {
                "status": "FAIL", "failure_stage": "receipt_size",
                "error": "Receipt exceeded 256 KiB cap; inspect bounded logs",
                "delivery_commit": os.environ.get("GITHUB_SHA"),
                "run_id": os.environ.get("GITHUB_RUN_ID"),
                "run_attempt": os.environ.get("GITHUB_RUN_ATTEMPT"),
                "workflow_ref": os.environ.get("GITHUB_WORKFLOW_REF"),
                "shipping_native_ui_packaging": "NOT_RUN",
            }
            serialized = json.dumps(receipt, indent=2) + "\n"
        (output / "result.json").write_text(serialized, encoding="utf-8")
    return 0 if receipt["status"] == "PASS" else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True,
                        help="Clean disposable checkout at the exact Desktop commit; will be patched")
    parser.add_argument("--output", type=Path, required=True,
                        help="New evidence directory outside the source checkout")
    args = parser.parse_args()
    raise SystemExit(qualify(args.source, args.output))
