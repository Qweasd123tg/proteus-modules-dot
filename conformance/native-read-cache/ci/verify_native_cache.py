#!/usr/bin/env python3
"""Verify our native-cache CI artifact structure; not independent Core execution."""
import argparse
import collections
import hashlib
import json
from pathlib import Path
import re

PIN = "1fc3ef223d10322815dd9290a50d045bc95402bb"
RECEIPT = "49bd04f80d9ce9edc5b4a4798cc1f205d02d4992eb1288a90ca77f40f823a78b"
SOURCE_FILES = {"Cargo.toml", "Cargo.lock", "README.md", "run_cache_probe.py", "test_runner_control.py", "src/main.rs", "src/allocation.rs"}
APIS = {"conversation_snapshot", "load_projection", "load_messages", "usage_snapshot_cold_store"}
TRACE_NAMES = ["positive-snapshot-trace", "positive-projection-trace", "schema-fallback-trace"]


def require(condition, message):
    if not condition:
        raise ValueError(message)


def integer(value):
    return type(value) is int and value >= 0


def same(left, right):
    """JSON equality without Python's bool/int/float coercions."""
    if type(left) is not type(right):
        return False
    if isinstance(left, dict):
        return left.keys() == right.keys() and all(same(left[key], right[key]) for key in left)
    if isinstance(left, list):
        return len(left) == len(right) and all(same(a, b) for a, b in zip(left, right))
    return left == right


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def text(path):
    require(path.stat().st_size <= 8 * 1024**2, f"oversize artifact: {path.name}")
    return path.read_text()


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, f"duplicate JSON key: {key}")
        result[key] = value
    return result


def document(path):
    def invalid_constant(value):
        raise ValueError(f"nonfinite JSON constant: {value}")
    return json.loads(text(path), object_pairs_hook=unique_object, parse_constant=invalid_constant)


def successful_owned_opens(lines, session):
    """Count completed successful exact-path opens, not suffix/ENOENT attempts.

    Our generated paths are ASCII. Unfinished or unparseable calls never count as
    successes; if they hide a required positive control, verification fails closed.
    This is diagnostic parsing, not a general strace implementation.
    """
    targets = {str(Path(session) / ".read-view.json"): "view", str(Path(session) / "journal.jsonl"): "journal"}
    counts = {"view": 0, "journal": 0}
    pattern = re.compile(r'\bopenat\([^,]*, ("(?:\\.|[^"\\])*"),.*\)\s+=\s+([0-9]+)(?:\s|$)')
    for line in lines:
        match = pattern.search(line)
        if match is None:
            continue
        try:
            path = json.loads(match.group(1))
        except json.JSONDecodeError:
            continue
        if path in targets:
            counts[targets[path]] += 1
    return counts


def specs(stage):
    """name -> (subcommand, count, prepare-prefix, optional canonical damage)."""
    if stage == "measurements":
        result = {}
        for count in [64, 256]:
            for repeat in range(1, 4):
                prefix = f"measure-{count}-r{repeat}"
                result[prefix + "-prepare"] = ("prepare", count, prefix, None)
                result[prefix] = ("read", count, prefix, None)
                result[prefix + "-native-reopen"] = ("reopen", count, prefix, None)
        return result
    result = {
        "positive-prepare": ("prepare", 64, "positive", None),
        "positive-read": ("read", 64, "positive", None),
        "positive-native-reopen": ("reopen", 64, "positive", None),
        "rollback-prepare": ("prepare", 64, "rollback", None),
        "rollback-control": ("rollback", 64, "rollback", None),
        "rollback-fresh-reader": ("read", 64, "rollback", None),
        "append-prepare": ("prepare", 64, "append", None),
        "append-invalidation": ("append", 64, "append", None),
        "append-fresh-reader": ("read", 65, "append", None),
    }
    for damage in ["malformed", "checksum", "schema", "journal-schema"]:
        prefix = "cache-" + damage
        result[prefix + "-prepare"] = ("prepare", 64, prefix, None)
        result[prefix + "-fallback"] = ("read", 64, prefix, None)
    for damage in ["malformed", "schema"]:
        prefix = "canonical-" + damage
        result[prefix + "-prepare"] = ("prepare", 64, prefix, None)
        result[prefix + "-before-damage-positive"] = ("positive-source", 64, prefix, None)
        result[prefix + "-strict-vs-display"] = ("invalid-source", 64, prefix, damage)
    return result


def validate_value(value, spec):
    command, count, _, damage = spec
    require(value.get("core_pin") == PIN, "wrong Core pin")
    expected_event = {"prepare": "prepared", "positive-source": "positive_source", "invalid-source": "invalid_source"}.get(command, command)
    require(value.get("event") == expected_event, "wrong event")
    if command == "prepare":
        require(integer(value.get("records")), "invalid record count")
        require(value.get("records") == count and value.get("native_producer") == "AgentAppServer::launch_resumed", "wrong native producer/count")
        for key in ["no_modules", "no_provider", "journal_unchanged_by_producer"]:
            require(value.get(key) is True, "missing preparation control: " + key)
    elif command == "invalid-source":
        diagnostic = "failed to parse journal" if damage == "malformed" else "unsupported journal schema_version 0"
        require(value.get("strict_rejected") is True and value.get("journal_unchanged") is True, "missing canonical rejection control")
        require(value.get("expected_diagnostic") == diagnostic and same(value.get("stale_display_messages"), count), "wrong canonical diagnosis/display")
        errors = value.get("errors", {})
        require(set(errors) == {"projection", "snapshot", "history", "usage", "audit"}, "incomplete strict API errors")
        require(all(isinstance(error, str) and diagnostic in error for error in errors.values()), "unrelated canonical rejection")
    else:
        require(integer(value.get("messages")), "invalid message count")
        require(value.get("messages") == count + (command == "append"), "wrong message count")
        if command == "read":
            require(value.get("equivalent") is True, "missing semantic equivalence")
        elif command == "reopen":
            require(value.get("journal_unchanged") is True, "native reopen changed source")
        elif command == "rollback":
            require(value.get("journal_and_cache_unchanged") is True, "rollback changed source/cache")
            require("history revision mismatch" in value.get("early_error", "") and "duplicate message id" in value.get("late_error", ""), "unrelated rollback rejection")
        elif command == "append":
            require(value.get("fresh_snapshot_matches_strict") is True and value.get("view_left_stale") is True, "missing append invalidation control")
            require(same(value.get("catalog_initial_messages"), count) and same(value.get("catalog_eventual_messages"), count + 1), "missing catalog refresh control")
        elif command == "positive-source":
            require(value.get("snapshot_projection_messages_usage_audit_passed") is True and value.get("journal_unchanged") is True, "incomplete same-source positive control")
    if command in {"read", "reopen"}:
        samples = value.get("samples", [])
        expected = APIS if command == "read" else {"native_app_transcript"}
        require(collections.Counter(sample.get("api") for sample in samples) == {api: 3 for api in expected}, "wrong sample cardinality")
        for sample in samples:
            require(integer(sample.get("elapsed_ns")), "invalid timing sample")
            allocations = sample.get("allocations", {})
            require(set(allocations) == {"allocation_calls", "requested_bytes", "deallocation_calls", "released_bytes"} and all(integer(x) for x in allocations.values()), "invalid allocation sample")


def validate_stage(result, environment, processes, outputs, traces, stage):
    """Pure structural/semantic checks; caller separately verifies current input bytes."""
    require(result.get("status") == "passed", "stage did not pass")
    require(environment.get("stage") == stage and environment.get("core_pin") == PIN, "wrong stage/pin")
    require(result.get("source_and_binary_unchanged") is True, "missing source stability control")
    before = environment.get("source_and_binary_hashes_before")
    require(isinstance(before, dict) and before and same(before, result.get("source_and_binary_hashes_after")), "source/binary hashes changed")
    require(type(result.get("tracing_available_at_end")) is bool, "missing tracing availability status")
    checks = result.get("checks", [])
    names = [check.get("name") for check in checks]
    require(len(names) == len(set(names)), "duplicate check name")
    by_name = {check["name"]: check for check in checks}
    required = specs(stage)
    require(set(required) <= set(names), "missing required check")
    extras = set(names) - set(required)
    require(extras <= (set(TRACE_NAMES) if stage == "functional" else set()), "unexpected extra check")
    for name, spec in required.items():
        check = by_name[name]
        require("value" in check and "status" not in check, "required check unavailable")
        require(same(outputs.get(name), check["value"]), "stdout/result mismatch")
        validate_value(check["value"], spec)
        process = processes.get(name, {})
        require(type(process.get("returncode")) is int and process.get("returncode") == 0 and process.get("traced") is False and process.get("new_process_group") is True, "required process failed or traced")
        require(process.get("timed_out") is False and process.get("drain_timed_out") is False and process.get("cleanup_error") is None, "required process timeout/cleanup failure")
        command = process.get("command", [])
        require(len(command) >= 4 and command[1] == spec[0], "wrong child subcommand")
        require(command[-2:] == [str(spec[1]), spec[3]] if spec[3] else command[-1] == str(spec[1]), "wrong child count/damage")
    observed = []
    owned_open_counts = {}
    unavailable_seen = False
    for name in TRACE_NAMES:
        if name not in by_name:
            continue
        check = by_name[name]
        require(not unavailable_seen, "tracing retried after unavailable")
        if check.get("status") == "trace_unavailable":
            unavailable_seen = True
            require(result.get("tracing_available_at_end") is False, "unavailable trace marked available")
            continue
        value = check.get("value", {})
        process = processes.get(name, {})
        require(type(process.get("returncode")) is int and process.get("returncode") == 0 and process.get("traced") is True and process.get("timed_out") is False, "trace process failed")
        require(process.get("new_process_group") is True and process.get("drain_timed_out") is False and process.get("cleanup_error") is None, "trace process cleanup/group failure")
        raw = dict(value)
        observations = raw.pop("openat_observations", None)
        require(same(outputs.get(name), raw), "trace stdout/result mismatch")
        expected_api = "projection" if name == "positive-projection-trace" else "snapshot"
        require(same(raw, {"event": "only", "core_pin": PIN, "api": expected_api, "messages": 64}), "wrong trace child result")
        lines = traces.get(name, "").splitlines()
        counted = {"view_cache_open_calls": sum('/.read-view.json"' in line for line in lines), "canonical_journal_open_calls": sum('/journal.jsonl"' in line for line in lines)}
        require(same(observations, counted), "trace count mismatch")
        prefix = "cache-schema" if name == "schema-fallback-trace" else "positive"
        successful = successful_owned_opens(lines, outputs[prefix + "-prepare"]["session_dir"])
        owned_open_counts[name] = successful
        if name == "positive-snapshot-trace":
            require(counted["view_cache_open_calls"] > 0 and counted["canonical_journal_open_calls"] == 0, "snapshot trace missed cache or opened journal")
            require(successful["view"] > 0 and successful["journal"] == 0, "snapshot trace lacks successful owned-cache open")
        else:
            require(counted["canonical_journal_open_calls"] > 0, "trace positive control missed journal")
            require(successful["journal"] > 0, "trace positive control lacks successful owned-journal open")
            if name == "schema-fallback-trace":
                require(counted["view_cache_open_calls"] > 0, "schema fallback did not inspect cache")
                require(successful["view"] > 0, "schema fallback lacks successful owned-cache open")
        observed.append(name)
    if set(observed) == set(TRACE_NAMES):
        require(result["tracing_available_at_end"] is True, "completed trace controls marked unavailable")
    return {"required_successful_children": len(required), "observed_trace_children": observed,
            "successful_owned_open_counts": owned_open_counts,
            "cache_hit_with_strict_and_invalid_cache_controls_observed": set(observed) == set(TRACE_NAMES),
            "trace_unavailable_during_execution": unavailable_seen}


def verify(directory, package, binary, stage, expected_receipt, require_traces=False):
    require(digest(package / "SOURCE-RECEIPT.json") == expected_receipt, "source receipt differs from reviewed hash")
    receipt = document(package / "SOURCE-RECEIPT.json")
    require(receipt.get("core_pin") == PIN and len(receipt["files"]) == len(SOURCE_FILES) and {item["path"] for item in receipt["files"]} == SOURCE_FILES, "wrong source inventory")
    for item in receipt["files"]:
        path = package / item["path"]
        require(same(path.stat().st_size, item["bytes"]) and digest(path) == item["sha256"], "reviewed source changed: " + item["path"])
    result, environment = document(directory / "result.json"), document(directory / "environment.json")
    hashes = environment.get("source_and_binary_hashes_before", {})
    expected_files = [binary, package / "Cargo.toml", package / "Cargo.lock", package / "run_cache_probe.py", package / "src/main.rs", package / "src/allocation.rs"]
    require(set(hashes) == {str(path) for path in expected_files}, "unexpected source/binary hash keys")
    require(all(digest(path) == hashes[str(path)] for path in expected_files), "current input bytes differ from run")
    names = [check["name"] for check in result.get("checks", [])]
    processes, outputs, traces = {}, {}, {}
    for name in names:
        require(re.fullmatch(r"[a-z0-9-]+", name) is not None, "invalid artifact check name")
        processes[name] = document(directory / (name + ".process.json"))
        if "value" in next(check for check in result["checks"] if check["name"] == name):
            outputs[name] = document(directory / (name + ".stdout.json"))
            if name in TRACE_NAMES:
                traces[name] = text(directory / (name + ".openat.txt"))
    summary = validate_stage(result, environment, processes, outputs, traces, stage)
    if require_traces:
        require(stage == "functional" and summary["cache_hit_with_strict_and_invalid_cache_controls_observed"], "required trace observations unavailable")
        require(environment.get("traces_requested") is True, "trace controls were not requested")
    if stage == "measurements":
        require(environment.get("traces_requested") is False, "measurement stage requested tracing")
    expected_limits = {"child_wall_seconds": 120, "child_cpu_seconds": 60, "child_address_space_bytes": 768*1024**2, "disk_reserve_bytes": 1024**3, "max_child_file_bytes": 8*1024**2}
    require(same(environment.get("limits"), expected_limits), "changed child resource limits")
    expected_env = {"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8"}
    for key, leaf in [("HOME", "home"), ("XDG_CONFIG_HOME", "xdg-config"), ("XDG_CACHE_HOME", "xdg-cache"), ("XDG_DATA_HOME", "xdg-data"), ("TMPDIR", "tmp")]:
        expected_env[key] = str(directory / leaf)
    require(same(environment.get("isolated_child_environment"), expected_env), "child environment not isolated as specified")
    for name, spec in specs(stage).items():
        prefix = spec[2]
        root = directory / ("dataset-" + prefix)
        session = Path(outputs[prefix + "-prepare"]["session_dir"])
        require(session.is_absolute() and session.is_relative_to(root), "session escapes owned dataset")
        command = spec[0]
        if command == "prepare":
            args = [command, str(root), str(spec[1])]
        elif command in {"read", "rollback"}:
            args = [command, str(session), str(spec[1])]
        else:
            args = [command, str(root), str(session), str(spec[1])]
            if spec[3]: args.append(spec[3])
        require(same(processes[name]["command"], [str(binary), *args]), "child command does not match owned fixture")
    for name in summary["observed_trace_children"]:
        prefix = "cache-schema" if name == "schema-fallback-trace" else "positive"
        session = outputs[prefix + "-prepare"]["session_dir"]
        api = "projection" if name == "positive-projection-trace" else "snapshot"
        command = ["/usr/bin/strace", "-f", "-qq", "-e", "trace=openat", "-s", "4096", "-o", str(directory / (name + ".openat.txt")), str(binary), "only", session, api, "64"]
        require(same(processes[name]["command"], command), "unexpected tracer command or lifetime scope")
    if summary["observed_trace_children"]:
        tracer = environment.get("tracer", {})
        require(tracer.get("version_returncode") == 0 and isinstance(tracer.get("version"), str) and tracer["version"], "missing tracer version")
        require(tracer.get("binary_sha256") == digest(Path("/usr/bin/strace")), "tracer bytes changed")
    return {"status": "verified", "stage": stage, "core_pin": PIN, "reviewed_receipt_sha256": expected_receipt,
            **summary, "limits": "Receipt consistency, not independent execution or proof against forged artifacts; no RSS/p95/causal speedup claim."}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--directory", required=True, type=Path)
    parser.add_argument("--package", required=True, type=Path)
    parser.add_argument("--binary", required=True, type=Path)
    parser.add_argument("--stage", required=True, choices=["functional", "measurements"])
    parser.add_argument("--expected-receipt", default=RECEIPT)
    parser.add_argument("--require-traces", action="store_true", help="accept functional stage only if all three trace controls were observed")
    args = parser.parse_args()
    print(json.dumps(verify(args.directory.resolve(strict=True), args.package.resolve(strict=True), args.binary.resolve(strict=True), args.stage, args.expected_receipt, args.require_traces), indent=2))


if __name__ == "__main__":
    main()
