#!/usr/bin/env python3
"""Targeted raw-argument qualification; no counters, full matrix or benchmark."""
import argparse
import importlib.util
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sys

PACKAGE = "foundation/2026-10-27/core-raw-arguments-targeted"
REPOSITORY = "Qweasd123tg/proteus-modules-dot"
BRANCH = "ci/core-raw-arguments-targeted-20261027"
WORKFLOW = ".github/workflows/core-raw-arguments-targeted.yml"
HELPER_SHA256 = "2f917a4ca4dc71a3dfa8cf2dc376991a7ddf1580cd347aaff8cb6ccc50568147"
HELPER_BYTES = 109703
GRAPH = ("foundation/2026-10-27/core-current-graph/check.py",
         "4cf85d5124f7d39cb38a3444287bf43254d74f1053a70fee926c6515ca3c6b3b")
GRAPH_MANIFEST = ("foundation/2026-10-27/core-current-graph/manifest.json",
                  "dca653f3eda6ece4e9f339f531669a14e249e7a0cf151dd77a58b9fea5eef603")

def checked_support_bytes(raw, expected_sha256, expected_bytes=None):
    if len(raw) > 1024 * 1024 or (expected_bytes is not None and len(raw) != expected_bytes):
        raise RuntimeError("pinned support length mismatch")
    if hashlib.sha256(raw).hexdigest() != expected_sha256:
        raise RuntimeError("pinned support digest mismatch")
    return raw

def read_support_source(path, expected_sha256, expected_bytes=None):
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise RuntimeError("support must be a regular non-symlink file")
    with path.open("rb") as stream:
        raw = stream.read(1024 * 1024 + 1)
    return checked_support_bytes(raw, expected_sha256, expected_bytes)

def load_support(publication, helper):
    helper = Path(helper)
    if helper.resolve().is_relative_to(publication):
        raise RuntimeError("downloaded helper must remain outside publication checkout")
    def read(item):
        return read_support_source(publication / item[0], item[1])
    def module(name, path, expected_sha256, expected_bytes=None):
        raw = read_support_source(path, expected_sha256, expected_bytes)
        result = importlib.util.module_from_spec(importlib.util.spec_from_loader(name, loader=None))
        result.__file__ = str(path)
        exec(compile(raw, result.__file__, "exec"), result.__dict__)
        return result
    h = module("raw_pr35_support", helper, HELPER_SHA256, HELPER_BYTES)
    g = module("raw_pr37_support", publication / GRAPH[0], GRAPH[1])
    graph = g.strict(read(GRAPH_MANIFEST))
    if graph["plans"]["production"]["tree"] != "9a122670d8e4360e4cdccc930569f141629baefc":
        raise h.GateRejected("wrong qualified foundation")
    g.LIBRARIES = dict(g.LIBRARIES, contracts=(
        "proteus-contracts", "proteus_contracts", "crates/proteus-contracts/src/lib.rs"))
    raw = g.bounded(publication / PACKAGE / "manifest.json")
    manifest = g.strict(raw)
    if h.file_sha(__file__) != manifest["controller_sha256"]:
        raise h.GateRejected("controller identity mismatch")
    for item in manifest["files"]:
        g.verify_file(h, publication, item)
    return h, g, graph, manifest, h.sha(raw)

def guard(h, g):
    ctx = g.context()
    if (os.environ.get("GITHUB_ACTIONS") != "true" or
            os.environ.get("GITHUB_EVENT_NAME") != "push" or
            os.environ.get("GITHUB_REF") != "refs/heads/" + BRANCH or
            ctx["repository"] != REPOSITORY or
            ctx["workflow_ref"] != REPOSITORY + "/" + WORKFLOW + "@refs/heads/" + BRANCH or
            not re.fullmatch(r"[0-9a-f]{40}", ctx["head"] or "") or
            not all(re.fullmatch(r"[1-9][0-9]*", ctx[key] or "") for key in ("run_id", "run_attempt"))):
        raise h.GateRejected("exact guarded targeted-qualification push required")
    return ctx

def selected_inventory(h, output, ignored_output, group):
    names, ignored = h.listed_tests(output), h.listed_tests(ignored_output)
    chosen = [name for name in names if group["filter"] is None or group["filter"] in name]
    if (len(names) != len(set(names)) or len(ignored) != len(set(ignored)) or
            not set(ignored).issubset(names) or sorted(chosen) != sorted(group["names"]) or
            set(chosen) & set(ignored)):
        raise h.GateRejected("selected inventory missing, changed, duplicated or ignored")
    return len(names) - len(chosen)

def selected_passes(h, output, names, filtered):
    # Inherited require_passes requires zero filtered tests. Preserve its strict
    # outcome contract, but explicitly bind this filtered count to --list.
    outcomes = re.findall(r"^test (\S+) \.\.\. (ok|FAILED|ignored)(?:, [^\n]*)?$", output, re.M)
    summaries = re.findall(
        r"^test result: (ok|FAILED)\. (\d+) passed; (\d+) failed; "
        r"(\d+) ignored; (\d+) measured; (\d+) filtered out; finished in [^\n]+$",
        output, re.M)
    starts = re.findall(r"^running (\d+) tests?$", output, re.M)
    if (sorted(outcomes) != sorted((name, "ok") for name in names) or len(summaries) != 1 or
            starts != [str(len(names))] or
            summaries[0] != ("ok", str(len(names)), "0", "0", "0", str(filtered))):
        raise h.GateRejected("selected libtest outcomes/summary/inventory mismatch")
    return {"passed": sorted(names), "filtered": filtered, "ignored": [], "count": len(names)}

def self_test(h):
    sample = b"pinned synthetic support"
    digest = hashlib.sha256(sample).hexdigest()
    assert checked_support_bytes(sample, digest, len(sample)) == sample
    for raw, wanted_hash, wanted_size in ((sample, digest, len(sample) + 1),
            (sample + b"x", digest, len(sample) + 1), (sample, "0" * 64, len(sample)),
            (b"x" * (1024 * 1024 + 1), digest, None)):
        try:
            checked_support_bytes(raw, wanted_hash, wanted_size)
        except RuntimeError:
            pass
        else:
            raise AssertionError("unverified support bytes accepted")
    names = ["one", "two"]
    log = ("running 2 tests\ntest one ... ok\ntest two ... ok\n"
           "test result: ok. 2 passed; 0 failed; 0 ignored; 0 measured; 9 filtered out; finished in 0.00s\n")
    assert selected_passes(h, log, names, 9)["count"] == 2
    for bad in (log.replace("9 filtered", "0 filtered"), log.replace("two ... ok", "two ... FAILED"),
                log.replace("two ... ok", "one ... ok"), log + log,
                log.replace("running 2", "running 0"), log.replace("two ... ok", "two ... ignored"),
                log.replace("2 passed", "1 passed"), log.replace("two ... ok", "foreign ... ok")):
        try:
            selected_passes(h, bad, names, 9)
        except h.GateRejected:
            pass
        else:
            raise AssertionError("invalid filtered log accepted")
    group = {"filter": "one", "names": ["one"]}
    assert selected_inventory(h, "one: test\ntwo: test\n", "", group) == 1
    for listed, ignored in (("one: test\none: test\n", ""), ("two: test\n", ""),
                            ("one: test\n", "one: test\n")):
        try:
            selected_inventory(h, listed, ignored, group)
        except h.GateRejected:
            pass
        else:
            raise AssertionError("invalid selected inventory accepted")

def prepare(h, g, runner, root, env, publication, graph, manifest):
    previous = root.parent / "publication-base"
    h.checkout(runner, "publication-base", previous, "https://github.com/" + REPOSITORY + ".git",
               manifest["publication_base"], env)
    old = h.parse_tree(runner.ok("publication-base-tree",
        ["git", "ls-tree", "-r", "-z", "--full-tree", "HEAD"], previous, env, 30, 2 * 1024 * 1024))
    new = h.parse_tree(runner.ok("publication-tree",
        ["git", "ls-tree", "-r", "-z", "--full-tree", "HEAD"], publication, env, 30, 2 * 1024 * 1024))
    if (h.complete_tree(old) != manifest["publication_base_tree"] or
            set(new) != set(old) | set(manifest["publication_files"]) or
            any(new.get(path) != entry for path, entry in old.items())):
        raise h.GateRejected("publication escaped six additive files")
    h.checkout(runner, "source", root, graph["core"]["repository"], graph["core"]["commit"], env)
    foundation = g.plan_all(h, runner, root, env, publication, graph)["production"][0]
    flat = h.parse_tree(runner.ok("raw-original-tree",
        ["git", "ls-tree", "-r", "-z", "--full-tree", "HEAD"], root, env, 30, 2 * 1024 * 1024))
    original = {path: value.decode() for path, value in foundation.items()}
    for path, expected in manifest["raw_preimages"].items():
        if flat.get(path, {}).get("sha") != expected:
            raise h.GateRejected("raw preimage identity mismatch")
        raw = None if expected is None else h.source_bytes(root, path)
        if raw is not None and h.git_blob(raw) != expected:
            raise h.GateRejected("raw preimage bytes mismatch")
        original[path] = None if raw is None else raw.decode()
    for path, expected in manifest["target_source_blobs"].items():
        raw = original.get(path)
        actual = h.git_blob(raw.encode()) if raw is not None else flat.get(path, {}).get("sha")
        if actual != expected:
            raise h.GateRejected("selected target source identity mismatch: " + path)
    patches = {item["id"]: g.verify_file(h, publication, item) for item in manifest["patches"]}
    plans = {}
    for arm, order in manifest["recipes"].items():
        files = dict(original)
        for key in order:
            h.apply_exact(files, patches[key], [])
        result = h.flat_with_files(flat, files)
        tree = h.complete_tree(result)
        if tree != manifest["trees"][arm]:
            raise h.GateRejected("raw source tree mismatch: " + arm)
        # Include the unchanged raw preimage so pure -> baseline restores the
        # deleted block explicitly; this transition is not production-monotone.
        plans[arm] = {path: value.encode() for path, value in files.items() if value is not None}
    return plans, h.complete_tree(new)

def compile_args(key):
    if key == "boundary":
        return ["cargo", "test", "--locked", "-p", "proteus-core", "--test",
                "execution_boundary", "--no-run", "--message-format=json"]
    package = "proteus-core" if key == "core" else "proteus-contracts"
    return ["cargo", "test", "--locked", "-p", package, "--lib", "--no-run", "--message-format=json"]

def binding(h, g, output, key, root, target):
    if key == "boundary":
        return g.default_integration(h, output, root, target, "execution_boundary",
            "crates/proteus-core/tests/execution_boundary.rs", "proteus-core")["executable"]
    return g.compiled(h, output, key, root, target)

def binary_hash(h, runner, label, binary, root, env):
    output = runner.ok(label, ["sha256sum", binary], root, env, 30)
    expected = h.file_sha(binary)
    if output != expected + "  " + str(binary) + "\n":
        raise h.GateRejected("binary digest output mismatch")
    return expected

def test_groups(h, g, runner, arm, root, target, env, groups):
    result = {}
    for key in dict.fromkeys(group["binary"] for group in groups):
        label = arm + "-" + key
        output = runner.ok(label + "-compile", compile_args(key), root, env, 1800, 24 * 1024 * 1024)
        binary = binding(h, g, output, key, root, target)
        before = binary_hash(h, runner, label + "-hash-before", binary, root, env)
        listed = runner.ok(label + "-inventory", [binary, "--list", "--format", "terse"], root, env, 30)
        ignored = runner.ok(label + "-ignored", [binary, "--list", "--ignored", "--format", "terse"], root, env, 30)
        cases = {}
        for group in [item for item in groups if item["binary"] == key]:
            filtered = selected_inventory(h, listed, ignored, group)
            argv = [binary] + ([] if group["filter"] is None else [group["filter"]]) + ["--test-threads=4"]
            raw = runner.ok(group["id"], argv, root, env, 600, 8 * 1024 * 1024)
            cases[group["id"]] = selected_passes(h, raw, group["names"], filtered)
        after = binary_hash(h, runner, label + "-hash-after", binary, root, env)
        if before != after:
            raise h.GateRejected("compiled executable changed during selected tests")
        result[key] = {"executable": binary, "sha256_before": before, "sha256_after": after, "groups": cases}
    return result

def run(h, g, graph, manifest, manifest_hash, args, publication):
    ctx = guard(h, g)
    work = Path(args.work).resolve()
    work.mkdir(parents=True, exist_ok=False)
    runner = h.Runner(Path(args.evidence).resolve(), work, manifest["resources"]["controller_seconds"])
    env = h.clean_env(work)
    root, target = work / "source", work / "target"
    receipt = {"schema": 1, "status": "INCOMPLETE", "context": ctx, "manifest_sha256": manifest_hash,
        "controller_sha256": manifest["controller_sha256"], "support": manifest["support"],
        "support_argument": str(Path(args.helper).resolve()),
        "source_root": str(root), "target_root": str(target), "work": str(work),
        "trees": manifest["trees"], "resources": manifest["resources"], "stages": runner.records, "arms": {}}
    try:
        receipt["initial_free_bytes"] = shutil.disk_usage(work).free
        if receipt["initial_free_bytes"] < h.INITIAL_FREE_BYTES:
            raise h.InfrastructureError("initial disk reserve below 8 GiB")
        if runner.ok("publication-head", ["git", "rev-parse", "HEAD"], publication, env, 30).strip() != ctx["head"]:
            raise h.GateRejected("publication head mismatch")
        for name in ("rustc", "cargo"):
            version = runner.ok(name + "-version", [name, "-V"], work, env, 30)
            if not version.startswith(name + " 1.95.0 "):
                raise h.GateRejected("wrong pinned Rust toolchain")
        plans, receipt["publication_tree"] = prepare(h, g, runner, root, env, publication, graph, manifest)
        receipt["all_plans_preflight"] = "PASS_BEFORE_SOURCE_REPLACEMENT"
        fixture_state = None
        lane_env = dict(env, CARGO_TARGET_DIR=str(target))
        for arm in ("pure", "baseline", "candidate"):
            h.materialize(runner, arm, root, plans[arm], manifest["trees"][arm], env)
            runner.ok(arm + "-format", ["cargo", "fmt", "--all", "--", "--check"], root, env, 180, 2 * 1024 * 1024)
            before = h.tracked_snapshot(runner, arm + "-source-before", root, env)
            entry = {"tree": manifest["trees"][arm],
                "source_snapshot_before_sha256": h.sha(json.dumps(before, sort_keys=True, separators=(",", ":")).encode())}
            receipt["arms"][arm] = entry
            if arm == "pure":
                # Reference-only fixture, actual stock SDK graph checked by
                # the pinned helper. False means no DCP/npm/stock Modules tests.
                lane_env, receipt["fixture"], fixture_state = g.fixture_setup(
                    h, runner, work, root, env, graph, False)
            entry["binaries"] = test_groups(h, g, runner, arm, root, target, lane_env,
                [item for item in manifest["groups"] if item["arm"] == arm])
            entry["source_snapshot_after_sha256"] = g.postflight(
                h, runner, arm, root, env, before, manifest["trees"][arm])
        g.fixture_postflight(h, runner, fixture_state, receipt["fixture"], env, graph)
        receipt["status"] = "RAW_ARGUMENT_TARGETED_SOURCE_PASS"
    except BaseException as error:
        receipt["status"] = "INFRASTRUCTURE_ERROR" if h.is_infrastructure(error) else "GATE_REJECTED"
        receipt["error"] = type(error).__name__ + ": " + str(error)
        raise
    finally:
        g.write_receipt(Path(args.evidence) / "result.json", receipt)

def audit(h, g, graph, manifest, manifest_hash, args, publication):
    ctx = guard(h, g)
    evidence = Path(args.evidence).resolve()
    receipt = g.strict(g.bounded(evidence / "result.json", 4 * 1024 * 1024))
    if (receipt["status"] != "RAW_ARGUMENT_TARGETED_SOURCE_PASS" or receipt["context"] != ctx or
            receipt["manifest_sha256"] != manifest_hash or receipt["controller_sha256"] != manifest["controller_sha256"] or
            receipt["support"] != manifest["support"] or
            receipt["support_argument"] != str(Path(args.helper).resolve()) or
            receipt["trees"] != manifest["trees"] or
            receipt["resources"] != manifest["resources"] or receipt["initial_free_bytes"] < h.INITIAL_FREE_BYTES or
            receipt["all_plans_preflight"] != "PASS_BEFORE_SOURCE_REPLACEMENT"):
        raise h.GateRejected("foreign, incomplete or incorrect current-run receipt")
    paths, records = h.phase_logs(evidence, receipt)
    if any(item["exit_code"] != 0 for item in records.values()):
        raise h.GateRejected("all commands must pass; no expected reds in this gate")
    work = Path(receipt["work"])
    root, target = work / "source", work / "target"
    if receipt["source_root"] != str(root) or receipt["target_root"] != str(target):
        raise h.GateRejected("source/target paths mismatch")
    def output(label, argv, cwd=root):
        item = records.get(label)
        if item is None or item["argv"] != [str(value) for value in argv] or item["cwd"] != str(cwd):
            raise h.GateRejected("raw command provenance mismatch: " + label)
        return {"code": 0, "output": h.bounded_file(paths[label], h.MAX_TOTAL_OUTPUT).decode("utf-8", "replace")}
    if output("publication-head", ["git", "rev-parse", "HEAD"], publication)["output"].strip() != ctx["head"]:
        raise h.GateRejected("publication raw head mismatch")
    published = h.parse_tree(output("publication-tree",
        ["git", "ls-tree", "-r", "-z", "--full-tree", "HEAD"], publication)["output"])
    previous = h.parse_tree(output("publication-base-tree",
        ["git", "ls-tree", "-r", "-z", "--full-tree", "HEAD"], work / "publication-base")["output"])
    if (h.complete_tree(published) != receipt["publication_tree"] or
            h.complete_tree(previous) != manifest["publication_base_tree"] or
            set(published) != set(previous) | set(manifest["publication_files"]) or
            any(published.get(path) != entry for path, entry in previous.items())):
        raise h.GateRejected("raw additive-publication provenance mismatch")
    positions = {record["stage"]: index for index, record in enumerate(receipt["stages"])}
    ordered = []
    for arm in ("pure", "baseline", "candidate"):
        ordered.append(arm + "-tree")
        groups = [item for item in manifest["groups"] if item["arm"] == arm]
        for key in dict.fromkeys(item["binary"] for item in groups):
            prefix = arm + "-" + key
            ordered += [prefix + "-compile", prefix + "-hash-before", prefix + "-inventory", prefix + "-ignored"]
            ordered += [item["id"] for item in groups if item["binary"] == key]
            ordered.append(prefix + "-hash-after")
        ordered.append(arm + "-final-tree")
    if any(label not in positions for label in ordered) or any(
            positions[left] >= positions[right] for left, right in zip(ordered, ordered[1:])):
        raise h.GateRejected("source/binary evidence order crossed an overwrite boundary")
    if set(receipt["arms"]) != {"pure", "baseline", "candidate"}:
        raise h.GateRejected("source arm inventory mismatch")
    for arm in ("pure", "baseline", "candidate"):
        entry = receipt["arms"][arm]
        if (entry["tree"] != manifest["trees"][arm] or
                entry["source_snapshot_before_sha256"] != entry["source_snapshot_after_sha256"] or
                not re.fullmatch(r"[0-9a-f]{64}", entry["source_snapshot_after_sha256"])):
            raise h.GateRejected("source arm snapshot mismatch")
        for label in (arm + "-tree", arm + "-final-tree"):
            if output(label, ["git", "write-tree"])["output"].strip() != manifest["trees"][arm]:
                raise h.GateRejected("source arm raw tree mismatch")
        for label, argv in ((arm + "-no-unstaged", ["git", "diff", "--quiet"]),
                            (arm + "-no-untracked", ["git", "ls-files", "--others", "--exclude-standard"])):
            if output(label, argv)["output"].strip():
                raise h.GateRejected("source postflight mutation")
        groups = [item for item in manifest["groups"] if item["arm"] == arm]
        if set(entry["binaries"]) != {item["binary"] for item in groups}:
            raise h.GateRejected("compiled binary inventory mismatch")
        for key, item in entry["binaries"].items():
            label = arm + "-" + key
            binary = binding(h, g, output(label + "-compile", compile_args(key))["output"], key, root, target)
            if binary != item["executable"]:
                raise h.GateRejected("compiler-bound executable mismatch")
            listed = output(label + "-inventory", [binary, "--list", "--format", "terse"])["output"]
            ignored = output(label + "-ignored", [binary, "--list", "--ignored", "--format", "terse"])["output"]
            expected_groups = {group["id"] for group in groups if group["binary"] == key}
            if set(item["groups"]) != expected_groups:
                raise h.GateRejected("test group receipt inventory mismatch")
            for suffix in ("before", "after"):
                digest = item["sha256_" + suffix]
                if (not re.fullmatch(r"[0-9a-f]{64}", digest) or
                        output(label + "-hash-" + suffix, ["sha256sum", binary])["output"] != digest + "  " + binary + "\n"):
                    raise h.GateRejected("raw executable digest mismatch")
            if item["sha256_before"] != item["sha256_after"]:
                raise h.GateRejected("executable changed within source arm")
            for group in [value for value in groups if value["binary"] == key]:
                filtered = selected_inventory(h, listed, ignored, group)
                argv = [binary] + ([] if group["filter"] is None else [group["filter"]]) + ["--test-threads=4"]
                parsed = selected_passes(h, output(group["id"], argv)["output"], group["names"], filtered)
                if not g.same_json_evidence(parsed, item["groups"][group["id"]]):
                    raise h.GateRejected("raw selected-test receipt mismatch")
    g.audit_fixture(h, output, records, receipt, graph, root, work, False)
    result = {"schema": 1, "status": "RAW_ARGUMENT_TARGETED_EXACT_PASS", "context": ctx,
        "receipt_sha256": h.file_sha(evidence / "result.json"), "manifest_sha256": manifest_hash,
        "production_tree": manifest["trees"]["pure"], "coverage": manifest["coverage"],
        "performance": "NOT_MEASURED", "raw_stages": len(records)}
    g.write_receipt(Path(args.audit_result), result)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--helper", required=True)
    parser.add_argument("--work")
    parser.add_argument("--evidence")
    parser.add_argument("--audit-result")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    publication = Path(os.environ.get("GITHUB_WORKSPACE", ".")).resolve()
    h, g, graph, manifest, digest = load_support(publication, args.helper)
    if not __debug__:
        raise h.GateRejected("assertions must remain enabled")
    if args.self_test:
        self_test(h)
        print("Support length/hash: positive and 4 rejection controls PASS")
        print("Filtered inventory/outcome parser: positive and 11 rejection controls PASS")
    elif args.audit_result:
        audit(h, g, graph, manifest, digest, args, publication)
    else:
        if not args.work or not args.evidence:
            parser.error("--work and --evidence required")
        run(h, g, graph, manifest, digest, args, publication)

if __name__ == "__main__":
    main()
