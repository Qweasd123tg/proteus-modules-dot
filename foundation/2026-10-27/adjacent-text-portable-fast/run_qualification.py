#!/usr/bin/env python3
"""Qualify a pinned PR28 source composition with the supported portable-fast build."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import selectors
import signal
import stat
import subprocess
import sys
import time
import tomllib

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[2]
GIB = 1024 ** 3
TAIL_BYTES = 65536
JSON_LIMIT = 8 * 1024 * 1024


def file_digest(path, poll=lambda: None):
    value = hashlib.sha256()
    with path.open("rb") as stream:
        while True:
            poll()
            chunk = stream.read(256 * 1024)
            if not chunk:
                break
            value.update(chunk)
    return value.hexdigest()


def safe_relative(value):
    path = Path(value)
    if path.is_absolute() or ".." in path.parts or not path.parts:
        raise ValueError(f"Unsafe relative path: {value}")
    return path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work-dir", type=Path, required=True)
    parser.add_argument("--evidence-dir", type=Path, required=True)
    parser.add_argument("--fixture", choices=("normal", "timeout", "output", "orphan-pipe", "orphan-closed", "signal"))
    args = parser.parse_args()
    work, evidence = args.work_dir.resolve(), args.evidence_dir.resolve()
    if work.exists() or evidence.exists():
        raise SystemExit("Fresh absent work and evidence directories are required; nothing is removed")
    work.mkdir(parents=True)
    evidence.mkdir(parents=True)
    spec = json.loads((ROOT / "manifest.json").read_text())
    result = {
        "schema": 1, "status": "running",
        "qualification_commit": os.environ.get("GITHUB_SHA"),
        "workflow_run_id": os.environ.get("GITHUB_RUN_ID"),
        "manifest_sha256": file_digest(ROOT / "manifest.json"),
        "prior_semantic_evidence": spec["prior_semantic_evidence"],
        "claims": spec["claims"], "limits": spec["limits"],
        "commands": [], "sources": {}, "stage_trees": {},
    }
    active = None
    interrupted = False
    interrupt_number = None
    controller_deadline = time.monotonic() + 9900

    def save():
        data = (json.dumps(result, indent=2, sort_keys=True) + "\n").encode()
        if len(data) > JSON_LIMIT:
            raise ValueError("Evidence JSON exceeds its 8 MiB bound")
        (evidence / "result.json").write_bytes(data)

    def disk():
        import shutil
        usage = shutil.disk_usage(work)
        return {"total_bytes": usage.total, "free_bytes": usage.free}

    def memory():
        values = {}
        for line in Path("/proc/meminfo").read_text().splitlines():
            name, value = line.split(":", 1)
            if name in ("MemTotal", "MemAvailable"):
                values[name + "_KiB"] = int(value.split()[0])
        return values

    def interrupted_signal(number, _frame):
        nonlocal interrupted, interrupt_number
        # A flag cannot interrupt Popen before its child handle is retained.
        interrupted, interrupt_number = True, number

    def check_cancel():
        if interrupted:
            raise InterruptedError(f"Controller interrupted by signal {interrupt_number}")
        if time.monotonic() >= controller_deadline:
            raise TimeoutError("Controller exceeded its 165-minute total deadline")

    def digest(path):
        return file_digest(path, check_cancel)

    def group_exists(pid):
        try:
            os.killpg(pid, 0)
            return True
        except ProcessLookupError:
            return False

    def kill_group(pid):
        try:
            os.killpg(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass

    for number in (signal.SIGTERM, signal.SIGINT):
        signal.signal(number, interrupted_signal)

    # No inherited Cargo target/profile/wrapper, npm, Git or Proteus source settings.
    env = {key: os.environ[key] for key in ("PATH", "HOME", "LANG", "LC_ALL", "TZ") if key in os.environ}
    env.update({
        "CI": "true", "PYTHONDONTWRITEBYTECODE": "1", "RUSTUP_TOOLCHAIN": "1.95.0",
        "RUSTUP_HOME": os.environ.get("RUSTUP_HOME", str(Path.home() / ".rustup")),
        "CARGO_HOME": str(work / "cargo-home"), "CARGO_BUILD_JOBS": "2",
        "CARGO_INCREMENTAL": "0", "RUST_TEST_THREADS": "4",
        "GIT_TERMINAL_PROMPT": "0", "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_COUNT": "0",
        "NPM_CONFIG_USERCONFIG": str(work / "npm-user.rc"),
        "NPM_CONFIG_GLOBALCONFIG": str(work / "npm-global.rc"),
        "npm_config_cache": str(work / "npm-cache"), "TMPDIR": str(work / "tmp"),
    })
    Path(env["CARGO_HOME"]).mkdir()
    Path(env["TMPDIR"]).mkdir()
    Path(env["NPM_CONFIG_USERCONFIG"]).write_text("")
    Path(env["NPM_CONFIG_GLOBALCONFIG"]).write_text("")

    def run(command, cwd=None, *, timeout=300, byte_cap=8 * 1024 * 1024, extra_env=None):
        nonlocal active
        command = [str(value) for value in command]
        run_env = env if extra_env is None else extra_env
        row = {"argv": command, "status": "running", "timeout_seconds": timeout,
               "output_byte_cap": byte_cap, "disk_before": disk()}
        result["commands"].append(row)
        save()
        print("+ " + " ".join(command), flush=True)
        started, tail, received = time.monotonic(), b"", 0
        selector = selectors.DefaultSelector()
        proc = None
        failure = None
        try:
            check_cancel()
            proc = subprocess.Popen(command, cwd=cwd, env=run_env, stdout=subprocess.PIPE,
                                    stderr=subprocess.STDOUT, start_new_session=True)
            active = proc
            row["pid"] = proc.pid
            check_cancel()
            save()
            os.set_blocking(proc.stdout.fileno(), False)
            selector.register(proc.stdout, selectors.EVENT_READ)
            while True:
                check_cancel()
                if time.monotonic() - started > timeout:
                    raise TimeoutError("Command wall-time bound exceeded")
                if disk()["free_bytes"] < 2 * GIB:
                    raise RuntimeError("Stopped before crossing the 2 GiB disk reserve")
                if not selector.select(0.5):
                    continue
                chunk = os.read(proc.stdout.fileno(), 4096)
                if not chunk:
                    break
                received += len(chunk)
                if received > byte_cap:
                    raise ValueError("Command output-byte bound exceeded")
                tail = (tail + chunk)[-TAIL_BYTES:]
                sys.stdout.buffer.write(chunk)
                sys.stdout.buffer.flush()
            code = proc.wait(timeout=min(10, max(0.1, timeout - (time.monotonic() - started))))
            check_cancel()
            row["exit_code"] = code
            # A reaped leader does not prove its original process group is empty.
            leaked = group_exists(proc.pid)
            row["leaked_process_group"] = leaked
            if leaked:
                raise RuntimeError("Command left descendants in its original process group")
            if code:
                raise subprocess.CalledProcessError(code, command)
            row["status"] = "success"
        except BaseException as exc:
            failure = exc
            row["status"] = "failure"
            row["error"] = f"{type(exc).__name__}: {exc}"
        finally:
            selector.close()
            if proc is not None:
                # Always address the group, including after normal leader exit.
                kill_group(proc.pid)
                if proc.poll() is None:
                    proc.wait(timeout=10)
                proc.stdout.close()
            active = None
            row.update({"elapsed_seconds": round(time.monotonic() - started, 3),
                        "output_bytes": received, "log_tail": tail.decode(errors="replace"),
                        "disk_after": disk()})
            save()
        if failure:
            raise failure
        return tail.decode(errors="replace").strip()

    def git(root, *argv):
        return run(["git", *argv], root)

    def fetch(name, repository, commit, tree):
        destination = work / name
        git(work, "init", destination)
        git(destination, "remote", "add", "origin", repository)
        run(["git", "-c", "credential.helper=", "fetch", "--depth=1", "origin", commit],
            destination, timeout=600)
        git(destination, "checkout", "--detach", "FETCH_HEAD")
        if git(destination, "rev-parse", "HEAD") != commit:
            raise ValueError(f"Wrong commit: {name}")
        if git(destination, "rev-parse", "HEAD^{tree}") != tree:
            raise ValueError(f"Wrong complete tree: {name}")
        if git(destination, "status", "--porcelain", "--untracked-files=normal"):
            raise ValueError(f"Dirty fetched source: {name}")
        return destination

    def verify_blobs(root, expected):
        observed = {}
        for relative, expected_blob in expected.items():
            path = root / safe_relative(relative)
            if expected_blob is None:
                if path.exists():
                    raise ValueError(f"Expected absent source: {relative}")
                observed[relative] = None
            else:
                blob = git(root, "hash-object", path)
                if blob != expected_blob:
                    raise ValueError(f"Source blob mismatch: {relative}")
                observed[relative] = blob
        return observed

    def stage(source, bundle_manifest, name):
        actual = git(source, "write-tree")
        if actual != bundle_manifest["expected_stage_git_trees"][name]:
            raise ValueError(f"Unexpected complete source stage: {name}")
        verify_blobs(source, bundle_manifest["stage_git_blobs"][name])
        result["stage_trees"][name] = actual
        save()

    def inventory(portable):
        rows, total, scanned = [], 0, 0
        pending = [portable]
        inventory_deadline = time.monotonic() + 120

        def poll():
            check_cancel()
            if time.monotonic() >= inventory_deadline:
                raise TimeoutError("Portable inventory exceeded its 120-second deadline")

        while pending:
            poll()
            directory = pending.pop()
            with os.scandir(directory) as entries:
                for entry in entries:
                    poll()
                    scanned += 1
                    if scanned > 50000:
                        raise ValueError("Portable inventory exceeds 50,000 total entries")
                    path = Path(entry.path)
                    relative = path.relative_to(portable)
                    if len(relative.parts) > 128:
                        raise ValueError("Portable inventory exceeds 128 path components")
                    relative = relative.as_posix()
                    metadata = entry.stat(follow_symlinks=False)
                    mode = stat.S_IMODE(metadata.st_mode)
                    if entry.is_symlink():
                        target = os.readlink(path)
                        if len(target.encode()) > 4096 or not path.resolve().is_relative_to(portable):
                            raise ValueError(f"Escaping or oversized portable symlink: {relative}")
                        rows.append({"path": relative, "type": "symlink", "mode": mode, "target": target})
                    elif entry.is_file(follow_symlinks=False):
                        if metadata.st_size > 2 * GIB:
                            raise ValueError(f"Oversized portable file: {relative}")
                        total += metadata.st_size
                        if total > 8 * GIB:
                            raise ValueError("Portable inventory exceeds 8 GiB of regular files")
                        rows.append({"path": relative, "type": "file", "mode": mode,
                                     "bytes": metadata.st_size, "sha256": file_digest(path, poll)})
                    elif entry.is_dir(follow_symlinks=False):
                        rows.append({"path": relative, "type": "directory", "mode": mode})
                        pending.append(path)
                    else:
                        raise ValueError(f"Unexpected special portable file: {relative}")
        poll()
        rows.sort(key=lambda row: row["path"])  # Only the already bounded inventory.
        record = {"schema": 1, "entries": rows, "entry_count": scanned,
                  "file_count": sum(row["type"] == "file" for row in rows),
                  "total_file_bytes": total}
        data = (json.dumps(record, indent=2, sort_keys=True) + "\n").encode()
        if len(data) > JSON_LIMIT:
            raise ValueError("Portable inventory exceeds its 8 MiB evidence bound")
        poll()
        return record, data

    def assert_clean(name, path, expected_commit, expected_tree):
        if git(path, "rev-parse", "HEAD") != expected_commit:
            raise ValueError(f"Changed source commit: {name}")
        if git(path, "rev-parse", "HEAD^{tree}") != expected_tree:
            raise ValueError(f"Changed source tree: {name}")
        if git(path, "status", "--porcelain", "--untracked-files=normal"):
            raise ValueError(f"Source became dirty: {name}")
        git(path, "diff", "--exit-code")
        git(path, "diff", "--cached", "--exit-code")

    save()
    try:
        if args.fixture:
            # Controller-only synthetic failure tests. No project source is fetched or run.
            fixtures = {
                "normal": ('print("fixture ok")', 5, 1024),
                "timeout": ("import time; time.sleep(60)", 0.2, 1024),
                "output": ('print("x" * 100000)', 5, 1024),
                "orphan-pipe": ("import subprocess,sys,os; subprocess.Popen([sys.executable,'-c','import time; time.sleep(60)']); os._exit(0)", 0.5, 1024),
                "orphan-closed": ("import subprocess,sys,os; subprocess.Popen([sys.executable,'-c','import os,time; os.close(1); os.close(2); time.sleep(60)']); os._exit(0)", 5, 1024),
                "signal": ("import time; time.sleep(60)", 30, 1024),
            }
            code, seconds, maximum = fixtures[args.fixture]
            result["fixture"] = args.fixture
            run([sys.executable, "-c", code], timeout=seconds, byte_cap=maximum)
            check_cancel()
            result["status"] = "success"
            return
        result["disk_initial"] = disk()
        result["memory_initial"] = memory()
        if result["disk_initial"]["free_bytes"] < 20 * GIB:
            raise RuntimeError("Fresh hosted build requires at least 20 GiB free; no cleanup is attempted")
        for relative, expected in spec["sha256"].items():
            if digest(REPO / safe_relative(relative)) != expected:
                raise ValueError(f"Qualification source checksum mismatch: {relative}")
        result["system_environment"] = {
            "runner_image": {key: os.environ.get(key) for key in ("ImageOS", "ImageVersion", "RUNNER_OS", "RUNNER_ARCH")},
            "platform": {"os": platform.system(), "architecture": platform.machine(), "libc": list(platform.libc_ver())},
            "selected_apt_packages": run(["dpkg-query", "-W", "-f", "${binary:Package}\\t${Version}\\n", *["build-essential","pkg-config","clang","lld","libssl-dev","bubblewrap","ripgrep","libxcb1-dev","libxcb-shape0-dev","libxcb-xfixes0-dev","libxcb-render0-dev","libxcb-randr0-dev","libxcb-xkb-dev","libxkbcommon-dev","libxkbcommon-x11-dev","libfontconfig1-dev","libfreetype6-dev","libwayland-dev","libvulkan-dev","libegl1-mesa-dev","libc6","libgcc-s1","libstdc++6"]]),
            "limit": "Runner image and system packages are observed, not locked; no bit-reproducible build claim",
        }
        result["toolchain"] = {
            "rustc": run(["rustc", "--version", "--verbose"]),
            "cargo": run(["cargo", "--version"]),
            "python": run(["python3", "--version"]),
            "node": run(["node", "--version"]),
            "npm": run(["npm", "--version"]),
        }
        if not result["toolchain"]["rustc"].startswith("rustc 1.95.0 "):
            raise ValueError("Unexpected Rust version")
        if result["toolchain"]["node"] != "v22.23.4" or result["toolchain"]["python"] != "Python 3.12.15":
            raise ValueError("Unexpected Node/Python version")
        bundle_spec = spec["bundle"]
        bundle = fetch("bundle", bundle_spec["repository"], bundle_spec["commit"], bundle_spec["tree"])
        manifest_path = bundle / bundle_spec["manifest"]
        if digest(manifest_path) != bundle_spec["manifest_sha256"]:
            raise ValueError("Unexpected reviewed PR28 manifest bytes")
        bm = json.loads(manifest_path.read_text())
        for relative, expected in bm["sha256"].items():
            if digest(bundle / safe_relative(relative)) != expected:
                raise ValueError(f"Reviewed PR28 bundle checksum mismatch: {relative}")
        desktop_spec = spec["sources"]["desktop"]
        desktop = fetch("desktop", desktop_spec["repository"], desktop_spec["commit"], desktop_spec["tree"])
        verify_blobs(desktop, bm["source_control_git_blobs"])
        stage(desktop, bm, "upstream")
        for label, patches in (
            ("reviewed_prerequisites", bm["prerequisite_patches"]),
            ("baseline_test_refactor", bm["test_refactor_patches"]),
            ("fixed_composition", bm["fix_patches"]),
        ):
            for relative in patches:
                patch = bundle / safe_relative(relative)
                git(desktop, "apply", "--check", "--index", patch)
                git(desktop, "apply", "--index", patch)
                git(desktop, "diff", "--cached", "--check")
            stage(desktop, bm, label)
        if sorted(git(desktop, "diff", "--cached", "--name-only").splitlines()) != sorted(bm["changed_files"]):
            raise ValueError("Unexpected modified source paths")
        if git(desktop, "diff", "--exit-code"):
            raise ValueError("Unstaged source difference")
        expected_specs = json.loads((desktop / "repositories.json").read_text())
        if {k: {"url": v["url"], "rev": v["rev"]} for k, v in expected_specs.items()} != bm["repositories_source_pins"]:
            raise ValueError("Reviewed Desktop dependency pin file changed")
        sources = {"desktop": desktop}
        for name in ("harness", "modules", "extensions"):
            source_spec = spec["sources"][name]
            path = fetch(name, source_spec["repository"], source_spec["commit"], source_spec["tree"])
            sources[name] = path
            env[expected_specs[name]["env"]] = str(path)
        # Fail closed on effective Cargo configuration outside the reviewed source files.
        for path in sources.values():
            verify_blobs(path, spec["source_control_blobs"][path.name])
            for ancestor in path.parents:
                for name in ("config", "config.toml"):
                    if (ancestor / ".cargo" / name).exists():
                        raise ValueError(f"Unreviewed ancestor Cargo configuration: {ancestor}")
            for name in ("target",):
                if (path / name).exists():
                    raise ValueError(f"Expected an absent fresh target directory: {path}")
        if (desktop / "build/Proteus").exists() or (desktop / "build/Proteus.next").exists():
            raise ValueError("Portable destination was not fresh")
        # Packaging source identity must name committed candidate bytes, not upstream + dirty.
        commit_bytes = spec["candidate_commit_utf8"].encode()
        commit_path = evidence / "source-commit.txt"
        commit_path.write_bytes(commit_bytes)
        candidate = git(desktop, "hash-object", "-t", "commit", "-w", commit_path)
        if candidate != spec["candidate_commit"]:
            raise ValueError("Deterministic candidate commit identity mismatch")
        git(desktop, "update-ref", "HEAD", candidate)
        result["candidate_commit"] = candidate
        result["candidate_commit_scope"] = "Local-only CI commit, not remotely fetchable from upstream; reconstruct from retained commit object and reviewed bundle"
        result["candidate_commit_sha256"] = digest(commit_path)
        result["candidate_tree"] = bm["expected_stage_git_trees"]["fixed_composition"]
        for name, path in sources.items():
            item = spec["sources"][name]
            commit = candidate if name == "desktop" else item["commit"]
            tree = result["candidate_tree"] if name == "desktop" else item["tree"]
            assert_clean(name, path, commit, tree)
            result["sources"][name] = {"repository": item["repository"], "commit": commit,
                                       "tree": tree, "clean": True}
        result["dependency_git_sources"] = {}
        for name, path in sources.items():
            lock = tomllib.loads((path / "Cargo.lock").read_text())
            observed = sorted({entry["source"] for entry in lock["package"]
                               if entry.get("source", "").startswith("git+")})
            if observed != spec["expected_dependency_git_sources"][name]:
                raise ValueError(f"Unexpected locked Git dependency graph: {name}")
            result["dependency_git_sources"][name] = observed
        result["dcp_package_lock_sha256"] = digest(sources["modules"] / "hook/dcp/package-lock.json")
        result["effective_build_env"] = {
            key: env[key] for key in ("RUSTUP_TOOLCHAIN", "CARGO_BUILD_JOBS", "CARGO_INCREMENTAL",
                                     "CARGO_HOME", "PROTEUS_HARNESS_SOURCE",
                                     "PROTEUS_MODULES_SOURCE", "PROTEUS_EXTENSIONS_SOURCE")
        }
        result["phase"] = "source_verified"
        save()
        # First build after committing the exact candidate tree: supported portable refresh.
        run(["python3", "scripts/portable.py", "--fast"], desktop, timeout=9000,
            byte_cap=32 * 1024 * 1024)
        portable = desktop / "build/Proteus"
        if not portable.is_dir() or (desktop / "build/Proteus.next").exists():
            raise ValueError("Portable assembly did not complete")
        if list((desktop / "build").glob("Proteus-*.tar.gz")):
            raise ValueError("Unexpected release archive in a portable-fast qualification")
        release = json.loads((portable / "share/release-sources.json").read_text())
        expected_names = {"desktop": "Proteus-desktop", "harness": "Proteus-core",
                          "modules": "Proteus-modules", "extensions": "Proteus-desktop-extensions"}
        if set(release["sources"]) != set(expected_names.values()):
            raise ValueError("Unexpected portable source manifest inventory")
        for name, upstream_name in expected_names.items():
            actual = release["sources"][upstream_name]
            expected = result["sources"][name]
            if actual != {"repository": expected["repository"], "commit": expected["commit"], "dirty": False}:
                raise ValueError(f"Portable source provenance mismatch: {name}")
        version = tomllib.loads((desktop / "Cargo.toml").read_text())["package"]["version"]
        if release["version"] != version:
            raise ValueError("Portable version mismatch")
        binaries = [
            ("proteus-native", desktop / "target/fast/proteus-native"),
            ("proteus", sources["harness"] / "target/release/proteus"),
            ("proteus-reference-module", sources["modules"] / "target/release/proteus-reference-module"),
        ]
        copied = {}
        for name, built in binaries:
            packaged = portable / "bin" / name
            if not built.is_file() or not packaged.is_file() or not os.access(packaged, os.X_OK):
                raise ValueError(f"Missing executable: {name}")
            if digest(built) != digest(packaged):
                raise ValueError(f"Stale or incorrect packaged binary: {name}")
            copied[name] = {"source": str(built), "bytes": packaged.stat().st_size, "sha256": digest(packaged)}
        for relative in git(sources["harness"], "ls-files", "configs").splitlines():
            if digest(sources["harness"] / relative) != digest(portable / "share" / relative):
                raise ValueError(f"Packaged tracked profile mismatch: {relative}")
        for original, packaged in (
            (desktop / "scripts/portable/proteus-native", portable / "proteus-native"),
            (desktop / "scripts/portable/system_proxy.py", portable / "share/system_proxy.py"),
        ):
            if digest(original) != digest(packaged):
                raise ValueError("Packaged launcher/proxy differs from reviewed source")
        packages = sorted((sources["extensions"] / "packages").glob("*/extension.json"))
        if not packages:
            raise ValueError("No extension packages")
        for path in packages:
            extension = json.loads(path.read_text())
            target = portable / "share/extensions" / path.parent.name
            if digest(path) != digest(target / "extension.json") or not list(target.glob("LICENSE*")):
                raise ValueError(f"Packaged extension metadata/license mismatch: {path.parent.name}")
            command = extension["command"][0]
            if command.startswith("bin/"):
                if digest(target / safe_relative(command)) != digest(sources["extensions"] / "target/release" / Path(command).name):
                    raise ValueError(f"Packaged extension binary mismatch: {path.parent.name}")
        for name in expected_names.values():
            if not list((portable / "share/licenses" / name).glob("LICENSE*")):
                raise ValueError(f"Missing source notices: {name}")
        before, before_bytes = inventory(portable)
        result["portable"] = {"manifest": release, "copied_binaries": copied,
                              "inventory_sha256": hashlib.sha256(before_bytes).hexdigest(),
                              "file_count": before["file_count"], "entry_count": before["entry_count"],
                              "total_file_bytes": before["total_file_bytes"],
                              "archive_created": False}
        (evidence / "portable-inventory.json").write_bytes(before_bytes)
        result["phase"] = "portable_built"
        save()
        # These are the supported folder probes, NOT an emulated native UX gate.
        probe = work / "synthetic-probes"
        probe.mkdir()
        probe_env = {key: env[key] for key in ("PATH", "LANG", "LC_ALL", "TZ") if key in env}
        for key, name in (("HOME", "home"), ("PROTEUS_HOME", "runtime"),
                          ("PROTEUS_CONFIG_HOME", "config"), ("XDG_CONFIG_HOME", "xdg-config"),
                          ("XDG_DATA_HOME", "xdg-data"), ("XDG_STATE_HOME", "xdg-state"),
                          ("XDG_CACHE_HOME", "xdg-cache"), ("TMPDIR", "tmp")):
            location = probe / name
            location.mkdir()
            probe_env[key] = str(location)
        probe_env.update({"PATH": str(portable / "bin") + os.pathsep + env["PATH"],
                          "PYTHONDONTWRITEBYTECODE": "1", "NO_PROXY": "localhost,127.0.0.1,::1",
                          "no_proxy": "localhost,127.0.0.1,::1"})
        for program in (portable / "bin/proteus", portable / "bin/proteus-native", portable / "proteus-native"):
            output = run([program, "--version"], probe, timeout=30, extra_env=probe_env)
            if version not in output:
                raise ValueError("Packaged binary/launcher version probe failed")
        for script, marker in (
            ("test_portable_dcp.py", "PASS: portable DCP wrapper initialization, sources/licenses, production runtime and WASM hooks"),
            ("test_portable_hooks.py", "PASS: relocated hook launchers, sources/licenses, inspection without execution and adapter Node gate"),
        ):
            output = run(["python3", desktop / "scripts" / script, portable], probe,
                         timeout=180, extra_env=probe_env)
            if marker not in output:
                raise ValueError(f"Missing positive folder probe record: {script}")
        output = run(["python3", sources["extensions"] / "tests/wire.py", "--packages",
                      portable / "share/extensions"], probe, timeout=300, extra_env=probe_env)
        match = re.search(r"(?m)^(\d+) packages: (\d+) real protocol messages checked$", output)
        if not match or int(match.group(1)) != len(packages) or int(match.group(2)) <= 0:
            raise ValueError("Missing complete packaged-extension wire evidence")
        result["folder_probes"] = {"status": "success", "extension_packages": int(match.group(1)),
                                   "extension_protocol_messages": int(match.group(2)),
                                   "native_window_exercised": False}
        after, after_bytes = inventory(portable)
        if after_bytes != before_bytes:
            raise ValueError("Folder probes changed the qualified portable payload")
        for name, path in sources.items():
            expected = result["sources"][name]
            assert_clean(name, path, expected["commit"], expected["tree"])
            verify_blobs(path, spec["source_control_blobs"][path.name])
        verify_blobs(desktop, bm["stage_git_blobs"]["fixed_composition"])
        check_cancel()
        result["phase"] = "complete"
        result["status"] = "success"
    except BaseException as exc:
        result["status"] = "failure"
        result["error"] = f"{type(exc).__name__}: {exc}"
        raise
    finally:
        if active is not None:
            kill_group(active.pid)
        cancelled_success = interrupted and result["status"] == "success"
        if cancelled_success:
            result["status"] = "failure"
            result["error"] = f"InterruptedError: Controller interrupted by signal {interrupt_number}"
        result["interrupted"] = interrupted
        result["disk_final"] = disk()
        result["memory_final"] = memory()
        save()
        if cancelled_success:
            raise InterruptedError(result["error"])


if __name__ == "__main__":
    main()
