#!/usr/bin/env python3
"""Bounded authored actual-Core append-group coordinator; never builds or calls a model."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import resource
import signal
import subprocess
import time

PIN = "1fc3ef223d10322815dd9290a50d045bc95402bb"
RESERVE = 1024**3
MAX_FILE = 8*1024**2


def require(condition, message):
    if not condition: raise ValueError(message)


def same(a, b):
    if type(a) is not type(b): return False
    if isinstance(a, dict): return a.keys() == b.keys() and all(same(a[key], b[key]) for key in a)
    if isinstance(a, list): return len(a) == len(b) and all(same(x, y) for x, y in zip(a, b))
    return a == b


def unsigned(value):
    return type(value) is int and value >= 0


def digest(path):
    with path.open("rb") as stream: return hashlib.file_digest(stream, "sha256").hexdigest()


def write(path, value):
    path.write_text(json.dumps(value, indent=2) + "\n")


def limits():
    resource.setrlimit(resource.RLIMIT_AS, (512*1024**2,)*2)
    resource.setrlimit(resource.RLIMIT_CPU, (30,)*2)
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    resource.setrlimit(resource.RLIMIT_FSIZE, (MAX_FILE,)*2)


def input_hashes(binary):
    package = Path(__file__).resolve().parent
    return {str(path): digest(path) for path in [binary, package / "Cargo.toml", package / "Cargo.lock", Path(__file__).resolve(), *sorted((package / "src").glob("*.rs"))]}


def validate_projection(value, count, batch):
    require(value.get("history_matches_exact_corpus") is True and value.get("consecutive_sequences") is True and value.get("all_payloads_inline") is True, "missing exact-history/sequence/inline control")
    require(same(value.get("records"), count//batch) and same(value.get("revision"), count//batch), "wrong revision or record count")
    require(same(value.get("default_blob_threshold_bytes"), 256*1024), "wrong pinned blob threshold")
    sizes = value.get("payload_bytes", [])
    require(len(sizes) == count//batch and all(unsigned(size) and 0 < size < 256*1024 for size in sizes), "invalid payload sizes or blob confound")
    require(unsigned(value.get("journal_bytes")) and 0 < value["journal_bytes"] <= MAX_FILE, "invalid journal size")


def validate_workload(value, count, batch):
    require(value.get("event") == "append_groups" and value.get("core_pin") == PIN, "wrong workload event/pin")
    require(same(value.get("messages"), count) and same(value.get("batch_size"), batch), "wrong workload dimensions")
    require(value.get("transaction_boundaries_differ") is True, "missing transaction-boundary qualification")
    validate_projection(value.get("validation", {}), count, batch)
    samples = value.get("append_samples", [])
    require(len(samples) == count//batch, "wrong append sample count")
    for index, sample in enumerate(samples):
        require(same(sample.get("append_index"), index+1) and same(sample.get("messages_in_group"), batch), "wrong append sample index/group")
        require(sample.get("cold_writer_initialization") is (index == 0), "incorrect cold-writer label")
        require(unsigned(sample.get("elapsed_ns")), "invalid elapsed time")
        counts = sample.get("allocations", {})
        require(set(counts) == {"allocation_calls", "requested_bytes", "deallocation_calls", "released_bytes"} and all(unsigned(n) for n in counts.values()), "invalid requested-allocation counters")
    return {"append_calls": len(samples), "whole_append_elapsed_ns_sum": sum(s["elapsed_ns"] for s in samples),
            "requested_bytes_sum": sum(s["allocations"]["requested_bytes"] for s in samples),
            "first_call_requested_bytes": samples[0]["allocations"]["requested_bytes"],
            "includes_cold_writer_initialization": True}


def validate_rollback(value, kind):
    require(value.get("event") == "rollback" and value.get("core_pin") == PIN and value.get("kind") == kind, "wrong rollback event/pin/kind")
    target = "11111111-1111-4111-8111-000000000000" if kind == "active" else "11111111-1111-4111-8111-000000000001"
    expected = "active history contains duplicate message id " + target
    require(value.get("expected_diagnostic") == expected and value.get("error_leaf") == expected and value.get("error", "").endswith(expected), "unrelated rollback rejection")
    require(value.get("rejected_journal_and_projection_unchanged") is True and value.get("valid_prefix_reused_same_ids") is True, "missing rollback/ID reuse control")
    for key, expected in [("final_messages", 3), ("final_records", 2), ("final_revision", 2), ("final_sequences", [1,2])]:
        require(same(value.get(key), expected), "rollback consumed state: " + key)


class Run:
    def __init__(self, binary, output):
        self.binary, self.output, self.checks = binary, output, []
        self.env = {"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8"}
        for key, leaf in [("HOME", "home"), ("XDG_CONFIG_HOME", "xdg-config"), ("XDG_CACHE_HOME", "xdg-cache"), ("XDG_DATA_HOME", "xdg-data"), ("TMPDIR", "tmp")]:
            path = output / leaf; path.mkdir(); self.env[key] = str(path)

    def execute(self, name, args):
        stat = os.statvfs(self.output)
        require(stat.f_bavail*stat.f_frsize >= RESERVE, "disk reserve below 1 GiB; no cleanup/retry")
        command = [str(self.binary), *map(str, args)]
        started = time.monotonic()
        try:
            process = subprocess.Popen(command, cwd=self.output, env=self.env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, start_new_session=True, preexec_fn=limits)
        except (FileNotFoundError, PermissionError) as error:
            write(self.output / f"{name}.process.json", {"command": command, "status": "spawn_failed", "error": repr(error)})
            raise
        timed_out = False; drain_timed_out = False; cleanup_error = None
        try:
            stdout, stderr = process.communicate(timeout=60)
        except subprocess.TimeoutExpired:
            timed_out = True
            try: os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError: pass
            try: stdout, stderr = process.communicate(timeout=10)
            except subprocess.TimeoutExpired as error:
                drain_timed_out = True; stdout, stderr = error.output or b"", error.stderr or b""
                if process.stdout: process.stdout.close()
                if process.stderr: process.stderr.close()
                try: process.wait(timeout=5)
                except subprocess.TimeoutExpired as error: cleanup_error = repr(error)
        if isinstance(stdout, bytes): stdout = stdout.decode(errors="replace")
        if isinstance(stderr, bytes): stderr = stderr.decode(errors="replace")
        # Retained-output cap, not a hard pipe-capture memory bound. This fixed
        # authored binary has <=256 small samples and never prints corpus bodies.
        oversized = len(stdout.encode()) > MAX_FILE or len(stderr.encode()) > MAX_FILE
        (self.output / f"{name}.stdout.json").write_bytes(stdout.encode()[:MAX_FILE])
        (self.output / f"{name}.stderr.txt").write_bytes(stderr.encode()[:MAX_FILE])
        write(self.output / f"{name}.process.json", {"command": command, "returncode": process.returncode, "wall_seconds": time.monotonic()-started,
              "new_process_group": True, "timed_out": timed_out, "drain_timed_out": drain_timed_out, "cleanup_error": cleanup_error, "oversized_output": oversized})
        if timed_out: raise RuntimeError(name + " exceeded wall bound; owned group killed; partial receipts retained")
        require(process.returncode == 0 and not oversized, f"{name} failed rc={process.returncode} or output bound")
        value = json.loads(stdout)
        require(value.get("core_pin") == PIN, "wrong child Core pin")
        self.checks.append({"name": name, "value": value})
        return value

    def workload(self, name, corpus, count, batch):
        root = self.output / ("dataset-" + name)
        value = self.execute(name, ["run", root, corpus, count, batch])
        summary = validate_workload(value, count, batch)
        session = Path(value["session_dir"])
        require(session.is_absolute() and session.is_relative_to(root), "session escaped owned root")
        history = Path(value["final_history_file"])
        require(history == root / "final-history.json" and history.stat().st_size <= 2*1024**2, "unexpected history evidence path/size")
        require(same(json.loads(history.read_bytes()), json.loads(corpus.read_bytes())[:count]), "returned history differs from shared exact corpus")
        if count == 256: require(digest(history) == digest(corpus), "full final-history bytes differ from corpus")
        journal_before = digest(session / "journal.jsonl")
        reopened = self.execute(name + "-reopen", ["reopen", session, corpus, count, batch])
        require(reopened.get("event") == "reopen" and reopened.get("journal_unchanged") is True, "missing fresh-reopen control")
        require(same(reopened.get("messages"), count) and same(reopened.get("batch_size"), batch), "wrong reopen dimensions")
        validate_projection(reopened.get("validation", {}), count, batch)
        require(same(reopened["validation"], value["validation"]), "fresh reopen projection differs")
        require(digest(session / "journal.jsonl") == journal_before, "fresh reopen changed journal bytes")
        return {"name": name, "messages": count, "batch_size": batch, **summary,
                "final_history_sha256": digest(history), "journal_sha256": journal_before}

    def run(self):
        corpus = self.output / "corpus.json"
        generated = self.execute("generate", ["generate", corpus])
        require(generated.get("event") == "corpus" and generated.get("deterministic_ids_and_values") is True and same(generated.get("messages"), 256), "invalid corpus generator result")
        require(corpus.stat().st_size <= 2*1024**2 and same(generated.get("corpus_bytes"), corpus.stat().st_size), "invalid corpus size")
        corpus_hash = digest(corpus)
        pilot = self.workload("pilot-64-b8", corpus, 64, 8)
        for kind in ["active", "incoming"]:
            value = self.execute("rollback-" + kind, ["rollback", self.output / ("dataset-rollback-" + kind), corpus, kind])
            validate_rollback(value, kind)
        workloads = []
        for batch in [1, 8, 64, 256]:
            for repeat in range(1, 4):
                workloads.append(self.workload(f"batch-{batch}-r{repeat}", corpus, 256, batch))
        require(digest(corpus) == corpus_hash, "shared corpus changed")
        require(len(self.checks) == 29, "wrong total child count")
        return {"pilot": pilot, "workloads": workloads, "corpus_sha256": corpus_hash, "corpus_unchanged": True}


def main():
    parser = argparse.ArgumentParser(); parser.add_argument("--binary", required=True, type=Path); parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(); binary = args.binary.resolve(strict=True)
    args.output.mkdir(parents=False, exist_ok=False); output = args.output.resolve()
    run = Run(binary, output); before = input_hashes(binary)
    write(output / "environment.json", {"core_pin": PIN, "platform": platform.platform(), "started_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "source_and_binary_hashes_before": before, "isolated_child_environment": run.env,
        "limits": {"child_wall_seconds": 60, "child_cpu_seconds": 30, "child_address_space_bytes": 512*1024**2, "max_child_file_bytes": MAX_FILE, "disk_reserve_bytes": RESERVE},
        "scope": "existing public append groups, no modules/models/tools; different transaction visibility; no general Core speedup"})
    try:
        observations = run.run(); after = input_hashes(binary)
        require(before == after, "source/binary changed during run")
        write(output / "result.json", {"status": "passed", "core_pin": PIN, "checks": run.checks, **observations,
            "source_and_binary_unchanged": True, "source_and_binary_hashes_after": after,
            "not_claimed": ["Core bug", "general Core speedup", "same transaction/crash visibility", "RSS", "p95", "isolated fsync timing", "authority/effect boundary batching"]})
    except BaseException as error:
        write(output / "result.json", {"status": "failed", "error": repr(error), "completed_checks": run.checks}); raise
    print(output / "result.json")


if __name__ == "__main__": main()
