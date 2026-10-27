#!/usr/bin/env python3
"""One exact pure compact/raw-parse composition canonical gate; historical controls remain separate."""
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
BRANCH = "ci/core-final-composition-20261027"
WORKFLOW = ".github/workflows/core-final-composition.yml"
COMPACT_SHA = "33c8ec75122e71db5d034410144bac273a4606dbda59ac8e63a205905bcc2c8d"
COMPACT_MANIFEST_SHA = "84e01c0e60b8936054cd1f6e91b7a1bc2bc500b7583160953e1976e9e1e75622"
FINAL_TREE = "44021ca3f2cdf91046345460709a254f04299e52"
EXECUTION_SOURCE = "crates/proteus-core/tests/execution_boundary.rs"
PASS = "EXACT_PURE_FINAL_COMPOSITION_CANONICAL_PASS"
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
        raise h.GateRejected("exact guarded final composition push required")
    return ctx


def requirements(h, manifest, old):
    for key in ("required_full", "required_core", "required_contracts",
                "additional_core", "additional_contracts", "execution_boundary_required"):
        names = manifest[key]
        if (not isinstance(names, list) or not names or any(not isinstance(x, str) or not x for x in names) or
                len(names) != len(set(names))):
            raise h.GateRejected("missing, malformed or duplicate final target requirement")
    if (len(manifest["additional_core"]) != 12 or len(manifest["additional_contracts"]) != 2 or
            len(manifest["execution_boundary_required"]) != 13):
        raise h.GateRejected("shipping raw-parse witness inventory differs")
    expected = {
        "required_full": sorted(set(old["required_full"] + manifest["additional_core"] +
                                    manifest["additional_contracts"] + manifest["execution_boundary_required"])),
        "required_core": sorted(set(old["required_core"] + manifest["additional_core"])),
        "required_contracts": sorted(set(old["required_contracts"] + manifest["additional_contracts"])),
    }
    if (any(manifest[key] != value for key, value in expected.items()) or
            [len(manifest[key]) for key in expected] != [177, 92, 15]):
        raise h.GateRejected("final mandatory inventory lost or added an unreviewed witness")
    return expected

def validate(h, manifest, old):
    if (manifest["schema"] != 1 or manifest["repository"] != REPOSITORY or manifest["branch"] != BRANCH or
            manifest["workflow"] != WORKFLOW or manifest["controller_sha256"] != h.file_sha(__file__) or
            manifest["source_base_tree"] != old["plans"]["production"]["tree"] or
            manifest["plan"]["tree"] != FINAL_TREE or
            [x["source"] for x in manifest["patches"]] != [
                "crates/proteus-module-protocol/tests/broker_v3.rs", "crates/proteus-core/src/core/bound_tools.rs"]):
        raise h.GateRejected("final source package identity mismatch")
    expected = dict(old["plans"]["production"]["changed_blobs"])
    for patch in manifest["patches"]:
        expected[patch["source"]] = patch["postimage_blob"]
    if manifest["plan"]["changed_blobs"] != expected:
        raise h.GateRejected("final composition changed unrelated source")
    requirements(h, manifest, old)





def identity(manifest, manifest_hash, ctx):
    return {"schema": 1, "context": ctx, "controller_sha256": manifest["controller_sha256"],
        "manifest_sha256": manifest_hash, "compact_controller_sha256": COMPACT_SHA,
        "compact_manifest_sha256": COMPACT_MANIFEST_SHA, "qualified_controller_sha256": c.QUALIFIER_SHA,
        "foundation_manifest_sha256": c.FOUNDATION_SHA, "support_sha256": q.HELPER_SHA256,
        "recipe_sha256": q.RECIPE_SHA256, "plan": manifest["plan"],
        "resource_policy": manifest["resources"]}

def canonical_bindings(h, output, root, target_root, foundation):
    custom, bindings = c.canonical_bindings(h, output, root, target_root, foundation)
    bindings["execution_boundary"] = q.default_integration(
        h, output, root, target_root, "execution_boundary", EXECUTION_SOURCE, "proteus-core")
    return custom, bindings

def boundaries(h, output, manifest, foundation, bindings):
    result = c.boundaries(h, output, manifest, foundation, bindings)
    result["execution_boundary"] = h.require_passes(
        q.sections(h, output, bindings)["execution_boundary"],
        manifest["execution_boundary_required"], exact_inventory=True)
    return result

def run(h, foundation, old, manifest, manifest_hash, args):
    ctx = guard(h)
    work = Path(args.work).resolve()
    work.mkdir(parents=True, exist_ok=False)
    runner = h.Runner(Path(args.evidence).resolve(), work, 6600)
    env = h.clean_env(work)
    receipt = dict(identity(manifest, manifest_hash, ctx), status="INCOMPLETE",
                   source_root=str(work / "source"), target_root=str(work / "target"), stages=runner.records,
                   environment_policy={"build_jobs": env["CARGO_BUILD_JOBS"], "rust_test_threads": env["RUST_TEST_THREADS"],
                                       "npm_audit": False, "secrets_inherited": False})
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
            raise h.GateRejected("publication escaped additive final composition package")
        receipt["publication_tree"] = h.complete_tree(current)
        for item in manifest["documents"]:
            q.verify_file(h, publication, item)
        receipt["tools"] = {}
        versions = [("rustc", ["rustc", "-Vv"]), ("cargo", ["cargo", "-V"])]
        versions += [("node", ["node", "--version"]), ("bubblewrap", ["/usr/bin/bwrap", "--version"])]
        for label, argv in versions:
            receipt["tools"][label] = runner.ok("version-" + label, argv, work, env, 30).strip()
        if not receipt["tools"]["rustc"].startswith("rustc 1.95.0 ") or not receipt["tools"]["cargo"].startswith("cargo 1.95.0 "):
            raise h.GateRejected("wrong official Rust toolchain")
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
        root, target_root = work / "source", work / "target"
        h.checkout(runner, "source", root, foundation["core"]["repository"], foundation["core"]["commit"], env)
        prepared = c.plans(h, runner, root, env, publication, old, foundation)
        base_files, base_identity = prepared["production"]
        if base_identity["tree"] != manifest["source_base_tree"]:
            raise h.GateRejected("compact production base differs")
        files = {path: raw.decode() for path, raw in base_files.items()}
        for patch in manifest["patches"]:
            path = patch["source"]
            pre = files[path].encode() if path in files else h.source_bytes(root, path)
            if h.git_blob(pre) != patch["preimage_blob"] or digest(pre) != patch["preimage_sha256"]:
                raise h.GateRejected("final patch preimage differs: " + path)
            files[path] = pre.decode()
            h.apply_exact(files, q.verify_file(h, publication, patch), [])
            post = files[path].encode()
            if h.git_blob(post) != patch["postimage_blob"] or digest(post) != patch["postimage_sha256"]:
                raise h.GateRejected("final patch postimage differs: " + path)
        flat = h.parse_tree(runner.ok("amendment-original-tree", ["git", "ls-tree", "-r", "-z", "--full-tree", "HEAD"],
                                     root, env, 30, 2 * 1024 * 1024))
        amended = h.flat_with_files(flat, files)
        actual = {"tree": h.complete_tree(amended), "changed_blobs": {
            path: value["sha"] for path, value in amended.items() if value["sha"] != flat.get(path, {}).get("sha")}}
        if actual != manifest["plan"]:
            raise h.GateRejected("complete final composition tree mismatch")
        receipt["all_plans_preflight"] = "PASS_BEFORE_ANY_SOURCE_REPLACEMENT"
        h.materialize(runner, "amendment", root, {path: value.encode() for path, value in files.items()},
                      actual["tree"], env)
        runner.ok("format", ["cargo", "fmt", "--all", "--", "--check"], root, env, 180, 2 * 1024 * 1024)
        before = h.tracked_snapshot(runner, "source-before", root, env)
        receipt["source_snapshot_before_sha256"] = digest(json.dumps(before, sort_keys=True, separators=(",", ":")).encode())
        lane_env, receipt["fixture"], state = c.fixture(h, runner, work, root, env, foundation)
        output = runner.ok("canonical-compile", [sys.executable, *foundation["canonical_harness"]["compile_arguments"]],
                           root, lane_env, 1800, 24 * 1024 * 1024)
        custom, bindings = canonical_bindings(h, output, root, target_root, foundation)
        binaries = {**{key: value["executable"] for key, value in custom.items()},
                    **{key: value["executable"] for key, value in bindings.items()}}
        receipt.update(canonical_binaries=custom, boundary_binaries=bindings,
                       binary_sha256_before={key: h.file_sha(path) for key, path in binaries.items()},
                       binary_bytes_before={key: Path(path).stat().st_size for key, path in binaries.items()})
        output = runner.ok("canonical-full", [sys.executable, "scripts/test.py", "full"],
                           root, lane_env, 1800, 40 * 1024 * 1024)
        receipt["canonical_full"] = h.require_canonical_passes(output, manifest["required_full"],
            foundation["canonical_harness"], custom, foundation["allowed_ignored"])
        if set(receipt["canonical_full"]["ignored"]) != set(foundation["allowed_ignored"]):
            raise h.GateRejected("canonical ignore set changed")
        receipt["boundaries"] = boundaries(h, output, manifest, foundation, bindings)
        receipt["binary_sha256_after"] = {key: h.file_sha(path) for key, path in binaries.items()}
        receipt["binary_bytes_after"] = {key: Path(path).stat().st_size for key, path in binaries.items()}
        if (receipt["binary_sha256_before"] != receipt["binary_sha256_after"] or
                receipt["binary_bytes_before"] != receipt["binary_bytes_after"]):
            raise h.GateRejected("canonical executable changed")
        q.fixture_postflight(h, runner, state, receipt["fixture"], env, foundation)
        receipt["source_snapshot_after_sha256"] = q.postflight(h, runner, "amendment", root, env, before, actual["tree"])
        receipt["status"] = PASS
    except BaseException as error:
        receipt["status"] = "INFRASTRUCTURE_ERROR" if h.is_infrastructure(error) else "GATE_REJECTED"
        receipt["error"] = f"{type(error).__name__}: {error}"
        raise
    finally:
        q.write_receipt(Path(args.evidence) / "result.json", receipt)


def audit(h, foundation, old, manifest, manifest_hash, args):
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
            raise h.GateRejected("foreign final canonical receipt")
        if receipt["status"] == "INFRASTRUCTURE_ERROR":
            raise h.InfrastructureError("exact canonical infrastructure failure: " + receipt.get("error", ""))
        if receipt["status"] != PASS:
            raise h.GateRejected("final canonical source phase not qualified: " + receipt.get("error", receipt["status"]))
        if (receipt.get("publication_tree") != tree or receipt.get("all_plans_preflight") != "PASS_BEFORE_ANY_SOURCE_REPLACEMENT" or
                type(receipt.get("initial_free_bytes")) is not int or receipt["initial_free_bytes"] < h.INITIAL_FREE_BYTES):
            raise h.GateRejected("canonical pass lacks publication/preflight/admission evidence")
        if receipt.get("environment_policy") != {"build_jobs": "2", "rust_test_threads": "4",
                "npm_audit": False, "secrets_inherited": False}:
            raise h.GateRejected("canonical environment policy differs")
        paths, records = h.phase_logs(Path(args.evidence), receipt)
        if any(record["exit_code"] != 0 for record in records.values()):
            raise h.GateRejected("pure canonical gate permits no intended failures")
        root, target_root = Path(receipt["source_root"]), Path(receipt["target_root"])
        work = root.parent
        if not root.is_absolute() or root.name != "source" or work.name != "core-final-composition-work" or target_root != work / "target":
            raise h.GateRejected("final source isolation mismatch")
        def output(label, argv=None, cwd=None):
            if label not in records:
                raise h.GateRejected("required stage missing: " + label)
            record = records[label]
            if argv is not None and (record["argv"] != [str(x) for x in argv] or record["cwd"] != str(cwd or root)):
                raise h.GateRejected("canonical raw command binding mismatch: " + label)
            return {"code": record["exit_code"], "output": h.bounded_file(paths[label], h.MAX_TOTAL_OUTPUT).decode("utf-8", "replace")}
        def get(label, argv, cwd=None):
            return output(label, argv, cwd)["output"]
        for name, argv, prefix in (("rustc", ["rustc", "-Vv"], "rustc 1.95.0 "),
                                   ("cargo", ["cargo", "-V"], "cargo 1.95.0 ")):
            value = get("version-" + name, argv, work).strip()
            if value != receipt["tools"][name] or not value.startswith(prefix):
                raise h.GateRejected("canonical tool receipt mismatch")
        for name, argv, expected in (("node", ["node", "--version"], "v22.18.0"),
                                     ("bubblewrap", ["/usr/bin/bwrap", "--version"], "bubblewrap 0.13.1")):
            value = get("version-" + name, argv, work).strip()
            if value != expected or receipt["tools"][name] != value:
                raise h.GateRejected("canonical prerequisite version mismatch")
        if get("sandbox-capabilities", ["getcap", "/usr/bin/bwrap"], work).strip():
            raise h.GateRejected("sandbox file capabilities changed")
        log = get("sandbox-evidence", ["cat", work.parent / "core-current-bwrap-evidence.txt"], work)
        q.sandbox_evidence(h, log, receipt["sandbox_binary_sha256"])
        if digest(log.encode()) != receipt["sandbox_receipt_sha256"]:
            raise h.GateRejected("sandbox prerequisite receipt mismatch")
        get("format", ["cargo", "fmt", "--all", "--", "--check"])
        custom, bindings = canonical_bindings(h, get("canonical-compile",
            [sys.executable, *foundation["canonical_harness"]["compile_arguments"]]), root, target_root, foundation)
        hashes, sizes = receipt["binary_sha256_before"], receipt["binary_bytes_before"]
        if (not q.same_json_evidence(custom, receipt["canonical_binaries"]) or
                not q.same_json_evidence(bindings, receipt["boundary_binaries"]) or
                hashes != receipt["binary_sha256_after"] or sizes != receipt["binary_bytes_after"] or
                set(hashes) != set(custom) | set(bindings) or set(sizes) != set(hashes) or
                any(not re.fullmatch(r"[0-9a-f]{64}", value) for value in hashes.values()) or
                any(type(size) is not int or not 0 < size <= 256 * 1024 * 1024 for size in sizes.values())):
            raise h.GateRejected("canonical compiler/default-feature/executable provenance mismatch")
        log = get("canonical-full", [sys.executable, "scripts/test.py", "full"])
        parsed = h.require_canonical_passes(log, manifest["required_full"],
            foundation["canonical_harness"], custom, foundation["allowed_ignored"])
        if (not q.same_json_evidence(parsed, receipt["canonical_full"]) or
                set(parsed["ignored"]) != set(foundation["allowed_ignored"]) or
                not q.same_json_evidence(boundaries(h, log, manifest, foundation, bindings), receipt["boundaries"])):
            raise h.GateRejected("canonical target-bound raw outcomes differ")
        c.fixture_audit(h, output, records, receipt, foundation, root, work)
        if (get("amendment-final-tree", ["git", "write-tree"]).strip() != manifest["plan"]["tree"] or
                get("amendment-no-unstaged", ["git", "diff", "--quiet"]).strip() or
                get("amendment-no-untracked", ["git", "ls-files", "--others", "--exclude-standard"]).strip() or
                receipt.get("source_snapshot_before_sha256") != receipt.get("source_snapshot_after_sha256") or
                not re.fullmatch(r"[0-9a-f]{64}", receipt.get("source_snapshot_after_sha256", ""))):
            raise h.GateRejected("final source postflight mismatch")
        if os.environ.get("FINAL_SOURCE_STEP_RESULT") != "success":
            raise h.InfrastructureError("exact current source step did not succeed")
        result.update(status=PASS, receipt_sha256=digest(raw), publication_tree=tree,
                      canonical=parsed, boundaries=receipt["boundaries"], required_full=len(manifest["required_full"]),
                      stages_verified=len(records), minimum_free_bytes=min(x["disk_free_minimum_bytes"] for x in records.values()),
                      scope="One pure final composition canonical full with exact target/source/fixture/executable postflights. Historical controls and failures remain separate; no release performance claim.")
    except BaseException as error:
        result["status"] = "INFRASTRUCTURE_ERROR" if h.is_infrastructure(error) else "GATE_REJECTED"
        result["error"] = f"{type(error).__name__}: {error}"
        raise
    finally:
        q.write_receipt(Path(args.audit_evidence) / "result.json", result)


def self_test(h, manifest, old):
    h.self_test()
    h.composition_self_test()
    requirements(h, manifest, old)
    mutations = []
    for key in ("required_full", "required_core", "required_contracts"):
        missing = json.loads(json.dumps(manifest))
        missing[key] = missing[key][1:]
        mutations.append(missing)
        duplicate = json.loads(json.dumps(manifest))
        duplicate[key].append(duplicate[key][0])
        mutations.append(duplicate)
    wrong = json.loads(json.dumps(manifest))
    wrong["execution_boundary_required"][0] = "foreign_case"
    mutations.append(wrong)
    for bad in mutations:
        try:
            requirements(h, bad, old)
        except h.GateRejected:
            pass
        else:
            raise h.GateRejected("mandatory inventory self-control accepted a mutation")
    names = manifest["execution_boundary_required"]
    body = "".join("test " + name + " ... ok\n" for name in names)
    body += "test result: ok. 13 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 0.00s\n"
    binding = {"execution_boundary": {"executable": "/evidence/execution_boundary",
                                      "cargo_label": "tests/execution_boundary.rs"}}
    log = "     Running tests/execution_boundary.rs (/evidence/execution_boundary)\n" + body
    section = q.sections(h, log, binding)["execution_boundary"]
    assert h.require_passes(section, names, exact_inventory=True)["passed"] == names
    for bad in (log.replace("tests/execution_boundary.rs", "tests/foreign.rs", 1),
                log.replace("test " + names[0] + " ... ok\n", ""),
                log.replace(" ... ok", " ... ignored", 1),
                log + "test foreign_case ... ok\n"):
        try:
            section = q.sections(h, bad, binding)["execution_boundary"]
            h.require_passes(section, names, exact_inventory=True)
        except h.GateRejected:
            pass
        else:
            raise h.GateRejected("target-bound raw parser accepted a mutation")
    print("Final 177-name inventory, execution-boundary section and inherited bounded self-controls PASS")

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
        self_test(h, manifest, old)
    elif args.run:
        if not args.work or not args.evidence or args.audit_evidence:
            parser.error("source run requires isolated work/evidence paths")
        run(h, foundation, old, manifest, digest(raw), args)
    else:
        if not args.evidence or not args.audit_evidence or args.work:
            parser.error("audit requires only source evidence and separate audit evidence")
        audit(h, foundation, old, manifest, digest(raw), args)

if __name__ == "__main__":
    main()
