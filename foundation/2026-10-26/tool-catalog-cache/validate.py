#!/usr/bin/env python3
"""Validate the pinned reference catalog candidate in fresh, isolated CI roots."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import selectors
import shutil
import signal
import subprocess
import sys
import time
import tomllib

BUNDLE = Path(__file__).resolve().parent
REPOS = {
    "modules": "https://github.com/Proteus-harness/Proteus-modules.git",
    "host": "https://github.com/Proteus-harness/Proteus-core.git",
}
COMMITS = {
    "modules": "0d9c5fd18f04e6e3a083351678065c5f72966792",
    "host": "63454d4e8b1e4e6b26d088fce2a17d46f30390ae",
}
PINNED_CORE = "f3d01053dff6113c31afbd885ef1ab1a8d931d53"
TAIL_BYTES = 65536
MIN_FREE = 2 * 1024**3
INITIAL_FREE = 8 * 1024**3
COMMAND_TIMEOUT = 40 * 60


def relative(root, name):
    part = Path(name)
    if part.is_absolute() or ".." in part.parts or not part.parts:
        raise ValueError(f"Unsafe path: {name}")
    path = root / part
    if not path.resolve().is_relative_to(root.resolve()):
        raise ValueError(f"Path escapes root: {name}")
    return path


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git_blob(path):
    data = path.read_bytes()
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


def check_blobs(root, expected):
    for name, digest in expected.items():
        path = relative(root, name)
        if path.is_symlink() or not path.is_file() or git_blob(path) != digest:
            raise ValueError(f"Git blob mismatch: {name}")


def check_pinned_graph(source):
    cargo = tomllib.loads((source / "Cargo.toml").read_text())
    for name in ("proteus-contracts", "proteus-core", "proteus-module-protocol",
                 "proteus-module-sdk", "proteus-process-host"):
        dependency = cargo["workspace"]["dependencies"][name]
        if dependency.get("git") != REPOS["host"] or dependency.get("rev") != PINNED_CORE:
            raise ValueError(f"Dependency graph changed: {name}")
    lock = tomllib.loads((source / "Cargo.lock").read_text())
    packages = [p for p in lock["package"] if p.get("source", "").startswith(
        "git+" + REPOS["host"])]
    if not packages or any(not p["source"].endswith("#" + PINNED_CORE) for p in packages):
        raise ValueError("Cargo.lock does not retain the pinned Core graph")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("scope", choices=("modules-pinned", "current-host"))
    parser.add_argument("--work-dir", type=Path, required=True)
    parser.add_argument("--evidence-dir", type=Path, required=True)
    args = parser.parse_args()
    work = args.work_dir.resolve()
    evidence = args.evidence_dir.resolve()
    temp = Path(os.environ["RUNNER_TEMP"]).resolve()
    if work.exists() or evidence.exists():
        raise SystemExit("Fresh absent work/evidence roots required; nothing is deleted")
    if not work.is_relative_to(temp) or not evidence.is_relative_to(temp):
        raise SystemExit("Work and evidence must stay inside RUNNER_TEMP")
    if work == evidence or work.is_relative_to(evidence) or evidence.is_relative_to(work):
        raise SystemExit("Work and evidence must be disjoint")
    if shutil.disk_usage(temp).free < INITIAL_FREE:
        raise SystemExit("Need 8 GiB free; no cleanup or deletion attempted")
    work.mkdir(parents=True)
    evidence.mkdir(parents=True)
    manifest_path = BUNDLE / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    result = {
        "schema": 1,
        "scope": args.scope,
        "status": "running",
        "bundle_head": os.environ.get("GITHUB_SHA"),
        "workflow_run_id": os.environ.get("GITHUB_RUN_ID"),
        "workflow_run_attempt": os.environ.get("GITHUB_RUN_ATTEMPT"),
        "manifest_sha256": sha256(manifest_path),
        "commands": [],
        "graphs": {"modules": COMMITS["modules"], "module_sdk_core": PINNED_CORE},
        "claims": {
            "functional_baseline": "Actual unchanged checkout, existing suite",
            "counter": "Authored copied-old lookup algorithm; not an old-checkout benchmark",
            "excluded": ["timing speedup", "RSS improvement", "full workspace", "portable release"],
        },
    }
    env = os.environ.copy()
    for name in ("PROTEUS_TEST_REFERENCE_MODULE", "PROTEUS_TEST_DCP_MODULE",
                 "PROTEUS_MODULES_SOURCE", "PROTEUS_HOOK_SDK_ROOT",
                 "PROTEUS_TEST_HARNESS_ROOT"):
        env.pop(name, None)
    env.update({
        "CARGO_BUILD_JOBS": "2", "CARGO_INCREMENTAL": "0",
        "RUST_TEST_THREADS": "4", "PYTHONDONTWRITEBYTECODE": "1",
        "GIT_TERMINAL_PROMPT": "0", "RUSTUP_TOOLCHAIN": "1.95.0",
        "CARGO_TARGET_DIR": str(work / "target-modules"),
        "CARGO_TERM_COLOR": "never",
    })

    def save():
        (evidence / "result.json").write_text(json.dumps(result, indent=2) + "\n")

    def run(argv, cwd=None, *, phase, required=(), allow_filtered=False, extra_env=None):
        if shutil.disk_usage(temp).free < MIN_FREE:
            raise RuntimeError("2 GiB runtime free-space floor reached; no deletion")
        command = [str(arg) for arg in argv]
        command_env = env | (extra_env or {})
        row = {"phase": phase, "argv": command, "cwd": str(cwd) if cwd else None,
               "status": "running"}
        result["commands"].append(row)
        save()
        print("+ " + " ".join(command), flush=True)
        started = time.monotonic()
        proc = subprocess.Popen(command, cwd=cwd, env=command_env,
                                stdin=subprocess.DEVNULL,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                start_new_session=True)
        tail = b""
        partial = b""
        passed = set()
        failed = set()
        summaries = []

        def observe(line):
            text = line.decode(errors="replace").strip()
            match = re.fullmatch(r"test (\S{1,400}) \.\.\. (ok|FAILED)", text)
            if match:
                names = passed if match[2] == "ok" else failed
                if len(names) >= 10000 and match[1] not in names:
                    raise RuntimeError("Test-name evidence limit exceeded")
                names.add(match[1])
            if text.startswith("test result:"):
                if len(summaries) >= 1000 or len(text) > 1024:
                    raise RuntimeError("Test-summary evidence limit exceeded")
                summaries.append(text)

        aborted = None
        code = None
        selector = selectors.DefaultSelector()
        selector.register(proc.stdout, selectors.EVENT_READ)
        try:
            while selector.get_map():
                if time.monotonic() - started > COMMAND_TIMEOUT:
                    raise TimeoutError("Command exceeded 40-minute limit")
                if shutil.disk_usage(temp).free < MIN_FREE:
                    raise RuntimeError("2 GiB runtime free-space floor reached")
                for key, _ in selector.select(timeout=1):
                    chunk = os.read(key.fileobj.fileno(), 65536)
                    if not chunk:
                        selector.unregister(key.fileobj)
                        continue
                    sys.stdout.buffer.write(chunk)
                    sys.stdout.buffer.flush()
                    tail = (tail + chunk)[-TAIL_BYTES:]
                    partial += chunk
                    lines = partial.split(b"\n")
                    partial = lines.pop()[-TAIL_BYTES:]
                    for line in lines:
                        observe(line)
            if partial:
                observe(partial)
            code = proc.wait(timeout=5)
        except Exception as exc:
            aborted = f"{type(exc).__name__}: {exc}"
            try:
                os.killpg(proc.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(proc.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                try:
                    proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    aborted += "; cleanup deadline exceeded; process reclamation unconfirmed"
            code = proc.poll()
        finally:
            selector.close()
            proc.stdout.close()
            row.update(exit_code=code, elapsed_seconds=round(time.monotonic() - started, 3),
                       log_tail=tail.decode(errors="replace"),
                       observed_passed_tests=sorted(passed),
                       observed_failed_tests=sorted(failed), summaries=summaries)
            row["status"] = "failure" if aborted or code else "success"
            if aborted:
                row["error"] = aborted
            save()
        if aborted or code:
            raise RuntimeError(f"{phase} failed: {aborted or code}")
        if failed or any(s.startswith("test result: FAILED.") for s in summaries):
            row["status"] = "failure"
            save()
            raise RuntimeError(f"{phase}: observed a failed test despite successful exit")
        if required:
            summary = re.fullmatch(
                r"test result: ok\. (\d+) passed; (\d+) failed; (\d+) ignored; "
                r"(\d+) measured; (\d+) filtered out; finished in .+",
                summaries[0],
            ) if len(summaries) == 1 else None
            counts = [int(value) for value in summary.groups()] if summary else None
            if (passed != set(required) or not counts or
                    counts[:4] != [len(required), 0, 0, 0] or
                    (not allow_filtered and counts[4] != 0)):
                row["status"] = "failure"
                save()
                raise RuntimeError(f"{phase}: exact executed inventory/summary mismatch; "
                                   f"missing={set(required) - passed}, extra={passed - set(required)}")
        return tail.decode(errors="replace").strip()

    def checkout(kind):
        spec = manifest["sources"][kind]
        if spec["repository"] != REPOS[kind] or spec["commit"] != COMMITS[kind]:
            raise ValueError(f"Unexpected source identity: {kind}")
        path = work / kind
        run(["git", "init", path], phase=f"{kind}:init")
        run(["git", "remote", "add", "origin", spec["repository"]], path, phase=f"{kind}:remote")
        run(["git", "-c", "credential.helper=", "fetch", "--depth=1", "origin",
             spec["commit"]], path, phase=f"{kind}:fetch")
        run(["git", "checkout", "--detach", "FETCH_HEAD"], path, phase=f"{kind}:checkout")
        if run(["git", "rev-parse", "HEAD"], path, phase=f"{kind}:head") != spec["commit"]:
            raise ValueError("Source commit mismatch")
        check_blobs(path, spec["input_blobs"])
        for name in spec.get("absent", []):
            target = relative(path, name)
            if target.exists() or target.is_symlink():
                raise ValueError(f"New path already exists: {name}")
        result[kind + "_tree"] = run(["git", "rev-parse", "HEAD^{tree}"], path,
                                     phase=f"{kind}:tree")
        if result[kind + "_tree"] != spec["tree"]:
            raise ValueError(f"Source tree mismatch: {kind}")
        return path

    def check_modules(source, phase, candidate=False):
        run(["git", "diff", "--exit-code"], source, phase=phase + ":worktree")
        if candidate:
            check_blobs(source, manifest["output_blobs"])
            tree = run(["git", "write-tree"], source, phase=phase + ":index-tree")
            if tree != result["candidate_tree"]:
                raise ValueError("Candidate index changed during validation")
        else:
            run(["git", "diff", "--cached", "--exit-code"], source, phase=phase + ":index")
            check_blobs(source, manifest["sources"]["modules"]["input_blobs"])
        check_blobs(source, manifest["graph_blobs"])

    def apply_candidate(source):
        patch = relative(BUNDLE, manifest["patch"]["path"])
        data = patch.read_bytes()
        if len(data) != manifest["patch"]["bytes"] or hashlib.sha1(data).hexdigest() != manifest["patch"]["sha1"]:
            raise ValueError("Patch identity mismatch")
        run(["git", "apply", "--check", "--index", patch], source, phase="candidate:apply-check")
        run(["git", "apply", "--index", patch], source, phase="candidate:apply")
        changed = run(["git", "diff", "--cached", "--name-only"], source,
                      phase="candidate:paths").splitlines()
        if sorted(changed) != sorted(manifest["output_blobs"]):
            raise ValueError(f"Unexpected changed paths: {changed}")
        check_blobs(source, manifest["output_blobs"])
        check_blobs(source, manifest["graph_blobs"])
        run(["git", "diff", "--cached", "--check"], source, phase="candidate:whitespace")
        rust_paths = [relative(source, p) for p in changed if p.endswith(".rs")]
        run(["rustfmt", "--check", "--edition", "2024", "--config", "skip_children=true",
             *rust_paths], source, phase="candidate:format")
        result["candidate_tree"] = run(["git", "write-tree"], source, phase="candidate:tree")
        if result["candidate_tree"] != manifest["candidate_tree"]:
            raise ValueError("Candidate full tree differs from reviewed snapshot")

    def worker(host, modules, label):
        output = run(["python3", "-B", "scripts/build_module.py", "--target-dir",
                      work / "target-modules"], host, phase=label + ":build-worker",
                     extra_env={"PROTEUS_MODULES_SOURCE": str(modules)})
        executable = Path(output.splitlines()[-1]).resolve()
        if not executable.is_file() or not executable.is_relative_to(work / "target-modules"):
            raise ValueError("Worker executable outside its dedicated target")
        result[label + "_worker"] = {"path": str(executable), "sha256": sha256(executable),
                                     "module_sdk_core": PINNED_CORE}
        return executable

    save()
    try:
        repo_root = BUNDLE.parents[2]
        for name, expected in manifest["bundle_sha256"].items():
            if sha256(relative(repo_root, name)) != expected:
                raise ValueError(f"Bundle input hash mismatch: {name}")
        rustc = run(["rustc", "--version", "--verbose"], phase="tools:rustc")
        if not rustc.startswith("rustc 1.95.0 "):
            raise ValueError("Expected Rust 1.95.0")
        run(["rustfmt", "--version"], phase="tools:rustfmt")
        node = run(["node", "--version"], phase="tools:node")
        if node != "v22.23.4":
            raise ValueError("Expected Node v22.23.4")
        python = run(["python3", "--version"], phase="tools:python")
        if python != "Python 3.12.15":
            raise ValueError("Expected Python 3.12.15")
        modules = checkout("modules")
        check_pinned_graph(modules)
        required = manifest["required_tests"]
        if args.scope == "modules-pinned":
            command = ["python3", "-B", "scripts/test.py", "-p", "proteus-reference-module",
                       "--test", "conformance"]
            run(command, modules, phase="baseline:real-wire", required=required["conformance"])
            check_modules(modules, "baseline:unchanged-source")
            apply_candidate(modules)
            run(["python3", "-B", "scripts/test.py", "-p", "proteus-reference-module",
                 "--bin", "proteus-reference-module", "exports::tools::tests"],
                modules, phase="candidate:helpers", required=required["helpers"],
                allow_filtered=True)
            run(command, modules, phase="candidate:real-wire", required=required["conformance"])
        else:
            host = checkout("host")
            result["graphs"]["host"] = COMMITS["host"]
            for label in ("baseline", "candidate"):
                if label == "candidate":
                    apply_candidate(modules)
                executable = worker(host, modules, label)
                run(["python3", "-B", "scripts/test.py", "-p", "proteus-core",
                     "--test", "module_swap"], host, phase=label + ":current-host-module-swap",
                    required=required["module_swap"], extra_env={
                        "CARGO_TARGET_DIR": str(work / "target-host"),
                        "PROTEUS_MODULES_SOURCE": str(modules),
                        "PROTEUS_TEST_REFERENCE_MODULE": str(executable),
                    })
                run(["git", "diff", "HEAD", "--exit-code"], host, phase=label + ":host-source-unchanged")
                check_blobs(host, manifest["sources"]["host"]["input_blobs"])
                check_modules(modules, label + ":module-source-unchanged",
                              candidate=(label == "candidate"))
        check_modules(modules, "final:source-and-lock-unchanged", candidate=True)
        check_pinned_graph(modules)
        result["status"] = "success"
    except Exception as exc:
        result["status"] = "failure"
        result["error"] = f"{type(exc).__name__}: {exc}"
        raise
    finally:
        save()


if __name__ == "__main__":
    main()
