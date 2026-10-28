#!/usr/bin/env python3
"""Hosted preparation only. Identical example overlay, canonical focused gates, locked builds."""
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
A = "e9d6bd06df78a5af85d055117a6697187730e30e"
B = "63454d4e8b1e4e6b26d088fce2a17d46f30390ae"
M = "7fceaebc3bed8add9b0e3091110f59deca86ba46"


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def run(command, *, cwd=None, env=None, stdout=None, stderr=None, timeout=1200, capture=False, check=True):
    process = subprocess.Popen(command, cwd=cwd, env=env,
                               stdout=subprocess.PIPE if capture else stdout,
                               stderr=stderr, start_new_session=True)
    try:
        if capture:
            data, _ = process.communicate(timeout=timeout)
            if len(data) > 1024*1024:
                raise ValueError("preparation scalar output too large")
        else:
            process.wait(timeout=timeout)
            data = None
        if process.returncode:
            raise subprocess.CalledProcessError(process.returncode, command)
        return data
    except BaseException:
        # A timed-out Python canonical runner may own Cargo/compiler descendants.
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait()
        raise


def output(command, cwd, env):
    return run(command, cwd=cwd, env=env, capture=True).decode().strip()


def main():
    def interrupted(signum, frame):
        raise RuntimeError("preparation interrupted by signal")
    signal.signal(signal.SIGTERM, interrupted)
    a, b, modules, out = [Path(x).resolve() for x in sys.argv[1:]]
    out.mkdir(exist_ok=False)
    env = dict(os.environ, CARGO_BUILD_JOBS="2", CARGO_INCREMENTAL="0",
               RUST_TEST_THREADS="4", PYTHONDONTWRITEBYTECODE="1")
    for key in ("RUSTFLAGS", "RUSTC_WRAPPER", "RUSTC_WORKSPACE_WRAPPER",
                "CARGO_ENCODED_RUSTFLAGS", "PROTEUS_TEST_REFERENCE_MODULE",
                "PROTEUS_TEST_DCP_MODULE", "PROTEUS_MODULES_SOURCE"):
        env.pop(key, None)
    env["PROTEUS_MODULES_SOURCE"] = str(modules)
    for source, pin in [(a,A), (b,B), (modules,M)]:
        if output(["git", "rev-parse", "HEAD"], source, env) != pin:
            raise ValueError("source pin mismatch")
        if output(["git", "status", "--porcelain", "--untracked-files=all"], source, env):
            raise ValueError("source is not clean")
    if sha(a/"Cargo.lock") != sha(b/"Cargo.lock"):
        raise ValueError("Core lockfiles differ")
    files = ["native_cold_probe.rs", "rss_control.rs", "launcher.py", "run.py", "prepare.py", "README.md"]
    provenance = {
        "core_a":A, "core_b":B, "modules":M,
        "bundle_head":os.environ["GITHUB_SHA"], "bundle_repository":os.environ["GITHUB_REPOSITORY"],
        "workflow_ref":os.environ["GITHUB_REF"], "workflow_run_id":os.environ["GITHUB_RUN_ID"],
        "workflow_sha256":sha(ROOT.parents[2]/".github/workflows/native-cold-recovery.yml"),
        "rustc":output(["rustc","--version","--verbose"], a, env),
        "cargo":output(["cargo","--version"], a, env),
        "source_files":{name:sha(ROOT/name) for name in files},
        "core_lock_sha256":sha(a/"Cargo.lock"), "modules_lock_sha256":sha(modules/"Cargo.lock"),
        "gates":[], "binary_sha256":{}, "status":"PREPARING",
    }
    provenance_path = out/"provenance.json"
    def checkpoint():
        provenance_path.write_text(json.dumps(provenance,indent=2,sort_keys=True)+"\n")
    checkpoint()
    # Explicit fresh fixture, built once at exact Modules pin, then reused by both Core lanes.
    reference = output(["python3","-B","scripts/build_module.py","--target-dir",str(out/"modules-target")], a, env)
    fixture = Path(reference)
    if not fixture.is_file():
        raise ValueError("canonical module builder did not return executable")
    env["PROTEUS_TEST_REFERENCE_MODULE"] = str(fixture)
    provenance["reference_binary_sha256"] = sha(fixture)
    checkpoint()
    overlay = ROOT/"native_cold_probe.rs"
    run(["rustfmt","--edition","2024","--check",str(overlay),str(ROOT/"rss_control.rs")],
                   env=env, check=True)
    for label, source in [("a",a), ("b",b)]:
        target = source/"crates/proteus-core/examples/native_cold_probe.rs"
        if target.exists():
            raise ValueError("overlay unexpectedly already present")
        target.write_bytes(overlay.read_bytes())
        if sha(target) != provenance["source_files"]["native_cold_probe.rs"]:
            raise ValueError("overlay identity")
        env["CARGO_TARGET_DIR"] = str(out/f"target-{label}")
        for selector in [
            ["--lib","core::session_journal"],
            ["--lib","core::session_store"],
            ["--test","session_writer_lock"],
        ]:
            command = ["python3","-B","scripts/test.py","-p","proteus-core",*selector,"--","--nocapture"]
            slug = selector[-1].replace("::","_")
            log = out/f"{label}-{slug}.log"
            with log.open("wb") as stream:
                run(command, cwd=source, env=env, stdout=stream,
                               stderr=subprocess.STDOUT, check=True, timeout=1200)
            if log.stat().st_size > 8*1024*1024:
                raise ValueError("gate log too large")
            text = log.read_text()
            summaries = re.findall(r"test result: ok\. (\d+) passed; (\d+) failed; (\d+) ignored;", text)
            if not summaries or not all(int(passed)>0 and failed=="0" for passed,failed,_ in summaries):
                raise ValueError("focused filter ran no passing tests")
            if selector[-1] == "core::session_store" and \
                not re.search(r"test [^\n]*usage_tracks_exchanges_and_matches_read_only_cold_journal \.\.\. ok", text):
                raise ValueError("cached usage/context gate absent")
            provenance["gates"].append({"core":label, "selector":selector,
                "summaries":summaries, "log":log.name, "log_sha256":sha(log)})
            checkpoint()
        build_log = out/f"{label}-release-build.jsonl"
        command = ["cargo","build","--locked","--release","-p","proteus-core",
                   "--example","native_cold_probe","--message-format=json-render-diagnostics"]
        with build_log.open("wb") as stream:
            run(command, cwd=source, env=env, stdout=stream,
                           stderr=sys.stderr, check=True, timeout=1200)
        executable = None
        with build_log.open() as stream:
            for line in stream:
                item = json.loads(line)
                if item.get("reason") == "compiler-artifact" and item.get("executable") \
                        and item["target"]["name"] == "native_cold_probe":
                    executable = Path(item["executable"])
        if executable is None or not executable.is_file():
            raise ValueError("missing actual Cargo executable")
        provenance[f"binary_{label}"] = str(executable)
        provenance["binary_sha256"][label] = sha(executable)
        checkpoint()
    control = out/"rss_control"
    run(["rustc","--edition","2024","-O",str(ROOT/"rss_control.rs"),"-o",str(control)],
                   env=env, check=True)
    provenance["binary_control"] = str(control)
    provenance["binary_sha256"]["control"] = sha(control)
    # The fixture source tree may have ignored target output; tracked source must stay unchanged.
    for source in [a,b,modules]:
        if output(["git","diff","--name-only"],source,env):
            raise ValueError("tracked input changed during preparation")
    provenance["status"] = "PASS"
    checkpoint()
    print(json.dumps({"prepared":True,"provenance_sha256":sha(out/"provenance.json")}),flush=True)


if __name__ == "__main__":
    main()
