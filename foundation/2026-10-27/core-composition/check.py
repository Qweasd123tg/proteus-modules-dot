#!/usr/bin/env python3
"""Qualify the exact Core foundation composition; authorized hosted CI only.

No shell command interpolation, upstream writes, automatic merge, release,
portable build, benchmark, or production-session access is performed.
"""
import argparse
import errno
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import selectors
import signal
import subprocess
import sys
import tempfile
import time

CORE_PIN = "63454d4e8b1e4e6b26d088fce2a17d46f30390ae"
MODULES_PIN = "7fceaebc3bed8add9b0e3091110f59deca86ba46"
TEST_PATH = "crates/proteus-core/tests/session_ownership_slice.rs"
TARGET = "session_ownership_slice"
MAX_TOTAL_OUTPUT = 128 * 1024 * 1024
PUBLICATION_REPOSITORY = "Qweasd123tg/proteus-modules-dot"
PUBLICATION_BRANCH = "ci/core-foundation-composition-20261027"
PHASE_STATUS = {
    "baseline": "BASELINE_EXPECTED_RED_PASS",
    "production": "PRODUCTION_COMPOSITION_PASS",
    "instrumented": "INSTRUMENTED_OVERLAP_PASS",
}
INITIAL_FREE_BYTES = 8 * 1024 ** 3
LOW_WATER_BYTES = 2 * 1024 ** 3


class InfrastructureError(RuntimeError):
    pass


class GateRejected(RuntimeError):
    pass


def is_infrastructure(error):
    return isinstance(error, (InfrastructureError, KeyboardInterrupt, SystemExit)) or (
        isinstance(error, OSError) and error.errno in (errno.ENOSPC, errno.EDQUOT))


def exhausted_output(output):
    # Require the operating-system diagnostic and its exact numeric errno.
    # A bare English phrase, generic compiler error or assertion is not enough.
    return bool(re.search(
        r"(?:No space left on device \(os error 28\)|Disk quota exceeded \(os error 122\)|"
        r"\[Errno 28\] No space left on device|\[Errno 122\] Disk quota exceeded)",
        output))


def sha(data):
    return hashlib.sha256(data).hexdigest()


def bounded_file(path, cap):
    with Path(path).open("rb") as stream:
        data = stream.read(cap + 1)
    if len(data) > cap:
        raise InfrastructureError(f"file exceeds {cap} bytes: {path}")
    return data


def file_sha(path, cap=1024 ** 3):
    digest = hashlib.sha256()
    count = 0
    with Path(path).open("rb") as stream:
        while True:
            chunk = stream.read(1024 * 1024)
            if not chunk:
                return digest.hexdigest()
            count += len(chunk)
            if count > cap:
                raise InfrastructureError(f"hashed file exceeds {cap} bytes: {path}")
            digest.update(chunk)


def kill_group(process):
    # Cooperating POSIX process groups only; this is not a sandbox or a claim
    # that deliberately escaped descendants can universally be terminated.
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass


class Runner:
    def __init__(self, evidence, work=None, seconds=6600):
        self.evidence = Path(evidence)
        self.evidence.mkdir(parents=True, exist_ok=False)
        self.records = []
        self.total_bytes = 0
        self.work = Path(work) if work else None
        self.deadline = time.monotonic() + seconds

    def run(self, label, argv, cwd, env, seconds, cap=1024 * 1024):
        if not re.fullmatch(r"[A-Za-z0-9_.-]{1,120}", label):
            raise InfrastructureError("invalid stage label")
        if len(self.records) >= 180:
            raise InfrastructureError("stage record limit")
        started = time.monotonic()
        deadline = min(started + seconds, self.deadline)
        output = bytearray()
        process = None
        selector = selectors.DefaultSelector()
        reason = None
        code = None
        free_before = shutil.disk_usage(self.work).free if self.work is not None else None
        min_free = free_before
        free_after = None
        try:
            if free_before is not None and free_before < LOW_WATER_BYTES:
                raise InfrastructureError(f"{label}: free space below 2 GiB before command")
            process = subprocess.Popen(
                [str(arg) for arg in argv], cwd=cwd, env=env,
                stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT, start_new_session=True,
            )
            os.set_blocking(process.stdout.fileno(), False)
            selector.register(process.stdout, selectors.EVENT_READ)
            while True:
                if self.work is not None:
                    observed_free = shutil.disk_usage(self.work).free
                    min_free = min(min_free, observed_free)
                    if observed_free < LOW_WATER_BYTES:
                        raise InfrastructureError(f"{label}: free space below 2 GiB")
                if time.monotonic() >= deadline:
                    raise InfrastructureError(f"{label}: deadline exceeded")
                if not selector.get_map() and process.poll() is not None:
                    break
                if selector.get_map():
                    events = selector.select(min(0.1, max(0.0, deadline - time.monotonic())))
                else:
                    time.sleep(min(0.02, max(0.0, deadline - time.monotonic())))
                    events = []
                for key, _ in events:
                    chunk = os.read(key.fileobj.fileno(), 65536)
                    if not chunk:
                        selector.unregister(key.fileobj)
                        continue
                    self.total_bytes += len(chunk)
                    if len(output) + len(chunk) > cap or self.total_bytes > MAX_TOTAL_OUTPUT:
                        raise InfrastructureError(f"{label}: output byte limit exceeded")
                    output.extend(chunk)
            code = process.wait(timeout=max(0.01, deadline - time.monotonic()))
            if code < 0:
                raise InfrastructureError(f"{label}: process ended by signal {code}")
            if self.work is not None:
                free_after = shutil.disk_usage(self.work).free
                min_free = min(min_free, free_after)
                if free_after < LOW_WATER_BYTES:
                    raise InfrastructureError(f"{label}: free space below 2 GiB after command")
            if code != 0 and exhausted_output(bytes(output).decode("utf-8", "replace")):
                raise InfrastructureError(f"{label}: explicit ENOSPC/EDQUOT diagnostic")
        except BaseException as error:
            reason = f"{type(error).__name__}: {error}"
            raise
        finally:
            # Kill the group even if its leader exited: a child may retain a
            # pipe or continue after closing stdout. Never return on EOF alone.
            if process is not None:
                kill_group(process)
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    kill_group(process)
                    raise InfrastructureError(f"{label}: failed to reap child")
                code = process.returncode
                if process.stdout is not None:
                    process.stdout.close()
            selector.close()
            raw = bytes(output)
            (self.evidence / f"{label}.log").write_bytes(raw)
            record = {
                "stage": label, "argv": [str(arg) for arg in argv], "cwd": str(Path(cwd).resolve()),
                "elapsed_seconds": time.monotonic() - started,
                "exit_code": code, "output_bytes": len(raw),
                "output_sha256": sha(raw), "infrastructure_error": reason,
                "disk_free_before_bytes": free_before, "disk_free_after_bytes": free_after,
                "disk_free_minimum_bytes": min_free,
            }
            self.records.append(record)
        if code is None or code < 0:
            raise InfrastructureError(f"{label}: process ended by signal or without status")
        return {"code": code, "output": bytes(output).decode("utf-8", "replace")}

    def ok(self, label, argv, cwd, env, seconds, cap=1024 * 1024):
        result = self.run(label, argv, cwd, env, seconds, cap)
        if result["code"] != 0:
            raise GateRejected(f"{label}: command failed with {result['code']}")
        return result["output"]


def classify(result, name, marker=None, marker_mode="line_prefix"):
    """Interpret a direct libtest binary, never a cargo/compiler exit."""
    text = result["output"]
    outcomes = re.findall(r"^test (\S+) \.\.\. (ok|FAILED|ignored)$", text, re.M)
    summaries = re.findall(
        r"^test result: (ok|FAILED)\. (\d+) passed; (\d+) failed; "
        r"(\d+) ignored; (\d+) measured; (\d+) filtered out; finished in [^\n]+$",
        text, re.M,
    )
    wanted = "FAILED" if marker else "ok"
    if outcomes != [(name, wanted)] or len(summaries) != 1:
        raise GateRejected(f"{name}: missing, duplicate, ignored, or unexpected test outcome")
    verdict, passed, failed, ignored, measured, _ = summaries[0]
    expected = (wanted, "0", "1", "0", "0") if marker else ("ok", "1", "0", "0", "0")
    if (verdict, passed, failed, ignored, measured) != expected:
        raise GateRejected(f"{name}: unexpected single-test summary")
    if result["code"] != (101 if marker else 0):
        raise GateRejected(f"{name}: unexpected direct-test exit status")
    if marker:
        header = f"---- {name} stdout ----\n"
        if text.count(header) != 1:
            raise GateRejected(f"{name}: missing unique captured panic section")
        failure = text.split(header, 1)[1].split("\nfailures:\n", 1)[0]
        if marker_mode == "error_line":
            # The exact five reviewed admission tests return anyhow::Result.
            # Their real Rust 1.95 output is a single Error line, not a panic.
            if failure.strip() != "Error: " + marker:
                raise GateRejected(f"{name}: wrong Result-returning behavioral failure")
        elif marker_mode in {"line_prefix", "contains"}:
            matched = (re.search(r"(?m)^" + re.escape(marker) + r":", failure)
                       if marker_mode == "line_prefix" else marker in failure)
            if not matched:
                raise GateRejected(f"{name}: failure was not the expected behavioral assertion")
            if "panicked at" not in failure:
                raise GateRejected(f"{name}: missing panic context")
        else:
            raise GateRejected("unknown behavioral failure classifier mode")
    return "EXPECTED_BEHAVIORAL_RED" if marker else "PASS"


def clean_env(work):
    allowed = {"PATH", "USER", "LOGNAME", "SHELL", "LANG", "LC_ALL", "TZ",
               "TMPDIR", "TMP", "TEMP", "SSL_CERT_FILE", "SSL_CERT_DIR",
               "HTTP_PROXY", "HTTPS_PROXY", "NO_PROXY",
               "http_proxy", "https_proxy", "no_proxy"}
    env = {key: value for key, value in os.environ.items() if key in allowed}
    home = work / "home"
    home.mkdir()
    user_npmrc, global_npmrc = work / "npm-user.conf", work / "npm-global.conf"
    user_npmrc.write_text("", encoding="utf-8")
    global_npmrc.write_text("", encoding="utf-8")
    env.update({
        "HOME": str(home),
        "RUSTUP_HOME": os.environ.get("RUSTUP_HOME", str(Path.home() / ".rustup")),
        "CARGO_HOME": str(work / "cargo-home"), "CARGO_BUILD_JOBS": "2",
        "CARGO_INCREMENTAL": "0", "CARGO_PROFILE_DEV_DEBUG": "0",
        "CARGO_PROFILE_TEST_DEBUG": "0", "RUST_TEST_THREADS": "4",
        "RUSTUP_TOOLCHAIN": "1.95.0", "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONOPTIMIZE": "0", "GIT_TERMINAL_PROMPT": "0",
        "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": "/dev/null",
        "CARGO_TERM_COLOR": "never", "RUST_BACKTRACE": "0",
        "npm_config_audit": "false", "NPM_CONFIG_AUDIT": "false",
        "npm_config_fund": "false", "NPM_CONFIG_FUND": "false",
        "npm_config_cache": str(work / "npm-cache"),
        "NPM_CONFIG_USERCONFIG": str(user_npmrc), "NPM_CONFIG_GLOBALCONFIG": str(global_npmrc),
    })
    for key in ("NO_PROXY", "no_proxy"):
        values = [x for x in env.get(key, "").split(",") if x]
        env[key] = ",".join(dict.fromkeys([*values, "localhost", "127.0.0.1", "::1"]))
    return env


def strict_json(raw):
    def pairs(values):
        out = {}
        for key, value in values:
            if key in out:
                raise GateRejected("duplicate JSON key")
            out[key] = value
        return out
    return json.loads(raw, object_pairs_hook=pairs)


def git_blob(data):
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


def valid_path(name):
    path = Path(name)
    if (not name or path.is_absolute() or str(path) != name or
        any(part in {"", ".", ".."} for part in name.split("/")) or "\0" in name):
        raise GateRejected("unsafe source path")
    return path


def source_bytes(root, name, required=True):
    path = root / valid_path(name)
    if not path.resolve().is_relative_to(root.resolve()):
        raise GateRejected("source escaped checkout")
    if path.is_symlink():
        raise GateRejected("symlink source is forbidden: " + name)
    if not path.exists():
        if required:
            raise GateRejected("missing source: " + name)
        return None
    if path.is_symlink() or not path.is_file():
        raise GateRejected("source is not a regular non-symlink file: " + name)
    return bounded_file(path, 4 * 1024 * 1024)


def parse_tree(output):
    flat = {}
    for item in output.split("\0"):
        if not item:
            continue
        header, name = item.split("\t", 1)
        mode, kind, digest = header.split()
        valid_path(name)
        if name in flat or not re.fullmatch(r"[0-9a-f]{40}", digest):
            raise GateRejected("invalid Git source inventory")
        flat[name] = {"mode": mode, "type": kind, "sha": digest}
    if not flat:
        raise GateRejected("empty Git source inventory")
    return flat


def complete_tree(flat):
    root = {}
    for path, entry in flat.items():
        node = root
        parts = path.split("/")
        for part in parts[:-1]:
            node = node.setdefault(part, {})
        if parts[-1] in node:
            raise GateRejected("duplicate source tree path")
        node[parts[-1]] = (entry["mode"], entry["sha"])
    def encode(node):
        values = []
        for name, value in node.items():
            directory = isinstance(value, dict)
            mode, digest = ("40000", encode(value)) if directory else value
            order = name.encode() + (b"/" if directory else b"")
            values.append((order, mode, name, digest))
        data = b"".join(mode.encode() + b" " + name.encode() + b"\0" + bytes.fromhex(digest)
                        for _, mode, name, digest in sorted(values))
        return hashlib.sha1(b"tree " + str(len(data)).encode() + b"\0" + data).hexdigest()
    return encode(root)


def patch_sections(patch):
    sections = []
    for section in re.split(r"(?=^diff --git )", patch, flags=re.M):
        if not section:
            continue
        lines = section.splitlines()
        header = re.fullmatch(r"diff --git a/(.+) b/(.+)", lines[0])
        if header is None or header[1] != header[2]:
            raise GateRejected("unsupported patch path or rename")
        path = header[2]
        valid_path(path)
        hunks = []
        index = 1
        while index < len(lines):
            match = re.match(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@", lines[index])
            if match is None:
                if lines[index].startswith(("@@", "GIT binary", "rename ", "deleted file")):
                    raise GateRejected("unsupported patch operation")
                index += 1
                continue
            old, new = [], []
            index += 1
            while index < len(lines) and not lines[index].startswith("@@"):
                line = lines[index]
                if not line or line[0] not in " +-":
                    raise GateRejected("invalid patch body / unsupported missing newline")
                if line[0] in " -":
                    old.append(line[1:])
                if line[0] in " +":
                    new.append(line[1:])
                index += 1
            if len(old) != int(match[2] or 1) or len(new) != int(match[4] or 1):
                raise GateRejected("patch hunk count mismatch")
            hunks.append({"old_start": int(match[1]),
                          "old": ("\n".join(old) + "\n") if old else "",
                          "new": ("\n".join(new) + "\n") if new else ""})
        if not hunks:
            raise GateRejected("patch has no hunks")
        sections.append((path, hunks))
    if not sections:
        raise GateRejected("empty patch")
    return sections


def apply_exact(files, patch, receipts):
    for path, hunks in patch_sections(patch):
        value = files.get(path)
        for hunk in hunks:
            old, new = hunk["old"], hunk["new"]
            if old:
                at = -1 if value is None else value.find(old)
                if at < 0 or value.find(old, at + 1) >= 0:
                    raise GateRejected("missing or nonunique complete hunk preimage: " + path)
                actual = value[:at].count("\n") + 1
                value = value[:at] + new + value[at + len(old):]
            else:
                if value is not None:
                    raise GateRejected("new patch path already exists: " + path)
                actual, value = 0, new
            receipts.append({"path": path, "old_start": hunk["old_start"], "actual_start": actual})
        files[path] = value


def overlay(files, entries):
    # Validate every preimage before modifying even the in-memory stage.
    for path, entry in entries.items():
        valid_path(path)
        content = files.get(path)
        digest = None if content is None else git_blob(content.encode())
        if digest != entry["original_blob"]:
            raise GateRejected("overlay preimage mismatch: " + path)
        if not isinstance(entry["content"], str):
            raise GateRejected("overlay content is not UTF-8 text")
    files.update({path: entry["content"] for path, entry in entries.items()})


def flat_with_files(base, files):
    flat = dict(base)
    for path, content in files.items():
        if content is not None:
            flat[path] = {"mode": base.get(path, {}).get("mode", "100644"),
                          "type": "blob", "sha": git_blob(content.encode())}
    return flat


def fetch_inputs(runner, work, env, manifest):
    root = work / "immutable-public-inputs"
    root.mkdir()
    runner.ok("inputs-init", ["git", "init", "-q"], root, env, 30)
    revisions = list(dict.fromkeys(item["commit"] for item in manifest["inputs"].values()))
    if manifest["publication_base"] not in revisions:
        revisions.append(manifest["publication_base"])
    for index, revision in enumerate(revisions):
        runner.ok(f"input-fetch-{index}", ["git", "fetch", "--depth=1",
                  "https://github.com/" + PUBLICATION_REPOSITORY + ".git", revision],
                  root, env, 180, 2 * 1024 * 1024)
        observed = runner.ok(f"input-pin-{index}", ["git", "rev-parse", "FETCH_HEAD"],
                             root, env, 10).strip()
        if observed != revision:
            raise GateRejected("immutable publication revision mismatch")
    inputs = {}
    for key, item in manifest["inputs"].items():
        if item["repository"] != PUBLICATION_REPOSITORY:
            raise GateRejected("unexpected input repository")
        valid_path(item["path"])
        text = runner.ok("input-" + key, ["git", "show", item["commit"] + ":" + item["path"]],
                         root, env, 30, item["bytes"] + 1)
        raw = text.encode()
        if len(raw) != item["bytes"] or sha(raw) != item["sha256"] or git_blob(raw) != item["git_blob"]:
            raise GateRejected("immutable input content mismatch: " + key)
        inputs[key] = text
    return root, inputs


def plan_composition(root, base, inputs, manifest, baseline):
    ownership = strict_json(inputs["ownership"])
    if ownership["version"] != "ownership-coordinated-v7" or ownership["base_commit"] != CORE_PIN:
        raise GateRejected("wrong ownership prerequisite")
    names = set(manifest["production_blobs"]) | set(manifest["baseline_blobs"])
    files = {name: None for name in names}
    # ALL actual original bytes are validated, then both plans are built in memory.
    for name in sorted(names):
        value = source_bytes(root, name, required=name in base)
        if name in base and (base[name]["type"] != "blob" or
                            base[name]["mode"] not in {"100644", "100755"} or
                            git_blob(value) != base[name]["sha"]):
            raise GateRejected("actual source preimage mismatch: " + name)
        files[name] = None if value is None else value.decode("utf-8")
    entries = ({TEST_PATH: ownership["files"][TEST_PATH],
                **ownership["baseline_additional_files"]} if baseline else ownership["files"])
    overlay(files, entries)
    stage_trees = {"ownership_tests" if baseline else "ownership": complete_tree(flat_with_files(base, files))}
    receipts = []
    apply_exact(files, inputs["recovery_tests"], receipts)
    if not baseline:
        apply_exact(files, inputs["recovery_fix"], receipts)
    stage_trees["recovery_tests" if baseline else "recovery"] = complete_tree(flat_with_files(base, files))
    apply_exact(files, inputs["admission_tests"], receipts)
    if not baseline:
        apply_exact(files, inputs["admission_fix"], receipts)
    stage_trees["final"] = complete_tree(flat_with_files(base, files))
    expected_stages = manifest["baseline_stage_trees" if baseline else "production_stage_trees"]
    if stage_trees != expected_stages:
        raise GateRejected("complete composition stage tree mismatch")
    changed = {path: value.encode() for path, value in files.items()
               if value is not None and git_blob(value.encode()) != base.get(path, {}).get("sha")}
    expected = manifest["baseline_blobs" if baseline else "production_blobs"]
    if {path: git_blob(raw) for path, raw in changed.items()} != expected:
        raise GateRejected("exact changed-path/postimage map mismatch")
    if not baseline:
        app = files["crates/proteus-core/src/app_server.rs"]
        own = ownership["files"]["crates/proteus-core/src/app_server.rs"]["content"]
        begin, end = "    pub async fn delete_workspace_session(", "    pub fn is_session_dir("
        old_methods = own[own.index(begin):own.index(end)]
        if app.count(old_methods) != 1:
            raise GateRejected("ownership coordinated deletion methods were not preserved verbatim")
        for marker in manifest["retention"]["required_app_server"]:
            if app.count(marker) != 1:
                raise GateRejected("missing or duplicated recovery/ownership retention marker")
        for marker in manifest["retention"]["forbidden_app_server"]:
            if marker in app:
                raise GateRejected("old recovery implementation survived composition")
        admission = strict_json(inputs["admission_manifest"])
        for path, digest in admission["stage_git_blobs"]["fixed"].items():
            if git_blob(changed[path]) != digest:
                raise GateRejected("admission postimage changed during composition")
    return changed, {"stage_trees": stage_trees, "hunks": receipts,
                     "blobs": {path: git_blob(raw) for path, raw in changed.items()}}


def materialize(runner, label, root, changed, expected_tree, env):
    # Called only after ALL baseline and candidate preflight checks succeeded.
    for name, raw in changed.items():
        target = root / valid_path(name)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
        if source_bytes(root, name) != raw:
            raise GateRejected("materialized source readback mismatch")
    runner.ok(label + "-stage", ["git", "add", "--", *sorted(changed)], root, env, 30)
    tree = runner.ok(label + "-tree", ["git", "write-tree"], root, env, 30).strip()
    if tree != expected_tree:
        raise GateRejected("materialized complete tree mismatch")
    runner.ok(label + "-diff-check", ["git", "diff", "--cached", "--check"], root, env, 30)


def require_passes(output, names, *, exact_inventory=False, allowed_ignored=()):
    outcomes = re.findall(r"^test (.+?) \.\.\. (ok|FAILED|ignored)(?:, [^\n]*)?$", output, re.M)
    passed = [name for name, status in outcomes if status == "ok"]
    ignored = [name for name, status in outcomes if status == "ignored"]
    if any(status == "FAILED" for _, status in outcomes):
        raise GateRejected("unexpected named test failure in successful command")
    for name in names:
        if passed.count(name) != 1 or name in ignored:
            raise GateRejected("required test missing, duplicated or ignored: " + name)
    if exact_inventory and (len(passed) != len(names) or set(passed) != set(names)):
        raise GateRejected("unexpected complete test inventory")
    if len(ignored) != len(set(ignored)) or set(ignored) - set(allowed_ignored):
        raise GateRejected("unexpected or duplicated ignored case")
    summaries = re.findall(
        r"^test result: (ok|FAILED)\. (\d+) passed; (\d+) failed; "
        r"(\d+) ignored; (\d+) measured; (\d+) filtered out; finished in [^\n]+$",
        output, re.M)
    if not summaries or any(s[0] != "ok" or int(s[2]) or int(s[4]) or int(s[5]) for s in summaries):
        raise GateRejected("missing or inconsistent successful libtest summaries")
    if (sum(int(s[1]) for s in summaries) != len(passed) or
        sum(int(s[3]) for s in summaries) != len(ignored)):
        raise GateRejected("PASS inventory differs from libtest summary total")
    return {"passed": passed, "ignored": ignored,
            "libtest_passed_count": len(passed), "summaries": summaries}


def compile_protocol_library(runner, lane, root, env):
    output = runner.ok(lane + "-protocol-compile",
                      ["cargo", "test", "--locked", "-p", "proteus-module-protocol", "--lib",
                       "--no-run", "--message-format=json"], root, env, 1800, 24 * 1024 * 1024)
    emitted = []
    for line in output.splitlines():
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        target = item.get("target", {})
        if (item.get("reason") == "compiler-artifact" and item.get("executable") and
            target.get("name") == "proteus_module_protocol" and target.get("kind") == ["lib"]):
            if Path(target["src_path"]).resolve() != (root / "crates/proteus-module-protocol/src/lib.rs").resolve():
                raise GateRejected("unexpected protocol library source")
            emitted.append(Path(item["executable"]).resolve())
    if len(emitted) != 1 or not emitted[0].is_relative_to(Path(env["CARGO_TARGET_DIR"])):
        raise GateRejected("missing or ambiguous protocol test executable")
    return emitted[0]


def source_after(runner, label, root, env, before, tree):
    after = tracked_snapshot(runner, label + "-source-after", root, env)
    if after != before:
        raise GateRejected(label + ": source changed during tests")
    runner.ok(label + "-no-unstaged", ["git", "diff", "--quiet"], root, env, 30)
    extra = runner.ok(label + "-no-untracked",
                     ["git", "ls-files", "--others", "--exclude-standard"], root, env, 30)
    if extra.strip():
        raise GateRejected(label + ": unexpected untracked source")
    observed = runner.ok(label + "-final-tree", ["git", "write-tree"], root, env, 30).strip()
    if observed != tree:
        raise GateRejected(label + ": source index changed")
    return sha(json.dumps(after, sort_keys=True, separators=(",", ":")).encode())


def checkout(runner, label, destination, repo, revision, env):
    destination.mkdir()
    runner.ok(label + "-init", ["git", "init", "-q"], destination, env, 30)
    runner.ok(label + "-fetch",
              ["git", "fetch", "--depth=1", repo, revision],
              destination, env, 180, 2 * 1024 * 1024)
    runner.ok(label + "-checkout", ["git", "checkout", "--detach", "FETCH_HEAD"],
              destination, env, 30)
    head = runner.ok(label + "-pin", ["git", "rev-parse", "HEAD"],
                     destination, env, 10).strip()
    if head != revision:
        raise GateRejected(f"{label}: wrong source revision")


def tracked_snapshot(runner, label, root, env, extra_files=()):
    listing = runner.ok(label, ["git", "ls-files", "-z"], root, env, 30, 2 * 1024 * 1024)
    files = {}
    for name in listing.split("\0"):
        if name:
            files[name] = sha(bounded_file(root / name, 32 * 1024 * 1024))
    # New authored files are untracked in the detached source checkout too.
    for name in extra_files:
        if name not in files:
            files[name] = sha(bounded_file(root / name, 4 * 1024 * 1024))
    return files


def compile_target(runner, lane, root, env):
    output = runner.ok(
        lane + "-compile",
        ["cargo", "test", "--locked", "-p", "proteus-core", "--test", TARGET,
         "--no-run", "--message-format=json"],
        root, env, 1500, 20 * 1024 * 1024,
    )
    emitted = []
    for line in output.splitlines():
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if (item.get("reason") == "compiler-artifact" and item.get("executable") and
            item.get("target", {}).get("name") == TARGET and
            item["target"].get("kind") == ["test"]):
            expected = (root / TEST_PATH).resolve()
            if Path(item["target"]["src_path"]).resolve() != expected:
                raise GateRejected("unexpected test target source")
            emitted.append(Path(item["executable"]).resolve())
    if len(emitted) != 1 or not emitted[0].is_relative_to(Path(env["CARGO_TARGET_DIR"])):
        raise GateRejected("missing or ambiguous compiled test executable")
    return emitted[0]


def listed_tests(output):
    return re.findall(r"^(\S+): test$", output, re.M)


def inventory(runner, lane, binary, root, env, specs):
    output = runner.ok(lane + "-inventory", [binary, "--list", "--format", "terse"],
                       root, env, 30, 128 * 1024)
    names = listed_tests(output)
    expected = specs["candidate_mandatory_tests"] + [specs["intentional_ignored_helper"]]
    if len(names) != len(expected) or set(names) != set(expected):
        raise GateRejected(f"{lane}: unexpected test inventory")
    output = runner.ok(lane + "-ignored", [binary, "--list", "--ignored", "--format", "terse"],
                       root, env, 30, 128 * 1024)
    if listed_tests(output) != [specs["intentional_ignored_helper"]]:
        raise GateRejected(f"{lane}: mandatory test is ignored")


def compile_library(runner, lane, root, env):
    output = runner.ok(
        lane + "-library-compile",
        ["cargo", "test", "--locked", "-p", "proteus-core", "--lib",
         "--no-run", "--message-format=json"],
        root, env, 1500, 20 * 1024 * 1024,
    )
    emitted = []
    for line in output.splitlines():
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if (item.get("reason") == "compiler-artifact" and item.get("executable") and
            item.get("target", {}).get("name") == "proteus_core" and
            item["target"].get("kind") == ["lib"]):
            expected = (root / "crates/proteus-core/src/lib.rs").resolve()
            if Path(item["target"]["src_path"]).resolve() != expected:
                raise GateRejected("unexpected library test source")
            emitted.append(Path(item["executable"]).resolve())
    if len(emitted) != 1 or not emitted[0].is_relative_to(Path(env["CARGO_TARGET_DIR"])):
        raise GateRejected("missing or ambiguous compiled library test executable")
    return emitted[0]


def library_inventory(runner, lane, binary, root, env, required):
    output = runner.ok(lane + "-library-inventory", [binary, "--list", "--format", "terse"],
                       root, env, 30, 256 * 1024)
    names = listed_tests(output)
    if any(names.count(name) != 1 for name in required):
        raise GateRejected("required library test missing or duplicated")
    output = runner.ok(lane + "-library-ignored",
                       [binary, "--list", "--ignored", "--format", "terse"],
                       root, env, 30, 128 * 1024)
    ignored = listed_tests(output)
    if set(required) & set(ignored):
        raise GateRejected("required library test is ignored")


def plan_instrumented(root, base, production_changed, patch, manifest):
    spec = manifest["cross_control"]
    paths = set(production_changed) | set(spec["preimage_blobs"])
    files = {}
    for path in paths:
        raw = source_bytes(root, path, required=path in base)
        if path in base:
            if base[path]["type"] != "blob" or base[path]["mode"] not in {"100644", "100755"} or git_blob(raw) != base[path]["sha"]:
                raise GateRejected("actual instrumentation base source mismatch")
        elif raw is not None:
            raise GateRejected("unexpected pre-existing test-only source path")
        files[path] = None if raw is None else raw.decode("utf-8")
    files.update({path: raw.decode("utf-8") for path, raw in production_changed.items()})
    if complete_tree(flat_with_files(base, files)) != manifest["production_stage_trees"]["final"]:
        raise GateRejected("instrumentation prerequisite is not exact production composition")
    for path, digest in spec["preimage_blobs"].items():
        raw = files.get(path)
        if (None if raw is None else git_blob(raw.encode())) != digest:
            raise GateRejected("test-only instrumentation preimage mismatch")
    before = dict(files)
    receipts = []
    apply_exact(files, patch, receipts)
    touched = {path for path in set(before) | set(files) if before.get(path) != files.get(path)}
    if touched != set(spec["postimage_blobs"]):
        raise GateRejected("instrumentation changed an unexpected path")
    if {path: git_blob(files[path].encode()) for path in touched} != spec["postimage_blobs"]:
        raise GateRejected("test-only instrumentation postimage mismatch")
    tree = complete_tree(flat_with_files(base, files))
    if tree != spec["tree"]:
        raise GateRejected("instrumented full source tree mismatch")
    changed = {path: text.encode() for path, text in files.items()
               if text is not None and git_blob(text.encode()) != base.get(path, {}).get("sha")}
    return changed, {"tree": tree, "hunks": receipts,
                     "blobs": {path: git_blob(raw) for path, raw in changed.items()},
                     "production_prerequisite_tree": manifest["production_stage_trees"]["final"]}


def qualify(args):
    if args.phase not in PHASE_STATUS:
        raise GateRejected("one exact phase is required")
    manifest_path = Path(args.manifest).resolve()
    if manifest_path != Path(__file__).resolve().with_name("manifest.json"):
        raise GateRejected("manifest must be the reviewed controller sibling")
    manifest_bytes = bounded_file(manifest_path, 1024 * 1024)
    manifest = strict_json(manifest_bytes)
    if (manifest["schema"] != 1 or manifest["core"]["commit"] != CORE_PIN or
        manifest["fixture"]["commit"] != MODULES_PIN or
        manifest["publication_repository"] != PUBLICATION_REPOSITORY or
        manifest["publication_branch"] != PUBLICATION_BRANCH or
        file_sha(Path(__file__), 1024 * 1024) != manifest["controller_sha256"]):
        raise GateRejected("controller/manifest/source identity mismatch")
    work = Path(args.work).resolve()
    work.mkdir(parents=True, exist_ok=False)
    runner = Runner(Path(args.evidence).resolve(), work, 6600)
    env = clean_env(work)
    receipt = {
        "schema": 2, "status": "INCOMPLETE", "phase": args.phase,
        "publication_commit": os.environ.get("GITHUB_SHA"),
        "repository": os.environ.get("GITHUB_REPOSITORY"),
        "workflow_ref": os.environ.get("GITHUB_WORKFLOW_REF"),
        "run_id": os.environ.get("GITHUB_RUN_ID"), "run_attempt": os.environ.get("GITHUB_RUN_ATTEMPT"),
        "controller_sha256": file_sha(Path(__file__), 1024 * 1024),
        "manifest_sha256": sha(manifest_bytes),
        "hosted_image": {"os": os.environ.get("ImageOS"), "version": os.environ.get("ImageVersion")},
        "inputs": manifest["inputs"], "cases": [], "stages": runner.records,
        "source_graph": {"core": manifest["core"], "canonical_fixture": manifest["fixture"]},
        "environment_policy": {"allowlisted": sorted(env), "npm_audit": False, "secrets_inherited": False},
        "coverage": "One isolated Core-only phase; all three exact phase receipts are required for aggregate qualification",
        "resource_policy": manifest["resources"],
        "source_tree_identities": {
            "baseline": manifest["baseline_stage_trees"]["final"],
            "production": manifest["production_stage_trees"]["final"],
            "instrumented": manifest["cross_control"]["tree"],
        },
        "excluded": ["config/image add-on", "optimized shipping Modules", "portable/native consumer",
                     "dependency updates", "same-UUID reincarnation", "mixed-version safety",
                     "malicious namespace mutation", "power-loss safety", "performance claims"],
    }
    try:
        if (os.environ.get("GITHUB_ACTIONS") != "true" or
            receipt["repository"] != PUBLICATION_REPOSITORY or
            os.environ.get("GITHUB_REF") != "refs/heads/" + PUBLICATION_BRANCH or
            os.environ.get("GITHUB_EVENT_NAME") != "push" or
            not re.fullmatch(r"[0-9a-f]{40}", receipt["publication_commit"] or "")):
            raise GateRejected("isolated authorized guarded-push context required")
        publication = Path(os.environ["GITHUB_WORKSPACE"]).resolve()
        actual = runner.ok("publication-head", ["git", "rev-parse", "HEAD"],
                           publication, env, 10).strip()
        if actual != receipt["publication_commit"]:
            raise GateRejected("publication checkout differs from GITHUB_SHA")
        free = shutil.disk_usage(work).free
        receipt["initial_free_bytes"] = free
        if free < INITIAL_FREE_BYTES:
            raise InfrastructureError("experimental infrastructure admission budget below 8 GiB; not a product failure")
        receipt["tool_versions"] = {}
        for label, command in (
            ("rustc", ["rustc", "-Vv"]), ("cargo", ["cargo", "-V"]),
            ("node", ["node", "--version"]), ("npm", ["npm", "--version"]),
            ("bubblewrap", ["/usr/bin/bwrap", "--version"]), ("python", [sys.executable, "--version"]),
        ):
            receipt["tool_versions"][label] = runner.ok(
                "version-" + label, command, work, env, 30, 65536).strip()
        if not receipt["tool_versions"]["rustc"].startswith("rustc 1.95.0 "):
            raise GateRejected("wrong Rust")
        if not receipt["tool_versions"]["cargo"].startswith("cargo 1.95.0 "):
            raise GateRejected("wrong Cargo")
        if receipt["tool_versions"]["node"] != "v22.18.0":
            raise GateRejected("wrong Node")
        if receipt["tool_versions"]["bubblewrap"] != "bubblewrap 0.13.1":
            raise GateRejected("wrong sandbox backend")
        backend = Path("/usr/bin/bwrap")
        info = backend.stat()
        if backend.is_symlink() or (stat.S_IMODE(info.st_mode), info.st_uid, info.st_gid) != (0o755, 0, 0):
            raise GateRejected("bwrap must be ordinary root-owned mode 0755, not symlink")
        capabilities = runner.ok("sandbox-capabilities", ["getcap", backend], work, env, 10, 65536).strip()
        if capabilities:
            raise GateRejected("bwrap must not have file capabilities")
        receipt["sandbox_backend"] = {
            "release": "v0.13.1", "archive_sha256": "0e85c8702248b8dd64144f594147553650cdd0e4c951690345faace79c217c4d",
            "binary_sha256": file_sha(backend, 16 * 1024 * 1024),
            "mode_uid_gid": ["0755", 0, 0], "capabilities": "none", "security_policy_changes": "none"}
        inputs_root, inputs = fetch_inputs(runner, work, env, manifest)
        publication_base = parse_tree(runner.ok(
            "publication-base-tree", ["git", "ls-tree", "-r", "-z", "--full-tree", manifest["publication_base"]],
            inputs_root, env, 30, 2 * 1024 * 1024))
        publication_tree = parse_tree(runner.ok(
            "publication-tree", ["git", "ls-tree", "-r", "-z", "--full-tree", "HEAD"],
            publication, env, 30, 2 * 1024 * 1024))
        if (complete_tree(publication_base) != manifest["publication_base_tree"] or
            set(publication_tree) != set(publication_base) | set(manifest["publication_files"]) or
            any(publication_tree.get(path) != entry for path, entry in publication_base.items())):
            raise GateRejected("publication altered base content or escaped five-file scope")
        receipt["publication_tree"] = complete_tree(publication_tree)
        receipt["publication_files"] = {
            path: file_sha(publication / valid_path(path), 1024 * 1024)
            for path in manifest["publication_files"]}
        if receipt["publication_files"][manifest["readme_path"]] != manifest["readme_sha256"]:
            raise GateRejected("README identity mismatch")
        control = manifest["cross_control"]
        control_bytes = bounded_file(publication / valid_path(control["patch_path"]), 1024 * 1024)
        if (len(control_bytes) != control["bytes"] or sha(control_bytes) != control["sha256"] or
            git_blob(control_bytes) != control["git_blob"]):
            raise GateRejected("test-only control patch identity mismatch")
        control_patch = control_bytes.decode("utf-8")
        ownership = strict_json(inputs["ownership"])
        specs = ownership["validation"]
        admission = strict_json(inputs["admission_manifest"])
        recovery = strict_json(inputs["recovery_manifest"])
        if (recovery["core"] != manifest["core"] or admission["source_commit"] != CORE_PIN or
            manifest["tests"]["recovery_required"] != recovery["required_passed_tests"] or
            manifest["tests"]["protocol_required"] != admission["checks"][0]["required_passed_tests"] or
            manifest["tests"]["module_swap_required"] != admission["module_checks"][0]["required_passed_tests"]):
            raise GateRejected("component test/source manifests differ")
        baseline, candidate, instrumented, modules = (
            work / name for name in ("baseline", "candidate", "instrumented", "canonical-modules"))
        source_lanes = (("baseline", baseline), ("candidate", candidate), ("instrumented", instrumented))
        for label, root in source_lanes:
            checkout(runner, label, root, "https://github.com/Proteus-harness/Proteus-core.git", CORE_PIN, env)
        source_maps = {}
        plans = {}
        for label, root in source_lanes:
            flat = parse_tree(runner.ok(label + "-original-tree",
                ["git", "ls-tree", "-r", "-z", "--full-tree", "HEAD"], root, env, 30, 2 * 1024 * 1024))
            if complete_tree(flat) != manifest["core"]["tree"]:
                raise GateRejected("Core complete source root mismatch")
            source_maps[label] = flat
            if label != "instrumented":
                plans[label] = plan_composition(root, flat, inputs, manifest, label == "baseline")
        plans["instrumented"] = plan_instrumented(
            instrumented, source_maps["instrumented"], plans["candidate"][0], control_patch, manifest)
        # ALL three plans are verified before the first source replacement.
        receipt["all_input_preflight"] = "PASS_BEFORE_ANY_SOURCE_REPLACEMENT"
        for label, root in source_lanes:
            changed, plan = plans[label]
            expected_tree = plan["tree"] if label == "instrumented" else plan["stage_trees"]["final"]
            materialize(runner, label, root, changed, expected_tree, env)
            receipt[label + "_composition"] = plan
        runner.ok("candidate-format", ["cargo", "fmt", "--all", "--", "--check"],
                  candidate, env, 180, 2 * 1024 * 1024)
        runner.ok("instrumented-format", ["cargo", "fmt", "--all", "--", "--check"],
                  instrumented, env, 180, 2 * 1024 * 1024)
        snapshots = {label: tracked_snapshot(runner, label + "-source-before", root, env)
                     for label, root in source_lanes}
        checkout(runner, "fixture", modules, "https://github.com/Proteus-harness/Proteus-modules.git", MODULES_PIN, env)
        fixture_tree = runner.ok("fixture-tree", ["git", "rev-parse", "HEAD^{tree}"], modules, env, 10).strip()
        if fixture_tree != manifest["fixture"]["tree"]:
            raise GateRejected("wrong canonical fixture tree")
        fixture_before = tracked_snapshot(runner, "fixture-source-before", modules, env)
        fixture_env = dict(env, PROTEUS_MODULES_SOURCE=str(modules),
                           CARGO_TARGET_DIR=str(work / "fixture-target"))
        output = runner.ok("build-reference-fixture",
            [sys.executable, "scripts/build_module.py", "--target-dir", work / "fixture-target"],
            candidate, fixture_env, 1800, 24 * 1024 * 1024)
        reference = Path(output.strip().splitlines()[-1]).resolve()
        if not reference.is_file() or not reference.is_relative_to(work / "fixture-target"):
            raise GateRejected("fixture builder did not return its isolated executable")
        receipt["reference_fixture_sha256"] = file_sha(reference)
        dcp = modules / "hook/dcp"
        runner.ok("dcp-install", ["npm", "ci", "--ignore-scripts", "--no-audit", "--no-fund"],
                  dcp, fixture_env, 300, 4 * 1024 * 1024)
        runner.ok("dcp-build", ["npm", "--no-audit", "--no-fund", "run", "build"],
                  dcp, fixture_env, 300, 4 * 1024 * 1024)
        worker = dcp / "dist/worker.js"
        if not worker.is_file():
            raise GateRejected("DCP fixture worker absent")
        receipt["dcp_worker_sha256"] = file_sha(worker, 8 * 1024 * 1024)
        full_env = dict(env, PROTEUS_MODULES_SOURCE=str(modules),
                       PROTEUS_TEST_REFERENCE_MODULE=str(reference),
                       PROTEUS_TEST_DCP_MODULE=str(worker))
        protocol_reds = [(case["expected_failed_tests"][0], case["assertion_markers"][0])
                         for case in admission["baselines"]]
        selected_lanes = {"baseline": (("baseline", baseline),),
                          "production": (("candidate", candidate),), "instrumented": ()}
        for lane, root in selected_lanes[args.phase]:
            lane_env = dict(full_env, CARGO_TARGET_DIR=str(work / (lane + "-target")))
            binary = compile_target(runner, lane, root, lane_env)
            receipt[lane + "_ownership_binary_sha256"] = file_sha(binary)
            inventory(runner, lane, binary, root, lane_env, specs)
            for index, name in enumerate(specs["candidate_mandatory_tests"]):
                marker = specs["baseline_expected_red"].get(name) if lane == "baseline" else None
                result = runner.run(f"{lane}-ownership-{index:02}", [binary, "--exact", name, "--test-threads=1"],
                                    root, lane_env, 90, 256 * 1024)
                receipt["cases"].append({"lane": lane, "name": name,
                                        "stage": f"{lane}-ownership-{index:02}",
                                        "verdict": classify(result, name, marker)})
            library = compile_library(runner, lane, root, lane_env)
            receipt[lane + "_library_sha256"] = file_sha(library)
            required = (list(specs["baseline_library_expected_red"]) +
                        specs["baseline_library_positive_controls"] +
                        [manifest["tests"]["recovery_baseline_name"]] if lane == "baseline" else
                        specs["candidate_extra_unit_tests"] + specs["candidate_existing_regression_tests"] +
                        manifest["tests"]["recovery_required"])
            if len(required) != len(set(required)):
                raise GateRejected("duplicate required library case")
            library_inventory(runner, lane, library, root, lane_env, required)
            for index, name in enumerate(required):
                marker = specs["baseline_library_expected_red"].get(name) if lane == "baseline" else None
                marker_mode = "line_prefix"
                if lane == "baseline" and name == manifest["tests"]["recovery_baseline_name"]:
                    marker = manifest["tests"]["recovery_baseline_marker"]
                    marker_mode = "contains"
                result = runner.run(f"{lane}-library-{index:02}",
                    [library, "--exact", name, "--test-threads=1"], root, lane_env, 90, 256 * 1024)
                receipt["cases"].append({"lane": lane, "name": name,
                                        "stage": f"{lane}-library-{index:02}",
                                        "verdict": classify(result, name, marker, marker_mode)})
            if lane == "baseline":
                protocol = compile_protocol_library(runner, lane, root, lane_env)
                receipt["baseline_protocol_sha256"] = file_sha(protocol)
                for index, (name, marker) in enumerate(protocol_reds):
                    result = runner.run(f"baseline-admission-{index:02}",
                        [protocol, "--exact", name, "--test-threads=1"], root, lane_env, 90, 256 * 1024)
                    receipt["cases"].append({"lane": lane, "name": name,
                                            "stage": f"baseline-admission-{index:02}",
                                            "verdict": classify(result, name, marker, "error_line")})
        if args.phase == "baseline":
            baseline_cases = [item for item in receipt["cases"] if item["lane"] == "baseline"]
            if (len(baseline_cases) != 20 or
                sum(item["verdict"] == "EXPECTED_BEHAVIORAL_RED" for item in baseline_cases) != 12 or
                sum(item["verdict"] == "PASS" for item in baseline_cases) != 8):
                raise GateRejected("baseline must contain exactly twelve known reds and eight positives")
        if args.phase == "production":
            candidate_env = dict(full_env, CARGO_TARGET_DIR=str(work / "candidate-target"))
            receipt["protocol"] = require_passes(runner.ok("candidate-protocol",
                [sys.executable, "scripts/test.py", "-p", "proteus-module-protocol", "--", "--test-threads=1"],
                candidate, candidate_env, 1800, 16 * 1024 * 1024), manifest["tests"]["protocol_required"])
            receipt["module_swap"] = require_passes(runner.ok("candidate-module-swap",
                [sys.executable, "scripts/test.py", "-p", "proteus-core", "--test", "module_swap", "--", "--test-threads=1"],
                candidate, candidate_env, 1800, 16 * 1024 * 1024), manifest["tests"]["module_swap_required"],
                exact_inventory=True)
            required_full = list(dict.fromkeys(
                specs["candidate_mandatory_tests"] + specs["candidate_extra_unit_tests"] +
                specs["candidate_existing_regression_tests"] + manifest["tests"]["recovery_required"] +
                manifest["tests"]["protocol_required"] + manifest["tests"]["module_swap_required"]))
            receipt["canonical_full"] = require_passes(runner.ok("candidate-canonical-full",
                [sys.executable, "scripts/test.py", "full"], candidate, candidate_env, 1800, 40 * 1024 * 1024),
                required_full, allowed_ignored=manifest["tests"]["full_allowed_ignored"])
            if set(receipt["canonical_full"]["ignored"]) != set(manifest["tests"]["full_allowed_ignored"]):
                raise GateRejected("canonical ignored inventory changed")
        if args.phase == "instrumented":
            instrumented_env = dict(full_env, CARGO_TARGET_DIR=str(work / "instrumented-target"))
            control_binary = compile_library(runner, "instrumented", instrumented, instrumented_env)
            receipt["instrumented_library_sha256"] = file_sha(control_binary)
            library_inventory(runner, "instrumented", control_binary, instrumented,
                              instrumented_env, [control["test_name"]])
            focused = runner.run("instrumented-overlap-control",
                [control_binary, "--exact", control["test_name"], "--test-threads=1", "--show-output"],
                instrumented, instrumented_env, 180, 1024 * 1024)
            receipt["cross_control"] = {"test_name": control["test_name"],
                "tree": control["tree"], "verdict": classify(focused, control["test_name"]),
                "unique_test_count": 1, "schedule_count": len(control["schedule_markers"])}
            markers = re.findall(r"^RECOVERY_OWNED_DELETE_SCHEDULE: [^\n]+$", focused["output"], re.M)
            if len(markers) != len(control["schedule_markers"]) or set(markers) != set(control["schedule_markers"]):
                raise GateRejected("cross-control did not finish each exact schedule once")
            receipt["cross_control"]["completed_schedule_markers"] = markers
            instrumented_required = list(dict.fromkeys(
                specs["candidate_extra_unit_tests"] + specs["candidate_existing_regression_tests"] +
                manifest["tests"]["recovery_required"] + [control["test_name"]]))
            unit_ignored = [name for name in manifest["tests"]["full_allowed_ignored"]
                            if name.startswith("core::")]
            receipt["instrumented_parallel_unit_suite"] = require_passes(runner.ok(
                "instrumented-parallel-unit-suite", [sys.executable, "scripts/test.py", "-p", "proteus-core", "--lib"],
                instrumented, instrumented_env, 1800, 24 * 1024 * 1024),
                instrumented_required, allowed_ignored=unit_ignored)
            if set(receipt["instrumented_parallel_unit_suite"]["ignored"]) != set(unit_ignored):
                raise GateRejected("instrumented unit-suite ignored inventory changed")
        for label, root in source_lanes:
            plan = plans[label][1]
            expected_tree = plan["tree"] if label == "instrumented" else plan["stage_trees"]["final"]
            receipt[label + "_source_snapshot_sha256"] = source_after(
                runner, label, root, env, snapshots[label], expected_tree)
        receipt["fixture_source_snapshot_sha256"] = source_after(
            runner, "fixture", modules, env, fixture_before, manifest["fixture"]["tree"])
        receipt["status"] = PHASE_STATUS[args.phase]
        if args.phase == "baseline":
            receipt["baseline_expected_red_count"] = 12
            receipt["baseline_positive_count"] = 8
        if args.phase == "production":
            receipt["required_full_named_passes"] = required_full
        receipt["counting_note"] = "Focused/full repeated executions are not extra unique tests. The overlap control is one new unique test with four deterministic schedules; its instrumentation tree is not production. No config/image or shipping-consumer qualification."
    except BaseException as error:
        receipt["status"] = "INFRASTRUCTURE_ERROR" if is_infrastructure(error) else "GATE_REJECTED"
        receipt["error"] = f"{type(error).__name__}: {error}"
        raise
    finally:
        payload = json.dumps(receipt, indent=2, ensure_ascii=False).encode() + b"\n"
        if len(payload) > 4 * 1024 * 1024:
            raise InfrastructureError("receipt size limit")
        (runner.evidence / "result.json").write_bytes(payload)



def phase_identity(receipt, phase, manifest, manifest_hash, context, require_pass=True):
    expected = {
        "schema": 2, "phase": phase, "status": PHASE_STATUS[phase],
        "publication_commit": context["publication_commit"],
        "repository": PUBLICATION_REPOSITORY,
        "workflow_ref": context["workflow_ref"], "run_id": context["run_id"],
        "run_attempt": context["run_attempt"],
        "controller_sha256": manifest["controller_sha256"], "manifest_sha256": manifest_hash,
        "inputs": manifest["inputs"],
        "source_graph": {"core": manifest["core"], "canonical_fixture": manifest["fixture"]},
        "resource_policy": manifest["resources"],
        "source_tree_identities": {
            "baseline": manifest["baseline_stage_trees"]["final"],
            "production": manifest["production_stage_trees"]["final"],
            "instrumented": manifest["cross_control"]["tree"],
        },
    }
    for key, value in expected.items():
        if key == "status" and not require_pass:
            continue
        if receipt.get(key) != value:
            raise GateRejected(f"{phase}: mismatched or nonpassing phase identity: {key}")
    if require_pass and (type(receipt.get("initial_free_bytes")) is not int or
            receipt["initial_free_bytes"] < INITIAL_FREE_BYTES):
        raise GateRejected(f"{phase}: missing admitted infrastructure budget")
    return expected


def phase_logs(root, receipt):
    if not root.is_dir() or root.is_symlink():
        raise GateRejected("phase evidence directory is absent or indirect")
    records = receipt.get("stages")
    if not isinstance(records, list) or not 1 <= len(records) <= 180:
        raise GateRejected("missing or oversized phase stage inventory")
    paths, by_label, total = {}, {}, 0
    for record in records:
        label = record.get("stage", "")
        if not re.fullmatch(r"[A-Za-z0-9_.-]{1,120}", label) or label in by_label:
            raise GateRejected("invalid or duplicate phase stage")
        count = record.get("output_bytes")
        if type(count) is not int or not 0 <= count <= MAX_TOTAL_OUTPUT:
            raise GateRejected("invalid stage byte count")
        total += count
        if total > MAX_TOTAL_OUTPUT:
            raise GateRejected("phase output exceeds total byte cap")
        path = root / (label + ".log")
        if (not path.is_file() or path.is_symlink() or path.stat().st_size != count or
                file_sha(path, MAX_TOTAL_OUTPUT) != record.get("output_sha256")):
            raise GateRejected("raw phase output differs from its digest receipt")
        if record.get("infrastructure_error") is not None:
            raise GateRejected("nonterminal or infrastructure stage cannot satisfy aggregation")
        if record.get("exit_code") not in (0, 101):
            raise GateRejected("unexpected phase command exit")
        for key in ("disk_free_before_bytes", "disk_free_after_bytes", "disk_free_minimum_bytes"):
            if type(record.get(key)) is not int or record[key] < LOW_WATER_BYTES:
                raise GateRejected("missing or exhausted phase disk sample")
        paths[label], by_label[label] = path, record
    expected_files = {"result.json"} | {label + ".log" for label in by_label}
    if {entry.name for entry in root.iterdir()} != expected_files:
        raise GateRejected("unexpected, duplicate or missing phase evidence file")
    return paths, by_label


def validate_phase_outcome(phase, receipt, paths, records, manifest):
    def result(label):
        if label not in records:
            raise GateRejected("mandatory raw stage missing: " + label)
        return {"code": records[label]["exit_code"],
                "output": bounded_file(paths[label], MAX_TOTAL_OUTPUT).decode("utf-8", "replace")}

    def command(label, argv, cwd):
        result(label)
        if records[label].get("argv") != [str(x) for x in argv] or records[label].get("cwd") != str(cwd):
            raise GateRejected("phase command/source binding differs: " + label)

    def compiled(lane, kind):
        label = lane + {"ownership": "-compile", "library": "-library-compile",
                        "protocol": "-protocol-compile"}[kind]
        record = records[label]
        root = Path(record.get("cwd", ""))
        if not root.is_absolute() or root.name != lane or root.parent.name != "core-composition-work":
            raise GateRejected("phase compile root is not its separate source lane")
        if any(part in (".", "..") for part in root.parts):
            raise GateRejected("indirect phase compile root")
        name, target_kind, source, args = {
            "ownership": (TARGET, ["test"], TEST_PATH, ["-p", "proteus-core", "--test", TARGET]),
            "library": ("proteus_core", ["lib"], "crates/proteus-core/src/lib.rs", ["-p", "proteus-core", "--lib"]),
            "protocol": ("proteus_module_protocol", ["lib"], "crates/proteus-module-protocol/src/lib.rs",
                         ["-p", "proteus-module-protocol", "--lib"]),
        }[kind]
        command(label, ["cargo", "test", "--locked", *args, "--no-run", "--message-format=json"], root)
        emitted = []
        for line in result(label)["output"].splitlines():
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            target = item.get("target", {})
            if (item.get("reason") == "compiler-artifact" and item.get("executable") and
                    target.get("name") == name and target.get("kind") == target_kind):
                if Path(target["src_path"]) != root / source:
                    raise GateRejected("compiled executable is from a foreign source target")
                binary = Path(item["executable"])
                if (not binary.is_absolute() or ".." in binary.parts or
                    not binary.is_relative_to(root.parent / (lane + "-target"))):
                    raise GateRejected("compiled executable is outside the fresh phase target")
                emitted.append(binary)
        if len(emitted) != 1:
            raise GateRejected("missing or ambiguous raw compiled executable")
        return root, emitted[0]

    inputs = {}
    for key, expected in manifest["inputs"].items():
        raw = bounded_file(paths["input-" + key], expected["bytes"] + 1)
        if len(raw) != expected["bytes"] or sha(raw) != expected["sha256"] or git_blob(raw) != expected["git_blob"]:
            raise GateRejected("aggregated immutable public input differs")
        inputs[key] = raw.decode("utf-8")
    specs = strict_json(inputs["ownership"])["validation"]
    admission = strict_json(inputs["admission_manifest"])
    control = manifest["cross_control"]
    tests = manifest["tests"]
    expected_compiles = {
        "baseline": {"baseline-compile", "baseline-library-compile", "baseline-protocol-compile"},
        "production": {"candidate-compile", "candidate-library-compile"},
        "instrumented": {"instrumented-library-compile"},
    }
    observed_compiles = {label for label in records if re.fullmatch(
        r"(?:baseline|candidate|instrumented)-(?:compile|library-compile|protocol-compile)", label)}
    if observed_compiles != expected_compiles[phase]:
        raise GateRejected("phase compiled-target inventory is missing or foreign")
    expected_cases = []
    binaries = {}
    if phase in ("baseline", "production"):
        lane = "baseline" if phase == "baseline" else "candidate"
        root, binaries["ownership"] = compiled(lane, "ownership")
        library_root, binaries["library"] = compiled(lane, "library")
        if root != library_root:
            raise GateRejected("ownership/library source roots differ")
        command(lane + "-inventory", [binaries["ownership"], "--list", "--format", "terse"], root)
        names = listed_tests(result(lane + "-inventory")["output"])
        expected_names = specs["candidate_mandatory_tests"] + [specs["intentional_ignored_helper"]]
        if len(names) != len(expected_names) or set(names) != set(expected_names):
            raise GateRejected("raw ownership compiled inventory differs")
        command(lane + "-ignored", [binaries["ownership"], "--list", "--ignored", "--format", "terse"], root)
        if listed_tests(result(lane + "-ignored")["output"]) != [specs["intentional_ignored_helper"]]:
            raise GateRejected("raw ownership ignore inventory differs")
        if phase == "baseline":
            protocol_root, binaries["protocol"] = compiled(lane, "protocol")
            if protocol_root != root:
                raise GateRejected("protocol source root differs")
    else:
        lane = "instrumented"
        root, binaries["library"] = compiled(lane, "library")
    command(lane + "-library-inventory", [binaries["library"], "--list", "--format", "terse"], root)
    library_names = listed_tests(result(lane + "-library-inventory")["output"])
    command(lane + "-library-ignored", [binaries["library"], "--list", "--ignored", "--format", "terse"], root)
    library_ignored = listed_tests(result(lane + "-library-ignored")["output"])
    if phase in ("baseline", "production"):
        lane = "baseline" if phase == "baseline" else "candidate"
        for index, name in enumerate(specs["candidate_mandatory_tests"]):
            marker = specs["baseline_expected_red"].get(name) if phase == "baseline" else None
            expected_cases.append((f"{lane}-ownership-{index:02}", lane, name, marker, "line_prefix"))
        required = (list(specs["baseline_library_expected_red"]) +
                    specs["baseline_library_positive_controls"] + [tests["recovery_baseline_name"]]
                    if phase == "baseline" else
                    specs["candidate_extra_unit_tests"] + specs["candidate_existing_regression_tests"] +
                    tests["recovery_required"])
        if any(library_names.count(name) != 1 or name in library_ignored for name in required):
            raise GateRejected("raw required library inventory differs or is ignored")
        for index, name in enumerate(required):
            marker = specs["baseline_library_expected_red"].get(name) if phase == "baseline" else None
            mode = "line_prefix"
            if phase == "baseline" and name == tests["recovery_baseline_name"]:
                marker, mode = tests["recovery_baseline_marker"], "contains"
            expected_cases.append((f"{lane}-library-{index:02}", lane, name, marker, mode))
        if phase == "baseline":
            for index, item in enumerate(admission["baselines"]):
                expected_cases.append((f"baseline-admission-{index:02}", lane,
                    item["expected_failed_tests"][0], item["assertion_markers"][0], "error_line"))
    classified = []
    for label, lane, name, marker, mode in expected_cases:
        kind = "ownership" if "-ownership-" in label else "protocol" if "-admission-" in label else "library"
        command(label, [binaries[kind], "--exact", name, "--test-threads=1"], root)
        classified.append({"lane": lane, "name": name, "stage": label,
                           "verdict": classify(result(label), name, marker, mode)})
    if receipt.get("cases") != classified:
        raise GateRejected("phase case inventory/classification differs from exact raw evidence")
    permitted_nonzero = {item["stage"] for item in classified if item["verdict"] == "EXPECTED_BEHAVIORAL_RED"}
    if {label for label, item in records.items() if item["exit_code"] != 0} != permitted_nonzero:
        raise GateRejected("unrelated nonzero stage cannot be baseline evidence")

    if phase == "baseline":
        if (len(classified) != 20 or
            sum(item["verdict"] == "EXPECTED_BEHAVIORAL_RED" for item in classified) != 12 or
            sum(item["verdict"] == "PASS" for item in classified) != 8 or
            receipt.get("baseline_expected_red_count") != 12 or receipt.get("baseline_positive_count") != 8):
            raise GateRejected("baseline aggregate count differs from twelve reds/eight positives")
    elif phase == "production":
        required_full = list(dict.fromkeys(
            specs["candidate_mandatory_tests"] + specs["candidate_extra_unit_tests"] +
            specs["candidate_existing_regression_tests"] + tests["recovery_required"] +
            tests["protocol_required"] + tests["module_swap_required"]))
        for key, label, required, exact, ignored in (
            ("protocol", "candidate-protocol", tests["protocol_required"], False, []),
            ("module_swap", "candidate-module-swap", tests["module_swap_required"], True, []),
            ("canonical_full", "candidate-canonical-full", required_full, False, tests["full_allowed_ignored"]),
        ):
            arguments = {
                "candidate-protocol": ["scripts/test.py", "-p", "proteus-module-protocol", "--", "--test-threads=1"],
                "candidate-module-swap": ["scripts/test.py", "-p", "proteus-core", "--test", "module_swap", "--", "--test-threads=1"],
                "candidate-canonical-full": ["scripts/test.py", "full"],
            }[label]
            actual_argv = records[label].get("argv", [])
            if not actual_argv or Path(actual_argv[0]).name != "python3":
                raise GateRejected("canonical gate interpreter differs")
            command(label, [actual_argv[0], *arguments], root)
            checked = strict_json(json.dumps(require_passes(result(label)["output"], required,
                                     exact_inventory=exact, allowed_ignored=ignored)))
            if receipt.get(key) != checked or set(checked["ignored"]) != set(ignored):
                raise GateRejected("production aggregate differs from raw required gate")
        if receipt.get("required_full_named_passes") != required_full:
            raise GateRejected("required production names changed")
    else:
        if library_names.count(control["test_name"]) != 1 or control["test_name"] in library_ignored:
            raise GateRejected("instrumented case is missing, duplicated or ignored")
        command("instrumented-overlap-control",
                [binaries["library"], "--exact", control["test_name"], "--test-threads=1", "--show-output"], root)
        focused = result("instrumented-overlap-control")
        markers = re.findall(r"^RECOVERY_OWNED_DELETE_SCHEDULE: [^\n]+$", focused["output"], re.M)
        if (len(markers) != 4 or set(markers) != set(control["schedule_markers"])):
            raise GateRejected("instrumented aggregate lacks four exact completed schedules")
        expected_control = {
            "test_name": control["test_name"], "tree": control["tree"],
            "verdict": classify(focused, control["test_name"]), "unique_test_count": 1,
            "schedule_count": 4, "completed_schedule_markers": markers,
        }
        if receipt.get("cross_control") != expected_control:
            raise GateRejected("instrumented focus receipt differs from raw output")
        required = list(dict.fromkeys(
            specs["candidate_extra_unit_tests"] + specs["candidate_existing_regression_tests"] +
            tests["recovery_required"] + [control["test_name"]]))
        ignored = [name for name in tests["full_allowed_ignored"] if name.startswith("core::")]
        actual_argv = records["instrumented-parallel-unit-suite"].get("argv", [])
        if not actual_argv or Path(actual_argv[0]).name != "python3":
            raise GateRejected("instrumented canonical gate interpreter differs")
        command("instrumented-parallel-unit-suite",
                [actual_argv[0], "scripts/test.py", "-p", "proteus-core", "--lib"], root)
        checked = strict_json(json.dumps(require_passes(result("instrumented-parallel-unit-suite")["output"],
                                 required, allowed_ignored=ignored)))
        if (receipt.get("instrumented_parallel_unit_suite") != checked or
                set(checked["ignored"]) != set(ignored)):
            raise GateRejected("instrumented parallel gate differs from raw output")
    for lane in ("baseline", "candidate", "instrumented", "fixture"):
        digest = receipt.get(lane + "_source_snapshot_sha256", "")
        if not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise GateRejected("missing unchanged source/index snapshot")
        expected_tree = {
            "baseline": manifest["baseline_stage_trees"]["final"],
            "candidate": manifest["production_stage_trees"]["final"],
            "instrumented": manifest["cross_control"]["tree"],
            "fixture": manifest["fixture"]["tree"],
        }[lane]
        if result(lane + "-final-tree")["output"].strip() != expected_tree:
            raise GateRejected("raw final source tree differs from frozen identity")
        if (result(lane + "-no-unstaged")["output"] or result(lane + "-no-untracked")["output"]):
            raise GateRejected("raw source/index cleanliness evidence is nonempty")
        if result(lane + "-source-after")["output"] != result(lane + "-source-before")["output"]:
            raise GateRejected("raw source inventory changed during phase")
    for key in ("reference_fixture_sha256", "dcp_worker_sha256"):
        if not re.fullmatch(r"[0-9a-f]{64}", receipt.get(key, "")):
            raise GateRejected("missing fixture binary provenance")
    binary_keys = {
        "baseline": ("baseline_ownership_binary_sha256", "baseline_library_sha256", "baseline_protocol_sha256"),
        "production": ("candidate_ownership_binary_sha256", "candidate_library_sha256"),
        "instrumented": ("instrumented_library_sha256",),
    }
    for key in binary_keys[phase]:
        if not re.fullmatch(r"[0-9a-f]{64}", receipt.get(key, "")):
            raise GateRejected("missing phase binary provenance")


def aggregate(args):
    evidence = Path(args.evidence).resolve()
    evidence.mkdir(parents=True, exist_ok=False)
    summary = {"schema": 2, "status": "INCOMPLETE", "phases": {}}
    try:
        manifest_path = Path(args.manifest).resolve()
        if manifest_path != Path(__file__).resolve().with_name("manifest.json"):
            raise GateRejected("aggregate manifest must be reviewed controller sibling")
        raw_manifest = bounded_file(manifest_path, 1024 * 1024)
        manifest = strict_json(raw_manifest)
        if (manifest["schema"] != 1 or
            file_sha(Path(__file__), 1024 * 1024) != manifest["controller_sha256"] or
            manifest["publication_repository"] != PUBLICATION_REPOSITORY or
            manifest["publication_branch"] != PUBLICATION_BRANCH):
            raise GateRejected("aggregate controller/manifest identity mismatch")
        context = {
            "publication_commit": os.environ.get("GITHUB_SHA"),
            "workflow_ref": os.environ.get("GITHUB_WORKFLOW_REF"),
            "run_id": os.environ.get("GITHUB_RUN_ID"), "run_attempt": os.environ.get("GITHUB_RUN_ATTEMPT"),
        }
        expected_workflow = PUBLICATION_REPOSITORY + "/.github/workflows/core-foundation-composition.yml@refs/heads/" + PUBLICATION_BRANCH
        if (os.environ.get("GITHUB_ACTIONS") != "true" or
            os.environ.get("GITHUB_REPOSITORY") != PUBLICATION_REPOSITORY or
            os.environ.get("GITHUB_REF") != "refs/heads/" + PUBLICATION_BRANCH or
            os.environ.get("GITHUB_EVENT_NAME") != "push" or
            context["workflow_ref"] != expected_workflow or
            not re.fullmatch(r"[0-9a-f]{40}", context["publication_commit"] or "") or
            not re.fullmatch(r"[1-9][0-9]*", context["run_id"] or "") or
            not re.fullmatch(r"[1-9][0-9]*", context["run_attempt"] or "")):
            raise GateRejected("aggregate requires the exact successful current-run matrix")
        publication = Path(os.environ["GITHUB_WORKSPACE"]).resolve()
        git = subprocess.run(["git", "rev-parse", "HEAD", "HEAD^{tree}"], cwd=publication,
            env={"PATH": os.environ["PATH"], "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": "/dev/null"},
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=10)
        observed = git.stdout.decode("ascii", "strict").splitlines()
        if (git.returncode != 0 or len(git.stdout) > 256 or len(git.stderr) > 4096 or
            observed[:1] != [context["publication_commit"]] or len(observed) != 2 or
            not re.fullmatch(r"[0-9a-f]{40}", observed[1])):
            raise GateRejected("aggregate publication checkout differs from exact head")
        publication_files = {path: file_sha(publication / valid_path(path), 1024 * 1024)
                             for path in manifest["publication_files"]}
        root = Path(args.aggregate).absolute()
        summary.update(context)
        # Preserve a current-run infrastructure outcome even when another phase
        # was skipped and therefore has no artifact. This can never create PASS.
        for phase in PHASE_STATUS:
            candidate_receipt = root / phase / "core-composition-evidence" / "result.json"
            if candidate_receipt.is_file() and not candidate_receipt.is_symlink():
                candidate_raw = bounded_file(candidate_receipt, 4 * 1024 * 1024)
                candidate = strict_json(candidate_raw)
                phase_identity(candidate, phase, manifest, sha(raw_manifest), context, require_pass=False)
                if candidate.get("status") == "INFRASTRUCTURE_ERROR":
                    summary["phases"][phase] = {"status": "INFRASTRUCTURE_ERROR",
                        "receipt_sha256": sha(candidate_raw), "error": candidate.get("error")}
                    raise InfrastructureError(phase + ": exact current-run phase reported infrastructure failure")
        if (os.environ.get("QUALIFICATION_MATRIX_RESULT") != "success" or
                os.environ.get("INSTRUMENTED_JOB_RESULT") != "success"):
            raise GateRejected("aggregate requires every phase job to succeed")
        if not root.is_dir() or root.is_symlink() or {x.name for x in root.iterdir()} != set(PHASE_STATUS):
            raise GateRejected("aggregate requires exactly three phase directories")
        common = None
        for phase in PHASE_STATUS:
            phase_root = root / phase
            if (phase_root.is_symlink() or not phase_root.is_dir() or
                {x.name for x in phase_root.iterdir()} != {"core-composition-evidence", "core-composition-bwrap-evidence.txt"}):
                raise GateRejected("foreign or incomplete phase artifact layout")
            directory = phase_root / "core-composition-evidence"
            path = directory / "result.json"
            if path.is_symlink() or not path.is_file():
                raise GateRejected("missing or indirect phase receipt")
            raw = bounded_file(path, 4 * 1024 * 1024)
            receipt = strict_json(raw)
            phase_identity(receipt, phase, manifest, sha(raw_manifest), context)
            if (receipt.get("publication_tree") != observed[1] or
                receipt.get("publication_files") != publication_files or
                receipt.get("all_input_preflight") != "PASS_BEFORE_ANY_SOURCE_REPLACEMENT"):
                raise GateRejected("phase publication/preflight evidence differs")
            paths, records = phase_logs(directory, receipt)
            validate_phase_outcome(phase, receipt, paths, records, manifest)
            if (receipt["baseline_composition"]["stage_trees"] != manifest["baseline_stage_trees"] or
                receipt["candidate_composition"]["stage_trees"] != manifest["production_stage_trees"] or
                receipt["instrumented_composition"]["tree"] != manifest["cross_control"]["tree"] or
                receipt["baseline_composition"]["blobs"] != manifest["baseline_blobs"] or
                receipt["candidate_composition"]["blobs"] != manifest["production_blobs"] or
                receipt["instrumented_composition"]["blobs"] != dict(
                    manifest["production_blobs"], **manifest["cross_control"]["postimage_blobs"])):
                raise GateRejected("phase composition identities differ from frozen manifest")
            shared = {key: receipt[key] for key in (
                "baseline_composition", "candidate_composition", "instrumented_composition",
                "baseline_source_snapshot_sha256", "candidate_source_snapshot_sha256",
                "instrumented_source_snapshot_sha256", "fixture_source_snapshot_sha256",
            )}
            if common is not None and shared != common:
                raise GateRejected("phase source composition or retained snapshots disagree")
            common = shared
            sandbox = phase_root / "core-composition-bwrap-evidence.txt"
            if sandbox.is_symlink() or not sandbox.is_file():
                raise GateRejected("missing sandbox prerequisite receipt")
            sandbox_raw = bounded_file(sandbox, 64 * 1024)
            if b"unprivileged_namespace_and_fd_probe=PASS\n" not in sandbox_raw:
                raise GateRejected("missing real sandbox prerequisite")
            summary["phases"][phase] = {
                "receipt_sha256": sha(raw), "status": receipt["status"],
                "stages": len(records), "raw_log_bytes": sum(r["output_bytes"] for r in records.values()),
                "initial_free_bytes": receipt["initial_free_bytes"],
                "minimum_sampled_free_bytes": min(r["disk_free_minimum_bytes"] for r in records.values()),
                "sandbox_receipt_sha256": sha(sandbox_raw),
            }
        summary.update(context)
        summary["manifest_sha256"] = sha(raw_manifest)
        summary["controller_sha256"] = manifest["controller_sha256"]
        summary["source_tree_identities"] = receipt["source_tree_identities"]
        summary["shared_source_receipts"] = common
        summary["status"] = "CORE_COMPOSITION_AND_TEST_ONLY_OVERLAP_PASS"
        summary["limitations"] = "Three exact isolated phases only; no config/image, shipping Modules, portable/native or performance qualification."
    except BaseException as error:
        summary["status"] = "INFRASTRUCTURE_ERROR" if is_infrastructure(error) else "AGGREGATION_REJECTED"
        summary["error"] = f"{type(error).__name__}: {error}"
        raise
    finally:
        (evidence / "result.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")


def self_test():
    assert listed_tests(
        "app_server::ownership_tests::case: test\nhelper: test\n2 tests, 0 benchmarks\n"
    ) == ["app_server::ownership_tests::case", "helper"], "libtest inventory parser"
    name, marker = "case", "OWNERSHIP_EXAMPLE"
    good = {
        "code": 101,
        "output": ("test case ... FAILED\n\nfailures:\n\n---- case stdout ----\n"
                   "thread 'case' panicked at test.rs:1:1:\nOWNERSHIP_EXAMPLE: bad\n\n"
                   "failures:\n    case\n\n"
                   "test result: FAILED. 0 passed; 1 failed; 0 ignored; 0 measured; "
                   "0 filtered out; finished in 0.00s\n"),
    }
    assert classify(good, name, marker) == "EXPECTED_BEHAVIORAL_RED"
    mutations = [
        {"code": 1}, {"code": -9},
        {"output": good["output"].replace("test case ... FAILED", "test other ... FAILED")},
        {"output": good["output"].replace("test case ... FAILED", "test case ... ignored")},
        {"output": good["output"].replace("0 passed; 1 failed", "0 passed; 0 failed")},
        {"output": good["output"].replace("OWNERSHIP_EXAMPLE: bad", "different assertion")},
        {"output": good["output"] + "test other ... FAILED\n"},
        {"output": good["output"] + "test case ... FAILED\n"},
        {"output": good["output"] + good["output"]},
        {"output": "error[E0000]: OWNERSHIP_EXAMPLE\n"},
    ]
    for mutation in mutations:
        try:
            classify(dict(good, **mutation), name, marker)
        except GateRejected:
            pass
        else:
            raise AssertionError("classifier accepted invalid evidence")
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        runner = Runner(root / "evidence")
        env = os.environ.copy()
        cases = [
            ("huge", "import os; os.write(1,b'x'*100000)", 1.0, 4096),
            ("pipe-held", "import subprocess,sys; subprocess.Popen([sys.executable,'-c',"
             "'import time; time.sleep(20)']); print('leader exited')", 0.3, 4096),
            ("eof-live", "import os,time; os.close(1); os.close(2); time.sleep(20)", 0.3, 4096),
        ]
        for label, code, timeout, cap in cases:
            started = time.monotonic()
            try:
                runner.run(label, [sys.executable, "-c", code], root, env, timeout, cap)
            except InfrastructureError:
                pass
            else:
                raise AssertionError(f"{label}: missing infrastructure rejection")
            assert time.monotonic() - started < 6.0, "cleanup exceeded self-test bound"
        def interrupt(_number, _frame):
            raise KeyboardInterrupt("self-test interruption")
        previous = signal.signal(signal.SIGALRM, interrupt)
        signal.setitimer(signal.ITIMER_REAL, 0.1)
        try:
            try:
                runner.run("interrupted", [sys.executable, "-c", "import time; time.sleep(20)"],
                           root, env, 2.0, 4096)
            except KeyboardInterrupt:
                pass
            else:
                raise AssertionError("interrupted stage did not propagate cancellation")
        finally:
            signal.setitimer(signal.ITIMER_REAL, 0)
            signal.signal(signal.SIGALRM, previous)
    print("Controller self-tests: 10 rejection, 4 process-limit and 1 inventory parser controls passed.")


def composition_self_test():
    files = {"a.rs": "alpha\nbeta\n"}
    receipts = []
    patch = ("diff --git a/a.rs b/a.rs\n--- a/a.rs\n+++ b/a.rs\n"
             "@@ -1,2 +1,2 @@\n alpha\n-beta\n+gamma\n")
    apply_exact(files, patch, receipts)
    assert files == {"a.rs": "alpha\ngamma\n"} and len(receipts) == 1
    bad_inputs = [
        ({"a.rs": "missing\n"}, patch),
        ({"a.rs": "alpha\nbeta\nalpha\nbeta\n"}, patch),
        ({"a.rs": "alpha\nbeta\n"}, patch.replace("-1,2", "-1,3")),
        ({"a.rs": "alpha\nbeta\n"}, patch.replace("b/a.rs", "b/../a.rs")),
    ]
    for old, bad in bad_inputs:
        try:
            apply_exact(old, bad, [])
        except GateRejected:
            pass
        else:
            raise AssertionError("composition parser accepted invalid preimage")
    new_patch = "diff --git a/new.rs b/new.rs\n--- /dev/null\n+++ b/new.rs\n@@ -0,0 +1,1 @@\n+new\n"
    changed = {}
    apply_exact(changed, new_patch, [])
    assert changed == {"new.rs": "new\n"}
    try:
        apply_exact(changed, new_patch, [])
    except GateRejected:
        pass
    else:
        raise AssertionError("new source path was overwritten")
    prior = {"a.rs": "a\n", "b.rs": "b\n"}
    frozen = dict(prior)
    try:
        overlay(prior, {
            "a.rs": {"original_blob": git_blob(b"a\n"), "content": "changed\n"},
            "b.rs": {"original_blob": "0" * 40, "content": "wrong\n"},
        })
    except GateRejected:
        pass
    else:
        raise AssertionError("overlay accepted wrong late preimage")
    assert prior == frozen, "overlay mutated before complete preflight"
    assert git_blob(b"") == "e69de29bb2d1d6434b8b29ae775ad8c2e48c5391"
    assert complete_tree({}) == "4b825dc642cb6eb9a060e54bf8d69288fbee4904"
    try:
        strict_json('{"same":1,"same":2}')
    except GateRejected:
        pass
    else:
        raise AssertionError("duplicate JSON keys accepted")
    good = "test pass ... ok\ntest helper ... ignored, child process\n\ntest result: ok. 1 passed; 0 failed; 1 ignored; 0 measured; 0 filtered out; finished in 0.00s\n"
    require_passes(good, ["pass"], exact_inventory=True, allowed_ignored=["helper"])
    for output, required in ((good, ["helper"]), (good.replace("helper", "other"), ["pass"]),
                             (good.replace("1 passed", "2 passed"), ["pass"]),
                             (good.replace("0 filtered", "1 filtered"), ["pass"])):
        try:
            require_passes(output, required, allowed_ignored=["helper"])
        except GateRejected:
            pass
        else:
            raise AssertionError("full-gate classifier accepted invalid inventory")
    admission_name = "v3::runtime::tests::abandoned_start_during_restart_is_not_dispatched"
    admission_marker = "abandoned restart admission reached the frame writer"
    result_error = {"code": 101, "output": (
        f"test {admission_name} ... FAILED\n\nfailures:\n\n"
        f"---- {admission_name} stdout ----\nError: {admission_marker}\n\n"
        f"failures:\n    {admission_name}\n\n"
        "test result: FAILED. 0 passed; 1 failed; 0 ignored; 0 measured; "
        "26 filtered out; finished in 0.00s\n")}
    assert classify(result_error, admission_name, admission_marker, "error_line") == "EXPECTED_BEHAVIORAL_RED"
    for mutation in (
        {"code": 1},
        {"output": result_error["output"].replace("Error: " + admission_marker, "Error: unrelated I/O failure")},
        {"output": result_error["output"].replace("Error: " + admission_marker, "printed marker: " + admission_marker)},
        {"output": result_error["output"].replace("Error: " + admission_marker, "Error: " + admission_marker + "\nthread panicked at unrelated.rs")},
        {"output": result_error["output"].replace("Error: " + admission_marker, "Error: " + admission_marker + "\nError: " + admission_marker)},
    ):
        try:
            classify(dict(result_error, **mutation), admission_name, admission_marker, "error_line")
        except GateRejected:
            pass
        else:
            raise AssertionError("Result-returning classifier accepted unrelated failure")
    print("Composition self-tests: exact/negative hunks, preflight atomicity, Git identities, strict JSON and ignored-inventory controls passed.")



def resource_aggregation_self_test():
    assert is_infrastructure(OSError(errno.ENOSPC, "full"))
    assert is_infrastructure(OSError(errno.EDQUOT, "quota"))
    assert not is_infrastructure(OSError(errno.ENOENT, "missing"))
    assert exhausted_output("error: No space left on device (os error 28)")
    assert exhausted_output("OSError: [Errno 122] Disk quota exceeded")
    assert not exhausted_output("assertion failed: No space left on device")
    assert not exhausted_output("error[E0000]: an ordinary compiler defect")
    manifest = {
        "controller_sha256": "c" * 64, "inputs": {}, "core": {}, "fixture": {}, "resources": {},
        "baseline_stage_trees": {"final": "b" * 40}, "production_stage_trees": {"final": "c" * 40},
        "cross_control": {"tree": "d" * 40},
    }
    context = {"publication_commit": "a" * 40, "workflow_ref": "exact", "run_id": "1", "run_attempt": "2"}
    for phase in PHASE_STATUS:
        receipt = {
            "schema": 2, "phase": phase, "status": PHASE_STATUS[phase],
            **context, "repository": PUBLICATION_REPOSITORY, "controller_sha256": "c" * 64,
            "manifest_sha256": "f" * 64, "inputs": {}, "source_graph": {"core": {}, "canonical_fixture": {}},
            "resource_policy": {}, "source_tree_identities": {
                "baseline": "b" * 40, "production": "c" * 40, "instrumented": "d" * 40},
            "initial_free_bytes": INITIAL_FREE_BYTES,
        }
        phase_identity(receipt, phase, manifest, "f" * 64, context)
        for key, value in (
            ("schema", 1), ("phase", "foreign"), ("status", "INCOMPLETE"),
            ("status", "INFRASTRUCTURE_ERROR"), ("publication_commit", "0" * 40),
            ("controller_sha256", "0" * 64), ("manifest_sha256", "0" * 64),
            ("run_id", "3"), ("run_attempt", "1"), ("inputs", {"unexpected": True}),
            ("source_tree_identities", {}), ("initial_free_bytes", INITIAL_FREE_BYTES - 1),
        ):
            try:
                phase_identity(dict(receipt, **{key: value}), phase, manifest, "f" * 64, context)
            except GateRejected:
                pass
            else:
                raise AssertionError("aggregate identity accepted foreign/incomplete evidence")
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        (root / "result.json").write_text("{}")
        (root / "stage.log").write_bytes(b"raw\n")
        record = {
            "stage": "stage", "output_bytes": 4, "output_sha256": sha(b"raw\n"),
            "infrastructure_error": None, "exit_code": 0,
            "disk_free_before_bytes": LOW_WATER_BYTES, "disk_free_after_bytes": LOW_WATER_BYTES,
            "disk_free_minimum_bytes": LOW_WATER_BYTES,
        }
        phase_logs(root, {"stages": [record]})
        bad = [
            {"stages": []}, {"stages": [record, record]},
            {"stages": [dict(record, output_sha256="0" * 64)]},
            {"stages": [dict(record, output_bytes=3)]},
            {"stages": [dict(record, exit_code=1)]},
            {"stages": [dict(record, infrastructure_error="ENOSPC")]},
            {"stages": [dict(record, disk_free_after_bytes=LOW_WATER_BYTES - 1)]},
        ]
        for receipt in bad:
            try:
                phase_logs(root, receipt)
            except GateRejected:
                pass
            else:
                raise AssertionError("aggregate raw-log guard accepted invalid evidence")
        (root / "unexpected.log").write_text("foreign")
        try:
            phase_logs(root, {"stages": [record]})
        except GateRejected:
            pass
        else:
            raise AssertionError("aggregate accepted unlisted output")
    print("Resource/aggregation self-tests: errno distinctions, all-phase identity negatives and raw digest/inventory controls passed.")


def main():
    if not __debug__:
        raise InfrastructureError("optimized Python disables required self-controls")
    def terminate(signum, _frame):
        raise KeyboardInterrupt(f"received signal {signum}")
    signal.signal(signal.SIGTERM, terminate)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--work", type=Path)
    parser.add_argument("--evidence", type=Path)
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--phase", choices=tuple(PHASE_STATUS))
    parser.add_argument("--aggregate", type=Path)
    args = parser.parse_args()
    if args.self_test:
        self_test()
        composition_self_test()
        resource_aggregation_self_test()
    elif args.aggregate is not None:
        if args.manifest is None or args.evidence is None or args.phase is not None or args.work is not None:
            parser.error("aggregation requires only --manifest, --aggregate and --evidence")
        aggregate(args)
    else:
        if None in (args.manifest, args.work, args.evidence, args.phase):
            parser.error("--manifest, --work, --evidence and --phase are required")
        qualify(args)


if __name__ == "__main__":
    main()
