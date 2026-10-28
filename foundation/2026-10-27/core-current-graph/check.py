#!/usr/bin/env python3
"""Exact current-graph Core qualification; immutable PR35 parsing/process helpers only."""
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
BRANCH = "ci/core-current-graph-20261027"
WORKFLOW = ".github/workflows/core-current-graph.yml"
HELPER_SHA256 = "2f917a4ca4dc71a3dfa8cf2dc376991a7ddf1580cd347aaff8cb6ccc50568147"
RECIPE_SHA256 = "0a6b5a4aba9112abe866fa5131d7f0f58a771f3542ec891af51f96d9bd7dae82"
QUALIFIED_TREE = "7dec0c811a514adf32a70907635939547e0a57cf"  # Historical helper recipe only.
PHASES = ("baseline", "production", "focused")
STATUSES = {phase: "CURRENT_GRAPH_" + phase.upper() + "_EXACT_PASS" for phase in PHASES}
LIBRARIES = {
    "core": ("proteus-core", "proteus_core", "crates/proteus-core/src/lib.rs"),
    "protocol": ("proteus-module-protocol", "proteus_module_protocol", "crates/proteus-module-protocol/src/lib.rs"),
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

def verify_file(h, root, item):
    raw = h.source_bytes(root, item["path"])
    if (len(raw) != item["bytes"] or h.sha(raw) != item["sha256"] or
            h.git_blob(raw) != item["git_blob"]):
        raise h.GateRejected("authored input identity mismatch: " + item["path"])
    return raw.decode("utf-8")

def context():
    return {key: os.environ.get(name) for key, name in {
        "head": "GITHUB_SHA", "repository": "GITHUB_REPOSITORY",
        "workflow_ref": "GITHUB_WORKFLOW_REF", "run_id": "GITHUB_RUN_ID",
        "run_attempt": "GITHUB_RUN_ATTEMPT"}.items()}

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
            package_identity(h, value.get("package_id"), root, source, package)
            candidates.append(str(executable))
    if len(candidates) != 1:
        raise h.GateRejected("missing or ambiguous compiled library")
    return candidates[0]

def require_inventory(h, output, ignored_output, required):
    listed = h.listed_tests(output)
    ignored = h.listed_tests(ignored_output)
    if any(listed.count(name) != 1 for name in required) or set(required) & set(ignored):
        raise h.GateRejected("mandatory exact test missing, duplicate or ignored")

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

def same_json_evidence(parsed, recorded):
    """Compare complete JSON evidence without tuple/list or bool/int ambiguity."""
    options = {"sort_keys": True, "separators": (",", ":"), "allow_nan": False}
    return json.dumps(parsed, **options) == json.dumps(recorded, **options)

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



def package_identity(h, package_id, root, source, package):
    # Cargo package IDs for these local workspace crates have one canonical path URI.
    marker = "/tests/" if "/tests/" in source else "/src/"
    package_root = root / source.split(marker, 1)[0]
    prefix = "path+" + package_root.as_uri() + "#"
    if not isinstance(package_id, str) or not package_id.startswith(prefix):
        raise h.GateRejected("compiler package is not the selected local workspace crate")
    fragment = package_id[len(prefix):]
    if "@" in fragment:
        name, fragment = fragment.split("@", 1)
        if name != package:
            raise h.GateRejected("compiler package name mismatch")
    if not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+(?:[-+][A-Za-z0-9.+-]+)?", fragment):
        raise h.GateRejected("compiler package version identity is malformed")
    return package_id


def write_receipt(path, receipt):
    encoded = (json.dumps(receipt, indent=2, allow_nan=False) + "\n").encode()
    if len(encoded) > 4 * 1024 * 1024:
        raise RuntimeError("bounded result receipt exceeds 4 MiB")
    Path(path).write_bytes(encoded)



def guard(h, ctx):
    if (os.environ.get("GITHUB_ACTIONS") != "true" or os.environ.get("GITHUB_EVENT_NAME") != "push" or
            os.environ.get("GITHUB_REF") != "refs/heads/" + BRANCH or ctx["repository"] != REPOSITORY or
            ctx["workflow_ref"] != REPOSITORY + "/" + WORKFLOW + "@refs/heads/" + BRANCH or
            not re.fullmatch(r"[0-9a-f]{40}", ctx["head"] or "") or
            not all(re.fullmatch(r"[1-9][0-9]*", ctx[key] or "") for key in ("run_id", "run_attempt"))):
        raise h.GateRejected("exact guarded current-graph push required")


def arm_cases(h, manifest, arm):
    cases = manifest["cases"]
    by_name = {case["name"]: case for case in cases}
    selections = manifest["phase_cases"]
    if (len(by_name) != len(cases) or set(selections) != {"copy_baseline", "cache_baseline", "focused"} or
            arm not in selections or set(selections["focused"]) != set(by_name)):
        raise h.GateRejected("invalid complete current case inventory")
    for names in selections.values():
        if (not isinstance(names, list) or not names or len(names) != len(set(names)) or
                any(name not in by_name for name in names)):
            raise h.GateRejected("unknown, duplicate or empty arm selection")
    return [by_name[name] for name in selections[arm]]


def validate_manifest(h, manifest):
    if (manifest["schema"] != 1 or manifest["repository"] != REPOSITORY or
            manifest["branch"] != BRANCH or manifest["workflow"] != WORKFLOW or
            manifest["controller_sha256"] != h.file_sha(__file__) or
            set(manifest["plans"]) != set(manifest["recipes"]) or
            set(manifest["plans"]) != {"prerequisite", "production", "candidate_tests", "focused", "copy_baseline", "cache_baseline"}):
        raise h.GateRejected("current package identity mismatch")
    for arm, count, red in (("copy_baseline", 19, 5), ("cache_baseline", 9, 3), ("focused", 35, 0)):
        selected = arm_cases(h, manifest, arm)
        observed_red = 0 if arm == "focused" else sum(bool(case.get("baseline_red")) for case in selected)
        if len(selected) != count or observed_red != red or manifest["case_counts"][arm] != {
                "total": count, "red": red, "green": count - red}:
            raise h.GateRejected("actual arm counts disagree with exact selections")
    for key in ("production_required_full", "focused_core_required", "focused_protocol_required",
                "existing_cache_required", "upstream_required", "protocol_required", "module_swap_required", "model_process_required"):
        names = manifest[key]
        if not isinstance(names, list) or not names or len(names) != len(set(names)):
            raise h.GateRejected("empty or duplicated mandatory inventory: " + key)
    if (len(manifest["existing_cache_required"]) != 6 or len(manifest["upstream_required"]) < 4 or
            not set(manifest["existing_cache_required"] + manifest["upstream_required"]).issubset(manifest["focused_core_required"]) or
            not set(manifest["existing_cache_required"] + manifest["upstream_required"] +
                    manifest["protocol_required"] + manifest["module_swap_required"] + manifest["model_process_required"] +
                    [manifest["next_model"]["test"]]).issubset(manifest["production_required_full"])):
        raise h.GateRejected("current boundary witnesses missing")
    for key, required in (("core", manifest["focused_core_required"]), ("protocol", manifest["focused_protocol_required"])):
        if not {case["name"] for case in arm_cases(h, manifest, "focused") if case["library"] == key}.issubset(required):
            raise h.GateRejected("full focused library omits direct controls")
    if [item["id"] for item in manifest["modules_tests"]["targets"]] != ["codex_compaction", "codex_model_resume"]:
        raise h.GateRejected("stock Modules target scope changed")


def plan_all(h, runner, root, env, publication, manifest):
    flat = h.parse_tree(runner.ok("source-original-tree",
        ["git", "ls-tree", "-r", "-z", "--full-tree", "HEAD"], root, env, 30, 2 * 1024 * 1024))
    if h.complete_tree(flat) != manifest["core"]["tree"]:
        raise h.GateRejected("current upstream tree mismatch")
    originals = {}
    for path, expected in manifest["preimages"].items():
        if flat.get(path, {}).get("sha") != expected:
            raise h.GateRejected("source preimage blob mismatch: " + path)
        raw = None if expected is None else h.source_bytes(root, path)
        if raw is not None and h.git_blob(raw) != expected:
            raise h.GateRejected("source preimage bytes mismatch: " + path)
        originals[path] = None if raw is None else raw.decode("utf-8")
    for path, expected in manifest["canonical_harness"]["source_blobs"].items():
        if flat.get(path, {}).get("sha") != expected or h.git_blob(h.source_bytes(root, path)) != expected:
            raise h.GateRejected("current canonical harness source mismatch")
    patches = {item["id"]: verify_file(h, publication, item) for item in manifest["patches"]}
    if len(patches) != len(manifest["patches"]):
        raise h.GateRejected("duplicate patch identity")
    plans = {}
    for arm, order in manifest["recipes"].items():
        files = dict(originals)
        for key in order:
            if key not in patches:
                raise h.GateRejected("unknown patch in arm recipe")
            h.apply_exact(files, patches[key], [])
        result = h.flat_with_files(flat, files)
        blobs = {path: item["sha"] for path, item in result.items()
                 if item["sha"] != flat.get(path, {}).get("sha")}
        plan = {"tree": h.complete_tree(result), "changed_blobs": blobs}
        if plan != manifest["plans"][arm]:
            raise h.GateRejected("complete source plan mismatch: " + arm)
        plans[arm] = ({path: files[path].encode() for path in blobs}, plan)
    # The sequential baseline transition only adds/overwrites tracked files.
    # It never deletes sources or cleans targets, and both complete trees were preflighted.
    if not set(plans["copy_baseline"][0]).issubset(plans["cache_baseline"][0]):
        raise h.GateRejected("baseline transition would leave an obsolete source path")
    return plans


def sections(h, output, bindings):
    headers = list(re.finditer(r"^     Running ([^\n]+?) \((/[^\n()]+)\)$|^   Doc-tests [^\n]+$", output, re.M))
    result = {}
    for key, value in bindings.items():
        matches = [(i, match) for i, match in enumerate(headers)
                   if match.group(2) == value["executable"]]
        if len(matches) != 1:
            raise h.GateRejected("missing or duplicate executed target: " + key)
        index, match = matches[0]
        if match.group(1) != value["cargo_label"]:
            raise h.GateRejected("executed Cargo target label mismatch: " + key)
        end = headers[index + 1].start() if index + 1 < len(headers) else len(output)
        result[key] = output[match.end():end]
    return result


def canonical_boundary(h, output, manifest, bindings):
    body = sections(h, output, bindings)
    ignored = [name for name in manifest["allowed_ignored"] if name.startswith("core::")]
    return {
        "core": h.require_passes(body["core"], manifest["canonical_core_required"], allowed_ignored=ignored),
        "protocol_lib": h.require_passes(body["protocol"], [name for name in manifest["protocol_required"] if name.startswith("v3::")]),
        "protocol_integration": h.require_passes(body["protocol_integration"], [name for name in manifest["protocol_required"] if not name.startswith("v3::")]),
        "module_swap": h.require_passes(body["module_swap"], manifest["module_swap_required"], exact_inventory=True),
        "hook_runtime": h.require_passes(body["hook_runtime"], manifest["hook_required"]),
        "model_process": h.require_passes(body["model_process"], manifest["model_process_required"]),
    }


def default_integration(h, output, root, target, name, source, package):
    found = []
    for line in output.splitlines():
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        item = value.get("target", {})
        if value.get("reason") != "compiler-artifact" or not value.get("executable") or item.get("name") != name:
            continue
        executable = Path(value["executable"]).resolve()
        if (item.get("kind") != ["test"] or Path(item.get("src_path", "")).resolve() != root / source or
                value.get("features") != [] or not value.get("profile", {}).get("test") or
                not executable.is_relative_to(target) or not isinstance(value.get("package_id"), str)):
            raise h.GateRejected("integration source/default-feature identity mismatch: " + name)
        package_identity(h, value["package_id"], root, source, package)
        found.append({"executable": str(executable), "source": str(root / source), "kind": ["test"],
                      "features": [], "cargo_label": "tests/" + name + ".rs",
                      "package": package, "package_id": value["package_id"]})
    if len(found) != 1:
        raise h.GateRejected("missing or ambiguous integration target: " + name)
    return found[0]


def postflight(h, runner, label, root, env, before, tree):
    after = h.tracked_snapshot(runner, label + "-source-after", root, env)
    if after != before:
        raise h.GateRejected(label + ": source bytes changed during execution")
    if runner.ok(label + "-final-tree", ["git", "write-tree"], root, env, 30).strip() != tree:
        raise h.GateRejected(label + ": source index changed")
    runner.ok(label + "-no-unstaged", ["git", "diff", "--quiet"], root, env, 30)
    if runner.ok(label + "-no-untracked", ["git", "ls-files", "--others", "--exclude-standard"], root, env, 30).strip():
        raise h.GateRejected(label + ": unexpected source files")
    return digest(json.dumps(after, sort_keys=True, separators=(",", ":")).encode())


def library_arm(h, runner, root, target, env, manifest, arm, result):
    selected = arm_cases(h, manifest, arm)
    result.update({"tree": manifest["plans"][arm]["tree"], "cases": [], "binaries": {}, "status": "INCOMPLETE"})
    for key in ("core", "protocol") if arm != "cache_baseline" else ("core",):
        output = runner.ok(arm + "-" + key + "-compile", compile_arguments(key), root, env, 1800, 24 * 1024 * 1024)
        binary = compiled(h, output, key, root, target)
        required = [case["name"] for case in selected if case["library"] == key]
        if arm == "focused":
            required = manifest["focused_core_required"] if key == "core" else manifest["focused_protocol_required"]
        inventory = runner.ok(arm + "-" + key + "-inventory", [binary, "--list", "--format", "terse"], root, env, 30, 512 * 1024)
        ignored = runner.ok(arm + "-" + key + "-ignored", [binary, "--list", "--ignored", "--format", "terse"], root, env, 30, 128 * 1024)
        require_inventory(h, inventory, ignored, required)
        result["binaries"][key] = {"executable": binary, "sha256_before": h.file_sha(binary)}
    for index, case in enumerate(selected):
        label = arm + f"-case-{index:02}"
        binary = result["binaries"][case["library"]]["executable"]
        observed = runner.run(label, [binary, "--exact", case["name"], "--test-threads=1"], root, env, 180, 1024 * 1024)
        verdict = classify_case(h, observed, case, arm != "focused")
        result["cases"].append({"name": case["name"], "stage": label, "verdict": verdict})
    if arm == "focused":
        name = manifest["overlap"]["test_name"]
        observed = runner.run("focused-overlap", [result["binaries"]["core"]["executable"],
            "--exact", name, "--test-threads=1", "--show-output"], root, env, 180, 1024 * 1024)
        h.classify(observed, name)
        markers = re.findall(r"^RECOVERY_OWNED_DELETE_SCHEDULE: [^\n]+$", observed["output"], re.M)
        if sorted(markers) != sorted(manifest["overlap"]["schedule_markers"]):
            raise h.GateRejected("retained overlap schedules differ")
        for key in ("core", "protocol"):
            required = manifest["focused_core_required"] if key == "core" else manifest["focused_protocol_required"]
            ignored = [name for name in manifest["allowed_ignored"] if name.startswith("core::")] if key == "core" else []
            parsed = h.require_passes(runner.ok("focused-" + key + "-full",
                [result["binaries"][key]["executable"], "--test-threads=4"], root, env, 1800, 24 * 1024 * 1024),
                required, allowed_ignored=ignored)
            if set(parsed["ignored"]) != set(ignored):
                raise h.GateRejected("focused ignored inventory changed")
            result[key + "_full"] = parsed
    for value in result["binaries"].values():
        value["sha256_after"] = h.file_sha(value["executable"])
        if value["sha256_before"] != value["sha256_after"]:
            raise h.GateRejected("library executable changed within its source arm")
    result["status"] = "EXACT_ARM_PASS"
    return result


def module_result(h, output, item):
    parsed = h.require_passes(output, item["cases"], exact_inventory=True)
    count = len(item["cases"])
    headers = [int(value) for value in re.findall(r"^running ([0-9]+) tests?$", output, re.M)]
    expected = [count] + [1] * item["inherited_killed_child_starts"]
    if sorted(headers) != sorted(expected) or len(parsed["summaries"]) != 1:
        raise h.GateRejected("stock Modules top-level/child harness boundaries differ")
    return parsed



def stock_graph(h, metadata, manifest):
    selected = {}
    for expected in manifest["modules_tests"]["core_packages"]:
        matches = [item for item in metadata["packages"] if item["name"] == expected["name"]]
        if (len(matches) != 1 or matches[0].get("source") != manifest["modules_tests"]["core_package_source"] or
                matches[0].get("version") != expected["version"]):
            raise h.GateRejected("stock Modules SDK package graph mismatch: " + expected["name"])
        item = matches[0]
        selected[item["name"]] = {key: item[key] for key in ("id", "source", "version", "manifest_path")}
    return selected



def fixture_closure(h, dcp, manifest):
    declared = manifest["fixture"]["dcp_dependency"]["closure"]
    lock = strict(bounded(dcp / "package-lock.json"))
    files, total = [], 0
    for relative, expected in sorted(declared.items()):
        installed = dcp / relative
        item = lock["packages"].get(relative, {})
        actual = {key: item.get(key, {}) if key == "dependencies" else item.get(key)
                  for key in ("version", "resolved", "integrity", "dependencies")}
        if (actual != expected or installed.is_symlink() or not installed.is_dir() or
                not installed.resolve().is_relative_to(dcp.resolve()) or
                strict(bounded(installed / "package.json")).get("version") != expected["version"]):
            raise h.GateRejected("locked installed fixture closure mismatch")
        for directory, directories, names in os.walk(installed, followlinks=False):
            for name in directories:
                if (Path(directory) / name).is_symlink():
                    raise h.GateRejected("fixture dependency directory symlink")
            for name in sorted(names):
                path = Path(directory) / name
                if path.is_symlink() or not path.is_file() or not path.resolve().is_relative_to(installed.resolve()):
                    raise h.GateRejected("fixture dependency file escaped installed package")
                size = path.stat().st_size
                total += size
                if size > 32 * 1024 * 1024 or total > 128 * 1024 * 1024 or len(files) >= 5000:
                    raise h.GateRejected("bounded fixture dependency closure exceeded")
                files.append({"path": str(path.relative_to(dcp)), "bytes": size, "sha256": h.file_sha(path, 32 * 1024 * 1024)})
    files.sort(key=lambda item: item["path"])
    return {"files": files, "bytes": total, "sha256": digest(json.dumps(files, sort_keys=True, separators=(",", ":")).encode())}


def stock_worker(h, output, modules, target, package_id):
    found = []
    for line in output.splitlines():
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        shape = item.get("target", {})
        if (item.get("reason") != "compiler-artifact" or not item.get("executable") or
                shape.get("name") != "proteus-reference-module" or shape.get("kind") != ["bin"]):
            continue
        path = Path(item["executable"]).resolve()
        if (item.get("package_id") != package_id or item.get("features") != [] or
                Path(shape.get("src_path", "")).resolve() != modules / "components/process-module/src/main.rs" or
                not path.is_relative_to(target)):
            raise h.GateRejected("stock test worker compiler identity mismatch")
        found.append({"executable": str(path), "package_id": package_id,
                      "source": str(modules / "components/process-module/src/main.rs"), "features": []})
    if len(found) != 1:
        raise h.GateRejected("stock test build lacks exactly one bound worker")
    return found[0]



def cargo_metadata(h, output):
    """Read one complete Cargo metadata JSON line from the retained combined log."""
    documents = []
    for line in output.splitlines():
        if not line.strip():
            continue
        try:
            value = strict(line)
        except json.JSONDecodeError as error:
            if line.lstrip().startswith(("{", "[")):
                raise h.GateRejected("malformed JSON-like Cargo metadata record") from error
            continue
        except RuntimeError as error:
            raise h.GateRejected("duplicate Cargo metadata object key") from error
        try:
            json.dumps(value, allow_nan=False)
        except ValueError as error:
            raise h.GateRejected("non-finite Cargo metadata value") from error
        documents.append(value)
    if len(documents) != 1:
        raise h.GateRejected("Cargo metadata must contain exactly one complete JSON record")
    value = documents[0]
    if (not isinstance(value, dict) or type(value.get("version")) is not int or value["version"] != 1 or
            not isinstance(value.get("packages"), list) or not value["packages"] or
            any(not isinstance(item, dict) for item in value["packages"]) or
            not isinstance(value.get("workspace_members"), list) or not value["workspace_members"] or
            any(not isinstance(item, str) or not item for item in value["workspace_members"]) or
            not isinstance(value.get("resolve"), dict) or not isinstance(value["resolve"].get("nodes"), list) or
            not isinstance(value.get("workspace_root"), str) or not value["workspace_root"].startswith("/") or
            not isinstance(value.get("target_directory"), str) or not value["target_directory"].startswith("/")):
        raise h.GateRejected("Cargo metadata complete-object schema mismatch")
    return value


def fixture_setup(h, runner, work, root, env, manifest, production):
    modules = work / "current-modules"
    target = work / "fixture-target"
    h.checkout(runner, "fixture", modules, manifest["fixture"]["repository"], manifest["fixture"]["commit"], env)
    if runner.ok("fixture-tree", ["git", "rev-parse", "HEAD^{tree}"], modules, env, 10).strip() != manifest["fixture"]["tree"]:
        raise h.GateRejected("current Modules source tree mismatch")
    before = h.tracked_snapshot(runner, "fixture-source-before", modules, env)
    for path, expected in manifest["fixture"]["source_sha256"].items():
        if h.file_sha(modules / path) != expected:
            raise h.GateRejected("fixture manifest/lock/source identity mismatch: " + path)
    fixture_env = dict(env, PROTEUS_MODULES_SOURCE=str(modules), CARGO_TARGET_DIR=str(target))
    metadata = cargo_metadata(h, runner.ok("fixture-metadata",
        ["cargo", "metadata", "--locked", "--manifest-path", modules / "Cargo.toml", "--format-version", "1"],
        modules, fixture_env, 300, 16 * 1024 * 1024))
    if Path(metadata["workspace_root"]).resolve() != modules or Path(metadata["target_directory"]).resolve() != target:
        raise h.GateRejected("Cargo metadata workspace/target differs from selected fixture")
    sdk_packages = stock_graph(h, metadata, manifest)
    workers = [item for item in metadata["packages"] if item["name"] == "proteus-reference-module"]
    if (len(workers) != 1 or workers[0].get("source") is not None or workers[0].get("features") != {} or
            Path(workers[0]["manifest_path"]).resolve() != modules / "components/process-module/Cargo.toml"):
        raise h.GateRejected("stock Modules local package metadata mismatch")
    worker_package = workers[0]
    nodes = [item for item in metadata["resolve"]["nodes"] if item["id"] == worker_package["id"]]
    if len(nodes) != 1 or nodes[0].get("features") != []:
        raise h.GateRejected("stock Modules default features differ")
    matches = [package for package in metadata["packages"] if package["name"] == "proteus-core"]
    if len(matches) != 1 or matches[0].get("source") != manifest["modules_tests"]["core_package_source"]:
        raise h.GateRejected("stock Modules graph does not resolve exactly the pinned stock Core")
    package = matches[0]
    sdk_manifest = Path(package["manifest_path"]).resolve()
    sdk = sdk_manifest.parents[2]
    if (sdk_manifest != sdk / "crates/proteus-core/Cargo.toml" or
            not sdk.is_relative_to(work / "cargo-home") or
            runner.ok("sdk-head", ["git", "rev-parse", "HEAD"], sdk, fixture_env, 10).strip() != manifest["core"]["commit"] or
            runner.ok("sdk-tree", ["git", "rev-parse", "HEAD^{tree}"], sdk, fixture_env, 10).strip() != manifest["core"]["tree"]):
        raise h.GateRejected("metadata-derived stock SDK checkout identity mismatch")
    sdk_before = h.tracked_snapshot(runner, "sdk-source-before", sdk, fixture_env)
    for path, expected in manifest["modules_tests"]["sdk_source_sha256"].items():
        if h.file_sha(sdk / path) != expected:
            raise h.GateRejected("stock SDK manifest/lock/source bytes mismatch: " + path)
    receipt = {"source_root": str(modules), "target_root": str(target), "sdk_root": str(sdk),
        "module_package_id": worker_package["id"], "sdk_package_id": package["id"], "sdk_package_source": package["source"], "sdk_packages": sdk_packages,
        "fixture_snapshot_before_sha256": digest(json.dumps(before, sort_keys=True, separators=(",", ":")).encode()),
        "sdk_snapshot_before_sha256": digest(json.dumps(sdk_before, sort_keys=True, separators=(",", ":")).encode()),
        "source_sha256": manifest["fixture"]["source_sha256"], "stock_module_tests": {}}
    if production:
        test_env = dict(fixture_env, PROTEUS_TEST_HARNESS_ROOT=str(sdk))
        argv = ["cargo", "test", "--locked", "--manifest-path", modules / "Cargo.toml",
                "-p", "proteus-reference-module"]
        for item in manifest["modules_tests"]["targets"]:
            argv += ["--test", item["id"]]
        output = runner.ok("stock-modules-compile", argv + ["--no-run", "--message-format=json"],
                           modules, test_env, 1800, 24 * 1024 * 1024)
        worker = stock_worker(h, output, modules, target, worker_package["id"])
        worker.update(bytes=Path(worker["executable"]).stat().st_size, sha256_before=h.file_sha(worker["executable"]))
        receipt["stock_worker"] = worker
        for item in manifest["modules_tests"]["targets"]:
            name = item["id"]
            binding = default_integration(h, output, modules, target, name, item["source"], "proteus-reference-module")
            if binding["package_id"] != worker_package["id"]:
                raise h.GateRejected("stock Modules test artifact package differs from metadata")
            binary = binding["executable"]
            binding["bytes"] = Path(binary).stat().st_size
            binding["sha256_before"] = h.file_sha(binary)
            inventory = runner.ok(name + "-inventory", [binary, "--list", "--format", "terse"], modules, test_env, 30, 512 * 1024)
            ignored = runner.ok(name + "-ignored", [binary, "--list", "--ignored", "--format", "terse"], modules, test_env, 30, 128 * 1024)
            require_inventory(h, inventory, ignored, item["cases"])
            if set(h.listed_tests(inventory)) != set(item["cases"]) or h.listed_tests(ignored):
                raise h.GateRejected("stock Modules complete inventory differs")
            parsed = module_result(h, runner.ok(name + "-full", [binary, "--test-threads=4"],
                modules, test_env, 1800, 24 * 1024 * 1024), item)
            binding["sha256_after"] = h.file_sha(binary)
            if binding["sha256_before"] != binding["sha256_after"] or Path(binary).stat().st_size != binding["bytes"]:
                raise h.GateRejected("stock Modules test executable changed")
            receipt["stock_module_tests"][name] = {"binding": binding, "parsed": parsed}
        worker["sha256_after"] = h.file_sha(worker["executable"])
        if worker["sha256_before"] != worker["sha256_after"] or Path(worker["executable"]).stat().st_size != worker["bytes"]:
            raise h.GateRejected("stock test worker changed during selected targets")
    output = runner.ok("build-reference-fixture",
        [sys.executable, "scripts/build_module.py", "--target-dir", target],
        root, fixture_env, 1800, 24 * 1024 * 1024)
    reference = Path(output.strip().splitlines()[-1]).resolve()
    if not reference.is_file() or not reference.is_relative_to(target):
        raise h.GateRejected("reference fixture is not the fresh isolated output")
    receipt["reference"] = {"path": str(reference), "bytes": reference.stat().st_size, "sha256_before": h.file_sha(reference)}
    lane_env = dict(env, CARGO_TARGET_DIR=str(work / "target"),
                    PROTEUS_MODULES_SOURCE=str(modules), PROTEUS_TEST_REFERENCE_MODULE=str(reference))
    if production:
        # Unchanged source is a canonical dependency only; no DCP development or advisory audit.
        dcp = modules / "hook/dcp"
        runner.ok("dcp-fixture-install", ["npm", "ci", "--ignore-scripts", "--no-audit", "--no-fund"],
                  dcp, fixture_env, 300, 4 * 1024 * 1024)
        runner.ok("dcp-fixture-build", ["npm", "--no-audit", "--no-fund", "run", "build"],
                  dcp, fixture_env, 300, 4 * 1024 * 1024)
        worker = dcp / "dist/worker.js"
        if not worker.is_file():
            raise h.GateRejected("unchanged canonical DCP worker missing")
        receipt["dcp"] = {"path": str(worker), "sha256_before": h.file_sha(worker, 8 * 1024 * 1024)}
        module = dcp / "dist/module.js"
        receipt["dcp_module"] = {"path": str(module), "sha256_before": h.file_sha(module, 8 * 1024 * 1024)}
        receipt["dcp_closure_before"] = fixture_closure(h, dcp, manifest)
        lane_env["PROTEUS_TEST_DCP_MODULE"] = str(worker)
    return lane_env, receipt, (modules, before, sdk, sdk_before)


def fixture_postflight(h, runner, state, receipt, env, manifest):
    modules, before, sdk, sdk_before = state
    receipt["fixture_snapshot_after_sha256"] = postflight(h, runner, "fixture", modules, env, before, manifest["fixture"]["tree"])
    sdk_after = h.tracked_snapshot(runner, "sdk-source-after", sdk, env)
    if sdk_after != sdk_before:
        raise h.GateRejected("stock SDK source changed during test/build")
    runner.ok("sdk-no-unstaged", ["git", "diff", "--quiet"], sdk, env, 30)
    if runner.ok("sdk-final-tree", ["git", "rev-parse", "HEAD^{tree}"], sdk, env, 10).strip() != manifest["core"]["tree"]:
        raise h.GateRejected("stock SDK final tree changed")
    receipt["sdk_snapshot_after_sha256"] = digest(json.dumps(sdk_after, sort_keys=True, separators=(",", ":")).encode())
    if "dcp" in receipt:
        receipt["dcp_closure_after"] = fixture_closure(h, modules / "hook/dcp", manifest)
        if receipt["dcp_closure_before"] != receipt["dcp_closure_after"]:
            raise h.GateRejected("locked fixture dependency closure changed")
    for key in ("reference", "dcp", "dcp_module"):
        if key in receipt:
            item = receipt[key]
            item["sha256_after"] = h.file_sha(item["path"])
            if item["sha256_before"] != item["sha256_after"] or (key == "reference" and Path(item["path"]).stat().st_size != item["bytes"]):
                raise h.GateRejected("fresh fixture executable changed: " + key)


def run_phase(h, manifest, manifest_hash, args):
    ctx = context()
    guard(h, ctx)
    work = Path(args.work).resolve()
    work.mkdir(parents=True, exist_ok=False)
    runner = h.Runner(Path(args.evidence).resolve(), work, 6600)
    env = h.clean_env(work)
    receipt = {"schema": 1, "phase": args.phase, "status": "INCOMPLETE", "context": ctx,
        "controller_sha256": h.file_sha(__file__), "manifest_sha256": manifest_hash,
        "support_sha256": HELPER_SHA256, "recipe_sha256": RECIPE_SHA256,
        "core": manifest["core"], "fixture_pin": manifest["fixture"], "plans": manifest["plans"],
        "resource_policy": manifest["resources"], "source_root": str(work / "source"),
        "target_root": str(work / "target"), "stages": runner.records, "arms": {},
        "environment_policy": {"allowlisted": sorted(env), "npm_audit": False, "secrets_inherited": False,
                               "rust_test_threads": env["RUST_TEST_THREADS"]},
        "coverage": "Current exact run/head/attempt only; independent aggregate and successful GitHub jobs required."}
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
            raise h.GateRejected("publication escaped additive current-graph package scope")
        receipt["publication_tree"] = h.complete_tree(new)
        for item in manifest["documents"]:
            verify_file(h, publication, item)
        receipt["tools"] = {}
        for label, argv in [("rustc", ["rustc", "-Vv"]), ("cargo", ["cargo", "-V"]),
                            ("node", ["node", "--version"]), ("bubblewrap", ["/usr/bin/bwrap", "--version"])]:
            receipt["tools"][label] = runner.ok("version-" + label, argv, work, env, 30).strip()
        if (not receipt["tools"]["rustc"].startswith("rustc 1.95.0 ") or
                not receipt["tools"]["cargo"].startswith("cargo 1.95.0 ") or
                receipt["tools"]["node"] != "v22.18.0" or receipt["tools"]["bubblewrap"] != "bubblewrap 0.13.1"):
            raise h.GateRejected("wrong official toolchain or sandbox dependency")
        backend = Path("/usr/bin/bwrap")
        info = backend.stat()
        if (backend.is_symlink() or (stat.S_IMODE(info.st_mode), info.st_uid, info.st_gid) != (0o755, 0, 0) or
                runner.ok("sandbox-capabilities", ["getcap", backend], work, env, 10).strip()):
            raise h.GateRejected("sandbox dependency is not ordinary capability-free 0755")
        receipt["sandbox_binary_sha256"] = h.file_sha(backend, 16 * 1024 * 1024)
        log = runner.ok("sandbox-evidence", ["cat", work.parent / "core-current-bwrap-evidence.txt"], work, env, 10, 65536)
        sandbox_evidence(h, log, receipt["sandbox_binary_sha256"])
        receipt["sandbox_receipt_sha256"] = digest(log.encode())
        root, target = work / "source", work / "target"
        h.checkout(runner, "source", root, manifest["core"]["repository"], manifest["core"]["commit"], env)
        plans = plan_all(h, runner, root, env, publication, manifest)
        receipt["all_plans_preflight"] = "PASS_BEFORE_ANY_SOURCE_REPLACEMENT"
        lane_env = dict(env, CARGO_TARGET_DIR=str(target))
        selected = ("copy_baseline", "cache_baseline") if args.phase == "baseline" else (args.phase,)
        fixture_state = None
        for arm in selected:
            changed, plan = plans[arm]
            h.materialize(runner, arm, root, changed, plan["tree"], env)
            runner.ok(arm + "-format", ["cargo", "fmt", "--all", "--", "--check"], root, env, 180, 2 * 1024 * 1024)
            before = h.tracked_snapshot(runner, arm + "-source-before", root, env)
            arm_receipt = {"tree": plan["tree"],
                "source_snapshot_before_sha256": digest(json.dumps(before, sort_keys=True, separators=(",", ":")).encode())}
            receipt["arms"][arm] = arm_receipt
            if args.phase != "baseline":
                lane_env, receipt["fixture"], fixture_state = fixture_setup(h, runner, work, root, env, manifest, args.phase == "production")
            if arm != "production":
                library_arm(h, runner, root, target, lane_env, manifest, arm, arm_receipt)
            else:
                output = runner.ok("canonical-compile",
                    [sys.executable, *manifest["canonical_harness"]["compile_arguments"]], root, lane_env, 1800, 24 * 1024 * 1024)
                custom = h.canonical_targets(output, root, target, manifest["canonical_harness"])
                bindings = {}
                for key in ("core", "protocol"):
                    binary = compiled(h, output, key, root, target)
                    bindings[key] = {"executable": binary, "cargo_label": "unittests src/lib.rs"}
                for key, name, source, package in (
                    ("hook_runtime", "hook_runtime", "crates/proteus-core/tests/hook_runtime.rs", "proteus-core"),
                    ("module_swap", "module_swap", "crates/proteus-core/tests/module_swap.rs", "proteus-core"),
                    ("model_process", "model_process", "crates/proteus-core/tests/model_process.rs", "proteus-core"),
                    ("protocol_integration", manifest["protocol_integration"]["name"], manifest["protocol_integration"]["source"], "proteus-module-protocol"),
                ):
                    bindings[key] = default_integration(h, output, root, target, name, source, package)
                binaries = {**{key: item["executable"] for key, item in custom.items()},
                            **{key: item["executable"] for key, item in bindings.items()}}
                arm_receipt.update(canonical_binaries=custom, boundary_binaries=bindings,
                    binary_sha256_before={key: h.file_sha(path) for key, path in binaries.items()})
                output = runner.ok("canonical-full", [sys.executable, "scripts/test.py", "full"],
                    root, lane_env, 1800, 40 * 1024 * 1024)
                arm_receipt["canonical_full"] = h.require_canonical_passes(output, manifest["production_required_full"],
                    manifest["canonical_harness"], custom, manifest["allowed_ignored"])
                if set(arm_receipt["canonical_full"]["ignored"]) != set(manifest["allowed_ignored"]):
                    raise h.GateRejected("canonical ignore set changed")
                arm_receipt["boundaries"] = canonical_boundary(h, output, manifest, bindings)
                arm_receipt["binary_sha256_after"] = {key: h.file_sha(path) for key, path in binaries.items()}
                if arm_receipt["binary_sha256_before"] != arm_receipt["binary_sha256_after"]:
                    raise h.GateRejected("canonical executable changed after no-run discovery")
                arm_receipt["status"] = "EXACT_ARM_PASS"
            arm_receipt["source_snapshot_after_sha256"] = postflight(h, runner, arm, root, env, before, plan["tree"])
        if fixture_state:
            fixture_postflight(h, runner, fixture_state, receipt["fixture"], env, manifest)
        receipt["status"] = STATUSES[args.phase]
    except BaseException as error:
        receipt["status"] = "INFRASTRUCTURE_ERROR" if h.is_infrastructure(error) else "GATE_REJECTED"
        receipt["error"] = f"{type(error).__name__}: {error}"
        raise
    finally:
        write_receipt(Path(args.evidence) / "result.json", receipt)


def phase_identity(h, receipt, phase, manifest, manifest_hash, ctx):
    expected = {"schema": 1, "phase": phase, "context": ctx,
        "controller_sha256": manifest["controller_sha256"], "manifest_sha256": manifest_hash,
        "support_sha256": HELPER_SHA256, "recipe_sha256": RECIPE_SHA256,
        "core": manifest["core"], "fixture_pin": manifest["fixture"], "plans": manifest["plans"],
        "resource_policy": manifest["resources"]}
    if any(not same_json_evidence(receipt.get(key), value) for key, value in expected.items()):
        raise h.GateRejected("foreign phase receipt identity")
    return receipt.get("status")


def pass_identity(h, receipt, phase, publication_tree):
    if (receipt.get("status") != STATUSES[phase] or receipt.get("publication_tree") != publication_tree or
            receipt.get("all_plans_preflight") != "PASS_BEFORE_ANY_SOURCE_REPLACEMENT" or
            type(receipt.get("initial_free_bytes")) is not int or receipt["initial_free_bytes"] < h.INITIAL_FREE_BYTES):
        raise h.GateRejected("phase lacks required completed provenance")


def require_jobs(h):
    if os.environ.get("QUALIFY_JOB_RESULT") != "success" or os.environ.get("FOCUSED_JOB_RESULT") != "success":
        raise h.InfrastructureError("current GitHub prerequisite jobs did not all succeed")


def audit_fixture(h, output, records, receipt, manifest, source, work, production):
    item = receipt["fixture"]
    modules, target, sdk = Path(item["source_root"]), Path(item["target_root"]), Path(item["sdk_root"])
    if modules != work / "current-modules" or target != work / "fixture-target" or not sdk.is_relative_to(work / "cargo-home"):
        raise h.GateRejected("fixture/stock SDK path isolation mismatch")
    def get(label, argv, cwd):
        return output(label, argv, cwd)["output"]
    metadata = cargo_metadata(h, get("fixture-metadata", ["cargo", "metadata", "--locked", "--manifest-path",
        modules / "Cargo.toml", "--format-version", "1"], modules))
    if Path(metadata["workspace_root"]).resolve() != modules or Path(metadata["target_directory"]).resolve() != target:
        raise h.GateRejected("Cargo metadata workspace/target differs from selected fixture")
    if not same_json_evidence(stock_graph(h, metadata, manifest), item["sdk_packages"]):
        raise h.GateRejected("stock SDK five-package graph receipt mismatch")
    workers = [value for value in metadata["packages"] if value["name"] == "proteus-reference-module"]
    if (len(workers) != 1 or workers[0].get("source") is not None or workers[0].get("features") != {} or
            workers[0].get("id") != item["module_package_id"] or
            Path(workers[0]["manifest_path"]).resolve() != modules / "components/process-module/Cargo.toml"):
        raise h.GateRejected("stock Modules local package receipt mismatch")
    nodes = [value for value in metadata["resolve"]["nodes"] if value["id"] == workers[0]["id"]]
    if len(nodes) != 1 or nodes[0].get("features") != []:
        raise h.GateRejected("stock Modules resolved features mismatch")
    packages = [value for value in metadata["packages"] if value["name"] == "proteus-core"]
    if (len(packages) != 1 or packages[0].get("source") != manifest["modules_tests"]["core_package_source"] or
            packages[0].get("id") != item["sdk_package_id"] or packages[0].get("source") != item["sdk_package_source"] or
            Path(packages[0]["manifest_path"]).resolve() != sdk / "crates/proteus-core/Cargo.toml"):
        raise h.GateRejected("stock SDK metadata receipt differs")
    for label, argv, cwd, expected in (
        ("fixture-pin", ["git", "rev-parse", "HEAD"], modules, manifest["fixture"]["commit"]),
        ("fixture-tree", ["git", "rev-parse", "HEAD^{tree}"], modules, manifest["fixture"]["tree"]),
        ("fixture-final-tree", ["git", "write-tree"], modules, manifest["fixture"]["tree"]),
        ("sdk-head", ["git", "rev-parse", "HEAD"], sdk, manifest["core"]["commit"]),
        ("sdk-tree", ["git", "rev-parse", "HEAD^{tree}"], sdk, manifest["core"]["tree"]),
        ("sdk-final-tree", ["git", "rev-parse", "HEAD^{tree}"], sdk, manifest["core"]["tree"]),
    ):
        if get(label, argv, cwd).strip() != expected:
            raise h.GateRejected("fixture/SDK identity postflight mismatch")
    for label, argv, cwd in (
        ("fixture-no-unstaged", ["git", "diff", "--quiet"], modules),
        ("fixture-no-untracked", ["git", "ls-files", "--others", "--exclude-standard"], modules),
        ("sdk-no-unstaged", ["git", "diff", "--quiet"], sdk),
    ):
        if get(label, argv, cwd).strip():
            raise h.GateRejected("fixture/SDK source mutation")
    for prefix in ("fixture", "sdk"):
        before, after = item.get(prefix + "_snapshot_before_sha256"), item.get(prefix + "_snapshot_after_sha256")
        if before != after or not re.fullmatch(r"[0-9a-f]{64}", after or ""):
            raise h.GateRejected("fixture/SDK byte snapshot mismatch")
    if item["source_sha256"] != manifest["fixture"]["source_sha256"]:
        raise h.GateRejected("fixture manifest/lock provenance mismatch")
    built = get("build-reference-fixture", [sys.executable, "scripts/build_module.py", "--target-dir", target], source)
    if str(Path(built.strip().splitlines()[-1]).resolve()) != item["reference"]["path"]:
        raise h.GateRejected("built reference path mismatch")
    if type(item["reference"].get("bytes")) is not int or not 0 < item["reference"]["bytes"] <= 256 * 1024 * 1024:
        raise h.GateRejected("reference executable byte count missing or excessive")
    for key in ("reference", "dcp", "dcp_module") if production else ("reference",):
        binary = item[key]
        expected_parent = target if key == "reference" else modules / "hook/dcp/dist"
        if (not Path(binary["path"]).is_relative_to(expected_parent) or
                binary.get("sha256_before") != binary.get("sha256_after") or
                not re.fullmatch(r"[0-9a-f]{64}", binary.get("sha256_after", ""))):
            raise h.GateRejected("fresh fixture binary provenance mismatch")
    if production:
        get("dcp-fixture-install", ["npm", "ci", "--ignore-scripts", "--no-audit", "--no-fund"], modules / "hook/dcp")
        get("dcp-fixture-build", ["npm", "--no-audit", "--no-fund", "run", "build"], modules / "hook/dcp")
        argv = ["cargo", "test", "--locked", "--manifest-path", modules / "Cargo.toml", "-p", "proteus-reference-module"]
        for test in manifest["modules_tests"]["targets"]:
            argv += ["--test", test["id"]]
        compile_log = get("stock-modules-compile", argv + ["--no-run", "--message-format=json"], modules)
        worker = stock_worker(h, compile_log, modules, target, item["module_package_id"])
        bound_worker = item["stock_worker"]
        if (any(bound_worker.get(key) != value for key, value in worker.items()) or
                bound_worker.get("sha256_before") != bound_worker.get("sha256_after") or
                not re.fullmatch(r"[0-9a-f]{64}", bound_worker.get("sha256_after", "")) or
                type(bound_worker.get("bytes")) is not int or not 0 < bound_worker["bytes"] <= 256 * 1024 * 1024):
            raise h.GateRejected("stock test worker pre/post provenance mismatch")
        closure = item["dcp_closure_before"]
        if not same_json_evidence(closure, item["dcp_closure_after"]):
            raise h.GateRejected("installed fixture closure changed")
        entries = closure["files"]
        paths = [entry["path"] for entry in entries]
        allowed = manifest["fixture"]["dcp_dependency"]["closure"]
        if (not 1 <= len(entries) <= 5000 or paths != sorted(set(paths)) or
                any(not any(path.startswith(prefix + "/") for prefix in allowed) or ".." in Path(path).parts for path in paths) or
                any(prefix + "/package.json" not in paths for prefix in allowed) or
                any(type(entry.get("bytes")) is not int or not 0 <= entry["bytes"] <= 32 * 1024 * 1024 or
                    not re.fullmatch(r"[0-9a-f]{64}", entry.get("sha256", "")) for entry in entries) or
                type(closure.get("bytes")) is not int or closure["bytes"] != sum(entry["bytes"] for entry in entries) or
                closure["bytes"] > 128 * 1024 * 1024 or
                closure["sha256"] != digest(json.dumps(entries, sort_keys=True, separators=(",", ":")).encode())):
            raise h.GateRejected("bounded installed fixture closure receipt malformed")
        if set(item["stock_module_tests"]) != {test["id"] for test in manifest["modules_tests"]["targets"]}:
            raise h.GateRejected("stock Modules completed target set mismatch")
        for test in manifest["modules_tests"]["targets"]:
            name = test["id"]
            binding = default_integration(h, compile_log, modules, target, name, test["source"], "proteus-reference-module")
            stored = item["stock_module_tests"][name]
            if binding["package_id"] != item["module_package_id"]:
                raise h.GateRejected("stock test package differs from metadata")
            if (any(stored["binding"].get(key) != value for key, value in binding.items()) or
                    stored["binding"]["sha256_before"] != stored["binding"]["sha256_after"] or
                    not re.fullmatch(r"[0-9a-f]{64}", stored["binding"]["sha256_after"]) or
                    type(stored["binding"].get("bytes")) is not int or not 0 < stored["binding"]["bytes"] <= 256 * 1024 * 1024):
                raise h.GateRejected("stock Modules compiled binary mismatch")
            binary = binding["executable"]
            inventory = get(name + "-inventory", [binary, "--list", "--format", "terse"], modules)
            ignored = get(name + "-ignored", [binary, "--list", "--ignored", "--format", "terse"], modules)
            require_inventory(h, inventory, ignored, test["cases"])
            if set(h.listed_tests(inventory)) != set(test["cases"]) or h.listed_tests(ignored):
                raise h.GateRejected("stock Modules complete test inventory mismatch")
            parsed = module_result(h, get(name + "-full", [binary, "--test-threads=4"], modules), test)
            if not same_json_evidence(parsed, stored["parsed"]):
                raise h.GateRejected("stock Modules raw full-target evidence mismatch")
    elif item["stock_module_tests"] or any(key in item for key in ("dcp", "dcp_module", "stock_worker", "dcp_closure_before", "dcp_closure_after")):
        raise h.GateRejected("focused fixture unexpectedly expanded execution scope")


def aggregate(h, manifest, manifest_hash, args):
    ctx = context()
    guard(h, ctx)
    evidence = Path(args.evidence).resolve()
    publication = Path(os.environ["GITHUB_WORKSPACE"]).resolve()
    runner = h.Runner(evidence, publication, 120)
    env = {key: value for key, value in os.environ.items() if key in {"PATH", "LANG", "LC_ALL", "TMPDIR", "TMP", "TEMP"}}
    env.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL="/dev/null", GIT_TERMINAL_PROMPT="0")
    result = {"schema": 1, "status": "INCOMPLETE", "context": ctx, "manifest_sha256": manifest_hash,
              "phases": {}, "stages": runner.records}
    try:
        if runner.ok("aggregate-head", ["git", "rev-parse", "HEAD"], publication, env, 10).strip() != ctx["head"]:
            raise h.GateRejected("aggregate checkout differs from current head")
        flat = h.parse_tree(runner.ok("aggregate-publication-tree", ["git", "ls-tree", "-r", "-z", "--full-tree", "HEAD"],
                                     publication, env, 30, 2 * 1024 * 1024))
        runner.ok("aggregate-clean-checkout", ["git", "diff", "--quiet", "HEAD"], publication, env, 10)
        tree = h.complete_tree(flat)
        result["publication_tree"] = tree
        available, missing, infrastructure, rejected = {}, [], [], []
        for phase in PHASES:
            path = Path(args.aggregate).resolve() / phase / "result.json"
            if not path.exists():
                missing.append(phase)
                continue
            raw = bounded(path, 4 * 1024 * 1024)
            receipt = strict(raw)
            status = phase_identity(h, receipt, phase, manifest, manifest_hash, ctx)
            available[phase] = (raw, receipt)
            if status == "INFRASTRUCTURE_ERROR":
                infrastructure.append(phase + ": " + str(receipt.get("error", "")))
            elif status != STATUSES[phase]:
                rejected.append(phase + ": " + str(status))
        if infrastructure:
            raise h.InfrastructureError("exact current-run infrastructure failure: " + "; ".join(infrastructure))
        if rejected:
            raise h.GateRejected("exact current-run phase not qualified: " + "; ".join(rejected))
        if missing:
            raise h.InfrastructureError("required current-run evidence unavailable: " + ", ".join(missing))
        for phase in PHASES:
            raw, receipt = available[phase]
            pass_identity(h, receipt, phase, tree)
            paths, records = h.phase_logs(Path(args.aggregate).resolve() / phase, receipt)
            source, target = Path(receipt["source_root"]), Path(receipt["target_root"])
            work = source.parent
            if not source.is_absolute() or source.name != "source" or work.name != "core-current-work" or target != work / "target":
                raise h.GateRejected("source/target isolation mismatch")
            def output(label, argv=None, cwd=None):
                if label not in records:
                    raise h.GateRejected("required stage missing: " + label)
                record = records[label]
                if argv is not None and (record["argv"] != [str(x) for x in argv] or record["cwd"] != str(cwd or source)):
                    raise h.GateRejected("required command/source binding mismatch: " + label)
                return {"code": record["exit_code"],
                        "output": h.bounded_file(paths[label], h.MAX_TOTAL_OUTPUT).decode("utf-8", "replace")}
            sandbox = output("sandbox-evidence", ["cat", work.parent / "core-current-bwrap-evidence.txt"], work)["output"]
            if digest(sandbox.encode()) != receipt["sandbox_receipt_sha256"]:
                raise h.GateRejected("sandbox receipt hash mismatch")
            sandbox_evidence(h, sandbox, receipt["sandbox_binary_sha256"])
            arms = ("copy_baseline", "cache_baseline") if phase == "baseline" else (phase,)
            if set(receipt["arms"]) != set(arms):
                raise h.GateRejected("selected source-arm inventory mismatch")
            permitted_reds = set()
            for arm in arms:
                item = receipt["arms"][arm]
                if item.get("tree") != manifest["plans"][arm]["tree"] or item.get("status") != "EXACT_ARM_PASS":
                    raise h.GateRejected("source arm not complete")
                output(arm + "-format", ["cargo", "fmt", "--all", "--", "--check"])
                if (output(arm + "-final-tree", ["git", "write-tree"])["output"].strip() != item["tree"] or
                        output(arm + "-no-unstaged", ["git", "diff", "--quiet"])["output"].strip() or
                        output(arm + "-no-untracked", ["git", "ls-files", "--others", "--exclude-standard"])["output"].strip() or
                        item.get("source_snapshot_before_sha256") != item.get("source_snapshot_after_sha256") or
                        not re.fullmatch(r"[0-9a-f]{64}", item.get("source_snapshot_after_sha256", ""))):
                    raise h.GateRejected("arm source/index postflight mismatch")
                if arm == "production":
                    compile_log = output("canonical-compile", [sys.executable, *manifest["canonical_harness"]["compile_arguments"]])["output"]
                    custom = h.canonical_targets(compile_log, source, target, manifest["canonical_harness"])
                    bindings = {}
                    for key in ("core", "protocol"):
                        bindings[key] = {"executable": compiled(h, compile_log, key, source, target),
                                         "cargo_label": "unittests src/lib.rs"}
                    for key, name, path, package in (
                        ("hook_runtime", "hook_runtime", "crates/proteus-core/tests/hook_runtime.rs", "proteus-core"),
                        ("module_swap", "module_swap", "crates/proteus-core/tests/module_swap.rs", "proteus-core"),
                        ("model_process", "model_process", "crates/proteus-core/tests/model_process.rs", "proteus-core"),
                        ("protocol_integration", manifest["protocol_integration"]["name"], manifest["protocol_integration"]["source"], "proteus-module-protocol"),
                    ):
                        bindings[key] = default_integration(h, compile_log, source, target, name, path, package)
                    hashes = item["binary_sha256_before"]
                    if (custom != item["canonical_binaries"] or bindings != item["boundary_binaries"] or
                            hashes != item["binary_sha256_after"] or set(hashes) != set(custom) | set(bindings) or
                            any(not re.fullmatch(r"[0-9a-f]{64}", value) for value in hashes.values())):
                        raise h.GateRejected("canonical compiler-artifact/default-feature/binary provenance mismatch")
                    log = output("canonical-full", [sys.executable, "scripts/test.py", "full"])["output"]
                    parsed = h.require_canonical_passes(log, manifest["production_required_full"],
                        manifest["canonical_harness"], custom, manifest["allowed_ignored"])
                    if (not same_json_evidence(parsed, item["canonical_full"]) or
                            set(parsed["ignored"]) != set(manifest["allowed_ignored"]) or
                            not same_json_evidence(canonical_boundary(h, log, manifest, bindings), item["boundaries"])):
                        raise h.GateRejected("canonical target-bound raw evidence mismatch")
                else:
                    selected = arm_cases(h, manifest, arm)
                    keys = ("core", "protocol") if arm != "cache_baseline" else ("core",)
                    if set(item["binaries"]) != set(keys):
                        raise h.GateRejected("library target inventory mismatch")
                    binaries = {}
                    for key in keys:
                        binary = compiled(h, output(arm + "-" + key + "-compile", compile_arguments(key))["output"], key, source, target)
                        stored = item["binaries"][key]
                        if (stored["executable"] != binary or stored["sha256_before"] != stored["sha256_after"] or
                                not re.fullmatch(r"[0-9a-f]{64}", stored["sha256_after"])):
                            raise h.GateRejected("source-arm binary provenance mismatch")
                        binaries[key] = binary
                        required = [case["name"] for case in selected if case["library"] == key]
                        if arm == "focused":
                            required = manifest["focused_core_required"] if key == "core" else manifest["focused_protocol_required"]
                        require_inventory(h,
                            output(arm + "-" + key + "-inventory", [binary, "--list", "--format", "terse"])["output"],
                            output(arm + "-" + key + "-ignored", [binary, "--list", "--ignored", "--format", "terse"])["output"], required)
                    cases = []
                    for index, case in enumerate(selected):
                        label = arm + f"-case-{index:02}"
                        observed = output(label, [binaries[case["library"]], "--exact", case["name"], "--test-threads=1"])
                        verdict = classify_case(h, observed, case, arm != "focused")
                        cases.append({"name": case["name"], "stage": label, "verdict": verdict})
                        if verdict == "EXPECTED_BEHAVIORAL_RED":
                            permitted_reds.add(label)
                    if cases != item["cases"] or sum(case["verdict"] == "EXPECTED_BEHAVIORAL_RED" for case in cases) != manifest["case_counts"][arm]["red"]:
                        raise h.GateRejected("case outcomes differ from independently classified raw logs")
                    if arm == "focused":
                        name = manifest["overlap"]["test_name"]
                        observed = output("focused-overlap", [binaries["core"], "--exact", name, "--test-threads=1", "--show-output"])
                        h.classify(observed, name)
                        if sorted(re.findall(r"^RECOVERY_OWNED_DELETE_SCHEDULE: [^\n]+$", observed["output"], re.M)) != sorted(manifest["overlap"]["schedule_markers"]):
                            raise h.GateRejected("retained overlap schedules mismatch")
                        for key in keys:
                            required = manifest["focused_core_required"] if key == "core" else manifest["focused_protocol_required"]
                            ignored = [name for name in manifest["allowed_ignored"] if name.startswith("core::")] if key == "core" else []
                            parsed = h.require_passes(output("focused-" + key + "-full",
                                [binaries[key], "--test-threads=4"])["output"], required, allowed_ignored=ignored)
                            if not same_json_evidence(parsed, item[key + "_full"]) or set(parsed["ignored"]) != set(ignored):
                                raise h.GateRejected("focused complete-library evidence mismatch")
            if phase != "baseline":
                audit_fixture(h, output, records, receipt, manifest, source, work, phase == "production")
            if {label for label, record in records.items() if record["exit_code"] == 101} != permitted_reds:
                raise h.GateRejected("unexpected failure cannot count as a mechanism negative")
            result["phases"][phase] = {"receipt_sha256": digest(raw), "status": receipt["status"],
                "stages": len(records), "minimum_free_bytes": min(record["disk_free_minimum_bytes"] for record in records.values())}
        require_jobs(h)
        result["status"] = "CURRENT_CORE_GRAPH_EXACT_PASS"
        result["counting"] = "28 baseline executions (20 green/8 intended red); 35 direct candidate cases; suite overlap is not additional unique cases. Stock Modules targets are separate stock-SDK evidence."
    except BaseException as error:
        result["status"] = "INFRASTRUCTURE_ERROR" if h.is_infrastructure(error) else "GATE_REJECTED"
        result["error"] = f"{type(error).__name__}: {error}"
        raise
    finally:
        write_receipt(evidence / "result.json", result)

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

    validate_manifest(h, manifest)
    for arm in manifest["phase_cases"]:
        assert arm_cases(h, manifest, arm)
    def rejected(call):
        try:
            call()
        except (h.GateRejected, h.InfrastructureError):
            return
        raise h.GateRejected("negative self-control was accepted")
    for arm in ("copy_baseline", "cache_baseline", "focused"):
        altered = json.loads(json.dumps(manifest))
        altered["phase_cases"][arm].append(altered["phase_cases"][arm][0])
        rejected(lambda: arm_cases(h, altered, arm))
    ctx = {"head": "a" * 40, "repository": REPOSITORY, "workflow_ref": "test", "run_id": "1", "run_attempt": "1"}
    base = {"schema": 1, "phase": "baseline", "context": ctx,
        "controller_sha256": manifest["controller_sha256"], "manifest_sha256": "m",
        "support_sha256": HELPER_SHA256, "recipe_sha256": RECIPE_SHA256,
        "core": manifest["core"], "fixture_pin": manifest["fixture"], "plans": manifest["plans"],
        "resource_policy": manifest["resources"], "status": "INFRASTRUCTURE_ERROR"}
    assert phase_identity(h, base, "baseline", manifest, "m", ctx) == "INFRASTRUCTURE_ERROR"
    good = dict(base, status=STATUSES["baseline"], publication_tree="t",
        all_plans_preflight="PASS_BEFORE_ANY_SOURCE_REPLACEMENT", initial_free_bytes=h.INITIAL_FREE_BYTES)
    pass_identity(h, good, "baseline", "t")
    for key in ("head", "run_id", "run_attempt"):
        rejected(lambda key=key: phase_identity(h, dict(good, context=dict(ctx, **{key: "foreign"})),
            "baseline", manifest, "m", ctx))
    for key in ("publication_tree", "all_plans_preflight", "initial_free_bytes"):
        altered = dict(good)
        altered.pop(key)
        rejected(lambda: pass_identity(h, altered, "baseline", "t"))
    saved = {key: os.environ.get(key) for key in ("QUALIFY_JOB_RESULT", "FOCUSED_JOB_RESULT")}
    try:
        os.environ.update(QUALIFY_JOB_RESULT="success", FOCUSED_JOB_RESULT="success")
        require_jobs(h)
        for value in ("failure", "cancelled", "skipped"):
            os.environ["FOCUSED_JOB_RESULT"] = value
            rejected(lambda: require_jobs(h))
    finally:
        for key, value in saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
    metadata_sample = {"version": 1, "packages": [{"name": "marker"}],
        "workspace_members": ["marker"], "resolve": {"nodes": []},
        "workspace_root": "/source", "target_directory": "/target"}
    metadata_json = json.dumps(metadata_sample, separators=(",", ":"))
    metadata_log = "    Updating crates.io index\n Downloaded example v1.0.0\n" + metadata_json + "\n"
    assert cargo_metadata(h, metadata_log) == metadata_sample
    for invalid in (
        "", "    Updating crates.io index\n", metadata_log + metadata_json + "\n",
        metadata_log + "42\n", metadata_log + '{"version":',
        '{"version":1,"version":1}\n', "[]\n",
        json.dumps(dict(metadata_sample, version=True)),
        json.dumps(dict(metadata_sample, workspace_root="relative")),
        json.dumps(dict(metadata_sample, resolve=None)),
        json.dumps(dict(metadata_sample, extra=float("nan"))),
    ):
        rejected(lambda invalid=invalid: cargo_metadata(h, invalid))
    sample = "running 1 test\ntest exact_json_control ... ok\n\ntest result: ok. 1 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 0.00s\n"
    parsed = h.require_passes(sample, ["exact_json_control"], exact_inventory=True)
    recorded = json.loads(json.dumps(parsed))
    assert parsed != recorded and same_json_evidence(parsed, recorded)
    for key, value in (("passed", ["foreign"]), ("ignored", ["exact_json_control"]),
                       ("libtest_passed_count", 2), ("libtest_passed_count", True),
                       ("summaries", []), ("extra", True)):
        assert not same_json_evidence(parsed, dict(recorded, **{key: value}))
    fake = {"one": {"executable": "/target/one", "cargo_label": "tests/one.rs"}}
    log = "     Running tests/one.rs (/target/one)\n" + sample
    assert sections(h, log, fake)["one"].strip() == sample.strip()
    for bad in (log + log, log.replace("/target/one", "/foreign"), log.replace("tests/one.rs", "tests/other.rs")):
        rejected(lambda bad=bad: sections(h, bad, fake))
    def synthetic(names, ignored=()):
        count = len(names) + len(ignored)
        return (f"running {count} tests\n" +
            "".join(f"test {name} ... ok\n" for name in names) +
            "".join(f"test {name} ... ignored\n" for name in ignored) +
            f"test result: ok. {len(names)} passed; 0 failed; {len(ignored)} ignored; 0 measured; 0 filtered out; finished in 0.00s\n")
    bindings = {key: {"executable": "/target/" + key, "cargo_label": "tests/" + key + ".rs"}
                for key in ("core", "protocol", "protocol_integration", "module_swap", "hook_runtime", "model_process")}
    bodies = {
        "core": synthetic(manifest["canonical_core_required"], [name for name in manifest["allowed_ignored"] if name.startswith("core::")]),
        "protocol": synthetic([name for name in manifest["protocol_required"] if name.startswith("v3::")]),
        "protocol_integration": synthetic([name for name in manifest["protocol_required"] if not name.startswith("v3::")]),
        "module_swap": synthetic(manifest["module_swap_required"]),
        "hook_runtime": synthetic(manifest["hook_required"]),
        "model_process": synthetic(manifest["model_process_required"]),
    }
    log = "".join("     Running " + bindings[key]["cargo_label"] + " (" + bindings[key]["executable"] + ")\n" + body
                  for key, body in bodies.items())
    canonical_boundary(h, log, manifest, bindings)
    for bad in (log + log, log.replace("/target/hook_runtime", "/foreign"),
                log.replace(manifest["hook_required"][0] + " ... ok", "foreign ... ok"),
                log.replace(manifest["module_swap_required"][0] + " ... ok", "foreign ... ok"),
                log.replace("/target/model_process", "/foreign"),
                log.replace(manifest["model_process_required"][0] + " ... ok", "foreign ... ok"),
                log.replace(" ... ok", " ... FAILED", 1)):
        rejected(lambda bad=bad: canonical_boundary(h, bad, manifest, bindings))
    for item in manifest["modules_tests"]["targets"]:
        count = len(item["cases"])
        log = f"running {count} tests\n" + "running 1 test\n" * item["inherited_killed_child_starts"]
        log += "".join(f"test {name} ... ok\n" for name in item["cases"])
        log += f"test result: ok. {count} passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 0.00s\n"
        module_result(h, log, item)
        for bad in (log + "running 1 test\n", log.replace(" ... ok", " ... FAILED", 1),
                    log.replace(item["cases"][0] + " ... ok", "foreign ... ok", 1),
                    log + "test result: ok. 0 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 0.00s\n"):
            rejected(lambda bad=bad: module_result(h, bad, item))
    print("Pinned inherited parsers/process controls, exact arm selection, JSON type-sensitive equality,")
    print("early-infrastructure/foreign-receipt rejection, job-result and current-target section controls PASS")
    print("Stock Modules exact complete-target and child-header boundary self-controls PASS")
    print("Exactly-one Cargo metadata document, schema and eleven rejection controls PASS")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--helper", required=True)
    parser.add_argument("--recipe", required=True)
    parser.add_argument("--phase", choices=PHASES)
    parser.add_argument("--work")
    parser.add_argument("--evidence")
    parser.add_argument("--aggregate")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if not __debug__:
        raise RuntimeError("assertions must remain enabled")
    raw = bounded(args.manifest)
    manifest = strict(raw)
    h, recipe = support(args)
    validate_manifest(h, manifest)
    if args.self_test:
        self_test(h, recipe, manifest)
    elif args.aggregate:
        if not args.evidence or args.phase or args.work:
            parser.error("aggregate requires only evidence and aggregate paths")
        aggregate(h, manifest, digest(raw), args)
    else:
        if not args.phase or not args.work or not args.evidence:
            parser.error("source phase/work/evidence required")
        run_phase(h, manifest, digest(raw), args)


if __name__ == "__main__":
    main()
