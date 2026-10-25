#!/usr/bin/env python3
"""Validate only the three authored examples; Python 3.11+, installed Rust 1.95.0.

No installation, shell command evaluation, foreign test suite, or cache cleanup.
Exit 0 = every required check passed; 1 = failed; 2 = incomplete/not executed.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import time
import tomllib

RUST = "1.95.0"
SDK_GIT = "https://github.com/Proteus-harness/Proteus-core.git"
SDK_REV = "3f36a003b4f3fde2242fc80f7aedac00dd127d1d"
SDK_SOURCE = f"git+{SDK_GIT}?rev={SDK_REV}#{SDK_REV}"
CARGO = ["rustup", "run", RUST, "cargo"]  # No --install: absence must fail closed.


@dataclass(frozen=True)
class Example:
    folder: str
    binary: str
    wire_test: str | None = None


EXAMPLES = (
    Example("hermes-verify-evidence", "proteus-example-hermes-verify-evidence",
            "external_binary_wire_v3_hook_v6_and_fixture_evidence"),
    Example("pi-ready-steps", "proteus-pi-ready-steps"),
    Example("letta-evidence-blocks", "proteus-example-letta-evidence-blocks",
            "executable_wire_v3_provider_v4_selection_catalog_errors_and_late_cancel"),
)
SUMMARY = re.compile(r"test result: (ok|FAILED)\. (\d+) passed; (\d+) failed; (\d+) ignored;")


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def source_evidence(directory: Path) -> dict:
    paths = {path for path in directory.iterdir() if path.is_file()
             and path.suffix in {".rs", ".toml", ".lock", ".json", ".py"}}
    for name in ("src", "tests", ".cargo"):
        folder = directory / name
        if folder.is_dir():
            paths.update(path for path in folder.rglob("*") if path.is_file())
    hashes = {path.relative_to(directory).as_posix(): digest(path) for path in sorted(paths)}
    encoded = json.dumps(hashes, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return {"source_sha256": hashlib.sha256(encoded).hexdigest(), "source_files": hashes}


def outcome(records: list[dict]) -> tuple[str, int]:
    if any(record["status"] == "failed" for record in records):
        return "failed", 1
    if not records or any(record["status"] != "passed" for record in records):
        return "incomplete", 2
    return "passed", 0


def preflight(root: Path, example: Example) -> dict:
    directory = root / "examples" / example.folder
    manifest_path, lock_path = directory / "Cargo.toml", directory / "Cargo.lock"
    manifest = tomllib.loads(manifest_path.read_text(encoding="utf-8"))
    lock = tomllib.loads(lock_path.read_text(encoding="utf-8"))
    dependency = manifest.get("dependencies", {}).get("proteus-module-sdk", {})
    if not isinstance(dependency, dict) or dependency.get("git") != SDK_GIT or dependency.get("rev") != SDK_REV:
        raise ValueError("SDK dependency is not pinned to the expected official Git revision")
    if "path" in dependency or "branch" in dependency or "tag" in dependency:
        raise ValueError("SDK path/branch/tag overrides are not permitted")
    if manifest.get("package", {}).get("name") != example.binary:
        raise ValueError("unexpected package identity")
    if manifest.get("workspace") != {}:
        raise ValueError("expected an independent empty [workspace], not external workspace members")
    if manifest.get("patch") or manifest.get("replace"):
        raise ValueError("dependency source overrides are not permitted")
    sdk = [item for item in lock.get("package", []) if item.get("name") == "proteus-module-sdk"]
    if len(sdk) != 1 or sdk[0].get("source") != SDK_SOURCE:
        raise ValueError("lockfile does not resolve exactly the pinned official SDK")
    if example.wire_test and example.wire_test not in (directory / "tests" / "wire.rs").read_text(encoding="utf-8"):
        raise ValueError("required authored real-binary wire test source is absent")
    return {"manifest_sha256": digest(manifest_path), "lock_sha256": digest(lock_path),
            **source_evidence(directory)}


def test_evidence(output: str, wire_test: str | None) -> dict:
    summaries = SUMMARY.findall(output)
    if not summaries:
        raise ValueError("cargo exited successfully but no executed Rust test summaries were found")
    passed = sum(int(item[1]) for item in summaries)
    failed = sum(int(item[2]) for item in summaries)
    ignored = sum(int(item[3]) for item in summaries)
    if passed < 1 or failed or ignored or any(item[0] != "ok" for item in summaries):
        raise ValueError(f"tests cannot be reported as a full pass: passed={passed}, failed={failed}, ignored={ignored}")
    if wire_test and not re.search(rf"^test {re.escape(wire_test)} \.\.\. ok$", output, re.MULTILINE):
        raise ValueError(f"required real-binary smoke test did not pass: {wire_test}")
    return {"passed": passed, "failed": failed, "ignored": ignored,
            "wire_smoke": wire_test, "wire_smoke_repeated": False}


def build_binary(output: str, binary_name: str) -> Path:
    paths: set[Path] = set()
    for line in output.splitlines():
        try:
            message = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(message, dict):
            continue
        target = message.get("target", {})
        if (message.get("reason") == "compiler-artifact" and target.get("name") == binary_name
                and "bin" in target.get("kind", []) and message.get("executable")):
            paths.add(Path(message["executable"]).resolve(strict=True))
    if len(paths) != 1:
        raise ValueError(f"expected exactly one compiler-reported binary for {binary_name}, found {len(paths)}")
    binary = paths.pop()
    if not binary.is_file():
        raise ValueError("compiler-reported binary is not a file")
    return binary


def smoke_evidence(output: str) -> dict:
    report = json.loads(output)
    require(isinstance(report, dict) and report.get("schema_version") == 1
            and report.get("status") == "passed", "smoke did not emit a success report")
    checks = report.get("checks_executed")
    require(isinstance(checks, list) and len(checks) == 14
            and all(isinstance(check, str) and check for check in checks)
            and len(set(checks)) == len(checks), "expected 14 distinct executed Pi wire checks")
    return {"checks_executed": checks, "count": len(checks)}


def stop_command(process: subprocess.Popen) -> tuple[str, str | None]:
    """Bounded cleanup, including a process-group-exit race and inherited pipes."""
    problems = []
    try:
        if os.name == "posix":
            os.killpg(process.pid, signal.SIGKILL)
        else:
            process.kill()
    except ProcessLookupError:
        pass  # An already-exited group is the only ignored signal failure.
    except OSError as error:
        problems.append(f"termination could not be verified: {error}")
    try:
        output, _ = process.communicate(timeout=5)
    except subprocess.TimeoutExpired as error:
        output = error.output or ""
        if isinstance(output, bytes):
            output = output.decode("utf-8", errors="replace")
        problems.append("cleanup pipe deadline exceeded; descendant termination is unverified")
        if process.stdout is not None:
            process.stdout.close()
        try:
            process.wait(timeout=1)
        except subprocess.TimeoutExpired:
            problems.append("child reap deadline exceeded")
    return output, "; ".join(problems) or None


class Runner:
    def __init__(self, root: Path, report: Path, timeout: float):
        self.root, self.report, self.timeout = root, report, timeout
        self.env = dict(os.environ)
        self.env["CARGO_TERM_COLOR"] = "never"
        # A relative caller path is resolved once, not separately in each example.
        target = Path(self.env.get("CARGO_TARGET_DIR", str(root / "target"))).expanduser().resolve()
        self.env["CARGO_TARGET_DIR"] = str(target)
        self.log_dir = report.parent / "logs"
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.replacements = [(str(target), "$CARGO_TARGET_DIR"), (sys.executable, "python3")]
        for name in ("CARGO_HOME", "RUSTUP_HOME"):
            if self.env.get(name):
                self.replacements.append((str(Path(self.env[name]).resolve()), f"${name}"))
        self.replacements.append((str(root), "."))
        self.replacements.sort(key=lambda pair: len(pair[0]), reverse=True)
        self.data = {"schema_version": 1, "started_at": now(), "status": "running",
                     "scope": "three-authored-examples-only", "rust_toolchain": RUST,
                     "sdk_revision": SDK_REV, "root": ".", "target_dir": "$CARGO_TARGET_DIR",
                     "runner_sha256": digest(Path(__file__)),
                     "pi_smoke_sha256": digest(Path(__file__).with_name("smoke_pi_wire.py")),
                     "checks": [], "not_covered": ["Core host assembly/config validation",
                     "real verification receipts", "live models/tools/network", "foreign project suites",
                     "end-to-end in-flight cancellation/concurrency", "release/optimized profile"]}
        self.save()

    def save(self) -> None:
        self.report.write_text(self.normalize(json.dumps(self.data, ensure_ascii=False, indent=2)) + "\n", encoding="utf-8")

    def normalize(self, text: str) -> str:
        for original, replacement in self.replacements:
            text = text.replace(original, replacement)
        return text

    def record(self, example: str, check: str, status: str, **details) -> dict:
        result = {"example": example, "check": check, "status": status, **details}
        self.data["checks"].append(result)
        self.save()
        print(f"[{status}] {example}: {check}", flush=True)
        return result

    def command(self, example: str, check: str, command: list[str], cwd: Path) -> tuple[dict, str]:
        started = time.monotonic()
        log_path = self.log_dir / f"{example}-{check}.log"
        print(f"[run] {example}: {' '.join(command)}", flush=True)
        status, returncode, output, reason, cleanup = "failed", None, "", None, None
        process = None
        try:
            process = subprocess.Popen(command, cwd=cwd, env=self.env, stdout=subprocess.PIPE,
                                       stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace",
                                       start_new_session=(os.name == "posix"))
            output, _ = process.communicate(timeout=self.timeout)
            returncode = process.returncode
            status = "passed" if returncode == 0 else "failed"
        except (subprocess.TimeoutExpired, KeyboardInterrupt) as error:
            if process is not None:
                # Terminate only this command's own group; never unrelated builds.
                output, cleanup = stop_command(process)
                returncode = process.returncode
            reason = "interrupted" if isinstance(error, KeyboardInterrupt) else "timeout"
            if isinstance(error, KeyboardInterrupt):
                status = "not_run"
        except OSError as error:
            reason = str(error)
        log_path.write_text(self.normalize(output), encoding="utf-8")
        result = self.record(example, check, status, command=command, cwd=str(cwd),
                             returncode=returncode, elapsed_seconds=round(time.monotonic() - started, 3),
                             log=str(log_path), reason=reason, cleanup_warning=cleanup)
        if reason == "interrupted":
            raise KeyboardInterrupt
        return result, output

    def verify(self, result: dict, operation) -> object | None:
        if result["status"] != "passed":
            return None
        try:
            value = operation()
        except (OSError, ValueError, KeyError, TypeError) as error:
            result.update(status="failed", reason=str(error))
            self.save()
            return None
        return value

    def run(self) -> int:
        rust, version = self.command("environment", "rustc", ["rustup", "run", RUST, "rustc", "--version"], self.root)
        self.verify(rust, lambda: require(version.startswith(f"rustc {RUST} "), "unexpected Rust version"))
        cargo, cargo_version = self.command("environment", "cargo", CARGO + ["--version"], self.root)
        self.verify(cargo, lambda: require(cargo_version.startswith(f"cargo {RUST} "), "unexpected Cargo version"))
        fmt, _ = self.command("environment", "rustfmt", ["rustup", "run", RUST, "rustfmt", "--version"], self.root)
        if fmt["status"] != "passed":
            fmt.update(status="not_run", reason="rustfmt is unavailable; runner does not install components")
            self.save()
        ready = rust["status"] == cargo["status"] == "passed"
        for example in EXAMPLES:
            directory = self.root / "examples" / example.folder
            try:
                initial_source = preflight(self.root, example)
                self.record(example.folder, "source-pin-and-lock", "passed", **initial_source)
            except (OSError, ValueError, TypeError) as error:
                self.record(example.folder, "source-pin-and-lock", "failed", reason=str(error))
                for check in ("fmt", "test", "build", "binary-smoke"):
                    self.record(example.folder, check, "not_run", reason="source/lock preflight failed")
                continue
            if not ready:
                for check in ("fmt", "test", "build", "binary-smoke"):
                    self.record(example.folder, check, "not_run", reason="required installed toolchain unavailable")
                continue
            if fmt["status"] == "passed":
                self.command(example.folder, "fmt", CARGO + ["fmt", "--all", "--", "--check"], directory)
            else:
                self.record(example.folder, "fmt", "not_run", reason="rustfmt unavailable")
            tested, output = self.command(example.folder, "test", CARGO + ["test", "--locked"], directory)
            evidence = self.verify(tested, lambda: test_evidence(output, example.wire_test))
            if evidence:
                tested["test_counts"] = evidence
                self.save()
            built, output = self.command(example.folder, "build", CARGO + ["build", "--locked", "--message-format=json"], directory)
            binary = self.verify(built, lambda: build_binary(output, example.binary))
            if binary:
                built.update(binary=str(binary), binary_sha256=digest(binary))
                self.save()
            if example.wire_test:
                self.record(example.folder, "binary-smoke", "passed" if evidence else "not_run",
                            covered_by="test", test_name=example.wire_test,
                            reason="Executed once by cargo test; not repeated after cargo build" if evidence else "required wire test has not passed")
            elif binary:
                smoke, output = self.command(example.folder, "binary-smoke",
                    [sys.executable, "-I", str(Path(__file__).with_name("smoke_pi_wire.py")), "--module", str(binary)], directory)
                wire_evidence = self.verify(smoke, lambda: smoke_evidence(output))
                if wire_evidence:
                    smoke["wire_checks"] = wire_evidence
                    self.save()
            else:
                self.record(example.folder, "binary-smoke", "not_run", reason="build did not produce a validated executable")
            final_source = source_evidence(directory)
            self.record(example.folder, "source-unchanged",
                        "passed" if final_source["source_sha256"] == initial_source["source_sha256"] else "failed",
                        source_sha256=final_source["source_sha256"],
                        reason="Source/config/test hashes compared before and after validation")
        return self.finish()

    def finish(self) -> int:
        self.data["status"], code = outcome(self.data["checks"])
        self.data.update(finished_at=now(), exit_code=code)
        self.save()
        print(f"{self.data['status']}: {self.report}", flush=True)
        return code


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--report", type=Path, help="default: ROOT/validation/results.json")
    parser.add_argument("--timeout", type=float, default=900, help="seconds per command (default 900)")
    args = parser.parse_args()
    if args.timeout <= 0:
        parser.error("--timeout must be positive")
    root = args.root.resolve(strict=True)
    report = (args.report or root / "validation" / "results.json").resolve()
    runner = Runner(root, report, args.timeout)
    try:
        return runner.run()
    except KeyboardInterrupt:
        runner.record("runner", "completion", "not_run", reason="interrupted")
        return runner.finish()
    except Exception as error:
        runner.record("runner", "completion", "failed", reason=f"{type(error).__name__}: {error}")
        return runner.finish()


if __name__ == "__main__":
    sys.exit(main())
