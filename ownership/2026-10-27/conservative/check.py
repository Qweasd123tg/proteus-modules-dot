#!/usr/bin/env python3
"""Qualify the reviewed coordinated ownership slice; run only in authorized hosted CI.

No shell command interpolation, upstream writes, automatic merge, release,
portable build, benchmark, or production-session access is performed.
"""
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
import tempfile
import time

CORE_PIN = "63454d4e8b1e4e6b26d088fce2a17d46f30390ae"
MODULES_PIN = "7fceaebc3bed8add9b0e3091110f59deca86ba46"
BUNDLE_SHA256 = "a54986d27e7f005e2d285765988830aa56a94e45b84c84f4bc2a870d1953f310"
TEST_PATH = "crates/proteus-core/tests/session_ownership_slice.rs"
TARGET = "session_ownership_slice"
MAX_TOTAL_OUTPUT = 80 * 1024 * 1024


class InfrastructureError(RuntimeError):
    pass


class GateRejected(RuntimeError):
    pass


def sha(data):
    return hashlib.sha256(data).hexdigest()


def bounded_file(path, cap):
    with Path(path).open("rb") as stream:
        data = stream.read(cap + 1)
    if len(data) > cap:
        raise InfrastructureError(f"file exceeds {cap} bytes: {path}")
    return data


def file_sha(path, cap=1024 ** 3):
    digest = hashlib.sha256()
    count = 0
    with Path(path).open("rb") as stream:
        while True:
            chunk = stream.read(1024 * 1024)
            if not chunk:
                return digest.hexdigest()
            count += len(chunk)
            if count > cap:
                raise InfrastructureError(f"hashed file exceeds {cap} bytes: {path}")
            digest.update(chunk)


def kill_group(process):
    # Cooperating POSIX process groups only; this is not a sandbox or a claim
    # that deliberately escaped descendants can universally be terminated.
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass


class Runner:
    def __init__(self, evidence):
        self.evidence = Path(evidence)
        self.evidence.mkdir(parents=True, exist_ok=False)
        self.records = []
        self.total_bytes = 0

    def run(self, label, argv, cwd, env, seconds, cap=1024 * 1024):
        if not re.fullmatch(r"[A-Za-z0-9_.-]{1,120}", label):
            raise InfrastructureError("invalid stage label")
        if len(self.records) >= 90:
            raise InfrastructureError("stage record limit")
        started = time.monotonic()
        deadline = started + seconds
        output = bytearray()
        process = None
        selector = selectors.DefaultSelector()
        reason = None
        code = None
        try:
            process = subprocess.Popen(
                [str(arg) for arg in argv], cwd=cwd, env=env,
                stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT, start_new_session=True,
            )
            os.set_blocking(process.stdout.fileno(), False)
            selector.register(process.stdout, selectors.EVENT_READ)
            while True:
                if time.monotonic() >= deadline:
                    raise InfrastructureError(f"{label}: deadline exceeded")
                if not selector.get_map() and process.poll() is not None:
                    break
                if selector.get_map():
                    events = selector.select(min(0.1, max(0.0, deadline - time.monotonic())))
                else:
                    time.sleep(min(0.02, max(0.0, deadline - time.monotonic())))
                    events = []
                for key, _ in events:
                    chunk = os.read(key.fileobj.fileno(), 65536)
                    if not chunk:
                        selector.unregister(key.fileobj)
                        continue
                    self.total_bytes += len(chunk)
                    if len(output) + len(chunk) > cap or self.total_bytes > MAX_TOTAL_OUTPUT:
                        raise InfrastructureError(f"{label}: output byte limit exceeded")
                    output.extend(chunk)
            code = process.wait(timeout=max(0.01, deadline - time.monotonic()))
            if code < 0:
                raise InfrastructureError(f"{label}: process ended by signal {code}")
        except BaseException as error:
            reason = f"{type(error).__name__}: {error}"
            raise
        finally:
            # Kill the group even if its leader exited: a child may retain a
            # pipe or continue after closing stdout. Never return on EOF alone.
            if process is not None:
                kill_group(process)
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    kill_group(process)
                    raise InfrastructureError(f"{label}: failed to reap child")
                code = process.returncode
                if process.stdout is not None:
                    process.stdout.close()
            selector.close()
            raw = bytes(output)
            (self.evidence / f"{label}.log").write_bytes(raw)
            record = {
                "stage": label, "argv": [str(arg) for arg in argv],
                "elapsed_seconds": time.monotonic() - started,
                "exit_code": code, "output_bytes": len(raw),
                "output_sha256": sha(raw), "infrastructure_error": reason,
            }
            self.records.append(record)
        if code is None or code < 0:
            raise InfrastructureError(f"{label}: process ended by signal or without status")
        return {"code": code, "output": bytes(output).decode("utf-8", "replace")}

    def ok(self, label, argv, cwd, env, seconds, cap=1024 * 1024):
        result = self.run(label, argv, cwd, env, seconds, cap)
        if result["code"] != 0:
            raise GateRejected(f"{label}: command failed with {result['code']}")
        return result["output"]


def classify(result, name, marker=None):
    """Interpret a direct libtest binary, never a cargo/compiler exit."""
    text = result["output"]
    outcomes = re.findall(r"^test (\S+) \.\.\. (ok|FAILED|ignored)$", text, re.M)
    summaries = re.findall(
        r"^test result: (ok|FAILED)\. (\d+) passed; (\d+) failed; "
        r"(\d+) ignored; (\d+) measured; (\d+) filtered out; finished in [^\n]+$",
        text, re.M,
    )
    wanted = "FAILED" if marker else "ok"
    if outcomes != [(name, wanted)] or len(summaries) != 1:
        raise GateRejected(f"{name}: missing, duplicate, ignored, or unexpected test outcome")
    verdict, passed, failed, ignored, measured, _ = summaries[0]
    expected = (wanted, "0", "1", "0", "0") if marker else ("ok", "1", "0", "0", "0")
    if (verdict, passed, failed, ignored, measured) != expected:
        raise GateRejected(f"{name}: unexpected single-test summary")
    if result["code"] != (101 if marker else 0):
        raise GateRejected(f"{name}: unexpected direct-test exit status")
    if marker:
        header = f"---- {name} stdout ----\n"
        if text.count(header) != 1:
            raise GateRejected(f"{name}: missing unique captured panic section")
        failure = text.split(header, 1)[1].split("\nfailures:\n", 1)[0]
        if not re.search(r"(?m)^" + re.escape(marker) + r":", failure):
            raise GateRejected(f"{name}: failure was not the expected behavioral assertion")
        if "panicked at" not in failure:
            raise GateRejected(f"{name}: missing panic context")
    return "EXPECTED_BEHAVIORAL_RED" if marker else "PASS"


def clean_env(work):
    env = os.environ.copy()
    for key in list(env):
        if ((key.startswith("PROTEUS_") and
             (key.endswith("_SOURCE") or key.startswith("PROTEUS_TEST_"))) or
            key.startswith("CARGO_TARGET_") or key.startswith("CARGO_BUILD_RUSTC") or
            key in {"CARGO_BUILD_TARGET", "CARGO_ENCODED_RUSTFLAGS", "CARGO_BUILD_RUSTDOC",
                    "RUSTFLAGS", "RUSTC", "RUSTDOC", "RUSTC_WRAPPER", "RUSTC_WORKSPACE_WRAPPER"}):
            env.pop(key, None)
    env.update({
        "CARGO_HOME": str(work / "cargo-home"),
        "CARGO_BUILD_JOBS": "2", "CARGO_INCREMENTAL": "0",
        "CARGO_PROFILE_DEV_DEBUG": "0", "CARGO_PROFILE_TEST_DEBUG": "0",
        "RUST_TEST_THREADS": "4", "RUSTUP_TOOLCHAIN": "1.95.0",
        "PYTHONDONTWRITEBYTECODE": "1", "PYTHONOPTIMIZE": "0", "GIT_TERMINAL_PROMPT": "0",
        "CARGO_TERM_COLOR": "never", "RUST_BACKTRACE": "0",
    })
    return env


def checkout(runner, label, destination, repo, revision, env):
    destination.mkdir()
    runner.ok(label + "-init", ["git", "init", "-q"], destination, env, 30)
    runner.ok(label + "-fetch",
              ["git", "fetch", "--depth=1", repo, revision],
              destination, env, 180, 2 * 1024 * 1024)
    runner.ok(label + "-checkout", ["git", "checkout", "--detach", "FETCH_HEAD"],
              destination, env, 30)
    head = runner.ok(label + "-pin", ["git", "rev-parse", "HEAD"],
                     destination, env, 10).strip()
    if head != revision:
        raise GateRejected(f"{label}: wrong source revision")


def apply_bundle(root, bundle, tests_only):
    changed = {}
    selected = ({TEST_PATH: bundle["files"][TEST_PATH], **bundle["baseline_additional_files"]}
                if tests_only else bundle["files"])
    for name, entry in selected.items():
        rel = Path(name)
        if rel.is_absolute() or ".." in rel.parts or not name.startswith("crates/proteus-core/"):
            raise GateRejected("unsafe bundle path")
        path = root / rel
        if entry["original_blob"] is None:
            if path.exists():
                raise GateRejected(f"new path already exists: {name}")
        else:
            data = bounded_file(path, 4 * 1024 * 1024)
            identity = hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()
            if identity != entry["original_blob"]:
                raise GateRejected(f"base blob mismatch: {name}")
        path.parent.mkdir(parents=True, exist_ok=True)
        content = entry["content"].encode("utf-8")
        path.write_bytes(content)
        changed[name] = sha(content)
    return changed


def tracked_snapshot(runner, label, root, env, extra_files=()):
    listing = runner.ok(label, ["git", "ls-files", "-z"], root, env, 30, 2 * 1024 * 1024)
    files = {}
    for name in listing.split("\0"):
        if name:
            files[name] = sha(bounded_file(root / name, 32 * 1024 * 1024))
    # New authored files are untracked in the detached source checkout too.
    for name in extra_files:
        if name not in files:
            files[name] = sha(bounded_file(root / name, 4 * 1024 * 1024))
    return files


def compile_target(runner, lane, root, env):
    output = runner.ok(
        lane + "-compile",
        ["cargo", "test", "--locked", "-p", "proteus-core", "--test", TARGET,
         "--no-run", "--message-format=json"],
        root, env, 1500, 20 * 1024 * 1024,
    )
    emitted = []
    for line in output.splitlines():
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if (item.get("reason") == "compiler-artifact" and item.get("executable") and
            item.get("target", {}).get("name") == TARGET and
            item["target"].get("kind") == ["test"]):
            expected = (root / TEST_PATH).resolve()
            if Path(item["target"]["src_path"]).resolve() != expected:
                raise GateRejected("unexpected test target source")
            emitted.append(Path(item["executable"]).resolve())
    if len(emitted) != 1 or not emitted[0].is_relative_to(Path(env["CARGO_TARGET_DIR"])):
        raise GateRejected("missing or ambiguous compiled test executable")
    return emitted[0]


def listed_tests(output):
    return re.findall(r"^(\S+): test$", output, re.M)


def inventory(runner, lane, binary, root, env, specs):
    output = runner.ok(lane + "-inventory", [binary, "--list", "--format", "terse"],
                       root, env, 30, 128 * 1024)
    names = listed_tests(output)
    expected = specs["candidate_mandatory_tests"] + [specs["intentional_ignored_helper"]]
    if len(names) != len(expected) or set(names) != set(expected):
        raise GateRejected(f"{lane}: unexpected test inventory")
    output = runner.ok(lane + "-ignored", [binary, "--list", "--ignored", "--format", "terse"],
                       root, env, 30, 128 * 1024)
    if listed_tests(output) != [specs["intentional_ignored_helper"]]:
        raise GateRejected(f"{lane}: mandatory test is ignored")


def compile_library(runner, lane, root, env):
    output = runner.ok(
        lane + "-library-compile",
        ["cargo", "test", "--locked", "-p", "proteus-core", "--lib",
         "--no-run", "--message-format=json"],
        root, env, 1500, 20 * 1024 * 1024,
    )
    emitted = []
    for line in output.splitlines():
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if (item.get("reason") == "compiler-artifact" and item.get("executable") and
            item.get("target", {}).get("name") == "proteus_core" and
            item["target"].get("kind") == ["lib"]):
            expected = (root / "crates/proteus-core/src/lib.rs").resolve()
            if Path(item["target"]["src_path"]).resolve() != expected:
                raise GateRejected("unexpected library test source")
            emitted.append(Path(item["executable"]).resolve())
    if len(emitted) != 1 or not emitted[0].is_relative_to(Path(env["CARGO_TARGET_DIR"])):
        raise GateRejected("missing or ambiguous compiled library test executable")
    return emitted[0]


def library_inventory(runner, lane, binary, root, env, required):
    output = runner.ok(lane + "-library-inventory", [binary, "--list", "--format", "terse"],
                       root, env, 30, 256 * 1024)
    names = listed_tests(output)
    if any(names.count(name) != 1 for name in required):
        raise GateRejected("required library test missing or duplicated")
    output = runner.ok(lane + "-library-ignored",
                       [binary, "--list", "--ignored", "--format", "terse"],
                       root, env, 30, 128 * 1024)
    ignored = listed_tests(output)
    if set(required) & set(ignored):
        raise GateRejected("required library test is ignored")


def qualify(args):
    bundle_bytes = bounded_file(args.bundle, 1024 * 1024)
    if sha(bundle_bytes) != BUNDLE_SHA256:
        raise GateRejected("authored source bundle identity mismatch")
    bundle = json.loads(bundle_bytes)
    if bundle["base_commit"] != CORE_PIN:
        raise GateRejected("wrong Core pin")
    specs = bundle["validation"]
    names = specs["candidate_mandatory_tests"]
    if len(names) != len(set(names)) or set(names) != (
            set(specs["baseline_expected_red"]) | set(specs["baseline_positive_controls"])):
        raise GateRejected("invalid test manifest")
    work = Path(args.work).resolve()
    work.mkdir(parents=True, exist_ok=False)
    runner = Runner(Path(args.evidence).resolve())
    env = clean_env(work)
    receipt = {
        "schema": 1, "status": "INCOMPLETE",
        "publication_commit": os.environ.get("GITHUB_SHA"),
        "repository": os.environ.get("GITHUB_REPOSITORY"),
        "workflow_ref": os.environ.get("GITHUB_WORKFLOW_REF"),
        "run_id": os.environ.get("GITHUB_RUN_ID"),
        "run_attempt": os.environ.get("GITHUB_RUN_ATTEMPT"),
        "controller_sha256": file_sha(Path(__file__), 1024 * 1024),
        "hosted_image": {"os": os.environ.get("ImageOS"), "version": os.environ.get("ImageVersion")},
        "sandbox_backend": {
            "source_release": "v0.13.1",
            "source_archive_sha256": "0e85c8702248b8dd64144f594147553650cdd0e4c951690345faace79c217c4d",
            "binary_sha256": file_sha("/usr/bin/bwrap", 16 * 1024 * 1024),
        },
        "bundle_sha256": BUNDLE_SHA256, "core_pin": CORE_PIN,
        "canonical_fixture_modules_pin": MODULES_PIN,
        "canonical_fixture_core_dependency": "bee0e409e746e2df9db32748d4f8ea02201bd4af",
        "coverage": "Stable writer ownership and explicit local-handle coordinated deletion",
        "excluded": ["config/image transactions", "retirement of all stale runtime/API handles",
                     "portable packaging", "benchmarks", "mixed-version safety",
                     "same-UUID reincarnation", "malicious namespace mutation", "power-loss safety"],
        "cases": [], "stages": runner.records,
    }
    try:
        if (os.environ.get("GITHUB_ACTIONS") != "true" or
            receipt["repository"] != "Qweasd123tg/proteus-modules-dot" or
            os.environ.get("GITHUB_REF") != "refs/heads/ci/session-ownership-conservative-20261027" or
            not re.fullmatch(r"[0-9a-f]{40}", receipt["publication_commit"] or "")):
            raise GateRejected("this controller requires the isolated authorized GitHub CI context")
        actual_publication = runner.ok(
            "publication-head", ["git", "rev-parse", "HEAD"],
            Path(__file__).resolve().parent, env, 10,
        ).strip()
        if actual_publication != receipt["publication_commit"]:
            raise GateRejected("publication checkout does not match GITHUB_SHA")
        receipt["tool_versions"] = {}
        for label, command in (
            ("rustc", ["rustc", "-Vv"]), ("cargo", ["cargo", "-V"]),
            ("node", ["node", "--version"]), ("npm", ["npm", "--version"]),
            ("bubblewrap", ["/usr/bin/bwrap", "--version"]),
            ("python", [sys.executable, "--version"]),
        ):
            receipt["tool_versions"][label] = runner.ok(
                "version-" + label, command, work, env, 30, 65536).strip()
        if not receipt["tool_versions"]["rustc"].startswith("rustc 1.95.0 "):
            raise GateRejected("wrong Rust compiler")
        if not receipt["tool_versions"]["cargo"].startswith("cargo 1.95.0 "):
            raise GateRejected("wrong Cargo")
        if receipt["tool_versions"]["node"] != "v22.18.0":
            raise GateRejected("wrong Node fixture-build toolchain")
        if receipt["tool_versions"]["bubblewrap"] != "bubblewrap 0.13.1":
            raise GateRejected("wrong sandbox backend version")
        backend_stat = Path("/usr/bin/bwrap").stat()
        if (backend_stat.st_mode & 0o7777, backend_stat.st_uid, backend_stat.st_gid) != (0o755, 0, 0):
            raise GateRejected("sandbox backend must be ordinary root-owned mode0755")
        receipt["sandbox_backend"]["mode_uid_gid"] = ["0755", 0, 0]
        capabilities = runner.ok("sandbox-file-capabilities",
                                 ["getcap", "/usr/bin/bwrap"], work, env, 10, 65536).strip()
        if capabilities:
            raise GateRejected("sandbox backend must not have file capabilities")
        receipt["sandbox_backend"]["file_capabilities"] = "none"
        baseline, candidate, modules = (work / name for name in ("baseline", "candidate", "modules"))
        checkout(runner, "baseline", baseline,
                 "https://github.com/Proteus-harness/Proteus-core.git", CORE_PIN, env)
        checkout(runner, "candidate", candidate,
                 "https://github.com/Proteus-harness/Proteus-core.git", CORE_PIN, env)
        receipt["baseline_test_files"] = apply_bundle(baseline, bundle, True)
        receipt["candidate_changed_files"] = apply_bundle(candidate, bundle, False)
        runner.ok("candidate-format", ["cargo", "fmt", "--all", "--", "--check"],
                  candidate, env, 180, 2 * 1024 * 1024)
        for lane, root in (("baseline", baseline), ("candidate", candidate)):
            runner.ok(lane + "-diff-check", ["git", "diff", "--check"], root, env, 30)
        snapshots = {}
        for lane, root in (("baseline", baseline), ("candidate", candidate)):
            snapshots[lane] = tracked_snapshot(
                runner, lane + "-source-before", root, env,
                receipt["baseline_test_files" if lane == "baseline" else "candidate_changed_files"])
        for lane, root in (("baseline", baseline), ("candidate", candidate)):
            lane_env = dict(env, CARGO_TARGET_DIR=str(work / (lane + "-target")))
            binary = compile_target(runner, lane, root, lane_env)
            receipt[lane + "_test_binary_sha256"] = file_sha(binary)
            inventory(runner, lane, binary, root, lane_env, specs)
            for index, name in enumerate(names):
                # Default captured output produces a single unambiguous outcome
                # line; failures still include their captured assertion/panic.
                result = runner.run(
                    f"{lane}-case-{index:02}", [binary, "--exact", name, "--test-threads=1"],
                    root, lane_env, 60, 256 * 1024,
                )
                marker = specs["baseline_expected_red"].get(name) if lane == "baseline" else None
                verdict = classify(result, name, marker)
                receipt["cases"].append({"lane": lane, "name": name, "verdict": verdict})
        checkout(runner, "fixtures", modules,
                 "https://github.com/Proteus-harness/Proteus-modules.git", MODULES_PIN, env)
        fixture_before = tracked_snapshot(runner, "fixture-source-before", modules, env)
        fixture_env = dict(env, PROTEUS_MODULES_SOURCE=str(modules),
                           CARGO_TARGET_DIR=str(work / "fixture-target"))
        output = runner.ok(
            "build-reference-fixture",
            [sys.executable, "scripts/build_module.py", "--target-dir", work / "fixture-target"],
            candidate, fixture_env, 1200, 16 * 1024 * 1024,
        )
        reference = Path(output.strip().splitlines()[-1]).resolve()
        if not reference.is_file() or not reference.is_relative_to(work / "fixture-target"):
            raise GateRejected("fixture builder did not return its actual isolated executable")
        receipt["reference_fixture_binary_sha256"] = file_sha(reference)
        dcp = modules / "hook/dcp"
        runner.ok("dcp-install", ["npm", "ci", "--ignore-scripts"], dcp, fixture_env, 300,
                  4 * 1024 * 1024)
        runner.ok("dcp-build", ["npm", "run", "build"], dcp, fixture_env, 300, 4 * 1024 * 1024)
        dcp_worker = dcp / "dist/worker.js"
        if not dcp_worker.is_file():
            raise GateRejected("DCP worker missing after build")
        dcp_outputs = [path for path in (dcp / "dist").rglob("*") if path.is_file()]
        if len(dcp_outputs) > 1000:
            raise InfrastructureError("DCP output file-count limit")
        receipt["dcp_dist_files"] = {
            str(path.relative_to(dcp)): file_sha(path, 8 * 1024 * 1024)
            for path in sorted(dcp_outputs)
        }
        full_env = dict(
            env, CARGO_TARGET_DIR=str(work / "candidate-target"),
            PROTEUS_MODULES_SOURCE=str(modules),
            PROTEUS_TEST_REFERENCE_MODULE=str(reference),
            PROTEUS_TEST_DCP_MODULE=str(dcp_worker),
        )
        for lane, root in (("baseline", baseline), ("candidate", candidate)):
            lane_env = dict(full_env, CARGO_TARGET_DIR=str(work / (lane + "-target")))
            binary = compile_library(runner, lane, root, lane_env)
            receipt[lane + "_library_binary_sha256"] = file_sha(binary)
            required = (list(specs["baseline_library_expected_red"]) +
                        specs["baseline_library_positive_controls"] if lane == "baseline" else
                        specs["candidate_extra_unit_tests"] + specs["candidate_existing_regression_tests"])
            if len(required) != len(set(required)):
                raise GateRejected("duplicate required library case")
            library_inventory(runner, lane, binary, root, lane_env, required)
            for index, name in enumerate(required):
                result = runner.run(
                    f"{lane}-library-case-{index:02}", [binary, "--exact", name, "--test-threads=1"],
                    root, lane_env, 60, 256 * 1024,
                )
                marker = specs["baseline_library_expected_red"].get(name) if lane == "baseline" else None
                verdict = classify(result, name, marker)
                receipt["cases"].append({"lane": lane + "-library", "name": name, "verdict": verdict})
        output = runner.ok("candidate-canonical-full",
                           [sys.executable, "scripts/test.py", "full"],
                           candidate, full_env, 1800, 32 * 1024 * 1024)
        for name in specs["candidate_extra_unit_tests"] + specs["candidate_existing_regression_tests"]:
            if len(re.findall(r"^test " + re.escape(name) + r" \.\.\. ok$", output, re.M)) != 1:
                raise GateRejected(f"full gate did not uniquely pass required test {name}")
        for lane, root in (("baseline", baseline), ("candidate", candidate)):
            after = tracked_snapshot(
                runner, lane + "-source-after", root, env,
                receipt["baseline_test_files" if lane == "baseline" else "candidate_changed_files"])
            if snapshots[lane] != after:
                raise GateRejected(f"{lane}: source changed during qualification")
            receipt[lane + "_source_snapshot_sha256"] = sha(
                json.dumps(after, sort_keys=True, separators=(",", ":")).encode())
        if fixture_before != tracked_snapshot(runner, "fixture-source-after", modules, env):
            raise GateRejected("canonical fixture source was modified")
        receipt["status"] = "SCOPED_GATES_PASS"
        receipt["unique_new_integration_cases"] = len(names)
        receipt["unique_new_unit_cases"] = len(specs["candidate_extra_unit_tests"])
        receipt["counting_note"] = "Baseline, candidate and full executions repeat suites; do not add them as unique coverage."
    except BaseException as error:
        receipt["status"] = ("INFRASTRUCTURE_ERROR" if isinstance(
            error, (InfrastructureError, KeyboardInterrupt, SystemExit)) else "GATE_REJECTED")
        receipt["error"] = f"{type(error).__name__}: {error}"
        raise
    finally:
        payload = json.dumps(receipt, indent=2, ensure_ascii=False).encode() + b"\n"
        if len(payload) > 2 * 1024 * 1024:
            raise InfrastructureError("receipt size limit")
        (runner.evidence / "result.json").write_bytes(payload)


def self_test():
    assert listed_tests(
        "app_server::ownership_tests::case: test\nhelper: test\n2 tests, 0 benchmarks\n"
    ) == ["app_server::ownership_tests::case", "helper"], "libtest inventory parser"
    name, marker = "case", "OWNERSHIP_EXAMPLE"
    good = {
        "code": 101,
        "output": ("test case ... FAILED\n\nfailures:\n\n---- case stdout ----\n"
                   "thread 'case' panicked at test.rs:1:1:\nOWNERSHIP_EXAMPLE: bad\n\n"
                   "failures:\n    case\n\n"
                   "test result: FAILED. 0 passed; 1 failed; 0 ignored; 0 measured; "
                   "0 filtered out; finished in 0.00s\n"),
    }
    assert classify(good, name, marker) == "EXPECTED_BEHAVIORAL_RED"
    mutations = [
        {"code": 1}, {"code": -9},
        {"output": good["output"].replace("test case ... FAILED", "test other ... FAILED")},
        {"output": good["output"].replace("test case ... FAILED", "test case ... ignored")},
        {"output": good["output"].replace("0 passed; 1 failed", "0 passed; 0 failed")},
        {"output": good["output"].replace("OWNERSHIP_EXAMPLE: bad", "different assertion")},
        {"output": good["output"] + "test other ... FAILED\n"},
        {"output": good["output"] + "test case ... FAILED\n"},
        {"output": good["output"] + good["output"]},
        {"output": "error[E0000]: OWNERSHIP_EXAMPLE\n"},
    ]
    for mutation in mutations:
        try:
            classify(dict(good, **mutation), name, marker)
        except GateRejected:
            pass
        else:
            raise AssertionError("classifier accepted invalid evidence")
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        runner = Runner(root / "evidence")
        env = os.environ.copy()
        cases = [
            ("huge", "import os; os.write(1,b'x'*100000)", 1.0, 4096),
            ("pipe-held", "import subprocess,sys; subprocess.Popen([sys.executable,'-c',"
             "'import time; time.sleep(20)']); print('leader exited')", 0.3, 4096),
            ("eof-live", "import os,time; os.close(1); os.close(2); time.sleep(20)", 0.3, 4096),
        ]
        for label, code, timeout, cap in cases:
            started = time.monotonic()
            try:
                runner.run(label, [sys.executable, "-c", code], root, env, timeout, cap)
            except InfrastructureError:
                pass
            else:
                raise AssertionError(f"{label}: missing infrastructure rejection")
            assert time.monotonic() - started < 6.0, "cleanup exceeded self-test bound"
        def interrupt(_number, _frame):
            raise KeyboardInterrupt("self-test interruption")
        previous = signal.signal(signal.SIGALRM, interrupt)
        signal.setitimer(signal.ITIMER_REAL, 0.1)
        try:
            try:
                runner.run("interrupted", [sys.executable, "-c", "import time; time.sleep(20)"],
                           root, env, 2.0, 4096)
            except KeyboardInterrupt:
                pass
            else:
                raise AssertionError("interrupted stage did not propagate cancellation")
        finally:
            signal.setitimer(signal.ITIMER_REAL, 0)
            signal.signal(signal.SIGALRM, previous)
    print("Controller self-tests: 10 rejection, 4 process-limit and 1 inventory parser controls passed.")


def main():
    if not __debug__:
        raise InfrastructureError("optimized Python disables required controller self-checks")
    def terminate(signum, _frame):
        raise KeyboardInterrupt(f"received signal {signum}")
    signal.signal(signal.SIGTERM, terminate)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path)
    parser.add_argument("--work", type=Path)
    parser.add_argument("--evidence", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
    else:
        if None in (args.bundle, args.work, args.evidence):
            parser.error("--bundle, --work and --evidence are required")
        qualify(args)


if __name__ == "__main__":
    main()
