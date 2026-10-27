#!/usr/bin/env python3
"""Scoped compact-validation correctness gate; pinned qualified helpers, no benchmark."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import stat
import sys

REPOSITORY = "Qweasd123tg/proteus-modules-dot"
BRANCH = "ci/core-compact-validation-20261027"
WORKFLOW = ".github/workflows/core-compact-validation.yml"
QUALIFIER_SHA = "4cf85d5124f7d39cb38a3444287bf43254d74f1053a70fee926c6515ca3c6b3b"
FOUNDATION_SHA = "dca653f3eda6ece4e9f339f531669a14e249e7a0cf151dd77a58b9fea5eef603"
FOUNDATION_TREE = "9a122670d8e4360e4cdccc930569f141629baefc"
PHASES = ("controls", "production")
ARM_STATUS = "EXACT_ARM_PASS"
PHASE_STATUS = {key: "COMPACT_" + key.upper() + "_EXACT_PASS" for key in PHASES}
q = None

def digest(raw):
    return hashlib.sha256(raw).hexdigest()

def bounded_input(path, cap):
    path = Path(path)
    if not path.is_file() or path.is_symlink() or path.stat().st_size > cap:
        raise RuntimeError("support input missing, indirect or oversized")
    with path.open("rb") as stream:
        raw = stream.read(cap + 1)
    if len(raw) > cap:
        raise RuntimeError("support input grew beyond cap")
    return raw

def support(args):
    global q
    raw = bounded_input(args.qualified_controller, 128 * 1024)
    foundation_raw = bounded_input(args.qualified_manifest, 256 * 1024)
    if len(raw) > 128 * 1024 or len(foundation_raw) > 256 * 1024 or digest(raw) != QUALIFIER_SHA or digest(foundation_raw) != FOUNDATION_SHA:
        raise RuntimeError("qualified support identity mismatch")
    spec = importlib.util.spec_from_file_location("qualified_current_graph", args.qualified_controller)
    q = importlib.util.module_from_spec(spec)
    # Reviewed imports/constants/definitions and __main__ guard only; no old orchestration.
    exec(compile(raw, str(args.qualified_controller), "exec"), q.__dict__)
    h, recipe = q.support(args)
    foundation = q.strict(foundation_raw)
    q.validate_manifest(h, foundation)
    if foundation["plans"]["production"]["tree"] != FOUNDATION_TREE:
        raise h.GateRejected("wrong qualified foundation")
    return h, recipe, foundation

def guard(h, ctx):
    if (os.environ.get("GITHUB_ACTIONS") != "true" or os.environ.get("GITHUB_EVENT_NAME") != "push" or
            os.environ.get("GITHUB_REF") != "refs/heads/" + BRANCH or ctx["repository"] != REPOSITORY or
            ctx["workflow_ref"] != REPOSITORY + "/" + WORKFLOW + "@refs/heads/" + BRANCH or
            not re.fullmatch(r"[0-9a-f]{40}", ctx["head"] or "") or
            not all(re.fullmatch(r"[1-9][0-9]*", ctx[key] or "") for key in ("run_id", "run_attempt"))):
        raise h.GateRejected("exact scoped compact push required")

def selected(manifest, arm):
    return manifest["cases"][:5] if arm == "baseline" else manifest["cases"]

def validate(h, manifest, foundation):
    if (manifest["schema"] != 1 or manifest["repository"] != REPOSITORY or manifest["branch"] != BRANCH or
            manifest["workflow"] != WORKFLOW or manifest["controller_sha256"] != h.file_sha(__file__) or
            manifest["foundation_manifest_sha256"] != FOUNDATION_SHA or
            manifest["foundation_tree"] != FOUNDATION_TREE or set(manifest["plans"]) != {"baseline", "candidate", "production"} or
            set(manifest["recipes"]) != set(manifest["plans"])):
        raise h.GateRejected("compact package identity mismatch")
    cases = manifest["cases"]
    if (len(cases) != 8 or len({x["name"] for x in cases}) != 8 or
            [x["library"] for x in cases] != ["core"] * 5 + ["contracts"] * 3 or
            sum("baseline_red" in x for x in cases) != 1 or "baseline_red" not in cases[0]):
        raise h.GateRejected("exact five/eight compact control inventory mismatch")
    for key in ("required_full", "required_core", "required_contracts"):
        names = manifest[key]
        if not isinstance(names, list) or not names or len(names) != len(set(names)):
            raise h.GateRejected("missing or duplicated compact target requirements")
    if (not set(foundation["production_required_full"]).issubset(manifest["required_full"]) or
            not set(foundation["canonical_core_required"]).issubset(manifest["required_core"]) or
            not set(manifest["required_core"] + manifest["required_contracts"]).issubset(manifest["required_full"])):
        raise h.GateRejected("qualified boundary coverage removed")
    if not set(manifest["plans"]["baseline"]["changed_blobs"]).issubset(manifest["plans"]["candidate"]["changed_blobs"]):
        raise h.GateRejected("control transition would leave obsolete source files")

def plans(h, runner, root, env, publication, manifest, foundation):
    flat = h.parse_tree(runner.ok("source-original-tree", ["git", "ls-tree", "-r", "-z", "--full-tree", "HEAD"],
                                 root, env, 30, 2 * 1024 * 1024))
    if h.complete_tree(flat) != foundation["core"]["tree"]:
        raise h.GateRejected("upstream tree mismatch")
    originals = {}
    expected = dict(foundation["preimages"])
    expected.update(manifest["raw_preimages"])
    for path, sha in expected.items():
        if flat.get(path, {}).get("sha") != sha:
            raise h.GateRejected("raw preimage mismatch: " + path)
        raw = None if sha is None else h.source_bytes(root, path)
        if raw is not None and h.git_blob(raw) != sha:
            raise h.GateRejected("raw source bytes mismatch")
        originals[path] = None if raw is None else raw.decode()
    prior_patches = {x["id"]: q.verify_file(h, publication, x) for x in foundation["patches"]}
    shared = dict(originals)
    for key in foundation["recipes"]["production"]:
        h.apply_exact(shared, prior_patches[key], [])
    shared_flat = h.flat_with_files(flat, shared)
    if h.complete_tree(shared_flat) != FOUNDATION_TREE:
        raise h.GateRejected("qualified production recipe did not reconstruct")
    for path, sha in manifest["foundation_preimages"].items():
        value = shared.get(path)
        if (None if value is None else h.git_blob(value.encode())) != sha:
            raise h.GateRejected("compact foundation preimage mismatch: " + path)
    patches = {x["id"]: q.verify_file(h, publication, x) for x in manifest["patches"]}
    result = {}
    for arm, order in manifest["recipes"].items():
        files = dict(shared)
        for key in order:
            h.apply_exact(files, patches[key], [])
        current = h.flat_with_files(flat, files)
        identity = {"tree": h.complete_tree(current), "changed_blobs": {
            path: item["sha"] for path, item in current.items() if item["sha"] != flat.get(path, {}).get("sha")}}
        if identity != manifest["plans"][arm]:
            raise h.GateRejected("complete compact source plan mismatch: " + arm)
        result[arm] = ({path: files[path].encode() for path in identity["changed_blobs"]}, identity)
    return result

def compile_arguments(key):
    return ["cargo", "test", "--locked", "-p", "proteus-" + key, "--lib", "--no-run", "--message-format=json"]

def compiled(h, output, key, root, target):
    if key != "contracts":
        return q.compiled(h, output, key, root, target)
    found = []
    source = "crates/proteus-contracts/src/lib.rs"
    for line in output.splitlines():
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        item = value.get("target", {})
        if value.get("reason") != "compiler-artifact" or not value.get("executable") or item.get("name") != "proteus_contracts" or item.get("kind") != ["lib"]:
            continue
        executable = Path(value["executable"]).resolve()
        if (Path(item.get("src_path", "")).resolve() != root / source or value.get("features") != [] or
                not value.get("profile", {}).get("test") or not executable.is_relative_to(target)):
            raise h.GateRejected("contracts default-feature/source binary mismatch")
        q.package_identity(h, value.get("package_id"), root, source, "proteus-contracts")
        found.append(str(executable))
    if len(found) != 1:
        raise h.GateRejected("missing or ambiguous contracts library")
    return found[0]

def classify(h, observed, case, arm):
    if arm != "baseline" or "baseline_red" not in case:
        return h.classify(observed, case["name"])
    red = case["baseline_red"]
    h.classify(observed, case["name"], red["marker"], "contains")
    failure = observed["output"].split("---- " + case["name"] + " stdout ----\n", 1)[1].split("\nfailures:\n", 1)[0]
    location = re.escape(red["source_suffix"]) + ":" + str(red["line"]) + ":" + str(red["column"]) + ":"
    if failure.count("panicked at") != 1 or len(re.findall(r"panicked at [^\n]*" + location + r"$", failure, re.M)) != 1:
        raise h.GateRejected("compact red failed at the wrong assertion")
    match = re.findall(re.escape(red["marker"]) +
        r" small=Allocations \{ bytes: ([0-9]+), calls: ([0-9]+) \}, large=Allocations \{ bytes: ([0-9]+), calls: ([0-9]+) \}", failure)
    if len(match) != 1:
        raise h.GateRejected("compact red lacks exact allocation diagnostics")
    small, small_calls, large, large_calls = map(int, match[0])
    if large <= small + 16384 or not small_calls or not large_calls:
        raise h.GateRejected("compact red does not prove the asserted allocation bound")
    return "EXPECTED_BEHAVIORAL_RED"

def controls(h, runner, root, target, env, manifest, arm, receipt):
    cases = selected(manifest, arm)
    receipt.update(cases=[], binaries={})
    for key in ("core",) if arm == "baseline" else ("core", "contracts"):
        output = runner.ok(arm + "-" + key + "-compile", compile_arguments(key), root, env, 1800, 24 * 1024 * 1024)
        binary = compiled(h, output, key, root, target)
        names = [x["name"] for x in cases if x["library"] == key]
        inventory = runner.ok(arm + "-" + key + "-inventory", [binary, "--list", "--format", "terse"], root, env, 30, 512 * 1024)
        ignored = runner.ok(arm + "-" + key + "-ignored", [binary, "--list", "--ignored", "--format", "terse"], root, env, 30, 128 * 1024)
        q.require_inventory(h, inventory, ignored, names)
        receipt["binaries"][key] = {"executable": binary, "sha256_before": h.file_sha(binary)}
    for index, case in enumerate(cases):
        label = arm + f"-case-{index:02}"
        binary = receipt["binaries"][case["library"]]["executable"]
        observed = runner.run(label, [binary, "--exact", case["name"], "--test-threads=1"], root, env, 180, 1024 * 1024)
        receipt["cases"].append({"name": case["name"], "stage": label, "verdict": classify(h, observed, case, arm)})
    for item in receipt["binaries"].values():
        item["sha256_after"] = h.file_sha(item["executable"])
        if item["sha256_before"] != item["sha256_after"]:
            raise h.GateRejected("control binary changed before source transition")
    receipt["status"] = ARM_STATUS

def fixture(h, runner, work, root, env, foundation):
    # False selects only the reviewed fresh-reference path, never stock Modules tests.
    lane_env, receipt, state = q.fixture_setup(h, runner, work, root, env, foundation, False)
    dcp = state[0] / "hook/dcp"
    fixture_env = dict(env, PROTEUS_MODULES_SOURCE=str(state[0]), CARGO_TARGET_DIR=str(work / "fixture-target"))
    runner.ok("dcp-fixture-install", ["npm", "ci", "--ignore-scripts", "--no-audit", "--no-fund"],
              dcp, fixture_env, 300, 4 * 1024 * 1024)
    runner.ok("dcp-fixture-build", ["npm", "--no-audit", "--no-fund", "run", "build"],
              dcp, fixture_env, 300, 4 * 1024 * 1024)
    for key, name in (("dcp", "worker.js"), ("dcp_module", "module.js")):
        path = dcp / "dist" / name
        receipt[key] = {"path": str(path), "sha256_before": h.file_sha(path, 8 * 1024 * 1024)}
    receipt["dcp_closure_before"] = q.fixture_closure(h, dcp, foundation)
    lane_env["PROTEUS_TEST_DCP_MODULE"] = receipt["dcp"]["path"]
    return lane_env, receipt, state

def fixture_audit(h, output, records, receipt, foundation, source, work):
    item = receipt["fixture"]
    projection = dict(receipt, fixture={key: value for key, value in item.items()
        if key not in {"dcp", "dcp_module", "dcp_closure_before", "dcp_closure_after"}})
    # Reference-only projection is audited by the immutable helper; DCP is checked below.
    q.audit_fixture(h, output, records, projection, foundation, source, work, False)
    dcp = Path(item["source_root"]) / "hook/dcp"
    for label, argv in (("dcp-fixture-install", ["npm", "ci", "--ignore-scripts", "--no-audit", "--no-fund"]),
                        ("dcp-fixture-build", ["npm", "--no-audit", "--no-fund", "run", "build"])):
        output(label, argv, dcp)
    for key, name in (("dcp", "worker.js"), ("dcp_module", "module.js")):
        binary = item[key]
        if (binary["path"] != str(dcp / "dist" / name) or binary.get("sha256_before") != binary.get("sha256_after") or
                not re.fullmatch(r"[0-9a-f]{64}", binary.get("sha256_after", ""))):
            raise h.GateRejected("unchanged canonical DCP binary provenance mismatch")
    closure = item["dcp_closure_before"]
    if not q.same_json_evidence(closure, item["dcp_closure_after"]):
        raise h.GateRejected("installed canonical fixture closure changed")
    entries = closure["files"]
    paths = [entry["path"] for entry in entries]
    allowed = foundation["fixture"]["dcp_dependency"]["closure"]
    if (not 1 <= len(entries) <= 5000 or paths != sorted(set(paths)) or
            any(not any(path.startswith(prefix + "/") for prefix in allowed) or ".." in Path(path).parts for path in paths) or
            any(prefix + "/package.json" not in paths for prefix in allowed) or
            any(type(entry.get("bytes")) is not int or not 0 <= entry["bytes"] <= 32 * 1024 * 1024 or
                not re.fullmatch(r"[0-9a-f]{64}", entry.get("sha256", "")) for entry in entries) or
            type(closure.get("bytes")) is not int or closure["bytes"] != sum(entry["bytes"] for entry in entries) or
            closure["bytes"] > 128 * 1024 * 1024 or
            closure["sha256"] != digest(json.dumps(entries, sort_keys=True, separators=(",", ":")).encode())):
        raise h.GateRejected("bounded canonical fixture closure receipt malformed")

def boundaries(h, output, manifest, foundation, bindings):
    inherited = dict(foundation, canonical_core_required=manifest["required_core"])
    result = q.canonical_boundary(h, output, inherited, bindings)
    result["contracts"] = h.require_passes(q.sections(h, output, bindings)["contracts"], manifest["required_contracts"])
    return result

def canonical_bindings(h, output, root, target, foundation):
    custom = h.canonical_targets(output, root, target, foundation["canonical_harness"])
    bindings = {key: {"executable": compiled(h, output, key, root, target), "cargo_label": "unittests src/lib.rs"}
                for key in ("core", "protocol", "contracts")}
    for key, name, source, package in (
        ("hook_runtime", "hook_runtime", "crates/proteus-core/tests/hook_runtime.rs", "proteus-core"),
        ("module_swap", "module_swap", "crates/proteus-core/tests/module_swap.rs", "proteus-core"),
        ("model_process", "model_process", "crates/proteus-core/tests/model_process.rs", "proteus-core"),
        ("protocol_integration", foundation["protocol_integration"]["name"], foundation["protocol_integration"]["source"], "proteus-module-protocol"),
    ):
        bindings[key] = q.default_integration(h, output, root, target, name, source, package)
    return custom, bindings

def run_phase(h, recipe, foundation, manifest, manifest_hash, args):
    ctx = q.context()
    guard(h, ctx)
    work = Path(args.work).resolve()
    work.mkdir(parents=True, exist_ok=False)
    runner = h.Runner(Path(args.evidence).resolve(), work, 6600)
    env = h.clean_env(work)
    receipt = {"schema": 1, "phase": args.phase, "status": "INCOMPLETE", "context": ctx,
        "controller_sha256": h.file_sha(__file__), "manifest_sha256": manifest_hash,
        "qualified_controller_sha256": QUALIFIER_SHA, "foundation_manifest_sha256": FOUNDATION_SHA,
        "support_sha256": q.HELPER_SHA256, "recipe_sha256": q.RECIPE_SHA256,
        "core": foundation["core"], "fixture_pin": foundation["fixture"], "plans": manifest["plans"],
        "resource_policy": manifest["resources"], "source_root": str(work / "source"),
        "target_root": str(work / "target"), "stages": runner.records, "arms": {},
        "environment_policy": {"allowlisted": sorted(env), "npm_audit": False, "secrets_inherited": False,
                               "rust_test_threads": env["RUST_TEST_THREADS"]}}
    try:
        receipt["initial_free_bytes"] = shutil.disk_usage(work).free
        if receipt["initial_free_bytes"] < h.INITIAL_FREE_BYTES:
            raise h.InfrastructureError("hosted admission requires 8 GiB free")
        publication = Path(os.environ["GITHUB_WORKSPACE"]).resolve()
        if runner.ok("publication-head", ["git", "rev-parse", "HEAD"], publication, env, 10).strip() != ctx["head"]:
            raise h.GateRejected("publication head mismatch")
        previous = work / "publication-base"
        h.checkout(runner, "publication-base", previous, "https://github.com/" + REPOSITORY + ".git",
                   manifest["publication_base"], env)
        old = h.parse_tree(runner.ok("publication-base-tree", ["git", "ls-tree", "-r", "-z", "--full-tree", "HEAD"],
                                    previous, env, 30, 2 * 1024 * 1024))
        new = h.parse_tree(runner.ok("publication-tree", ["git", "ls-tree", "-r", "-z", "--full-tree", "HEAD"],
                                    publication, env, 30, 2 * 1024 * 1024))
        if (h.complete_tree(old) != manifest["publication_base_tree"] or
                set(new) != set(old) | set(manifest["publication_files"]) or
                any(new.get(path) != value for path, value in old.items())):
            raise h.GateRejected("publication escaped additive compact package scope")
        receipt["publication_tree"] = h.complete_tree(new)
        for item in manifest["documents"]:
            q.verify_file(h, publication, item)
        receipt["tools"] = {}
        versions = [("rustc", ["rustc", "-Vv"]), ("cargo", ["cargo", "-V"])]
        if args.phase == "production":
            versions += [("node", ["node", "--version"]), ("bubblewrap", ["/usr/bin/bwrap", "--version"])]
        for label, argv in versions:
            receipt["tools"][label] = runner.ok("version-" + label, argv, work, env, 30).strip()
        if not receipt["tools"]["rustc"].startswith("rustc 1.95.0 ") or not receipt["tools"]["cargo"].startswith("cargo 1.95.0 "):
            raise h.GateRejected("wrong official Rust toolchain")
        if args.phase == "production":
            if receipt["tools"]["node"] != "v22.18.0" or receipt["tools"]["bubblewrap"] != "bubblewrap 0.13.1":
                raise h.GateRejected("wrong canonical dependency tool versions")
            backend = Path("/usr/bin/bwrap")
            info = backend.stat()
            if (backend.is_symlink() or (stat.S_IMODE(info.st_mode), info.st_uid, info.st_gid) != (0o755, 0, 0) or
                    runner.ok("sandbox-capabilities", ["getcap", backend], work, env, 10).strip()):
                raise h.GateRejected("sandbox backend capability/mode mismatch")
            receipt["sandbox_binary_sha256"] = h.file_sha(backend, 16 * 1024 * 1024)
            log = runner.ok("sandbox-evidence", ["cat", work.parent / "core-current-bwrap-evidence.txt"], work, env, 10, 65536)
            q.sandbox_evidence(h, log, receipt["sandbox_binary_sha256"])
            receipt["sandbox_receipt_sha256"] = digest(log.encode())
        root, target = work / "source", work / "target"
        h.checkout(runner, "source", root, foundation["core"]["repository"], foundation["core"]["commit"], env)
        prepared = plans(h, runner, root, env, publication, manifest, foundation)
        receipt["all_plans_preflight"] = "PASS_BEFORE_ANY_SOURCE_REPLACEMENT"
        lane_env = dict(env, CARGO_TARGET_DIR=str(target))
        arms = ("baseline", "candidate") if args.phase == "controls" else ("production",)
        for arm in arms:
            changed, plan = prepared[arm]
            h.materialize(runner, arm, root, changed, plan["tree"], env)
            runner.ok(arm + "-format", ["cargo", "fmt", "--all", "--", "--check"], root, env, 180, 2 * 1024 * 1024)
            before = h.tracked_snapshot(runner, arm + "-source-before", root, env)
            current = {"tree": plan["tree"], "source_snapshot_before_sha256":
                digest(json.dumps(before, sort_keys=True, separators=(",", ":")).encode())}
            receipt["arms"][arm] = current
            if arm != "production":
                controls(h, runner, root, target, lane_env, manifest, arm, current)
            else:
                lane_env, receipt["fixture"], state = fixture(h, runner, work, root, env, foundation)
                output = runner.ok("canonical-compile", [sys.executable, *foundation["canonical_harness"]["compile_arguments"]],
                                   root, lane_env, 1800, 24 * 1024 * 1024)
                custom, bindings = canonical_bindings(h, output, root, target, foundation)
                binaries = {**{k: v["executable"] for k, v in custom.items()}, **{k: v["executable"] for k, v in bindings.items()}}
                current.update(canonical_binaries=custom, boundary_binaries=bindings,
                               binary_sha256_before={k: h.file_sha(p) for k, p in binaries.items()})
                output = runner.ok("canonical-full", [sys.executable, "scripts/test.py", "full"],
                                   root, lane_env, 1800, 40 * 1024 * 1024)
                current["canonical_full"] = h.require_canonical_passes(output, manifest["required_full"],
                    foundation["canonical_harness"], custom, foundation["allowed_ignored"])
                if set(current["canonical_full"]["ignored"]) != set(foundation["allowed_ignored"]):
                    raise h.GateRejected("canonical ignore set changed")
                current["boundaries"] = boundaries(h, output, manifest, foundation, bindings)
                current["binary_sha256_after"] = {k: h.file_sha(p) for k, p in binaries.items()}
                if current["binary_sha256_before"] != current["binary_sha256_after"]:
                    raise h.GateRejected("canonical executable changed")
                current["status"] = ARM_STATUS
                q.fixture_postflight(h, runner, state, receipt["fixture"], env, foundation)
            current["source_snapshot_after_sha256"] = q.postflight(h, runner, arm, root, env, before, plan["tree"])
        receipt["status"] = PHASE_STATUS[args.phase]
    except BaseException as error:
        receipt["status"] = "INFRASTRUCTURE_ERROR" if h.is_infrastructure(error) else "GATE_REJECTED"
        receipt["error"] = f"{type(error).__name__}: {error}"
        raise
    finally:
        q.write_receipt(Path(args.evidence) / "result.json", receipt)

def phase_identity(h, receipt, phase, manifest, manifest_hash, foundation, ctx):
    expected = {"schema": 1, "phase": phase, "context": ctx,
        "controller_sha256": manifest["controller_sha256"], "manifest_sha256": manifest_hash,
        "qualified_controller_sha256": QUALIFIER_SHA, "foundation_manifest_sha256": FOUNDATION_SHA,
        "support_sha256": q.HELPER_SHA256, "recipe_sha256": q.RECIPE_SHA256,
        "core": foundation["core"], "fixture_pin": foundation["fixture"], "plans": manifest["plans"],
        "resource_policy": manifest["resources"]}
    if any(not q.same_json_evidence(receipt.get(key), value) for key, value in expected.items()):
        raise h.GateRejected("foreign compact phase receipt identity")
    return receipt.get("status")

def aggregate(h, foundation, manifest, manifest_hash, args):
    ctx = q.context()
    guard(h, ctx)
    publication = Path(os.environ["GITHUB_WORKSPACE"]).resolve()
    runner = h.Runner(Path(args.evidence).resolve(), publication, 120)
    env = {k: v for k, v in os.environ.items() if k in {"PATH", "LANG", "LC_ALL", "TMPDIR", "TMP", "TEMP"}}
    env.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL="/dev/null", GIT_TERMINAL_PROMPT="0")
    result = {"schema": 1, "status": "INCOMPLETE", "context": ctx,
              "manifest_sha256": manifest_hash, "phases": {}, "stages": runner.records}
    try:
        if runner.ok("aggregate-head", ["git", "rev-parse", "HEAD"], publication, env, 10).strip() != ctx["head"]:
            raise h.GateRejected("aggregate checkout differs from current head")
        flat = h.parse_tree(runner.ok("aggregate-publication-tree", ["git", "ls-tree", "-r", "-z", "--full-tree", "HEAD"],
                                     publication, env, 30, 2 * 1024 * 1024))
        runner.ok("aggregate-clean-checkout", ["git", "diff", "--quiet", "HEAD"], publication, env, 10)
        result["publication_tree"] = tree = h.complete_tree(flat)
        available, missing, infrastructure, rejected = {}, [], [], []
        for phase in PHASES:
            path = Path(args.aggregate).resolve() / phase / "result.json"
            if not path.exists():
                missing.append(phase)
                continue
            raw = q.bounded(path, 4 * 1024 * 1024)
            receipt = q.strict(raw)
            status = phase_identity(h, receipt, phase, manifest, manifest_hash, foundation, ctx)
            available[phase] = (raw, receipt)
            if status == "INFRASTRUCTURE_ERROR":
                infrastructure.append(phase + ": " + str(receipt.get("error", "")))
            elif status != PHASE_STATUS[phase]:
                rejected.append(phase + ": " + str(status))
        if infrastructure:
            raise h.InfrastructureError("exact current-run infrastructure failure: " + "; ".join(infrastructure))
        if rejected:
            raise h.GateRejected("exact current-run phase not qualified: " + "; ".join(rejected))
        if missing:
            raise h.InfrastructureError("required current-run evidence unavailable: " + ", ".join(missing))
        for phase in PHASES:
            raw, receipt = available[phase]
            if (receipt.get("publication_tree") != tree or receipt.get("all_plans_preflight") != "PASS_BEFORE_ANY_SOURCE_REPLACEMENT" or
                    type(receipt.get("initial_free_bytes")) is not int or receipt["initial_free_bytes"] < h.INITIAL_FREE_BYTES):
                raise h.GateRejected("successful phase lacks publication/preflight/admission evidence")
            paths, records = h.phase_logs(Path(args.aggregate).resolve() / phase, receipt)
            source, target = Path(receipt["source_root"]), Path(receipt["target_root"])
            work = source.parent
            if not source.is_absolute() or source.name != "source" or work.name != "core-compact-work" or target != work / "target":
                raise h.GateRejected("compact source/target isolation mismatch")
            def output(label, argv=None, cwd=None):
                if label not in records:
                    raise h.GateRejected("required stage missing: " + label)
                record = records[label]
                if argv is not None and (record["argv"] != [str(x) for x in argv] or record["cwd"] != str(cwd or source)):
                    raise h.GateRejected("required command/source binding mismatch: " + label)
                return {"code": record["exit_code"], "output": h.bounded_file(paths[label], h.MAX_TOTAL_OUTPUT).decode("utf-8", "replace")}
            for label, argv, expected in (("rustc", ["rustc", "-Vv"], "rustc 1.95.0 "),
                                          ("cargo", ["cargo", "-V"], "cargo 1.95.0 ")):
                value = output("version-" + label, argv, work)["output"].strip()
                if not value.startswith(expected) or receipt["tools"].get(label) != value:
                    raise h.GateRejected("tool version raw evidence mismatch")
            if phase == "production":
                for label, argv, expected in (("node", ["node", "--version"], "v22.18.0"),
                                              ("bubblewrap", ["/usr/bin/bwrap", "--version"], "bubblewrap 0.13.1")):
                    value = output("version-" + label, argv, work)["output"].strip()
                    if value != expected or receipt["tools"].get(label) != value:
                        raise h.GateRejected("canonical prerequisite version mismatch")
                if output("sandbox-capabilities", ["getcap", "/usr/bin/bwrap"], work)["output"].strip():
                    raise h.GateRejected("sandbox file capabilities changed")
                log = output("sandbox-evidence", ["cat", work.parent / "core-current-bwrap-evidence.txt"], work)["output"]
                q.sandbox_evidence(h, log, receipt["sandbox_binary_sha256"])
                if digest(log.encode()) != receipt["sandbox_receipt_sha256"]:
                    raise h.GateRejected("sandbox prerequisite receipt mismatch")
            arms = ("baseline", "candidate") if phase == "controls" else ("production",)
            if set(receipt["arms"]) != set(arms):
                raise h.GateRejected("selected compact arm inventory mismatch")
            permitted_reds = set()
            for arm in arms:
                item = receipt["arms"][arm]
                if item.get("tree") != manifest["plans"][arm]["tree"] or item.get("status") != ARM_STATUS:
                    raise h.GateRejected("compact source arm incomplete")
                output(arm + "-format", ["cargo", "fmt", "--all", "--", "--check"])
                if (output(arm + "-final-tree", ["git", "write-tree"])["output"].strip() != item["tree"] or
                        output(arm + "-no-unstaged", ["git", "diff", "--quiet"])["output"].strip() or
                        output(arm + "-no-untracked", ["git", "ls-files", "--others", "--exclude-standard"])["output"].strip() or
                        item.get("source_snapshot_before_sha256") != item.get("source_snapshot_after_sha256") or
                        not re.fullmatch(r"[0-9a-f]{64}", item.get("source_snapshot_after_sha256", ""))):
                    raise h.GateRejected("compact source/index postflight mismatch")
                if arm == "production":
                    compile_log = output("canonical-compile", [sys.executable, *foundation["canonical_harness"]["compile_arguments"]])["output"]
                    custom, bindings = canonical_bindings(h, compile_log, source, target, foundation)
                    hashes = item["binary_sha256_before"]
                    if (custom != item["canonical_binaries"] or bindings != item["boundary_binaries"] or
                            hashes != item["binary_sha256_after"] or set(hashes) != set(custom) | set(bindings) or
                            any(not re.fullmatch(r"[0-9a-f]{64}", value) for value in hashes.values())):
                        raise h.GateRejected("canonical compiler/default-feature/binary provenance mismatch")
                    log = output("canonical-full", [sys.executable, "scripts/test.py", "full"])["output"]
                    parsed = h.require_canonical_passes(log, manifest["required_full"], foundation["canonical_harness"],
                                                        custom, foundation["allowed_ignored"])
                    if (not q.same_json_evidence(parsed, item["canonical_full"]) or
                            set(parsed["ignored"]) != set(foundation["allowed_ignored"]) or
                            not q.same_json_evidence(boundaries(h, log, manifest, foundation, bindings), item["boundaries"])):
                        raise h.GateRejected("canonical target-bound raw evidence mismatch")
                else:
                    cases = selected(manifest, arm)
                    keys = ("core",) if arm == "baseline" else ("core", "contracts")
                    if set(item["binaries"]) != set(keys):
                        raise h.GateRejected("control library inventory mismatch")
                    binaries = {}
                    for key in keys:
                        binary = compiled(h, output(arm + "-" + key + "-compile", compile_arguments(key))["output"], key, source, target)
                        stored = item["binaries"][key]
                        if (stored["executable"] != binary or stored["sha256_before"] != stored["sha256_after"] or
                                not re.fullmatch(r"[0-9a-f]{64}", stored["sha256_after"])):
                            raise h.GateRejected("control binary pre/post identity mismatch")
                        binaries[key] = binary
                        q.require_inventory(h, output(arm + "-" + key + "-inventory", [binary, "--list", "--format", "terse"])["output"],
                            output(arm + "-" + key + "-ignored", [binary, "--list", "--ignored", "--format", "terse"])["output"],
                            [case["name"] for case in cases if case["library"] == key])
                    outcomes = []
                    for index, case in enumerate(cases):
                        label = arm + f"-case-{index:02}"
                        observed = output(label, [binaries[case["library"]], "--exact", case["name"], "--test-threads=1"])
                        verdict = classify(h, observed, case, arm)
                        outcomes.append({"name": case["name"], "stage": label, "verdict": verdict})
                        if verdict == "EXPECTED_BEHAVIORAL_RED":
                            permitted_reds.add(label)
                    if outcomes != item["cases"] or sum(x["verdict"] == "EXPECTED_BEHAVIORAL_RED" for x in outcomes) != (1 if arm == "baseline" else 0):
                        raise h.GateRejected("control outcomes differ from raw classification")
            if phase == "production":
                fixture_audit(h, output, records, receipt, foundation, source, work)
            elif "fixture" in receipt:
                raise h.GateRejected("controls unexpectedly used a process fixture")
            if {label for label, record in records.items() if record["exit_code"] == 101} != permitted_reds:
                raise h.GateRejected("unexpected failure cannot count as a mechanism negative")
            result["phases"][phase] = {"receipt_sha256": digest(raw), "status": receipt["status"],
                "stages": len(records), "minimum_free_bytes": min(record["disk_free_minimum_bytes"] for record in records.values())}
        if os.environ.get("QUALIFY_JOB_RESULT") != "success":
            raise h.InfrastructureError("current compact source jobs did not all succeed")
        result["status"] = "COMPACT_EXACT_CORRECTNESS_PASS"
        result["counting"] = "Five baseline controls (four green, one intended red), eight candidate controls, one pure canonical full. No release speed/RAM claim."
    except BaseException as error:
        result["status"] = "INFRASTRUCTURE_ERROR" if h.is_infrastructure(error) else "GATE_REJECTED"
        result["error"] = f"{type(error).__name__}: {error}"
        raise
    finally:
        q.write_receipt(Path(args.evidence) / "result.json", result)


def self_test(h, recipe, foundation, manifest):
    # Immutable helper self-controls run only in hosted CI, never product tests.
    q.self_test(h, recipe, foundation)
    validate(h, manifest, foundation)
    assert len(selected(manifest, "baseline")) == 5 and len(selected(manifest, "candidate")) == 8
    def rejected(call):
        try:
            call()
        except (h.GateRejected, h.InfrastructureError):
            return
        raise h.GateRejected("negative compact self-control accepted")
    case = manifest["cases"][0]
    name, red = case["name"], case["baseline_red"]
    failure = ("running 1 test\n" + f"test {name} ... FAILED\n\nfailures:\n\n---- {name} stdout ----\n" +
        f"thread '{name}' panicked at {red['source_suffix']}:{red['line']}:{red['column']}:\n" +
        red["marker"] + " small=Allocations { bytes: 1024, calls: 4 }, large=Allocations { bytes: 4194304, calls: 8 }\n" +
        f"\nfailures:\n    {name}\n\ntest result: FAILED. 0 passed; 1 failed; 0 ignored; 0 measured; 0 filtered out; finished in 0.00s\n")
    assert classify(h, {"code": 101, "output": failure}, case, "baseline") == "EXPECTED_BEHAVIORAL_RED"
    for observed in (
        {"code": 0, "output": failure},
        {"code": 101, "output": failure.replace("4194304", "1024")},
        {"code": 101, "output": failure.replace(red["marker"], "immediate startup")},
        {"code": 101, "output": failure.replace(str(red["line"]) + ":", "999999:")},
        {"code": 101, "output": failure.replace("calls: 8", "calls: 0")},
        {"code": 101, "output": failure + f"test {name} ... FAILED\n"},
        {"code": 101, "output": failure.replace(red["marker"], "panicked at elsewhere:1:1:\\n" + red["marker"])},
        {"code": 101, "output": "compiler failed\n"},
        {"code": 124, "output": failure},
    ):
        rejected(lambda observed=observed: classify(h, observed, case, "baseline"))
    rejected(lambda: classify(h, {"code": 101, "output": failure}, case, "candidate"))
    for case in manifest["cases"]:
        log = ("running 1 test\n" + f"test {case['name']} ... ok\n\n" +
               "test result: ok. 1 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 0.00s\n")
        assert classify(h, {"code": 0, "output": log}, case, "candidate") == "PASS"
    ctx = {"head": "a" * 40, "repository": REPOSITORY, "workflow_ref": "test", "run_id": "1", "run_attempt": "1"}
    base = {"schema": 1, "phase": "controls", "context": ctx,
        "controller_sha256": manifest["controller_sha256"], "manifest_sha256": "m",
        "qualified_controller_sha256": QUALIFIER_SHA, "foundation_manifest_sha256": FOUNDATION_SHA,
        "support_sha256": q.HELPER_SHA256, "recipe_sha256": q.RECIPE_SHA256,
        "core": foundation["core"], "fixture_pin": foundation["fixture"], "plans": manifest["plans"],
        "resource_policy": manifest["resources"], "status": "INFRASTRUCTURE_ERROR"}
    assert phase_identity(h, base, "controls", manifest, "m", foundation, ctx) == "INFRASTRUCTURE_ERROR"
    for key in ("head", "run_id", "run_attempt", "repository", "workflow_ref"):
        rejected(lambda key=key: phase_identity(h, dict(base, context=dict(ctx, **{key: "foreign"})),
                 "controls", manifest, "m", foundation, ctx))
    def synthetic(names, ignored=()):
        return (f"running {len(names) + len(ignored)} tests\n" +
                "".join(f"test {name} ... ok\n" for name in names) +
                "".join(f"test {name} ... ignored\n" for name in ignored) +
                f"test result: ok. {len(names)} passed; 0 failed; {len(ignored)} ignored; 0 measured; 0 filtered out; finished in 0.00s\n")
    names = {"core": manifest["required_core"], "contracts": manifest["required_contracts"],
        "protocol": [x for x in foundation["protocol_required"] if x.startswith("v3::")],
        "protocol_integration": [x for x in foundation["protocol_required"] if not x.startswith("v3::")],
        "module_swap": foundation["module_swap_required"], "hook_runtime": foundation["hook_required"],
        "model_process": foundation["model_process_required"]}
    bindings = {key: {"executable": "/target/" + key, "cargo_label": "tests/" + key + ".rs"} for key in names}
    log = "".join("     Running " + bindings[key]["cargo_label"] + " (" + bindings[key]["executable"] + ")\n" +
        synthetic(values, [x for x in foundation["allowed_ignored"] if x.startswith("core::")] if key == "core" else ())
        for key, values in names.items())
    boundaries(h, log, manifest, foundation, bindings)
    for invalid in (log + log, log.replace("/target/contracts", "/foreign"),
                    log.replace(manifest["required_contracts"][0] + " ... ok", "foreign ... ok"),
                    log.replace(manifest["existing_boundary"]["core"][0] + " ... ok", "foreign ... ok")):
        rejected(lambda invalid=invalid: boundaries(h, invalid, manifest, foundation, bindings))
    print("Compact exact allocation assertion, eight controls, foreign identity and contracts/Core target-bound self-controls PASS")

def main():
    parser = argparse.ArgumentParser()
    for key in ("manifest", "helper", "recipe", "qualified-controller", "qualified-manifest"):
        parser.add_argument("--" + key, required=True)
    parser.add_argument("--phase", choices=PHASES)
    parser.add_argument("--work")
    parser.add_argument("--evidence")
    parser.add_argument("--aggregate")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if not __debug__:
        raise RuntimeError("assertions must remain enabled")
    h, recipe, foundation = support(args)
    raw = q.bounded(args.manifest, 256 * 1024)
    manifest = q.strict(raw)
    validate(h, manifest, foundation)
    if args.self_test:
        self_test(h, recipe, foundation, manifest)
    elif args.aggregate:
        if not args.evidence or args.phase or args.work:
            parser.error("aggregate requires only evidence and aggregate paths")
        aggregate(h, foundation, manifest, digest(raw), args)
    else:
        if not args.phase or not args.work or not args.evidence:
            parser.error("source phase/work/evidence required")
        run_phase(h, recipe, foundation, manifest, digest(raw), args)

if __name__ == "__main__":
    main()
