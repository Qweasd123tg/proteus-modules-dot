#!/usr/bin/env python3
"""Qualify the config/image add-on only in its explicitly authorized hosted lane."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import signal
import sys

CORE_PIN = "63454d4e8b1e4e6b26d088fce2a17d46f30390ae"
PREREQUISITE_COMMIT = "d92dc1b1b9ed6e95f58439e486aed94e234cc2b5"
PREREQUISITE_BUNDLE = "a3a2fa1818cbfa724c0b01c87d4079b359bd1c3dbd373c770dd8abef5077d0b6"
PREREQUISITE_CONTROLLER = "f14c22254f0ccbb2c976c5073e2b5030f82348ddfe7c335f061e405c4b7190d2"
BUNDLE_SHA256 = "5850266d7ba5abf60c086b1a53435811785610663b9a88483403044bcaa4333c"
BRANCH = "refs/heads/ci/session-sidecar-fencing-20261027"


def read_small(path, cap=1024 * 1024):
    with Path(path).open("rb") as stream:
        data = stream.read(cap + 1)
    if len(data) > cap:
        raise RuntimeError(f"file exceeds {cap} bytes: {path}")
    return data


def digest(data):
    return hashlib.sha256(data).hexdigest()


def prerequisite(root):
    folder = root / "ownership/2026-10-27/conservative"
    bundle_bytes = read_small(folder / "candidate.json")
    controller_bytes = read_small(folder / "check.py")
    if digest(bundle_bytes) != PREREQUISITE_BUNDLE:
        raise RuntimeError("immutable PR #31 prerequisite bundle identity mismatch")
    if digest(controller_bytes) != PREREQUISITE_CONTROLLER:
        raise RuntimeError("immutable bounded runner identity mismatch")
    # This is the exact reviewed predecessor controller, not an arbitrary plugin.
    spec = importlib.util.spec_from_file_location("pinned_ownership_gate", folder / "check.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return json.loads(bundle_bytes), module


def apply_overlay(gate, root, files):
    changed = {}
    for name, entry in files.items():
        relative = Path(name)
        if (relative.is_absolute() or ".." in relative.parts or
                not (name.startswith("crates/proteus-core/") or name.startswith("docs/guides/"))):
            raise gate.GateRejected("unsafe add-on path")
        path = root / relative
        if entry["original_blob"] is None:
            if path.exists():
                raise gate.GateRejected(f"unexpected existing new path: {name}")
        else:
            data = gate.bounded_file(path, 4 * 1024 * 1024)
            identity = hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()
            if identity != entry["original_blob"]:
                raise gate.GateRejected(f"prerequisite source mismatch: {name}")
        data = entry["content"].encode("utf-8")
        if len(data) > 4 * 1024 * 1024:
            raise gate.GateRejected("add-on source file cap")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        changed[name] = digest(data)
    return changed


def required_passes(gate, output, names):
    for name in names:
        if len(re.findall(r"^test " + re.escape(name) + r" \.\.\. ok$", output, re.M)) != 1:
            raise gate.GateRejected(f"full gate did not uniquely pass {name}")


def qualify(args):
    previous, gate = prerequisite(args.prerequisite_root.resolve())
    bundle_bytes = read_small(args.bundle)
    if digest(bundle_bytes) != BUNDLE_SHA256:
        raise gate.GateRejected("add-on source bundle identity mismatch")
    bundle = json.loads(bundle_bytes)
    if (bundle["base_commit"] != CORE_PIN or
            bundle["prerequisite"]["commit"] != PREREQUISITE_COMMIT or
            bundle["prerequisite"]["sha256"] != PREREQUISITE_BUNDLE):
        raise gate.GateRejected("wrong source composition")
    tests = bundle["test_manifest"]
    baseline_tests = list(tests["baseline_expected_red"]) + tests["baseline_positive_controls"]
    candidate_tests = tests["candidate_new_tests"]
    if (len(baseline_tests) != len(set(baseline_tests)) or
            len(candidate_tests) != len(set(candidate_tests)) or
            set(candidate_tests) != set(baseline_tests + tests["candidate_only_tests"])):
        raise gate.GateRejected("invalid new test inventory")
    if set(tests["module_swap_required_tests"]) - set(tests["full_required_existing_tests"]):
        raise gate.GateRejected("module_swap was omitted from the mandatory full gate")
    work = args.work.resolve()
    work.mkdir(parents=True, exist_ok=False)
    runner = gate.Runner(args.evidence.resolve())
    env = gate.clean_env(work)
    # Dependency resolution is allowed; the advisory metadata POST is not.
    # Normalize every inherited case variant before enforcing the child policy.
    for key in list(env):
        if key.lower() == "npm_config_audit":
            env.pop(key)
    env["npm_config_audit"] = "false"
    receipt = {
        "schema": 1, "status": "INCOMPLETE",
        "publication_commit": os.environ.get("GITHUB_SHA"),
        "repository": os.environ.get("GITHUB_REPOSITORY"),
        "workflow_ref": os.environ.get("GITHUB_WORKFLOW_REF"),
        "run_id": os.environ.get("GITHUB_RUN_ID"),
        "run_attempt": os.environ.get("GITHUB_RUN_ATTEMPT"),
        "core_pin": CORE_PIN,
        "prerequisite_commit": PREREQUISITE_COMMIT,
        "prerequisite_bundle_sha256": PREREQUISITE_BUNDLE,
        "bounded_runner_sha256": PREREQUISITE_CONTROLLER,
        "bundle_sha256": BUNDLE_SHA256,
        "controller_sha256": gate.file_sha(__file__, 1024 * 1024),
        "canonical_fixture_modules_pin": gate.MODULES_PIN,
        "cases": [], "stages": runner.records,
        "limits": {"stages": 90, "total_output_bytes": gate.MAX_TOTAL_OUTPUT},
        "npm_audit_policy": {
            "npm_config_audit": env["npm_config_audit"],
            "inherited_case_variants": "removed before setting the lowercase value",
            "scope": "sanitized base environment, fixtures, builds and canonical full nested helpers",
            "advisory_metadata_post": "disabled; no audit query is authorized or invoked",
        },
        "excluded": [
            "grouped image/config/journal atomicity", "individual-file crash safety",
            "same-identity reincarnation tokens", "comprehensive stale API retirement",
            "portable packaging", "mixed-version ownership safety",
            "malicious filesystem mutation",
        ],
    }
    try:
        if (os.environ.get("GITHUB_ACTIONS") != "true" or
                receipt["repository"] != "Qweasd123tg/proteus-modules-dot" or
                os.environ.get("GITHUB_REF") != BRANCH or
                not re.fullmatch(r"[0-9a-f]{40}", receipt["publication_commit"] or "")):
            raise gate.GateRejected("wrong isolated hosted context")
        head = runner.ok("publication-head", ["git", "rev-parse", "HEAD"],
                         Path(__file__).resolve().parent, env, 10).strip()
        if head != receipt["publication_commit"]:
            raise gate.GateRejected("publication checkout mismatch")
        head = runner.ok("prerequisite-head", ["git", "rev-parse", "HEAD"],
                         args.prerequisite_root.resolve(), env, 10).strip()
        if head != PREREQUISITE_COMMIT:
            raise gate.GateRejected("prerequisite checkout mismatch")
        gate.self_test()
        receipt["bounded_runner_self_test"] = "PASS"
        versions = {}
        for label, command in (
                ("rustc", ["rustc", "-Vv"]), ("cargo", ["cargo", "-V"]),
                ("node", ["node", "--version"]), ("npm", ["npm", "--version"]),
                ("bubblewrap", ["/usr/bin/bwrap", "--version"]),
                ("python", [sys.executable, "--version"])):
            versions[label] = runner.ok("version-" + label, command, work, env, 30, 65536).strip()
        receipt["tool_versions"] = versions
        if not versions["rustc"].startswith("rustc 1.95.0 ") or not versions["cargo"].startswith("cargo 1.95.0 "):
            raise gate.GateRejected("wrong Rust toolchain")
        if versions["node"] != "v22.18.0" or versions["bubblewrap"] != "bubblewrap 0.13.1":
            raise gate.GateRejected("wrong fixture/sandbox dependency")
        backend = Path("/usr/bin/bwrap").stat()
        if (backend.st_mode & 0o7777, backend.st_uid, backend.st_gid) != (0o755, 0, 0):
            raise gate.GateRejected("sandbox backend must be ordinary root-owned mode 0755")
        if runner.ok("sandbox-capabilities", ["getcap", "/usr/bin/bwrap"], work, env, 10, 65536).strip():
            raise gate.GateRejected("sandbox file capabilities must be absent")
        receipt["sandbox_binary_sha256"] = gate.file_sha("/usr/bin/bwrap", 16 * 1024 * 1024)

        baseline, candidate, modules = (work / name for name in ("baseline", "candidate", "modules"))
        roots = (("baseline", baseline), ("candidate", candidate))
        changes = {}
        before = {}
        for lane, root in roots:
            gate.checkout(runner, lane, root,
                          "https://github.com/Proteus-harness/Proteus-core.git", CORE_PIN, env)
            prior = gate.apply_bundle(root, previous, False)
            overlay = bundle["baseline_overlay" if lane == "baseline" else "candidate_overlay"]
            extra = apply_overlay(gate, root, overlay)
            changes[lane] = {**prior, **extra}
            runner.ok(lane + "-diff-check", ["git", "diff", "--check"], root, env, 30)
            before[lane] = gate.tracked_snapshot(
                runner, lane + "-source-before", root, env, changes[lane])
        receipt["composed_changed_files"] = changes
        runner.ok("candidate-format", ["cargo", "fmt", "--all", "--", "--check"],
                  candidate, env, 180, 2 * 1024 * 1024)

        gate.checkout(runner, "fixtures", modules,
                      "https://github.com/Proteus-harness/Proteus-modules.git", gate.MODULES_PIN, env)
        fixture_before = gate.tracked_snapshot(runner, "fixture-source-before", modules, env)
        fixture_env = dict(env, PROTEUS_MODULES_SOURCE=str(modules),
                           CARGO_TARGET_DIR=str(work / "fixture-target"))
        output = runner.ok(
            "build-reference-fixture",
            [sys.executable, "scripts/build_module.py", "--target-dir", work / "fixture-target"],
            candidate, fixture_env, 1200, 16 * 1024 * 1024)
        reference = Path(output.strip().splitlines()[-1]).resolve()
        if not reference.is_file() or not reference.is_relative_to(work / "fixture-target"):
            raise gate.GateRejected("reference fixture identity/path mismatch")
        receipt["reference_fixture_binary_sha256"] = gate.file_sha(reference)
        dcp = modules / "hook/dcp"
        runner.ok("dcp-install", ["npm", "ci", "--ignore-scripts", "--no-audit"], dcp, fixture_env, 300, 4 * 1024 * 1024)
        runner.ok("dcp-build", ["npm", "--no-audit", "run", "build"], dcp, fixture_env, 300, 4 * 1024 * 1024)
        worker = dcp / "dist/worker.js"
        if not worker.is_file():
            raise gate.GateRejected("DCP worker is missing")
        dist = [path for path in (dcp / "dist").rglob("*") if path.is_file()]
        if len(dist) > 1000:
            raise gate.InfrastructureError("DCP artifact count limit")
        receipt["dcp_dist_files"] = {
            str(path.relative_to(dcp)): gate.file_sha(path, 8 * 1024 * 1024)
            for path in sorted(dist)
        }
        full_env = dict(env, PROTEUS_MODULES_SOURCE=str(modules),
                        PROTEUS_TEST_REFERENCE_MODULE=str(reference),
                        PROTEUS_TEST_DCP_MODULE=str(worker),
                        CARGO_TARGET_DIR=str(work / "candidate-target"))
        for lane, root in roots:
            lane_env = dict(full_env, CARGO_TARGET_DIR=str(work / (lane + "-target")))
            binary = gate.compile_library(runner, lane, root, lane_env)
            names = baseline_tests if lane == "baseline" else candidate_tests
            gate.library_inventory(runner, lane, binary, root, lane_env, names)
            receipt[lane + "_library_sha256"] = gate.file_sha(binary)
            for index, name in enumerate(names):
                result = runner.run(
                    f"{lane}-case-{index:02}", [binary, "--exact", name, "--test-threads=1"],
                    root, lane_env, 90, 256 * 1024)
                marker = tests["baseline_expected_red"].get(name) if lane == "baseline" else None
                verdict = gate.classify(result, name, marker)
                receipt["cases"].append({"lane": lane, "name": name, "verdict": verdict})

        output = runner.ok("candidate-canonical-full",
                           [sys.executable, "scripts/test.py", "full"],
                           candidate, full_env, 2400, 32 * 1024 * 1024)
        required_passes(gate, output, candidate_tests + tests["full_required_existing_tests"])
        if not re.search(r"Running tests/module_swap\.rs \(", output):
            raise gate.GateRejected("canonical full gate did not expose module_swap execution")
        receipt["canonical_full"] = "PASS"
        receipt["module_swap"] = {
            "target": "module_swap",
            "required_passed_tests": tests["module_swap_required_tests"],
            "source": "unchanged canonical scripts/test.py full output",
        }
        for lane, root in roots:
            after = gate.tracked_snapshot(runner, lane + "-source-after", root, env, changes[lane])
            if after != before[lane]:
                raise gate.GateRejected(f"{lane}: source changed during qualification")
            receipt[lane + "_source_snapshot_sha256"] = digest(
                json.dumps(after, sort_keys=True, separators=(",", ":")).encode())
        if fixture_before != gate.tracked_snapshot(runner, "fixture-source-after", modules, env):
            raise gate.GateRejected("canonical module fixture source changed")
        receipt["unique_new_tests"] = len(candidate_tests)
        receipt["new_expected_baseline_reds"] = len(tests["baseline_expected_red"])
        receipt["counting_note"] = "Baseline/candidate/full executions repeat the same cases; do not sum them."
        receipt["status"] = "COMPOSED_GATES_PASS"
    except BaseException as error:
        receipt["status"] = ("INFRASTRUCTURE_ERROR" if isinstance(
            error, (gate.InfrastructureError, KeyboardInterrupt, SystemExit)) else "GATE_REJECTED")
        receipt["error"] = f"{type(error).__name__}: {error}"
        raise
    finally:
        data = json.dumps(receipt, indent=2, ensure_ascii=False).encode() + b"\n"
        if len(data) > 2 * 1024 * 1024:
            raise gate.InfrastructureError("receipt size limit")
        (runner.evidence / "result.json").write_bytes(data)


def main():
    if not __debug__:
        raise RuntimeError("optimized Python disables controller rejection checks")
    def terminate(number, _frame):
        raise KeyboardInterrupt(f"received signal {number}")
    signal.signal(signal.SIGTERM, terminate)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--prerequisite-root", type=Path, required=True)
    parser.add_argument("--work", type=Path, required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    qualify(parser.parse_args())


if __name__ == "__main__":
    main()
