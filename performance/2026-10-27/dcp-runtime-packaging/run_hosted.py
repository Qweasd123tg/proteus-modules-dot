#!/usr/bin/env python3
"""Bounded isolated-branch Node packaging proof. Never runs npm audit or publishes code."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time

MODULES = "0d9c5fd18f04e6e3a083351678065c5f72966792"
HARNESS = "f3d01053dff6113c31afbd885ef1ab1a8d931d53"
SHIPPING_HARNESS = "63454d4e8b1e4e6b26d088fce2a17d46f30390ae"
BUNDLE_SHA256 = "605e302fcf0cd734b0213ae1638aadc75b432e4ea6b2760f23c026e90267831c"
HERE = Path(__file__).resolve().parent
REPORT = {"schema": 1, "status": "running", "commands": [], "claims": {
    "scope": "Linux x64 Node.js packaging only; no portable consumer or full Rust workspace proof.",
    "security": "Zod 4.1.8 remains embedded; this is not vulnerability remediation.",
    "audit": "No npm advisory POST. All npm operations use no-audit and ignore-scripts where applicable."}}
ENV = {}
EVIDENCE = None

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def write(name, value):
    (EVIDENCE / name).write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")

def run(label, command, cwd=None, expect=0, timeout=180, env=None):
    start = time.monotonic()
    child = subprocess.Popen(command, cwd=cwd, env=env or ENV, stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE, start_new_session=True)
    try:
        stdout, stderr = child.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        os.killpg(child.pid, signal.SIGKILL)
        stdout, stderr = child.communicate()
        REPORT["commands"].append({"label": label, "argv": [str(x) for x in command], "timeout": True})
        raise RuntimeError(label + " exceeded its deadline")
    record = {"label": label, "argv": [str(x) for x in command], "exitCode": child.returncode,
              "seconds": round(time.monotonic() - start, 3), "stdoutBytes": len(stdout), "stderrBytes": len(stderr)}
    REPORT["commands"].append(record)
    for suffix, data in [("stdout", stdout), ("stderr", stderr)]:
        (EVIDENCE / (label + "." + suffix + ".txt")).write_bytes(data[:512 * 1024])
    if len(stdout) + len(stderr) > 1024 * 1024:
        raise RuntimeError(label + " output exceeds the bounded capture budget")
    if (expect == 0 and child.returncode != 0) or (expect != 0 and child.returncode == 0):
        raise RuntimeError(label + " unexpected exit code " + str(child.returncode))
    return stdout.decode("utf-8", errors="strict")

def fetch(repository, revision, path, label):
    path.mkdir()
    run(label + "-init", ["git", "init", "--quiet", str(path)])
    run(label + "-fetch", ["git", "-C", str(path), "-c", "credential.helper=", "fetch", "--quiet",
        "--depth=1", "https://github.com/Proteus-harness/" + repository + ".git", revision], timeout=240)
    run(label + "-checkout", ["git", "-C", str(path), "checkout", "--quiet", "--detach", "FETCH_HEAD"])
    assert run(label + "-revision", ["git", "-C", str(path), "rev-parse", "HEAD"]).strip() == revision

def inventory(path):
    records = []
    for file in sorted(path.rglob("*"), key=lambda item: item.relative_to(path).as_posix()):
        name = file.relative_to(path).as_posix()
        if file.is_symlink():
            records.append({"path": name, "type": "symlink", "target": os.readlink(file)})
        elif file.is_file():
            records.append({"path": name, "type": "file", "bytes": file.stat().st_size, "sha256": digest(file)})
    return {"schema": 1, "bytes": sum(item.get("bytes", 0) for item in records),
            "regularFiles": sum(item["type"] == "file" for item in records), "files": records}

def tests(label, root, expected_files):
    files = sorted(root.glob("tests/*.test.mjs"))
    assert {file.name for file in files} == set(expected_files)
    output = run(label, ["node", "--no-global-search-paths", "--test", "--test-reporter=tap",
                         *[str(path) for path in files]], cwd=root, timeout=180)
    counts = {}
    for key in ("tests", "pass", "fail", "cancelled", "skipped", "todo"):
        match = re.search(r"^# " + key + r" (\d+)$", output, re.MULTILINE)
        if match is None:
            raise RuntimeError("missing TAP total: " + key)
        counts[key] = int(match[1])
    assert counts["tests"] > 0 and counts["tests"] == counts["pass"]
    assert all(counts[key] == 0 for key in ("fail", "cancelled", "skipped", "todo"))
    REPORT.setdefault("tests", {})[label] = counts

def main():
    global ENV, EVIDENCE
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work", required=True, type=Path)
    parser.add_argument("--evidence", required=True, type=Path)
    args = parser.parse_args()
    args.work.mkdir()
    EVIDENCE = args.evidence
    EVIDENCE.mkdir()
    assert shutil.disk_usage(args.work).free >= 4 * 1024 ** 3, "need 4 GiB free; no cleanup is attempted"
    home = args.work / "isolated-home"
    home.mkdir()
    userconfig, globalconfig = home / "npm-user.conf", home / "npm-global.conf"
    userconfig.touch()
    globalconfig.touch()
    ENV = {"PATH": os.environ["PATH"], "HOME": str(home), "XDG_DATA_HOME": str(home / "data"),
           "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8", "TZ": "UTC", "PYTHONDONTWRITEBYTECODE": "1",
           "GIT_TERMINAL_PROMPT": "0", "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": "/dev/null",
           "npm_config_audit": "false", "npm_config_fund": "false", "npm_config_update_notifier": "false",
           "npm_config_registry": "https://registry.npmjs.org/", "npm_config_cache": str(args.work / "npm-cache"),
           "npm_config_userconfig": str(userconfig), "npm_config_globalconfig": str(globalconfig)}
    try:
        assert run("node-version", ["node", "--version"]).strip() == "v22.23.4"
        REPORT["npmVersion"] = run("npm-version", ["npm", "--no-audit", "--version"]).strip()
        REPORT["modulesRevision"], REPORT["harnessRevision"] = MODULES, HARNESS
        REPORT["bundleSha256"] = digest(HERE / "source-bundle.json")
        assert REPORT["bundleSha256"] == BUNDLE_SHA256
        source, core = args.work / "baseline-source", args.work / "harness"
        fetch("Proteus-modules", MODULES, source, "modules")
        fetch("Proteus-core", HARNESS, core, "harness")
        shipping_core = args.work / "shipping-harness"
        fetch("Proteus-core", SHIPPING_HARNESS, shipping_core, "shipping-harness")
        REPORT["shippingHarnessRevision"] = SHIPPING_HARNESS
        ENV["PROTEUS_TEST_HARNESS_ROOT"] = str(core)
        apply = [sys.executable, "-B", "-I", str(HERE / "apply.py"), "--source", str(source),
                 "--bundle", str(HERE / "source-bundle.json"), "--sha256", BUNDLE_SHA256]
        wrong_base = list(apply)
        wrong_base[wrong_base.index("--source") + 1] = str(shipping_core)
        run("reject-wrong-base", wrong_base + ["--output", str(args.work / "rejected-base")], expect=1)
        assert not (args.work / "rejected-base").exists()
        bad = list(apply)
        bad[-1] = "0" * 64
        run("reject-wrong-bundle-hash", bad + ["--output", str(args.work / "rejected-hash")], expect=1)
        assert not (args.work / "rejected-hash").exists()
        dirty = source / "untracked-packaging-negative-control"
        dirty.write_text("only this fixture", encoding="utf-8")
        try:
            run("reject-dirty-source", apply + ["--output", str(args.work / "rejected-dirty")], expect=1)
        finally:
            dirty.unlink()
        assert not (args.work / "rejected-dirty").exists()
        tampered = json.loads((HERE / "source-bundle.json").read_text(encoding="utf-8"))
        next(item for item in tampered["files"] if item["originalGitBlob"])["originalGitBlob"] = "0" * 40
        bad_bundle = args.work / "bad-base-blob.json"
        bad_bundle.write_text(json.dumps(tampered), encoding="utf-8")
        bad_apply = [sys.executable, "-B", "-I", str(HERE / "apply.py"), "--source", str(source),
                     "--bundle", str(bad_bundle), "--sha256", digest(bad_bundle)]
        run("reject-wrong-original-blob", bad_apply + ["--output", str(args.work / "rejected-blob")], expect=1)
        assert not (args.work / "rejected-blob").exists()
        output = args.work / "candidate"
        run("apply-candidate", apply + ["--output", str(output)])
        run("reject-existing-output", apply + ["--output", str(output)], expect=1)
        baseline, candidate = source / "hook/dcp", output / "tree/hook/dcp"
        old = json.loads((baseline / "package-lock.json").read_text())
        new = json.loads((candidate / "package-lock.json").read_text())
        assert old["packages"].keys() == new["packages"].keys()
        for name in old["packages"]:
            for key in ("version", "resolved", "integrity"):
                assert old["packages"][name].get(key) == new["packages"][name].get(key), (name, key)
        assert new["packages"][""]["dependencies"] == {"@anthropic-ai/tokenizer": "0.0.4"}
        assert new["packages"][""]["devDependencies"]["@tarquinen/opencode-dcp"] == "3.2.0"
        original_tests = ["module.test.mjs", "worker.test.mjs", "composition.test.mjs", "cache-composition.test.mjs"]
        for label, root in [("baseline", baseline), ("candidate", candidate)]:
            run(label + "-install", ["npm", "ci", "--ignore-scripts", "--no-audit", "--no-fund"], cwd=root, timeout=300)
            run(label + "-build", ["npm", "--no-audit", "--no-fund", "run", "build"], cwd=root)
        hashes = {}
        for name in ("worker.js", "module.js"):
            a, b = digest(baseline / "dist" / name), digest(candidate / "dist" / name)
            assert a == b, "packaging changed runtime JavaScript: " + name
            hashes[name] = a
        REPORT["unchangedDistSha256"] = hashes
        tests("baseline-original-tests", baseline, original_tests)
        tests("candidate-before-prune-tests", candidate, original_tests + ["packaging.test.mjs"])
        # Rebuild the original shipping dependency classification, without esbuild dev dependencies.
        baseline_stage = args.work / "baseline-stage"
        baseline_stage.mkdir()
        for name in ("src", "dist", "tests", "README.md", "build.mjs", "package.json", "package-lock.json", "node_modules"):
            src, dst = baseline / name, baseline_stage / name
            if src.is_dir(): shutil.copytree(src, dst, symlinks=True)
            else: shutil.copy2(src, dst)
        run("baseline-production-prune", ["npm", "prune", "--omit=dev", "--ignore-scripts", "--no-audit",
                                          "--no-fund", "--offline"], cwd=baseline_stage)
        baseline_inventory = inventory(baseline_stage)
        write("baseline-shipping-inventory.json", baseline_inventory)
        stage = args.work / "candidate-stage"
        run("candidate-production-stage", ["npm", "--no-audit", "--no-fund", "run", "package:runtime", "--", str(stage)], cwd=candidate)
        for suffix in ("before-prune.json", "after-prune.json", "prune-summary.json"):
            shutil.copy2(Path(str(stage) + "." + suffix), EVIDENCE / ("candidate." + suffix))
        # This root is never a descendant of either installation or the checkout.
        isolated = Path(tempfile.mkdtemp(prefix="proteus-dcp-relocated-", dir="/tmp"))
        relocated = isolated / "runtime"
        stage.rename(relocated)
        for ancestor in relocated.parents:
            assert not (ancestor / "node_modules").exists(), "runtime can fall back to ancestor node_modules"
        runtime_env = dict(ENV)
        runtime_home = isolated / "home"
        runtime_home.mkdir()
        runtime_env["HOME"], runtime_env["XDG_DATA_HOME"] = str(runtime_home), str(runtime_home / "data")
        (baseline_stage / "packaging").mkdir()
        shutil.copy2(candidate / "packaging/probe.mjs", baseline_stage / "packaging/probe.mjs")
        baseline_probe = json.loads(run("baseline-direct-tokenizer-worker-probe",
            ["node", "--no-global-search-paths", "packaging/probe.mjs"], cwd=baseline_stage))
        candidate_probe = json.loads(run("relocated-direct-tokenizer-worker-probe",
            ["node", "--no-global-search-paths", "packaging/probe.mjs"], cwd=relocated, env=runtime_env))
        assert baseline_probe == candidate_probe, "tokenizer/protocol baseline mismatch"
        REPORT["relocatedProbe"] = candidate_probe
        previous_env = ENV
        ENV = runtime_env
        try:
            tests("relocated-original-and-packaging-tests", relocated, original_tests + ["packaging.test.mjs"])
            ENV["PROTEUS_TEST_HARNESS_ROOT"] = str(shipping_core)
            try:
                tests("relocated-shipping-harness-tests", relocated, original_tests + ["packaging.test.mjs"])
            finally:
                ENV["PROTEUS_TEST_HARNESS_ROOT"] = str(core)
            wasm = relocated / "node_modules/tiktoken/lite/tiktoken_bg.wasm"
            REPORT["wasmSha256"] = digest(wasm)
            hidden = wasm.with_suffix(".wasm.negative-control")
            wasm.rename(hidden)
            try:
                run("missing-wasm-must-fail", ["node", "--no-global-search-paths", "packaging/probe.mjs"],
                    cwd=relocated, expect=1)
                assert "wasm" in (EVIDENCE / "missing-wasm-must-fail.stderr.txt").read_text().lower()
            finally:
                hidden.rename(wasm)
            assert digest(wasm) == REPORT["wasmSha256"]
            worker = relocated / "dist/worker.js"
            original_worker = worker.read_bytes()
            for label, suffix in [
                ("abnormal-worker-exit-must-fail", b"\nprocess.exitCode = 23;\n"),
                ("late-malformed-frame-must-fail", b'\nprocess.stdout.write("late malformed frame\\n");\n'),
            ]:
                try:
                    worker.write_bytes(original_worker + suffix)
                    run(label, ["node", "--no-global-search-paths", "packaging/probe.mjs"],
                        cwd=relocated, expect=1)
                finally:
                    worker.write_bytes(original_worker)
            assert digest(worker) == REPORT["unchangedDistSha256"]["worker.js"]
        finally:
            ENV = previous_env
        final_inventory = inventory(relocated)
        write("final-relocated-inventory.json", final_inventory)
        REPORT["shippingBytes"] = {"baseline": baseline_inventory["bytes"], "candidate": final_inventory["bytes"],
                                  "netReduction": baseline_inventory["bytes"] - final_inventory["bytes"]}
        for name in ("esbuild-metafile.json", "embedded-packages.json", "source-inventory.json"):
            shutil.copy2(relocated / "dist/provenance" / name, EVIDENCE / name)
        embedded = json.loads((EVIDENCE / "embedded-packages.json").read_text())
        assert any(item["path"] == "node_modules/zod" and item["version"] == "4.1.8" for item in embedded["packages"])
        assert not (relocated / "node_modules/zod").exists()
        assert not (relocated / "node_modules/@tarquinen/opencode-dcp").exists()
        assert not (relocated / "node_modules/esbuild").exists()
        assert (relocated / "dist/provenance/upstream/opencode-dcp/lib").is_dir()
        assert (relocated / "dist/provenance/package-notices/node_modules/@opencode-ai/plugin/LICENSE.upstream").is_file()
        assert run("source-remains-clean", ["git", "-C", str(source), "status", "--porcelain=v1",
                                          "--untracked-files=all"]).strip() == ""
        REPORT["status"] = "passed"
        REPORT["remainingGate"] = "Consumer portable rebuild and launcher integration at the shipping Core/desktop revisions."
    except BaseException as error:
        REPORT["status"], REPORT["error"] = "failed", str(error)
        raise
    finally:
        # Keep public lock diagnostics if npm canonicalized metadata before a failed stage.
        observed_lock = args.work / "candidate-stage/package-lock.json"
        if observed_lock.is_file():
            shutil.copy2(observed_lock, EVIDENCE / "candidate-stage-observed-package-lock.json")
            REPORT["observedStageLockSha256"] = digest(observed_lock)
        write("result.json", REPORT)
        assert sum(path.stat().st_size for path in EVIDENCE.rglob("*") if path.is_file()) < 32 * 1024 * 1024

if __name__ == "__main__":
    main()
