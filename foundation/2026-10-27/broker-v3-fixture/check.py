#!/usr/bin/env python3
"""One complete broker_v3 test-only amendment gate; never full compact qualification."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import sys

REPOSITORY = "Qweasd123tg/proteus-modules-dot"
BRANCH = "ci/core-broker-fixture-20261027"
WORKFLOW = ".github/workflows/core-broker-fixture.yml"
COMPACT_SHA = "33c8ec75122e71db5d034410144bac273a4606dbda59ac8e63a205905bcc2c8d"
COMPACT_MANIFEST_SHA = "84e01c0e60b8936054cd1f6e91b7a1bc2bc500b7583160953e1976e9e1e75622"
SOURCE = "crates/proteus-module-protocol/tests/broker_v3.rs"
PASS = "TARGETED_TEST_AMENDMENT_PASS_NOT_FULL_COMPACT_QUALIFICATION"
c = q = None

def digest(raw):
    return hashlib.sha256(raw).hexdigest()

def bounded(path, cap):
    path = Path(path)
    if not path.is_file() or path.is_symlink() or path.stat().st_size > cap:
        raise RuntimeError("missing, indirect or oversized pinned input")
    with path.open("rb") as stream:
        value = stream.read(cap + 1)
    if len(value) > cap:
        raise RuntimeError("pinned input grew beyond cap")
    return value

def support(args):
    global c, q
    raw = bounded(args.compact_controller, 128 * 1024)
    old_raw = bounded(args.compact_manifest, 256 * 1024)
    if digest(raw) != COMPACT_SHA or digest(old_raw) != COMPACT_MANIFEST_SHA:
        raise RuntimeError("immutable compact support mismatch")
    spec = importlib.util.spec_from_file_location("compact_gate_support", args.compact_controller)
    c = importlib.util.module_from_spec(spec)
    exec(compile(raw, str(args.compact_controller), "exec"), c.__dict__)
    h, recipe, foundation = c.support(args)
    q = c.q
    old = q.strict(old_raw)
    c.validate(h, old, foundation)
    return h, recipe, foundation, old

def guard(h):
    ctx = q.context()
    if (os.environ.get("GITHUB_ACTIONS") != "true" or os.environ.get("GITHUB_EVENT_NAME") != "push" or
            os.environ.get("GITHUB_REF") != "refs/heads/" + BRANCH or ctx["repository"] != REPOSITORY or
            ctx["workflow_ref"] != REPOSITORY + "/" + WORKFLOW + "@refs/heads/" + BRANCH or
            not re.fullmatch(r"[0-9a-f]{40}", ctx["head"] or "") or
            not all(re.fullmatch(r"[1-9][0-9]*", ctx[key] or "") for key in ("run_id", "run_attempt"))):
        raise h.GateRejected("exact guarded broker fixture push required")
    return ctx

def validate(h, manifest, old):
    if (manifest["schema"] != 1 or manifest["repository"] != REPOSITORY or manifest["branch"] != BRANCH or
            manifest["workflow"] != WORKFLOW or manifest["controller_sha256"] != h.file_sha(__file__) or
            manifest["source_base_tree"] != old["plans"]["production"]["tree"] or
            len(manifest["cases"]) != 21 or len(set(manifest["cases"])) != 21 or
            "protocol_faults_fail_closed_and_restart_lazily" not in manifest["cases"] or
            manifest["patch"]["source"] != SOURCE):
        raise h.GateRejected("broker fixture package inventory/identity mismatch")
    expected = dict(old["plans"]["production"]["changed_blobs"])
    expected[SOURCE] = manifest["patch"]["postimage_blob"]
    if manifest["plan"]["changed_blobs"] != expected:
        raise h.GateRejected("targeted amendment changed unrelated source")

def compile_argv():
    return ["cargo", "test", "--locked", "-p", "proteus-module-protocol",
            "--test", "broker_v3", "--no-run", "--message-format=json"]

def target(h, output, root, target_root):
    return q.default_integration(h, output, root, target_root, "broker_v3", SOURCE, "proteus-module-protocol")

def inventory(h, listing, ignored, names):
    q.require_inventory(h, listing, ignored, names)
    if set(h.listed_tests(listing)) != set(names) or h.listed_tests(ignored):
        raise h.GateRejected("complete broker target inventory or ignores differ")

def identity(manifest, manifest_hash, ctx):
    return {"schema": 1, "context": ctx, "controller_sha256": manifest["controller_sha256"],
        "manifest_sha256": manifest_hash, "compact_controller_sha256": COMPACT_SHA,
        "compact_manifest_sha256": COMPACT_MANIFEST_SHA, "plan": manifest["plan"],
        "resource_policy": manifest["resources"]}

def run(h, foundation, old, manifest, manifest_hash, args):
    ctx = guard(h)
    work = Path(args.work).resolve()
    work.mkdir(parents=True, exist_ok=False)
    runner = h.Runner(Path(args.evidence).resolve(), work, 2700)
    env = h.clean_env(work)
    receipt = dict(identity(manifest, manifest_hash, ctx), status="INCOMPLETE",
                   source_root=str(work / "source"), target_root=str(work / "target"), stages=runner.records)
    try:
        receipt["initial_free_bytes"] = shutil.disk_usage(work).free
        if receipt["initial_free_bytes"] < h.INITIAL_FREE_BYTES:
            raise h.InfrastructureError("initial hosted disk reserve below 8 GiB")
        publication = Path(os.environ["GITHUB_WORKSPACE"]).resolve()
        if runner.ok("publication-head", ["git", "rev-parse", "HEAD"], publication, env, 10).strip() != ctx["head"]:
            raise h.GateRejected("publication head mismatch")
        previous = work / "publication-base"
        h.checkout(runner, "publication-base", previous, "https://github.com/" + REPOSITORY + ".git",
                   manifest["publication_base"], env)
        prior = h.parse_tree(runner.ok("publication-base-tree", ["git", "ls-tree", "-r", "-z", "--full-tree", "HEAD"],
                                      previous, env, 30, 2 * 1024 * 1024))
        current = h.parse_tree(runner.ok("publication-tree", ["git", "ls-tree", "-r", "-z", "--full-tree", "HEAD"],
                                        publication, env, 30, 2 * 1024 * 1024))
        if (h.complete_tree(prior) != manifest["publication_base_tree"] or
                set(current) != set(prior) | set(manifest["publication_files"]) or
                any(current.get(path) != value for path, value in prior.items())):
            raise h.GateRejected("publication escaped additive test amendment")
        receipt["publication_tree"] = h.complete_tree(current)
        receipt["tools"] = {}
        for name, argv, prefix in (("rustc", ["rustc", "-Vv"], "rustc 1.95.0 "),
                                   ("cargo", ["cargo", "-V"], "cargo 1.95.0 "),
                                   ("python", ["python3", "--version"], "Python 3.")):
            value = runner.ok("version-" + name, argv, work, env, 30).strip()
            if not value.startswith(prefix):
                raise h.GateRejected("target tool version mismatch")
            receipt["tools"][name] = value
        root, target_root = work / "source", work / "target"
        h.checkout(runner, "source", root, foundation["core"]["repository"], foundation["core"]["commit"], env)
        prepared = c.plans(h, runner, root, env, publication, old, foundation)
        base_files, base_identity = prepared["production"]
        if base_identity["tree"] != manifest["source_base_tree"]:
            raise h.GateRejected("compact production base differs")
        pre = h.source_bytes(root, SOURCE)
        if h.git_blob(pre) != manifest["patch"]["preimage_blob"]:
            raise h.GateRejected("broker test preimage differs")
        files = {path: raw.decode() for path, raw in base_files.items()}
        files[SOURCE] = pre.decode()
        patch = q.verify_file(h, publication, manifest["patch"])
        h.apply_exact(files, patch, [])
        flat = h.parse_tree(runner.ok("amendment-original-tree", ["git", "ls-tree", "-r", "-z", "--full-tree", "HEAD"],
                                     root, env, 30, 2 * 1024 * 1024))
        amended = h.flat_with_files(flat, files)
        actual = {"tree": h.complete_tree(amended), "changed_blobs": {
            path: value["sha"] for path, value in amended.items() if value["sha"] != flat.get(path, {}).get("sha")}}
        if actual != manifest["plan"]:
            raise h.GateRejected("complete test-only amendment tree mismatch")
        receipt["all_plans_preflight"] = "PASS_BEFORE_ANY_SOURCE_REPLACEMENT"
        h.materialize(runner, "amendment", root, {path: value.encode() for path, value in files.items()},
                      actual["tree"], env)
        runner.ok("format", ["cargo", "fmt", "--all", "--", "--check"], root, env, 180, 2 * 1024 * 1024)
        before = h.tracked_snapshot(runner, "source-before", root, env)
        receipt["source_snapshot_before_sha256"] = digest(json.dumps(before, sort_keys=True, separators=(",", ":")).encode())
        lane_env = dict(env, CARGO_TARGET_DIR=str(target_root))
        compiled = runner.ok("target-compile", compile_argv(), root, lane_env, 1800, 24 * 1024 * 1024)
        binding = target(h, compiled, root, target_root)
        binary = binding["executable"]
        receipt["binary"] = dict(binding, bytes=Path(binary).stat().st_size, sha256_before=h.file_sha(binary))
        listing = runner.ok("target-list", [binary, "--list", "--format", "terse"], root, lane_env, 30, 512 * 1024)
        ignored = runner.ok("target-ignored", [binary, "--list", "--ignored", "--format", "terse"], root, lane_env, 30, 128 * 1024)
        inventory(h, listing, ignored, manifest["cases"])
        output = runner.ok("target-full", [binary, "--test-threads=4"], root, lane_env, 180, 4 * 1024 * 1024)
        receipt["parsed"] = h.require_passes(output, manifest["cases"], exact_inventory=True)
        receipt["binary"]["sha256_after"] = h.file_sha(binary)
        if receipt["binary"]["sha256_before"] != receipt["binary"]["sha256_after"] or receipt["binary"]["bytes"] != Path(binary).stat().st_size:
            raise h.GateRejected("broker executable changed")
        receipt["source_snapshot_after_sha256"] = q.postflight(h, runner, "amendment", root, env, before, actual["tree"])
        receipt["status"] = PASS
    except BaseException as error:
        receipt["status"] = "INFRASTRUCTURE_ERROR" if h.is_infrastructure(error) else "GATE_REJECTED"
        receipt["error"] = f"{type(error).__name__}: {error}"
        raise
    finally:
        q.write_receipt(Path(args.evidence) / "result.json", receipt)

def audit(h, manifest, manifest_hash, args):
    ctx = guard(h)
    publication = Path(os.environ["GITHUB_WORKSPACE"]).resolve()
    runner = h.Runner(Path(args.audit_evidence).resolve(), publication, 120)
    env = {key: value for key, value in os.environ.items() if key in {"PATH", "LANG", "LC_ALL", "TMPDIR", "TMP", "TEMP"}}
    env.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL="/dev/null", GIT_TERMINAL_PROMPT="0")
    result = dict(identity(manifest, manifest_hash, ctx), status="INCOMPLETE", stages=runner.records)
    try:
        if runner.ok("audit-head", ["git", "rev-parse", "HEAD"], publication, env, 10).strip() != ctx["head"]:
            raise h.GateRejected("audit head mismatch")
        tree = runner.ok("audit-tree", ["git", "rev-parse", "HEAD^{tree}"], publication, env, 10).strip()
        runner.ok("audit-clean", ["git", "diff", "--quiet", "HEAD"], publication, env, 10)
        raw = q.bounded(Path(args.evidence) / "result.json", 4 * 1024 * 1024)
        receipt = q.strict(raw)
        if any(not q.same_json_evidence(receipt.get(key), value) for key, value in identity(manifest, manifest_hash, ctx).items()):
            raise h.GateRejected("foreign targeted receipt")
        if receipt["status"] == "INFRASTRUCTURE_ERROR":
            raise h.InfrastructureError("exact target infrastructure failure: " + receipt.get("error", ""))
        if receipt["status"] != PASS:
            raise h.GateRejected("targeted source phase not qualified: " + receipt.get("error", receipt["status"]))
        if (receipt.get("publication_tree") != tree or receipt.get("all_plans_preflight") != "PASS_BEFORE_ANY_SOURCE_REPLACEMENT" or
                type(receipt.get("initial_free_bytes")) is not int or receipt["initial_free_bytes"] < h.INITIAL_FREE_BYTES):
            raise h.GateRejected("targeted pass lacks publication/preflight/admission evidence")
        paths, records = h.phase_logs(Path(args.evidence), receipt)
        if any(record["exit_code"] != 0 for record in records.values()):
            raise h.GateRejected("targeted gate permits no intended failures")
        root, target_root = Path(receipt["source_root"]), Path(receipt["target_root"])
        work = root.parent
        if not root.is_absolute() or root.name != "source" or work.name != "core-broker-fixture-work" or target_root != work / "target":
            raise h.GateRejected("targeted source isolation mismatch")
        def get(label, argv, cwd=None):
            record = records[label]
            if record["argv"] != [str(x) for x in argv] or record["cwd"] != str(cwd or root):
                raise h.GateRejected("targeted raw command binding mismatch")
            return h.bounded_file(paths[label], h.MAX_TOTAL_OUTPUT).decode("utf-8", "replace")
        for name, argv, prefix in (("rustc", ["rustc", "-Vv"], "rustc 1.95.0 "),
                                   ("cargo", ["cargo", "-V"], "cargo 1.95.0 "),
                                   ("python", ["python3", "--version"], "Python 3.")):
            value = get("version-" + name, argv, work).strip()
            if value != receipt["tools"][name] or not value.startswith(prefix):
                raise h.GateRejected("targeted tool receipt mismatch")
        get("format", ["cargo", "fmt", "--all", "--", "--check"])
        binding = target(h, get("target-compile", compile_argv()), root, target_root)
        stored = receipt["binary"]
        if (any(stored.get(key) != value for key, value in binding.items()) or
                stored.get("sha256_before") != stored.get("sha256_after") or
                not re.fullmatch(r"[0-9a-f]{64}", stored.get("sha256_after", "")) or
                type(stored.get("bytes")) is not int or not 0 < stored["bytes"] <= 256 * 1024 * 1024):
            raise h.GateRejected("target executable/compiler provenance mismatch")
        binary = binding["executable"]
        inventory(h, get("target-list", [binary, "--list", "--format", "terse"]),
                  get("target-ignored", [binary, "--list", "--ignored", "--format", "terse"]), manifest["cases"])
        parsed = h.require_passes(get("target-full", [binary, "--test-threads=4"]), manifest["cases"], exact_inventory=True)
        if not q.same_json_evidence(parsed, receipt["parsed"]):
            raise h.GateRejected("targeted raw outcomes differ")
        if (get("amendment-final-tree", ["git", "write-tree"]).strip() != manifest["plan"]["tree"] or
                get("amendment-no-unstaged", ["git", "diff", "--quiet"]).strip() or
                get("amendment-no-untracked", ["git", "ls-files", "--others", "--exclude-standard"]).strip() or
                receipt.get("source_snapshot_before_sha256") != receipt.get("source_snapshot_after_sha256") or
                not re.fullmatch(r"[0-9a-f]{64}", receipt.get("source_snapshot_after_sha256", ""))):
            raise h.GateRejected("targeted source postflight mismatch")
        result.update(status=PASS, receipt_sha256=digest(raw), publication_tree=tree, passed=parsed["passed"],
                      stages_verified=len(records), minimum_free_bytes=min(x["disk_free_minimum_bytes"] for x in records.values()),
                      scope="Only this complete test target is qualified. Prior failed canonical run and absent postflights remain failures; no full compact qualification or performance claim.")
    except BaseException as error:
        result["status"] = "INFRASTRUCTURE_ERROR" if h.is_infrastructure(error) else "GATE_REJECTED"
        result["error"] = f"{type(error).__name__}: {error}"
        raise
    finally:
        q.write_receipt(Path(args.audit_evidence) / "result.json", result)

def self_test(h, manifest):
    h.self_test()
    h.composition_self_test()
    names = manifest["cases"]
    listing = "".join(name + ": test\n" for name in names)
    inventory(h, listing, "", names)
    for bad_listing, bad_ignored in (
        (listing + "foreign: test\n", ""),
        (listing, names[0] + ": test\n"),
        (listing.replace(names[0] + ": test\n", ""), ""),
        (listing + names[0] + ": test\n", ""),
    ):
        try:
            inventory(h, bad_listing, bad_ignored, names)
        except h.GateRejected:
            pass
        else:
            raise h.GateRejected("target inventory accepted missing/extra/duplicate/ignored case")
    log = "running 21 tests\n" + "".join("test " + name + " ... ok\n" for name in names)
    log += "test result: ok. 21 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 0.00s\n"
    assert h.require_passes(log, names, exact_inventory=True)["passed"] == names
    for bad in (log.replace(names[0], "foreign", 1), log.replace(" ... ok", " ... ignored", 1),
                log.replace(" ... ok", " ... FAILED", 1), log + "test foreign ... ok\n"):
        try:
            h.require_passes(bad, names, exact_inventory=True)
        except h.GateRejected:
            pass
        else:
            raise h.GateRejected("target parser accepted invalid complete inventory")
    print("Exact complete broker target and inherited bounded process/source self-controls PASS")

def main():
    parser = argparse.ArgumentParser()
    for key in ("manifest", "compact-controller", "compact-manifest", "qualified-controller", "qualified-manifest", "helper", "recipe"):
        parser.add_argument("--" + key, required=True)
    mode = parser.add_mutually_exclusive_group(required=True)
    for key in ("run", "audit", "self-test"):
        mode.add_argument("--" + key, action="store_true")
    parser.add_argument("--work")
    parser.add_argument("--evidence")
    parser.add_argument("--audit-evidence")
    args = parser.parse_args()
    if not __debug__:
        raise RuntimeError("assertions required")
    h, recipe, foundation, old = support(args)
    raw = q.bounded(args.manifest, 128 * 1024)
    manifest = q.strict(raw)
    validate(h, manifest, old)
    if args.self_test:
        self_test(h, manifest)
    elif args.run:
        if not args.work or not args.evidence or args.audit_evidence:
            parser.error("source run requires isolated work/evidence paths")
        run(h, foundation, old, manifest, digest(raw), args)
    else:
        if not args.evidence or not args.audit_evidence or args.work:
            parser.error("audit requires only source evidence and separate audit evidence")
        audit(h, manifest, digest(raw), args)

if __name__ == "__main__":
    main()
