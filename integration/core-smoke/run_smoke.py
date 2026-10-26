#!/usr/bin/env python3
"""Run only the authored host smoke and explicitly supplied example executables.

No Cargo builds, external models, upstream test suites, or user hooks. Output is
fresh-only and retained, including failures. An empty HOME prevents addon/config
lookup from reaching the caller's user state. This is not an OS sandbox.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import signal
import subprocess
import time

PIN = "3f36a003b4f3fde2242fc80f7aedac00dd127d1d"
BINARIES = ["proteus-pi-ready-steps", "proteus-example-hermes-verify-evidence",
            "proteus-example-letta-evidence-blocks"]
MIN_FREE_BYTES = 1024 ** 3


def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def save(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--example-bin-dir", type=Path, required=True)
    parser.add_argument("--examples-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    binary = args.binary.resolve(strict=True)
    bins = args.example_bin_dir.resolve(strict=True)
    sources = args.examples_dir.resolve(strict=True)
    for executable in [binary, *(bins / name for name in BINARIES)]:
        if not executable.is_file() or not os.access(executable, os.X_OK):
            parser.error(f"not an executable file: {executable}")
    if shutil.disk_usage(args.output.parent).free < MIN_FREE_BYTES:
        raise RuntimeError("less than 1 GiB free; no deletion attempted")
    args.output.mkdir(exist_ok=False)
    output = args.output.resolve(strict=True)
    workspace = output / "workspace"
    home = output / "home"
    workspace.mkdir()
    home.mkdir()
    package = Path(__file__).resolve().parent
    example_files = sorted(path for name in ["pi-ready-steps", "hermes-verify-evidence", "letta-evidence-blocks"]
                           for path in (sources / name).rglob("*") if path.is_file()
                           and "target" not in path.relative_to(sources).parts)
    manifest = {
        "schema_version": 1, "core_and_sdk_pin": PIN,
        "started_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "platform": platform.platform(), "python": platform.python_version(),
        "binary_sha256": {str(path): digest(path) for path in [binary, *(bins / name for name in BINARIES)]},
        "harness_sha256": {str(path.relative_to(package)): digest(path) for path in
            [package / "Cargo.toml", package / "Cargo.lock", package / "scenarios.json", Path(__file__), *sorted((package / "src").glob("*.rs"))]},
        "example_source_sha256": {str(path.relative_to(sources)): digest(path) for path in example_files},
        "timeout_seconds": 60, "minimum_free_bytes": MIN_FREE_BYTES,
        "scope": "real Core host integration, model-free; not agent-turn/journal/sandbox evidence",
    }
    save(output / "inputs.json", manifest)
    env = {"PATH": os.defpath, "HOME": str(home), "XDG_CONFIG_HOME": str(home),
           "PROTEUS_EXAMPLE_BIN_DIR": str(bins), "PROTEUS_EXAMPLES_SOURCE_DIR": str(sources),
           "PROTEUS_SMOKE_WORKSPACE": str(workspace)}
    started = time.monotonic()
    try:
        process = subprocess.Popen([str(binary)], cwd=workspace, env=env,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   text=True, start_new_session=True)
        try:
            stdout, stderr = process.communicate(timeout=60)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            try:
                stdout, stderr = process.communicate(timeout=5)
                cleanup = "parent process group killed and pipes drained; component-owned descendant groups not proven terminated"
            except subprocess.TimeoutExpired as drain_error:
                stdout = drain_error.stdout or ""
                stderr = drain_error.stderr or ""
                if isinstance(stdout, bytes):
                    stdout = stdout.decode("utf-8", errors="replace")
                if isinstance(stderr, bytes):
                    stderr = stderr.decode("utf-8", errors="replace")
                process.stdout.close()
                process.stderr.close()
                cleanup = "parent process group killed; pipe drain exceeded 5 seconds; descendant cleanup incomplete/unproven"
            (output / "stdout.json").write_text(stdout)
            (output / "stderr.txt").write_text(stderr)
            raise RuntimeError("60-second smoke timeout; " + cleanup)
        (output / "stdout.json").write_text(stdout)
        (output / "stderr.txt").write_text(stderr)
        save(output / "process.json", {"returncode": process.returncode,
             "elapsed_seconds": time.monotonic() - started})
        if process.returncode:
            raise RuntimeError(f"smoke failed with {process.returncode}; see stderr.txt")
        report = json.loads(stdout)
        expected = json.loads((package / "scenarios.json").read_text())
        if report["core_commit"] != PIN or [check["name"] for check in report["checks"]] != expected["checks"]:
            raise RuntimeError("unexpected smoke version or check count")
        if not all(check["status"] == "passed" for check in report["checks"]):
            raise RuntimeError("non-passing check")
        if list(workspace.iterdir()) or list(home.iterdir()):
            raise RuntimeError("smoke changed its empty workspace or HOME")
        for path, expected_hash in manifest["binary_sha256"].items():
            if digest(Path(path)) != expected_hash:
                raise RuntimeError(f"binary changed during smoke: {path}")
        for name, expected_hash in manifest["harness_sha256"].items():
            if digest(package / name) != expected_hash:
                raise RuntimeError(f"harness source changed during smoke: {name}")
        for name, expected_hash in manifest["example_source_sha256"].items():
            if digest(sources / name) != expected_hash:
                raise RuntimeError(f"example source changed during smoke: {name}")
        save(output / "result.json", {"status": "passed", "check_count": len(report["checks"]),
             "input_hashes_unchanged": True,
             "workspace_and_home_unchanged": True, "free_bytes_after": shutil.disk_usage(output).free})
    except BaseException as error:
        save(output / "result.json", {"status": "failed", "error": repr(error)})
        raise
    print(output / "result.json")


if __name__ == "__main__":
    main()
