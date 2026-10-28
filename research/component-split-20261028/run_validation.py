#!/usr/bin/env python3
"""One bounded hosted validation; never imports or invokes upstream runners.

No retries, caches, profiles changes, full workspace tests, Core/Desktop binary,
portable packaging, DCP preparation or model execution. Fresh source and target.
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
import time

HERE = Path(__file__).resolve().parent
MODULES_URL = "https://github.com/Proteus-harness/Proteus-modules.git"
BASE_SHA = "56571639c804443dbca58e054fff8631ecb8b312"
BASE_TREE = "93d0c3eb6fbd6a94c03d2abb88a6bd37e7eb287a"
SDK_SHA = "1f533a13f20a93bf164f7c8a169553b0b219bb51"
TOOLCHAIN = "1.95.0"
BUDGET_SECONDS = 1200
MAX_LOG_BYTES = 8 * 1024 * 1024
STAGE_NAMES = (
    "source", "static_graph", "controller_tests", "wire_controller_tests", "format",
    "plan_graph", "reference_graph", "adapter_tests", "plan_tests",
    "plan_release", "reference_release", "artifact_identity_before",
    "wire_parity", "artifact_identity_after", "source_identity_after",
)


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def artifact(path):
    return {"path": str(path), "sha256": sha256(path), "size_bytes": path.stat().st_size}


def terminate_group(process):
    # Waiting for the group leader alone does not establish descendant cleanup.
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    try:
        process.wait(timeout=2)
    except subprocess.TimeoutExpired:
        pass
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    process.wait(timeout=2)


def parse_graph(raw, expected_root):
    nodes = []
    for line in raw.splitlines():
        match = re.match(r"^(\d+)::([A-Za-z0-9_-]+) v([^ :]+)(?: [^\n]*)?::[^\n]*$", line)
        if not match:
            raise ValueError(f"unrecognized cargo tree line: {line[:180]!r}")
        nodes.append({"depth": int(match[1]), "package": match[2], "version": match[3], "line": line})
    if not nodes or nodes[0]["depth"] != 0 or nodes[0]["package"] != expected_root:
        raise ValueError("cargo tree root mismatch")
    packages = sorted({node["package"] for node in nodes})
    forbidden = {"proteus-core", "proteus-desktop", "proteus-native"}
    if expected_root == "proteus-plan-module":
        forbidden |= {"proteus-reference-module", "file-tools", "git-tools", "shell-tool",
                      "model-pack", "coding-workflow", "memory-pack", "sqlite-memory"}
    if forbidden.intersection(packages):
        raise ValueError(f"forbidden selected graph packages: {sorted(forbidden.intersection(packages))}")
    return {"root": expected_root, "packages": packages, "nodes": nodes,
            "claim": "Cargo selected normal/build dependency graph; not exact compiled build-unit proof"}


class Validation:
    def __init__(self, work, evidence):
        self.work = work.resolve()
        self.evidence = evidence.resolve()
        self.evidence.mkdir(parents=True, exist_ok=True)
        self.started = time.monotonic()
        self.deadline = self.started + BUDGET_SECONDS
        self.module = self.work / "candidate"
        self.report = {"schema": 1, "status": "running", "stages": {
            name: {"status": "not_run"} for name in STAGE_NAMES}, "commands": [],
            "limits": {"wall_seconds": BUDGET_SECONDS, "cargo_jobs": 2,
                       "log_bytes_per_command": MAX_LOG_BYTES, "automatic_retries": 0},
            "run": {name: os.environ.get(name) for name in (
                "GITHUB_REPOSITORY", "GITHUB_SHA", "GITHUB_RUN_ID", "GITHUB_RUN_ATTEMPT")}}
        self.env = dict(os.environ, CARGO_BUILD_JOBS="2", RUST_TEST_THREADS="2",
                        CARGO_INCREMENTAL="0", CARGO_TARGET_DIR=str(self.work / "target"),
                        GIT_TERMINAL_PROMPT="0", CARGO_NET_RETRY="0",
                        RUSTUP_TOOLCHAIN=TOOLCHAIN, PYTHONDONTWRITEBYTECODE="1")
        self.serial = 0
        self.save()

    def save(self):
        self.report["elapsed_seconds"] = round(time.monotonic() - self.started, 3)
        (self.evidence / "result.json").write_text(json.dumps(self.report, indent=2) + "\n")

    def command(self, stage, argv, cwd=None, timeout=120):
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("overall validation time budget exhausted; no retry")
        self.serial += 1
        name = f"{self.serial:02d}-{stage}"
        record = {"stage": stage, "argv": argv, "cwd": str(cwd or self.work),
                  "timeout_seconds": round(min(timeout, remaining), 3), "status": "running"}
        self.report["commands"].append(record)
        self.save()
        start = time.monotonic()
        deadline = start + min(timeout, remaining)
        streams = {"stdout": bytearray(), "stderr": bytearray()}
        try:
            process = subprocess.Popen(argv, cwd=cwd or self.work, env=self.env,
                                       stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                       stderr=subprocess.PIPE, start_new_session=True)
        except OSError as exc:
            record.update(status="fail", error=f"{type(exc).__name__}: {exc}",
                          elapsed_seconds=round(time.monotonic() - start, 3))
            self.save()
            raise
        selector = selectors.DefaultSelector()
        selector.register(process.stdout, selectors.EVENT_READ, "stdout")
        selector.register(process.stderr, selectors.EVENT_READ, "stderr")
        error = None
        try:
            while selector.get_map():
                if time.monotonic() >= deadline:
                    raise TimeoutError("command deadline exceeded; no retry")
                for key, _ in selector.select(min(0.2, max(0, deadline - time.monotonic()))):
                    data = os.read(key.fd, 65536)
                    if not data:
                        selector.unregister(key.fileobj)
                    else:
                        streams[key.data].extend(data)
                        if sum(map(len, streams.values())) > MAX_LOG_BYTES:
                            raise RuntimeError("command output budget exceeded")
            process.wait(timeout=max(0.01, deadline - time.monotonic()))
            if process.returncode:
                raise RuntimeError(f"command exited {process.returncode}")
        except Exception as exc:
            error = exc
        finally:
            try:
                terminate_group(process)
            except Exception as cleanup_error:
                record["cleanup_error"] = f"{type(cleanup_error).__name__}: {cleanup_error}"
                error = error or cleanup_error
            selector.close()
            process.stdout.close()
            process.stderr.close()
            for channel, data in streams.items():
                path = self.evidence / f"{name}.{channel}.log"
                path.write_bytes(data)
                record[channel] = artifact(path)
            record.update(status="fail" if error else "pass", exit_code=process.returncode,
                          elapsed_seconds=round(time.monotonic() - start, 3))
            if error:
                record["error"] = f"{type(error).__name__}: {error}"
            self.save()
        if error:
            raise error
        return bytes(streams["stdout"]).decode("utf-8", errors="strict")

    def stage(self, name, callback, dependencies=()):
        failed = [dep for dep in dependencies if self.report["stages"][dep]["status"] != "pass"]
        if failed:
            self.report["stages"][name] = {"status": "not_run", "reason": "failed prerequisites", "dependencies": failed}
            self.save()
            return
        try:
            value = callback()
            self.report["stages"][name] = {"status": "pass", "evidence": value}
        except Exception as exc:
            self.report["stages"][name] = {"status": "fail", "error": f"{type(exc).__name__}: {exc}"}
        self.save()

    def verify_source_files(self, manifest, phase):
        records = []
        for item in manifest["files"]:
            key = "source_sha256" if phase == "before" else "candidate_sha256"
            path = self.module / item["path"]
            expected = item[key]
            actual = sha256(path) if path.is_file() else None
            if actual != expected:
                raise ValueError(f"{phase} source identity mismatch: {item['path']}")
            records.append({"path": item["path"], "sha256": actual})
        return records

    def prepare(self):
        if self.work.exists():
            raise ValueError("work directory already exists; refusing stale source/target reuse")
        self.work.mkdir(parents=True)
        manifest = json.loads((HERE / "source-manifest.json").read_text())
        if (manifest["base_sha"], manifest["base_tree"], manifest["core_dependency_sha"]) != (BASE_SHA, BASE_TREE, SDK_SHA):
            raise ValueError("unexpected source base/tree/SDK identity")
        if sha256(HERE / "component-source.patch") != manifest["patch_sha256"]:
            raise ValueError("source patch hash mismatch")
        # Bind every delivered controller/fixture file before invoking any of them.
        payload = json.loads((HERE / "payload-sha256.json").read_text())
        for relative, digest in payload.items():
            if sha256(HERE / relative) != digest:
                raise ValueError(f"delivery payload hash mismatch: {relative}")
        self.report["payload_sha256"] = payload
        self.report["source_manifest"] = manifest
        delivery = HERE.parents[1]
        self.report["delivery_identity"] = {
            "commit": self.command("source", ["git", "rev-parse", "HEAD"], delivery).strip(),
            "tree": self.command("source", ["git", "rev-parse", "HEAD^{tree}"], delivery).strip()}
        if self.report["delivery_identity"]["commit"] != os.environ.get("GITHUB_SHA"):
            raise ValueError("delivery checkout does not match exact workflow head")
        self.report["rustc"] = self.command("source", ["rustc", f"+{TOOLCHAIN}", "--version", "--verbose"])
        self.report["cargo"] = self.command("source", ["cargo", f"+{TOOLCHAIN}", "--version"])
        self.command("source", ["git", "init", "--quiet", str(self.module)])
        self.command("source", ["git", "fetch", "--no-tags", "--depth=1", MODULES_URL, BASE_SHA], self.module, 180)
        if self.command("source", ["git", "rev-parse", "FETCH_HEAD"], self.module).strip() != BASE_SHA:
            raise ValueError("fetched commit mismatch")
        self.command("source", ["git", "checkout", "--detach", "--quiet", "FETCH_HEAD"], self.module)
        if self.command("source", ["git", "rev-parse", "HEAD^{tree}"], self.module).strip() != BASE_TREE:
            raise ValueError("fetched source tree mismatch")
        before = self.verify_source_files(manifest, "before")
        (self.work / "upstream").mkdir()
        for name in ("Cargo.toml", "Cargo.lock"):
            (self.work / "upstream" / name).write_bytes((self.module / name).read_bytes())
        self.command("source", ["git", "apply", "--check", "--index", str(HERE / "component-source.patch")], self.module)
        self.command("source", ["git", "apply", "--index", str(HERE / "component-source.patch")], self.module)
        self.command("source", ["git", "diff", "--cached", "--check"], self.module)
        changed = self.command("source", ["git", "diff", "--cached", "--name-only"], self.module).splitlines()
        if sorted(changed) != sorted(item["path"] for item in manifest["files"]):
            raise ValueError("applied path set mismatch")
        applied_tree = self.command("source", ["git", "write-tree"], self.module).strip()
        if applied_tree != manifest["candidate_tree"]:
            raise ValueError("applied full source tree mismatch")
        return {"before": before, "after": self.verify_source_files(manifest, "after"), "applied_tree": applied_tree}

    def cargo(self, stage, args, timeout=360):
        return self.command(stage, ["cargo", f"+{TOOLCHAIN}", *args], self.module, timeout)

    def graph(self, stage, package):
        raw = self.cargo(stage, ["tree", "--locked", "--manifest-path", str(self.module / "Cargo.toml"),
                                "--edges", "normal,build", "--prefix", "depth", "--format", "::{p}::{f}",
                                "--color", "never", "-p", package], 180)
        graph = parse_graph(raw, package)
        (self.evidence / f"{stage}.json").write_text(json.dumps(graph, indent=2) + "\n")
        return {"root": package, "packages": graph["packages"], "claim": graph["claim"]}

    def release(self, stage, package, component, timeout):
        package_id = self.cargo(stage, ["pkgid", "--locked", "-p", package], 60).strip()
        raw = self.cargo(stage, ["build", "--locked", "--release", "-p", package,
                                 "--bin", package, "--message-format=json"], timeout)
        expected_source = (self.module / "components" / component / "src/main.rs").resolve()
        selected = []
        finished = []
        for line in raw.splitlines():
            message = json.loads(line)
            if message.get("reason") == "build-finished":
                finished.append(message.get("success"))
            if message.get("reason") != "compiler-artifact":
                continue
            if "bin" not in message.get("target", {}).get("kind", []):
                continue
            if message["package_id"] != package_id or message["target"]["name"] != package:
                raise ValueError("unexpected executable artifact in selected release")
            if message["profile"].get("test") is not False:
                raise ValueError("test artifact cannot qualify a release binary")
            if Path(message["target"]["src_path"]).resolve() != expected_source:
                raise ValueError("compiled executable source path mismatch")
            executable = Path(message["executable"]).resolve()
            if executable != (self.work / "target/release" / package).resolve():
                raise ValueError("executable escaped the fresh selected release target")
            selected.append({"package_id": package_id, "target": message["target"],
                             "profile": message["profile"], "fresh": message["fresh"],
                             "artifact": artifact(executable)})
        if len(finished) != 1 or finished[0] is not True or len(selected) != 1:
            raise ValueError("missing/ambiguous Cargo successful selected binary artifact")
        return selected[0]

    def binaries(self):
        return {package: artifact(Path(self.report["stages"][stage]["evidence"]["artifact"]["path"]))
                for package, stage in (("proteus-plan-module", "plan_release"),
                                       ("proteus-reference-module", "reference_release"))}

    def parity(self):
        self.command("wire_parity", [sys.executable, "-B", str(HERE / "tools/component_wire_parity.py"),
                     "--reference", self.report["stages"]["reference_release"]["evidence"]["artifact"]["path"],
                     "--candidate", self.report["stages"]["plan_release"]["evidence"]["artifact"]["path"],
                     "--output", str(self.evidence / "parity-report.json")], timeout=135)
        path = self.evidence / "parity-report.json"
        report = json.loads(path.read_text())
        if report.get("status") != "passed" or report.get("modules_baseline") != BASE_SHA or report.get("sdk_revision") != SDK_SHA:
            raise ValueError("wire report status/source identity mismatch")
        if not report.get("scenarios") or any(row["status"] != "passed" for row in report["scenarios"]):
            raise ValueError("wire report has missing/unpassed scenarios")
        return {"report": artifact(path), "scenarios": [{"name": row["name"], "status": row["status"]}
                                                        for row in report["scenarios"]]}

    def finish_source(self):
        manifest = self.report["source_manifest"]
        files = self.verify_source_files(manifest, "after")
        self.command("source_identity_after", ["git", "diff", "--exit-code"], self.module)
        tree = self.command("source_identity_after", ["git", "write-tree"], self.module).strip()
        if tree != manifest["candidate_tree"]:
            raise ValueError("source tree changed during validation")
        return {"files": files, "tree": tree}

    def execute(self):
        self.stage("source", self.prepare)
        self.stage("static_graph", lambda: self.command("static_graph", [sys.executable, "-B", str(HERE / "graph/verify_component_graph.py"), str(self.work)], timeout=30), ("source",))
        self.stage("controller_tests", lambda: self.command("controller_tests", [sys.executable, "-B", "-m", "unittest", "-v", "test_validation_controls"], HERE, 60), ("source",))
        self.stage("wire_controller_tests", lambda: self.command("wire_controller_tests", [sys.executable, "-B", "-m", "unittest", "-v", "test_component_wire_parity"], HERE / "tools", 60), ("source",))
        # Formatting failure remains required, but must not suppress compile diagnostics.
        self.stage("format", lambda: self.cargo("format", ["fmt", "--check", "-p", "proteus-tool-adapter", "-p", "proteus-plan-module", "-p", "proteus-reference-module"], 60), ("source",))
        self.stage("plan_graph", lambda: self.graph("plan_graph", "proteus-plan-module"), ("source", "static_graph"))
        self.stage("reference_graph", lambda: self.graph("reference_graph", "proteus-reference-module"), ("source", "static_graph"))
        self.stage("adapter_tests", lambda: self.cargo("adapter_tests", ["test", "--locked", "-p", "proteus-tool-adapter", "--lib", "--", "--nocapture"]), ("source", "static_graph", "plan_graph"))
        self.stage("plan_tests", lambda: self.cargo("plan_tests", ["test", "--locked", "-p", "proteus-plan-module", "--bin", "proteus-plan-module", "--", "--nocapture"]), ("source", "static_graph", "plan_graph"))
        self.stage("plan_release", lambda: self.release("plan_release", "proteus-plan-module", "plan-module", 480), ("source", "static_graph", "plan_graph"))
        self.stage("reference_release", lambda: self.release("reference_release", "proteus-reference-module", "process-module", 600), ("source", "static_graph", "reference_graph"))
        self.stage("artifact_identity_before", self.binaries, ("plan_release", "reference_release"))
        self.stage("wire_parity", self.parity, ("artifact_identity_before", "wire_controller_tests", "controller_tests"))
        def after():
            actual = self.binaries()
            if actual != self.report["stages"]["artifact_identity_before"]["evidence"]:
                raise ValueError("binary identities changed during wire run")
            return actual
        self.stage("artifact_identity_after", after, ("artifact_identity_before",))
        self.stage("source_identity_after", self.finish_source, ("source",))
        self.report["status"] = "pass" if all(stage["status"] == "pass" for stage in self.report["stages"].values()) else "fail"
        self.save()
        print(json.dumps({"status": self.report["status"], "stages": {k: v["status"] for k, v in self.report["stages"].items()}}, indent=2))
        return 0 if self.report["status"] == "pass" else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work-dir", required=True, type=Path)
    parser.add_argument("--evidence-dir", required=True, type=Path)
    args = parser.parse_args()
    if args.work_dir.resolve() == args.evidence_dir.resolve() or args.work_dir.resolve() in args.evidence_dir.resolve().parents:
        parser.error("evidence must be outside the fresh work directory")
    return Validation(args.work_dir, args.evidence_dir).execute()


if __name__ == "__main__":
    raise SystemExit(main())
