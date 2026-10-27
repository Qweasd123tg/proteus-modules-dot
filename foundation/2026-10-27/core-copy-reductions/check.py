#!/usr/bin/env python3
"""Exact, bounded hosted qualification of four Core copy reductions.

The pinned PR 35 support module provides reviewed process/source/parser helpers.
Its former qualification entry points are never invoked. No upstream writes,
merge, deployment, paid runner, cleanup, dependency updates or benchmarks.
"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import signal
import stat
import sys

REPOSITORY = "Qweasd123tg/proteus-modules-dot"
BRANCH = "ci/core-copy-reductions-20261027"
HELPER_SHA256 = "2f917a4ca4dc71a3dfa8cf2dc376991a7ddf1580cd347aaff8cb6ccc50568147"
RECIPE_SHA256 = "0a6b5a4aba9112abe866fa5131d7f0f58a771f3542ec891af51f96d9bd7dae82"
QUALIFIED_TREE = "7dec0c811a514adf32a70907635939547e0a57cf"
PHASES = ("baseline", "production", "focused")
STATUSES = {phase: phase.upper() + "_EXACT_PASS" for phase in PHASES}
LIBRARIES = {
    "core": ("proteus-core", "proteus_core", "crates/proteus-core/src/lib.rs"),
    "protocol": ("proteus-module-protocol", "proteus_module_protocol",
                 "crates/proteus-module-protocol/src/lib.rs"),
}


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def bounded(path, cap=1024 * 1024):
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise RuntimeError("expected regular file: " + str(path))
    with path.open("rb") as stream:
        raw = stream.read(cap + 1)
    if len(raw) > cap:
        raise RuntimeError("file limit: " + str(path))
    return raw


def strict(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise RuntimeError("duplicate JSON key")
            result[key] = value
        return result
    return json.loads(raw, object_pairs_hook=pairs)


def support(args):
    helper_raw = bounded(args.helper)
    recipe_raw = bounded(args.recipe)
    if digest(helper_raw) != HELPER_SHA256 or digest(recipe_raw) != RECIPE_SHA256:
        raise RuntimeError("immutable support source mismatch")
    # Source review confirms imports/constants/definitions plus a __main__ guard.
    # This import does not call the old CLI, qualify, aggregate, or self-controls.
    spec = importlib.util.spec_from_file_location("qualified_pr35_support", args.helper)
    module = importlib.util.module_from_spec(spec)
    exec(compile(helper_raw, str(args.helper), "exec"), module.__dict__)
    recipe = module.strict_json(recipe_raw)
    if recipe["production_stage_trees"]["final"] != QUALIFIED_TREE:
        raise RuntimeError("wrong qualified baseline recipe")
    return module, recipe


def context():
    return {key: os.environ.get(name) for key, name in {
        "head": "GITHUB_SHA", "repository": "GITHUB_REPOSITORY",
        "workflow_ref": "GITHUB_WORKFLOW_REF", "run_id": "GITHUB_RUN_ID",
        "run_attempt": "GITHUB_RUN_ATTEMPT"}.items()}


def guard(h, ctx):
    if (os.environ.get("GITHUB_ACTIONS") != "true" or
            os.environ.get("GITHUB_EVENT_NAME") != "push" or
            os.environ.get("GITHUB_REF") != "refs/heads/" + BRANCH or
            ctx["repository"] != REPOSITORY or
            ctx["workflow_ref"] != REPOSITORY + "/.github/workflows/core-copy-reductions.yml@refs/heads/" + BRANCH or
            not re.fullmatch(r"[0-9a-f]{40}", ctx["head"] or "") or
            not all(re.fullmatch(r"[1-9][0-9]*", ctx[key] or "")
                    for key in ("run_id", "run_attempt"))):
        raise h.GateRejected("authorized exact guarded-push context required")


def load_manifest(h, args):
    path = Path(args.manifest).resolve()
    if path != Path(__file__).resolve().with_name("manifest.json"):
        raise h.GateRejected("manifest must be controller sibling")
    raw = bounded(path)
    manifest = h.strict_json(raw)
    if (manifest["schema"] != 1 or manifest["repository"] != REPOSITORY or
            manifest["branch"] != BRANCH or manifest["baseline_tree"] != QUALIFIED_TREE or
            manifest["controller_sha256"] != h.file_sha(__file__) or
            manifest["support"]["controller"]["sha256"] != HELPER_SHA256 or
            manifest["support"]["manifest"]["sha256"] != RECIPE_SHA256):
        raise h.GateRejected("package identity mismatch")
    return manifest, digest(raw)


def verify_file(h, root, item):
    raw = h.source_bytes(root, item["path"])
    if (len(raw) != item["bytes"] or h.sha(raw) != item["sha256"] or
            h.git_blob(raw) != item["git_blob"]):
        raise h.GateRejected("authored input identity mismatch: " + item["path"])
    return raw.decode("utf-8")


def plan_all(h, root, flat, qualified, patches, overlap, manifest):
    paths = set(qualified)
    for patch in [*patches.values(), overlap]:
        paths.update(path for path, _ in h.patch_sections(patch))
    files = {}
    for path in sorted(paths):
        raw = h.source_bytes(root, path, required=path in flat)
        if path in flat and (flat[path]["type"] != "blob" or
                flat[path]["mode"] not in {"100644", "100755"} or
                h.git_blob(raw) != flat[path]["sha"]):
            raise h.GateRejected("source preimage mismatch: " + path)
        files[path] = None if raw is None else raw.decode("utf-8")
    files.update({path: raw.decode("utf-8") for path, raw in qualified.items()})
    if h.complete_tree(h.flat_with_files(flat, files)) != QUALIFIED_TREE:
        raise h.GateRejected("qualified production prerequisite mismatch")
    for path, spec in manifest["preimages"].items():
        raw = files.get(path)
        if ((None if raw is None else h.git_blob(raw.encode())) != spec):
            raise h.GateRejected("slice source preimage mismatch: " + path)

    plans = {}
    def save(name, source):
        tree = h.complete_tree(h.flat_with_files(flat, source))
        blobs = {path: h.git_blob(value.encode()) for path, value in source.items()
                 if value is not None and h.git_blob(value.encode()) != flat.get(path, {}).get("sha")}
        expected = manifest["plans"][name]
        if tree != expected["tree"] or blobs != expected["changed_blobs"]:
            raise h.GateRejected("complete plan identity mismatch: " + name)
        plans[name] = ({path: value.encode() for path, value in source.items()
                       if path in blobs}, {"tree": tree, "changed_blobs": blobs})
    for item in manifest["slices"]:
        production, tested = dict(files), dict(files)
        h.apply_exact(production, patches[item["production_patch"]], [])
        h.apply_exact(tested, patches[item["test_patch"]], [])
        save(item["id"] + "-production", production)
        save(item["id"] + "-baseline-tests", tested)
        h.apply_exact(tested, patches[item["production_patch"]], [])
        save(item["id"] + "-candidate-tests", tested)
    production, tested = dict(files), dict(files)
    for item in manifest["slices"]:
        h.apply_exact(production, patches[item["production_patch"]], [])
        h.apply_exact(tested, patches[item["test_patch"]], [])
    save("production", production)
    save("baseline", tested)
    for item in manifest["slices"]:
        h.apply_exact(tested, patches[item["production_patch"]], [])
    save("candidate-tests", tested)
    h.apply_exact(tested, overlap, [])
    save("focused", tested)
    return plans


def compile_arguments(key):
    return ["cargo", "test", "--locked", "-p", LIBRARIES[key][0],
            "--lib", "--no-run", "--message-format=json"]


def compiled(h, output, key, root, target):
    package, name, source = LIBRARIES[key]
    candidates = []
    for line in output.splitlines():
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        item = value.get("target", {})
        if (value.get("reason") == "compiler-artifact" and value.get("executable") and
                item.get("name") == name and item.get("kind") == ["lib"]):
            executable = Path(value["executable"]).resolve()
            if (Path(item["src_path"]).resolve() != root / source or
                    value.get("features") != [] or not value.get("profile", {}).get("test") or
                    not executable.is_relative_to(target)):
                raise h.GateRejected("compiled target/source/default-feature identity mismatch")
            candidates.append(str(executable))
    if len(candidates) != 1:
        raise h.GateRejected("missing or ambiguous compiled library")
    return candidates[0]


def classify_case(h, result, case, baseline):
    red = case.get("baseline_red") if baseline else None
    if red is None:
        return h.classify(result, case["name"])
    if red["kind"] == "message":
        return h.classify(result, case["name"], red["marker"], "contains")
    if red["kind"] != "frame_pointer":
        raise h.GateRejected("unknown genuine negative control")
    # Generic classifier binds exactly one nonignored case, 101, panic section.
    h.classify(result, case["name"], "assertion \x60left == right\x60 failed", "contains")
    text = result["output"]
    failure = text.split("---- " + case["name"] + " stdout ----\n", 1)[1].split("\nfailures:\n", 1)[0]
    location = re.escape(red["source_suffix"]) + ":" + str(red["line"]) + ":" + str(red["column"]) + ":"
    if len(re.findall(r"panicked at [^\n]*" + location + r"$", failure, re.M)) != 1:
        raise h.GateRejected("frame control failed at the wrong source assertion")
    values = re.findall(r"^\s*(?:left|right): Some\(([0-9]+)\)$", failure, re.M)
    if len(values) != 2 or values[0] == values[1] or "left: Some(" not in failure or "right: Some(" not in failure:
        raise h.GateRejected("frame control did not prove distinct nonempty String pointers")
    return "EXPECTED_BEHAVIORAL_RED"


def require_inventory(h, output, ignored_output, required):
    listed = h.listed_tests(output)
    ignored = h.listed_tests(ignored_output)
    if any(listed.count(name) != 1 for name in required) or set(required) & set(ignored):
        raise h.GateRejected("mandatory exact test missing, duplicate or ignored")


def existing_required(recipe, inputs):
    specs = strict(inputs["ownership"])["validation"]
    return list(dict.fromkeys(
        specs["candidate_mandatory_tests"] + specs["candidate_extra_unit_tests"] +
        specs["candidate_existing_regression_tests"] + recipe["tests"]["recovery_required"] +
        recipe["tests"]["protocol_required"] + recipe["tests"]["module_swap_required"]))



def sandbox_evidence(h, output, binary_sha256):
    required = [
        "source_release=v0.13.1",
        "source_sha256=0e85c8702248b8dd64144f594147553650cdd0e4c951690345faace79c217c4d",
        "vendor_selftests=NOT_RUN; canonical_Core_sandbox_tests=REQUIRED",
        "security_policy_changes=NONE", "bubblewrap 0.13.1",
        "mode_uid_gid=755:0:0", "file_capabilities=NONE",
        "unprivileged_namespace_and_fd_probe=PASS",
    ]
    lines = output.splitlines()
    if any(lines.count(line) != 1 for line in required):
        raise h.GateRejected("missing or duplicated real sandbox prerequisite evidence")
    hashes = re.findall(r"^([0-9a-f]{64})  /usr/bin/bwrap$", output, re.M)
    if hashes != [binary_sha256]:
        raise h.GateRejected("sandbox prerequisite binary differs from phase backend")


def run_phase(h, recipe, manifest, manifest_hash, args):
    ctx = context()
    guard(h, ctx)
    work = Path(args.work).resolve()
    work.mkdir(parents=True, exist_ok=False)
    runner = h.Runner(Path(args.evidence).resolve(), work, 6600)
    env = h.clean_env(work)
    receipt = {
        "schema": 1, "phase": args.phase, "status": "INCOMPLETE", "context": ctx,
        "controller_sha256": h.file_sha(__file__), "manifest_sha256": manifest_hash,
        "support_sha256": HELPER_SHA256, "recipe_sha256": RECIPE_SHA256,
        "baseline_tree": QUALIFIED_TREE, "plans": manifest["plans"],
        "stages": runner.records, "cases": [], "resource_policy": manifest["resources"],
        "source_root": str(work / "source"), "target_root": str(work / "target"),
        "environment_policy": {"allowlisted": sorted(env), "npm_audit": False,
                               "secrets_inherited": False},
        "coverage": "Only this current head, run, attempt and exact phase; aggregate required.",
    }
    try:
        receipt["initial_free_bytes"] = shutil.disk_usage(work).free
        if receipt["initial_free_bytes"] < h.INITIAL_FREE_BYTES:
            raise h.InfrastructureError("hosted admission requires 8 GiB free")
        publication = Path(os.environ["GITHUB_WORKSPACE"]).resolve()
        if runner.ok("publication-head", ["git", "rev-parse", "HEAD"], publication, env, 10).strip() != ctx["head"]:
            raise h.GateRejected("publication head mismatch")
        inputs_root, inputs = h.fetch_inputs(runner, work, env, recipe)
        old = h.parse_tree(runner.ok("publication-base-tree",
            ["git", "ls-tree", "-r", "-z", "--full-tree", manifest["publication_base"]],
            inputs_root, env, 30, 2 * 1024 * 1024))
        new = h.parse_tree(runner.ok("publication-tree",
            ["git", "ls-tree", "-r", "-z", "--full-tree", "HEAD"],
            publication, env, 30, 2 * 1024 * 1024))
        if (h.complete_tree(old) != manifest["publication_base_tree"] or
                set(new) != set(old) | set(manifest["publication_files"]) or
                any(new.get(path) != value for path, value in old.items())):
            raise h.GateRejected("publication escaped additive personal-repository package scope")
        receipt["publication_tree"] = h.complete_tree(new)
        patches = {item["path"]: verify_file(h, publication, item)
                   for item in manifest["patches"]}
        overlap = patches.pop(manifest["overlap"]["path"])
        for item in manifest["documents"]:
            verify_file(h, publication, item)
        receipt["tools"] = {}
        for label, argv in [("rustc", ["rustc", "-Vv"]), ("cargo", ["cargo", "-V"]),
                            ("node", ["node", "--version"]), ("bubblewrap", ["/usr/bin/bwrap", "--version"])]:
            receipt["tools"][label] = runner.ok("version-" + label, argv, work, env, 30).strip()
        if (not receipt["tools"]["rustc"].startswith("rustc 1.95.0 ") or
                not receipt["tools"]["cargo"].startswith("cargo 1.95.0 ") or
                receipt["tools"]["node"] != "v22.18.0" or
                receipt["tools"]["bubblewrap"] != "bubblewrap 0.13.1"):
            raise h.GateRejected("wrong official toolchain or sandbox dependency")
        backend = Path("/usr/bin/bwrap")
        info = backend.stat()
        if (backend.is_symlink() or (stat.S_IMODE(info.st_mode), info.st_uid, info.st_gid) != (0o755, 0, 0) or
                runner.ok("sandbox-capabilities", ["getcap", backend], work, env, 10).strip()):
            raise h.GateRejected("sandbox dependency is not ordinary capability-free 0755")
        receipt["sandbox_binary_sha256"] = h.file_sha(backend, 16 * 1024 * 1024)
        sandbox_log = runner.ok("sandbox-evidence", ["cat", work.parent / "core-copy-bwrap-evidence.txt"], work, env, 10, 65536)
        sandbox_evidence(h, sandbox_log, receipt["sandbox_binary_sha256"])
        receipt["sandbox_receipt_sha256"] = h.sha(sandbox_log.encode())
        root = work / "source"
        h.checkout(runner, "source", root, recipe["core"]["repository"], recipe["core"]["commit"], env)
        flat = h.parse_tree(runner.ok("source-original-tree",
            ["git", "ls-tree", "-r", "-z", "--full-tree", "HEAD"], root, env, 30, 2 * 1024 * 1024))
        if h.complete_tree(flat) != recipe["core"]["tree"]:
            raise h.GateRejected("upstream source tree mismatch")
        for path, blob in recipe["canonical_harness"]["source_blobs"].items():
            if flat.get(path, {}).get("sha") != blob or h.git_blob(h.source_bytes(root, path)) != blob:
                raise h.GateRejected("canonical wrapper/harness preimage mismatch")
        qualified, _ = h.plan_composition(root, flat, inputs, recipe, False)
        plans = plan_all(h, root, flat, qualified, patches, overlap, manifest)
        receipt["all_plans_preflight"] = "PASS_BEFORE_ANY_SOURCE_REPLACEMENT"
        changed, plan = plans[args.phase]
        h.materialize(runner, "selected", root, changed, plan["tree"], env)
        runner.ok("selected-format", ["cargo", "fmt", "--all", "--", "--check"],
                  root, env, 180, 2 * 1024 * 1024)
        before = h.tracked_snapshot(runner, "selected-source-before", root, env)
        receipt["source_snapshot_before_sha256"] = h.sha(json.dumps(before, sort_keys=True, separators=(",", ":")).encode())
        lane_env = dict(env, CARGO_TARGET_DIR=str(work / "target"))
        if args.phase != "baseline":
            modules = work / "canonical-modules"
            h.checkout(runner, "fixture", modules, recipe["fixture"]["repository"],
                       recipe["fixture"]["commit"], env)
            if runner.ok("fixture-tree", ["git", "rev-parse", "HEAD^{tree}"],
                         modules, env, 10).strip() != recipe["fixture"]["tree"]:
                raise h.GateRejected("canonical fixture tree mismatch")
            fixture_before = h.tracked_snapshot(runner, "fixture-source-before", modules, env)
            fixture_env = dict(env, PROTEUS_MODULES_SOURCE=str(modules),
                               CARGO_TARGET_DIR=str(work / "fixture-target"))
            output = runner.ok("build-reference-fixture",
                [sys.executable, "scripts/build_module.py", "--target-dir", work / "fixture-target"],
                root, fixture_env, 1800, 24 * 1024 * 1024)
            reference = Path(output.strip().splitlines()[-1]).resolve()
            if not reference.is_file() or not reference.is_relative_to(work / "fixture-target"):
                raise h.GateRejected("wrong isolated reference fixture executable")
            lane_env.update(PROTEUS_MODULES_SOURCE=str(modules), PROTEUS_TEST_REFERENCE_MODULE=str(reference))
            receipt["fixture_artifacts"] = {"reference_sha256": h.file_sha(reference)}
            if args.phase == "production":
                # Unchanged pinned DCP is ONLY the pre-existing canonical fixture.
                # No DCP source/metadata experiment or advisory submission occurs.
                dcp = modules / "hook/dcp"
                runner.ok("canonical-dcp-fixture-install",
                    ["npm", "ci", "--ignore-scripts", "--no-audit", "--no-fund"],
                    dcp, fixture_env, 300, 4 * 1024 * 1024)
                runner.ok("canonical-dcp-fixture-build", ["npm", "--no-audit", "--no-fund", "run", "build"],
                          dcp, fixture_env, 300, 4 * 1024 * 1024)
                worker = dcp / "dist/worker.js"
                if not worker.is_file():
                    raise h.GateRejected("unchanged canonical fixture worker missing")
                receipt["fixture_artifacts"]["dcp_worker_sha256"] = h.file_sha(worker, 8 * 1024 * 1024)
                lane_env["PROTEUS_TEST_DCP_MODULE"] = str(worker)
        if args.phase in ("baseline", "focused"):
            receipt["binaries"] = {}
            for key in LIBRARIES:
                output = runner.ok(key + "-compile", compile_arguments(key),
                    root, lane_env, 1800, 24 * 1024 * 1024)
                binary = compiled(h, output, key, root, work / "target")
                required = [case["name"] for case in manifest["cases"] if case["library"] == key]
                if key == "core" and args.phase == "focused":
                    required.append(recipe["cross_control"]["test_name"])
                inventory = runner.ok(key + "-inventory",
                    [binary, "--list", "--format", "terse"], root, lane_env, 30, 512 * 1024)
                ignored = runner.ok(key + "-ignored",
                    [binary, "--list", "--ignored", "--format", "terse"], root, lane_env, 30, 128 * 1024)
                require_inventory(h, inventory, ignored, required)
                receipt["binaries"][key] = {"executable": binary, "sha256_before": h.file_sha(binary)}
            for index, case in enumerate(manifest["cases"]):
                label = f"case-{index:02}"
                binary = receipt["binaries"][case["library"]]["executable"]
                result = runner.run(label, [binary, "--exact", case["name"], "--test-threads=1"],
                                    root, lane_env, 180, 1024 * 1024)
                verdict = classify_case(h, result, case, args.phase == "baseline")
                receipt["cases"].append({"name": case["name"], "stage": label, "verdict": verdict})
            if args.phase == "focused":
                name = recipe["cross_control"]["test_name"]
                result = runner.run("overlap", [receipt["binaries"]["core"]["executable"],
                    "--exact", name, "--test-threads=1", "--show-output"], root, lane_env, 180, 1024 * 1024)
                h.classify(result, name)
                markers = re.findall(r"^RECOVERY_OWNED_DELETE_SCHEDULE: [^\n]+$", result["output"], re.M)
                if sorted(markers) != sorted(recipe["cross_control"]["schedule_markers"]):
                    raise h.GateRejected("missing or duplicate retained overlap schedule")
                ownership = strict(inputs["ownership"])["validation"]
                required = (ownership["candidate_extra_unit_tests"] +
                    ownership["candidate_existing_regression_tests"] + recipe["tests"]["recovery_required"] +
                    [case["name"] for case in manifest["cases"] if case["library"] == "core"] + [name])
                ignored = [name for name in recipe["tests"]["full_allowed_ignored"] if name.startswith("core::")]
                receipt["parallel_unit"] = h.require_passes(runner.ok("focused-parallel-unit",
                    [sys.executable, "scripts/test.py", "-p", "proteus-core", "--lib"],
                    root, lane_env, 1800, 24 * 1024 * 1024), required, allowed_ignored=ignored)
                if set(receipt["parallel_unit"]["ignored"]) != set(ignored):
                    raise h.GateRejected("focused unit ignored inventory changed")
                receipt["protocol"] = h.require_passes(runner.ok("focused-protocol",
                    [sys.executable, "scripts/test.py", "-p", "proteus-module-protocol", "--", "--test-threads=1"],
                    root, lane_env, 1800, 16 * 1024 * 1024),
                    recipe["tests"]["protocol_required"] +
                    [case["name"] for case in manifest["cases"] if case["library"] == "protocol"])
            for value in receipt["binaries"].values():
                value["sha256_after"] = h.file_sha(value["executable"])
                if value["sha256_before"] != value["sha256_after"]:
                    raise h.GateRejected("focused binary changed after discovery")
        else:
            receipt["protocol"] = h.require_passes(runner.ok("production-protocol",
                [sys.executable, "scripts/test.py", "-p", "proteus-module-protocol", "--", "--test-threads=1"],
                root, lane_env, 1800, 16 * 1024 * 1024), recipe["tests"]["protocol_required"])
            receipt["module_swap"] = h.require_passes(runner.ok("production-module-swap",
                [sys.executable, "scripts/test.py", "-p", "proteus-core", "--test", "module_swap", "--", "--test-threads=1"],
                root, lane_env, 1800, 16 * 1024 * 1024), recipe["tests"]["module_swap_required"], exact_inventory=True)
            output = runner.ok("canonical-compile",
                [sys.executable, *recipe["canonical_harness"]["compile_arguments"]],
                root, lane_env, 1800, 24 * 1024 * 1024)
            binaries = h.canonical_targets(output, root, work / "target", recipe["canonical_harness"])
            receipt["canonical_binaries"] = binaries
            receipt["canonical_sha256_before"] = {name: h.file_sha(value["executable"])
                                                  for name, value in binaries.items()}
            output = runner.ok("canonical-full", [sys.executable, "scripts/test.py", "full"],
                               root, lane_env, 1800, 40 * 1024 * 1024)
            receipt["canonical_sha256_after"] = {name: h.file_sha(value["executable"])
                                                 for name, value in binaries.items()}
            if receipt["canonical_sha256_before"] != receipt["canonical_sha256_after"]:
                raise h.GateRejected("canonical binaries changed after discovery")
            receipt["required_full"] = existing_required(recipe, inputs)
            receipt["canonical_full"] = h.require_canonical_passes(output, receipt["required_full"],
                recipe["canonical_harness"], binaries, recipe["tests"]["full_allowed_ignored"])
            if set(receipt["canonical_full"]["ignored"]) != set(recipe["tests"]["full_allowed_ignored"]):
                raise h.GateRejected("canonical ignored inventory changed")
        if args.phase != "baseline":
            receipt["fixture_snapshot"] = h.source_after(
                runner, "fixture", modules, env, fixture_before, recipe["fixture"]["tree"])
        receipt["source_snapshot_after_sha256"] = h.source_after(
            runner, "selected", root, env, before, plan["tree"])
        if receipt["source_snapshot_before_sha256"] != receipt["source_snapshot_after_sha256"]:
            raise h.GateRejected("source snapshot changed")
        receipt["status"] = STATUSES[args.phase]
    except BaseException as error:
        receipt["status"] = "INFRASTRUCTURE_ERROR" if h.is_infrastructure(error) else "GATE_REJECTED"
        receipt["error"] = f"{type(error).__name__}: {error}"
        raise
    finally:
        raw = json.dumps(receipt, indent=2).encode() + b"\n"
        if len(raw) > 4 * 1024 * 1024:
            raise h.InfrastructureError("receipt exceeds bound")
        (runner.evidence / "result.json").write_bytes(raw)



def phase_invariants(h, receipt, phase, manifest, manifest_hash, ctx):
    invariant = {
        "schema": 1, "phase": phase, "context": ctx,
        "controller_sha256": manifest["controller_sha256"], "manifest_sha256": manifest_hash,
        "support_sha256": HELPER_SHA256, "recipe_sha256": RECIPE_SHA256,
        "baseline_tree": QUALIFIED_TREE, "plans": manifest["plans"],
        "resource_policy": manifest["resources"],
    }
    if any(receipt.get(key) != value for key, value in invariant.items()):
        raise h.GateRejected("foreign phase invariant identity: " + phase)
    return receipt.get("status")


def phase_pass_identity(h, receipt, phase, current_tree):
    if (receipt.get("status") != STATUSES[phase] or receipt.get("publication_tree") != current_tree or
            receipt.get("all_plans_preflight") != "PASS_BEFORE_ANY_SOURCE_REPLACEMENT" or
            type(receipt.get("initial_free_bytes")) is not int or
            receipt["initial_free_bytes"] < h.INITIAL_FREE_BYTES):
        raise h.GateRejected("phase lacks exact passing progress/admission identity: " + phase)


def require_jobs(h, qualify, focused):
    if qualify != "success" or focused != "success":
        raise h.InfrastructureError("a required GitHub phase job did not succeed")


def aggregate(h, recipe, manifest, manifest_hash, args):
    ctx = context()
    guard(h, ctx)
    evidence = Path(args.evidence).resolve()
    publication = Path(os.environ["GITHUB_WORKSPACE"]).resolve()
    verification = h.Runner(evidence, publication, 120)
    verify_env = {key: value for key, value in os.environ.items()
                  if key in {"PATH", "LANG", "LC_ALL", "TMPDIR", "TMP", "TEMP"}}
    verify_env.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL="/dev/null", GIT_TERMINAL_PROMPT="0")
    result = {"schema": 1, "status": "INCOMPLETE", "context": ctx,
              "manifest_sha256": manifest_hash, "phases": {}, "stages": verification.records}
    try:
        if verification.ok("aggregate-head", ["git", "rev-parse", "HEAD"], publication, verify_env, 10).strip() != ctx["head"]:
            raise h.GateRejected("aggregate checkout differs from exact current head")
        current_flat = h.parse_tree(verification.ok("aggregate-publication-tree",
            ["git", "ls-tree", "-r", "-z", "--full-tree", "HEAD"], publication, verify_env, 30, 2 * 1024 * 1024))
        verification.ok("aggregate-clean-checkout", ["git", "diff", "--quiet", "HEAD"], publication, verify_env, 10)
        current_tree = h.complete_tree(current_flat)
        result["publication_tree"] = current_tree
        # Pre-scan every available receipt before interpreting pass-only progress.
        # Early admission/network/disk failures may precede publication/preflight
        # fields; a missing sibling artifact must not hide exact-context infra.
        available, missing, infrastructure, rejected = {}, [], [], []
        for phase in PHASES:
            path = Path(args.aggregate).resolve() / phase / "result.json"
            if not path.exists():
                missing.append(phase)
                continue
            raw = bounded(path, 4 * 1024 * 1024)
            receipt = h.strict_json(raw)
            phase_invariants(h, receipt, phase, manifest, manifest_hash, ctx)
            available[phase] = (raw, receipt)
            if receipt.get("status") == "INFRASTRUCTURE_ERROR":
                infrastructure.append(phase + ": " + str(receipt.get("error", "")))
            elif receipt.get("status") != STATUSES[phase]:
                rejected.append(phase + ": " + str(receipt.get("status")))
        if infrastructure:
            raise h.InfrastructureError("exact current-run infrastructure failure: " + "; ".join(infrastructure))
        if rejected:
            raise h.GateRejected("exact current-run phase not qualified: " + "; ".join(rejected))
        if missing:
            raise h.InfrastructureError("required phase evidence unavailable; product status unresolved: " + ", ".join(missing))
        for phase in PHASES:
            root = Path(args.aggregate).resolve() / phase
            raw, receipt = available[phase]
            phase_pass_identity(h, receipt, phase, current_tree)
            paths, records = h.phase_logs(root, receipt)
            source = Path(receipt["source_root"])
            target = Path(receipt["target_root"])
            if (not source.is_absolute() or source.name != "source" or
                    source.parent.name != "core-copy-work" or target != source.parent / "target"):
                raise h.GateRejected("phase source/target isolation mismatch")
            def output(label, argv=None):
                if label not in records:
                    raise h.GateRejected("required stage missing: " + label)
                if argv is not None and (records[label]["argv"] != [str(x) for x in argv] or
                        records[label]["cwd"] != str(source)):
                    raise h.GateRejected("required command/source binding mismatch: " + label)
                return {"code": records[label]["exit_code"],
                        "output": h.bounded_file(paths[label], h.MAX_TOTAL_OUTPUT).decode("utf-8", "replace")}
            sandbox_log = output("sandbox-evidence")["output"]
            if (records["sandbox-evidence"]["argv"] != ["cat", str(source.parent.parent / "core-copy-bwrap-evidence.txt")] or
                    records["sandbox-evidence"]["cwd"] != str(source.parent) or
                    h.sha(sandbox_log.encode()) != receipt.get("sandbox_receipt_sha256")):
                raise h.GateRejected("sandbox prerequisite provenance mismatch")
            sandbox_evidence(h, sandbox_log, receipt.get("sandbox_binary_sha256"))
            output("selected-format", ["cargo", "fmt", "--all", "--", "--check"])
            if (output("selected-final-tree", ["git", "write-tree"])["output"].strip() != manifest["plans"][phase]["tree"] or
                    output("selected-no-unstaged", ["git", "diff", "--quiet"])["output"].strip() or
                    output("selected-no-untracked", ["git", "ls-files", "--others", "--exclude-standard"])["output"].strip() or
                    receipt.get("source_snapshot_before_sha256") != receipt.get("source_snapshot_after_sha256") or
                    not re.fullmatch(r"[0-9a-f]{64}", receipt.get("source_snapshot_after_sha256", ""))):
                raise h.GateRejected("source/index postflight mismatch")
            permitted_red_stages = set()
            if phase in ("baseline", "focused"):
                binaries = {}
                for key in LIBRARIES:
                    binary = compiled(h, output(key + "-compile", compile_arguments(key))["output"], key, source, target)
                    value = receipt["binaries"][key]
                    if (value.get("executable") != binary or value.get("sha256_before") != value.get("sha256_after") or
                            not re.fullmatch(r"[0-9a-f]{64}", value.get("sha256_after", ""))):
                        raise h.GateRejected("binary provenance mismatch")
                    binaries[key] = binary
                    required = [case["name"] for case in manifest["cases"] if case["library"] == key]
                    if key == "core" and phase == "focused":
                        required.append(recipe["cross_control"]["test_name"])
                    require_inventory(h,
                        output(key + "-inventory", [binary, "--list", "--format", "terse"])["output"],
                        output(key + "-ignored", [binary, "--list", "--ignored", "--format", "terse"])["output"], required)
                cases = []
                for index, case in enumerate(manifest["cases"]):
                    label = f"case-{index:02}"
                    observed = output(label, [binaries[case["library"]], "--exact", case["name"], "--test-threads=1"])
                    verdict = classify_case(h, observed, case, phase == "baseline")
                    cases.append({"name": case["name"], "stage": label, "verdict": verdict})
                    if verdict == "EXPECTED_BEHAVIORAL_RED":
                        permitted_red_stages.add(label)
                if cases != receipt["cases"]:
                    raise h.GateRejected("case receipt differs from independently classified raw logs")
                if phase == "baseline" and len(permitted_red_stages) != manifest["baseline_red_count"]:
                    raise h.GateRejected("genuine negative-control count mismatch")
                if phase == "focused":
                    name = recipe["cross_control"]["test_name"]
                    observed = output("overlap", [binaries["core"], "--exact", name, "--test-threads=1", "--show-output"])
                    h.classify(observed, name)
                    markers = re.findall(r"^RECOVERY_OWNED_DELETE_SCHEDULE: [^\n]+$", observed["output"], re.M)
                    if sorted(markers) != sorted(recipe["cross_control"]["schedule_markers"]):
                        raise h.GateRejected("retained overlap schedule mismatch")
                    ignored = [name for name in recipe["tests"]["full_allowed_ignored"] if name.startswith("core::")]
                    parsed = h.require_passes(output("focused-parallel-unit",
                        [sys.executable, "scripts/test.py", "-p", "proteus-core", "--lib"])["output"],
                        manifest["focused_core_required"], allowed_ignored=ignored)
                    if not same_json_evidence(parsed, receipt["parallel_unit"]) or set(parsed["ignored"]) != set(ignored):
                        raise h.GateRejected("focused parallel unit evidence mismatch")
                    parsed = h.require_passes(output("focused-protocol",
                        [sys.executable, "scripts/test.py", "-p", "proteus-module-protocol", "--", "--test-threads=1"])["output"],
                        recipe["tests"]["protocol_required"] +
                        [case["name"] for case in manifest["cases"] if case["library"] == "protocol"])
                    if not same_json_evidence(parsed, receipt["protocol"]):
                        raise h.GateRejected("focused protocol evidence mismatch")
            else:
                parsed = h.require_passes(output("production-protocol",
                    [sys.executable, "scripts/test.py", "-p", "proteus-module-protocol", "--", "--test-threads=1"])["output"],
                    recipe["tests"]["protocol_required"])
                if not same_json_evidence(parsed, receipt["protocol"]):
                    raise h.GateRejected("production protocol evidence mismatch")
                parsed = h.require_passes(output("production-module-swap",
                    [sys.executable, "scripts/test.py", "-p", "proteus-core", "--test", "module_swap", "--", "--test-threads=1"])["output"],
                    recipe["tests"]["module_swap_required"], exact_inventory=True)
                if not same_json_evidence(parsed, receipt["module_swap"]):
                    raise h.GateRejected("module-swap evidence mismatch")
                binaries = h.canonical_targets(output("canonical-compile",
                    [sys.executable, *recipe["canonical_harness"]["compile_arguments"]])["output"],
                    source, target, recipe["canonical_harness"])
                if (binaries != receipt["canonical_binaries"] or
                        receipt["canonical_sha256_before"] != receipt["canonical_sha256_after"] or
                        set(receipt["canonical_sha256_before"]) != set(binaries) or
                        any(not re.fullmatch(r"[0-9a-f]{64}", value) for value in receipt["canonical_sha256_before"].values()) or
                        receipt["required_full"] != manifest["production_required_full"]):
                    raise h.GateRejected("canonical source/feature/binary provenance mismatch")
                parsed = h.require_canonical_passes(output("canonical-full",
                    [sys.executable, "scripts/test.py", "full"])["output"], manifest["production_required_full"],
                    recipe["canonical_harness"], binaries, recipe["tests"]["full_allowed_ignored"])
                if not same_json_evidence(parsed, receipt["canonical_full"]) or set(parsed["ignored"]) != set(recipe["tests"]["full_allowed_ignored"]):
                    raise h.GateRejected("canonical full evidence mismatch")
            if phase != "baseline":
                fixture_root = str(source.parent / "canonical-modules")
                for label, argv in [
                    ("fixture-final-tree", ["git", "write-tree"]),
                    ("fixture-no-unstaged", ["git", "diff", "--quiet"]),
                    ("fixture-no-untracked", ["git", "ls-files", "--others", "--exclude-standard"]),
                ]:
                    if records.get(label, {}).get("argv") != argv or records.get(label, {}).get("cwd") != fixture_root:
                        raise h.GateRejected("fixture postflight source/command binding mismatch")
                if records.get("fixture-final-tree", {}).get("exit_code") != 0 or output("fixture-final-tree")["output"].strip() != recipe["fixture"]["tree"]:
                    raise h.GateRejected("fixture final identity missing")
                for label in ("fixture-no-unstaged", "fixture-no-untracked"):
                    if output(label)["output"].strip():
                        raise h.GateRejected("fixture source changed")
            if {label for label, item in records.items() if item["exit_code"] == 101} != permitted_red_stages:
                raise h.GateRejected("unrelated failing command cannot satisfy qualification")
            result["phases"][phase] = {"receipt_sha256": digest(raw), "status": receipt["status"],
                "stages": len(records), "minimum_free_bytes": min(item["disk_free_minimum_bytes"] for item in records.values())}
        require_jobs(h, os.environ.get("QUALIFY_JOB_RESULT"), os.environ.get("FOCUSED_JOB_RESULT"))
        result["status"] = "CORE_COPY_REDUCTIONS_EXACT_PASS"
        result["counting"] = "Named controls and canonical gates overlap; no additive unique-test or performance claim."
    except BaseException as error:
        result["status"] = "INFRASTRUCTURE_ERROR" if h.is_infrastructure(error) else "GATE_REJECTED"
        result["error"] = f"{type(error).__name__}: {error}"
        raise
    finally:
        (evidence / "result.json").write_text(json.dumps(result, indent=2) + "\n")


def same_json_evidence(parsed, recorded):
    """Compare complete JSON evidence without tuple/list or bool/int ambiguity."""
    options = {"sort_keys": True, "separators": (",", ":"), "allow_nan": False}
    return json.dumps(parsed, **options) == json.dumps(recorded, **options)


def self_test(h, recipe, manifest):
    h.self_test()
    h.composition_self_test()
    h.canonical_parser_self_test(recipe["canonical_harness"])
    case = next(case for case in manifest["cases"] if case.get("baseline_red", {}).get("kind") == "frame_pointer")
    name = case["name"]
    red = case["baseline_red"]
    failure = ("running 1 test\n" + f"test {name} ... FAILED\n\nfailures:\n\n---- {name} stdout ----\n" +
        f"thread '{name}' panicked at crates/proteus-module-protocol/src/v3/{red['source_suffix']}:{red['line']}:{red['column']}:\n" +
        "assertion \x60left == right\x60 failed\n  left: Some(1000)\n right: Some(2000)\n\nfailures:\n" +
        f"    {name}\n\ntest result: FAILED. 0 passed; 1 failed; 0 ignored; 0 measured; 0 filtered out; finished in 0.00s\n")
    if classify_case(h, {"code": 101, "output": failure}, case, True) != "EXPECTED_BEHAVIORAL_RED":
        raise h.GateRejected("frame parser positive self-control")
    for invalid in [
        {"code": 0, "output": failure},
        {"code": 101, "output": failure.replace("Some(2000)", "Some(1000)")},
        {"code": 101, "output": failure.replace(str(red["line"]) + ":", "999999:")},
        {"code": 101, "output": failure.replace("left: Some", "left: None #")},
        {"code": 101, "output": failure + f"\ntest {name} ... FAILED\n"},
        {"code": 101, "output": "compiler failed\n"},
    ]:
        try:
            classify_case(h, invalid, case, True)
        except h.GateRejected:
            pass
        else:
            raise h.GateRejected("frame parser accepted invalid self-control")
    ctx = {"head": "a" * 40, "repository": REPOSITORY, "workflow_ref": "test", "run_id": "1", "run_attempt": "1"}
    base = {
        "schema": 1, "phase": "baseline", "context": ctx,
        "controller_sha256": manifest["controller_sha256"], "manifest_sha256": "m",
        "support_sha256": HELPER_SHA256, "recipe_sha256": RECIPE_SHA256,
        "baseline_tree": QUALIFIED_TREE, "plans": manifest["plans"], "resource_policy": manifest["resources"],
        "status": "INFRASTRUCTURE_ERROR",
    }
    # Genuine early infra is identified without fields that could not yet exist.
    assert phase_invariants(h, base, "baseline", manifest, "m", ctx) == "INFRASTRUCTURE_ERROR"
    good = dict(base, status=STATUSES["baseline"], publication_tree="t",
                all_plans_preflight="PASS_BEFORE_ANY_SOURCE_REPLACEMENT",
                initial_free_bytes=h.INITIAL_FREE_BYTES)
    phase_pass_identity(h, good, "baseline", "t")
    for key in ("head", "run_id", "run_attempt"):
        altered = dict(good, context=dict(ctx, **{key: "foreign"}))
        try:
            phase_invariants(h, altered, "baseline", manifest, "m", ctx)
        except h.GateRejected:
            pass
        else:
            raise h.GateRejected("aggregate accepted a foreign " + key)
    for key in ("publication_tree", "all_plans_preflight", "initial_free_bytes"):
        altered = dict(good)
        altered.pop(key)
        try:
            phase_pass_identity(h, altered, "baseline", "t")
        except h.GateRejected:
            pass
        else:
            raise h.GateRejected("aggregate accepted missing PASS field " + key)
    require_jobs(h, "success", "success")
    for values in (("failure", "success"), ("success", "cancelled"), ("success", "skipped")):
        try:
            require_jobs(h, *values)
        except h.InfrastructureError:
            pass
        else:
            raise h.GateRejected("aggregate accepted an unsuccessful GitHub job")
    sample = ("running 1 test\ntest exact_json_control ... ok\n\n"
              "test result: ok. 1 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 0.00s\n")
    parsed = h.require_passes(sample, ["exact_json_control"], exact_inventory=True)
    recorded = json.loads(json.dumps(parsed))
    # The inherited parser intentionally returns tuple rows; receipts contain JSON arrays.
    assert parsed != recorded
    assert same_json_evidence(parsed, recorded)
    for key, value in (
        ("passed", ["foreign_test"]),
        ("ignored", ["exact_json_control"]),
        ("libtest_passed_count", 2),
        ("libtest_passed_count", True),
        ("summaries", [["ok", "2", "0", "0", "0", "0"]]),
        ("summaries", list(reversed(recorded["summaries"][0]))),
    ):
        altered = dict(recorded, **{key: value})
        assert not same_json_evidence(parsed, altered)
    altered = dict(recorded, extra_unexpected_field=True)
    assert not same_json_evidence(parsed, altered)
    altered = dict(recorded)
    altered.pop("summaries")
    assert not same_json_evidence(parsed, altered)
    print("JSON receipt roundtrip and eight evidence-mutation rejection controls PASS")
    print("Aggregate identity, early-infrastructure and job-result controls PASS")
    print("Pinned helper and six strict frame-negative rejection controls PASS")


def main():
    if not __debug__:
        raise RuntimeError("Python assertions must remain enabled")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--helper", type=Path, required=True)
    parser.add_argument("--recipe", type=Path, required=True)
    parser.add_argument("--phase", choices=PHASES)
    parser.add_argument("--work", type=Path)
    parser.add_argument("--evidence", type=Path)
    parser.add_argument("--aggregate", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    h, recipe = support(args)
    manifest, manifest_hash = load_manifest(h, args)
    signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(KeyboardInterrupt("SIGTERM")))
    if args.self_test:
        self_test(h, recipe, manifest)
    elif args.aggregate is not None:
        if args.phase is not None or args.work is not None or args.evidence is None:
            parser.error("aggregate requires evidence and no phase/work")
        aggregate(h, recipe, manifest, manifest_hash, args)
    else:
        if None in (args.phase, args.work, args.evidence):
            parser.error("phase, work and evidence are required")
        run_phase(h, recipe, manifest, manifest_hash, args)


if __name__ == "__main__":
    main()
