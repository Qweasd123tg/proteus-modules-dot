"""Synthetic artifact-verifier tests; never execute Core, Cargo, strace or fixture."""
import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

SPEC = importlib.util.spec_from_file_location("native_cache_verifier", Path(__file__).with_name("verify_native_cache.py"))
v = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(v)


def sample(api):
    return {"api": api, "elapsed_ns": 123, "allocations": {"allocation_calls": 1, "requested_bytes": 8, "deallocation_calls": 1, "released_bytes": 8}}


def fixture(stage="functional"):
    checks, processes, outputs = [], {}, {}
    for name, spec in v.specs(stage).items():
        command, count, prefix, damage = spec
        value = {"event": {"prepare": "prepared", "positive-source": "positive_source", "invalid-source": "invalid_source"}.get(command, command), "core_pin": v.PIN}
        if command == "prepare":
            value.update(records=count, native_producer="AgentAppServer::launch_resumed", no_modules=True, no_provider=True, journal_unchanged_by_producer=True, session_dir="/synthetic/dataset-" + prefix + "/session")
        elif command == "invalid-source":
            diagnostic = "failed to parse journal" if damage == "malformed" else "unsupported journal schema_version 0"
            value.update(strict_rejected=True, journal_unchanged=True, expected_diagnostic=diagnostic, stale_display_messages=count, errors={api: "context: " + diagnostic for api in ["projection", "snapshot", "history", "usage", "audit"]})
        else:
            value["messages"] = count + (command == "append")
            if command == "read": value.update(equivalent=True, samples=[sample(api) for _ in range(3) for api in sorted(v.APIS)])
            if command == "reopen": value.update(journal_unchanged=True, samples=[sample("native_app_transcript") for _ in range(3)])
            if command == "rollback": value.update(journal_and_cache_unchanged=True, early_error="history revision mismatch", late_error="duplicate message id")
            if command == "append": value.update(fresh_snapshot_matches_strict=True, view_left_stale=True, catalog_initial_messages=count, catalog_eventual_messages=count+1)
            if command == "positive-source": value.update(snapshot_projection_messages_usage_audit_passed=True, journal_unchanged=True)
        args = ["/synthetic/binary", command, "/synthetic/session", str(count)]
        if damage: args.append(damage)
        processes[name] = {"command": args, "returncode": 0, "traced": False, "new_process_group": True, "timed_out": False, "drain_timed_out": False, "cleanup_error": None}
        checks.append({"name": name, "value": value})
        outputs[name] = copy.deepcopy(value)
    hashes = {"/synthetic/binary": "a" * 64}
    return [{"status": "passed", "source_and_binary_unchanged": True, "source_and_binary_hashes_after": hashes, "checks": checks, "tracing_available_at_end": False}, {"stage": stage, "core_pin": v.PIN, "source_and_binary_hashes_before": copy.deepcopy(hashes)}, processes, outputs, {}, stage]


def change(data, name, key, value):
    next(c for c in data[0]["checks"] if c["name"] == name)["value"][key] = value
    data[3][name][key] = copy.deepcopy(value)


def add_traces(data):
    for name in v.TRACE_NAMES:
        api = "projection" if name == "positive-projection-trace" else "snapshot"
        value = {"event": "only", "core_pin": v.PIN, "api": api, "messages": 64}
        data[3][name] = copy.deepcopy(value)
        view, journal = (1, 0) if name == "positive-snapshot-trace" else ((0, 1) if api == "projection" else (1, 1))
        value["openat_observations"] = {"view_cache_open_calls": view, "canonical_journal_open_calls": journal}
        session = "/synthetic/dataset-" + ("cache-schema" if name == "schema-fallback-trace" else "positive") + "/session"
        data[4][name] = (f'123 openat(AT_FDCWD, "{session}/.read-view.json", O_RDONLY) = 3\n' if view else '') + (f'123 openat(AT_FDCWD, "{session}/journal.jsonl", O_RDONLY) = 3\n' if journal else '')
        data[2][name] = {"returncode": 0, "traced": True, "timed_out": False, "new_process_group": True, "drain_timed_out": False, "cleanup_error": None}
        data[0]["checks"].append({"name": name, "value": value})
    data[0]["tracing_available_at_end"] = True


class VerifierTests(unittest.TestCase):
    def rejects(self, data, diagnostic):
        with self.assertRaisesRegex(ValueError, diagnostic): v.validate_stage(*data)

    def test_complete_untraced_functional_is_not_cache_hit_proof(self):
        result = v.validate_stage(*fixture())
        self.assertEqual(result["required_successful_children"], 23)
        self.assertFalse(result["cache_hit_with_strict_and_invalid_cache_controls_observed"])

    def test_complete_measurements(self):
        self.assertEqual(v.validate_stage(*fixture("measurements"))["required_successful_children"], 18)

    def test_missing_required_child(self):
        data = fixture(); data[0]["checks"].pop(); self.rejects(data, "missing required check")

    def test_duplicate_child(self):
        data = fixture(); data[0]["checks"].append(data[0]["checks"][0]); self.rejects(data, "duplicate check name")

    def test_required_child_cannot_be_unavailable(self):
        data = fixture(); data[0]["checks"][0] = {"name": "positive-prepare", "status": "trace_unavailable"}; self.rejects(data, "required check unavailable")

    def test_wrong_pin(self):
        data = fixture(); change(data, "positive-read", "core_pin", "wrong"); self.rejects(data, "wrong Core pin")

    def test_stdout_mismatch(self):
        data = fixture(); data[3]["positive-read"]["messages"] = 1; self.rejects(data, "stdout/result mismatch")

    def test_stdout_integer_float_mismatch(self):
        data = fixture(); data[3]["positive-read"]["messages"] = 64.0; self.rejects(data, "stdout/result mismatch")

    def test_stdout_boolean_integer_mismatch(self):
        data = fixture(); data[3]["positive-read"]["equivalent"] = 1; self.rejects(data, "stdout/result mismatch")

    def test_canonical_display_float_rejected(self):
        data = fixture(); change(data, "canonical-schema-strict-vs-display", "stale_display_messages", 64.0); self.rejects(data, "wrong canonical diagnosis/display")

    def test_unrelated_canonical_rejection(self):
        data = fixture(); change(data, "canonical-schema-strict-vs-display", "errors", {api: "Permission denied" for api in ["projection", "snapshot", "history", "usage", "audit"]}); self.rejects(data, "unrelated canonical rejection")

    def test_source_hash_change(self):
        data = fixture(); data[0]["source_and_binary_hashes_after"] = {"/synthetic/binary": "b"*64}; self.rejects(data, "hashes changed")

    def test_traced_timing_rejected(self):
        data = fixture(); data[2]["positive-read"]["traced"] = True; self.rejects(data, "required process failed or traced")

    def test_nonzero_and_boolean_process_exit_rejected(self):
        for code in [1, False]:
            data = fixture(); data[2]["positive-read"]["returncode"] = code; self.rejects(data, "required process failed or traced")

    def test_wrong_sample_cardinality(self):
        data = fixture(); change(data, "positive-read", "samples", [sample("conversation_snapshot")]*12); self.rejects(data, "wrong sample cardinality")

    def test_non_numeric_allocation_rejected(self):
        data = fixture(); samples = copy.deepcopy(data[3]["positive-read"]["samples"]); samples[0]["allocations"]["requested_bytes"] = True; change(data, "positive-read", "samples", samples); self.rejects(data, "invalid allocation sample")

    def test_all_trace_controls_observed(self):
        data = fixture(); add_traces(data)
        self.assertTrue(v.validate_stage(*data)["cache_hit_with_strict_and_invalid_cache_controls_observed"])

    def test_trace_count_fabrication_rejected(self):
        data = fixture(); add_traces(data); data[4]["positive-snapshot-trace"] = ""; self.rejects(data, "trace count mismatch")

    def test_trace_counter_boolean_rejected(self):
        data = fixture(); add_traces(data); next(c for c in data[0]["checks"] if c["name"] == "positive-snapshot-trace")["value"]["openat_observations"]["view_cache_open_calls"] = True; self.rejects(data, "trace count mismatch")

    def test_unrelated_cache_open_rejected_after_positive_control(self):
        data = fixture(); add_traces(data); self.assertTrue(v.validate_stage(*data)["cache_hit_with_strict_and_invalid_cache_controls_observed"])
        data[4]["positive-snapshot-trace"] = data[4]["positive-snapshot-trace"].replace("/synthetic/dataset-positive/session/", "/unrelated/")
        self.rejects(data, "snapshot trace lacks successful owned-cache open")

    def test_failed_owned_cache_open_rejected_after_positive_control(self):
        data = fixture(); add_traces(data); self.assertTrue(v.validate_stage(*data)["cache_hit_with_strict_and_invalid_cache_controls_observed"])
        data[4]["positive-snapshot-trace"] = data[4]["positive-snapshot-trace"].replace("= 3", "= -1 ENOENT (No such file or directory)")
        self.rejects(data, "snapshot trace lacks successful owned-cache open")

    def test_unrelated_journal_open_rejected_after_positive_control(self):
        data = fixture(); add_traces(data); self.assertTrue(v.validate_stage(*data)["cache_hit_with_strict_and_invalid_cache_controls_observed"])
        data[4]["positive-projection-trace"] = data[4]["positive-projection-trace"].replace("/synthetic/dataset-positive/session/", "/unrelated/")
        self.rejects(data, "trace positive control lacks successful owned-journal open")

    def test_failed_owned_journal_open_rejected_after_positive_control(self):
        data = fixture(); add_traces(data); self.assertTrue(v.validate_stage(*data)["cache_hit_with_strict_and_invalid_cache_controls_observed"])
        data[4]["positive-projection-trace"] = data[4]["positive-projection-trace"].replace("= 3", "= -1 EACCES (Permission denied)")
        self.rejects(data, "trace positive control lacks successful owned-journal open")

    def test_missing_positive_journal_open_rejected(self):
        data = fixture(); add_traces(data); data[4]["positive-projection-trace"] = ""; next(c for c in data[0]["checks"] if c["name"] == "positive-projection-trace")["value"]["openat_observations"]["canonical_journal_open_calls"] = 0; self.rejects(data, "positive control missed journal")

    def test_trace_retry_after_unavailable_rejected(self):
        data = fixture(); add_traces(data); data[0]["checks"][-3] = {"name": "positive-snapshot-trace", "status": "trace_unavailable"}; data[0]["tracing_available_at_end"] = False; self.rejects(data, "tracing retried after unavailable")

    def test_duplicate_json_keys_rejected(self):
        with self.assertRaisesRegex(ValueError, "duplicate JSON key"): json.loads('{"status":"failed","status":"passed"}', object_pairs_hook=v.unique_object)

    def test_complete_filesystem_gate_and_changed_bytes(self):
        # Tiny authored synthetic receipts only; the file named binary is plain text.
        with tempfile.TemporaryDirectory(prefix="native-cache-verifier-control-") as temp:
            root = Path(temp); package = root / "package"; package.mkdir(); (package / "src").mkdir()
            binary = root / "not-executed-binary"; binary.write_text("synthetic not executable")
            entries = []
            for name in sorted(v.SOURCE_FILES):
                path = package / name; path.write_text("synthetic " + name)
                entries.append({"path": name, "bytes": path.stat().st_size, "sha256": v.digest(path)})
            receipt = package / "SOURCE-RECEIPT.json"; receipt.write_text(json.dumps({"core_pin": v.PIN, "files": entries}))
            output = root / "output"; output.mkdir()
            data = fixture()
            hashes = {str(path): v.digest(path) for path in [binary, package / "Cargo.toml", package / "Cargo.lock", package / "run_cache_probe.py", package / "src/main.rs", package / "src/allocation.rs"]}
            data[0]["source_and_binary_hashes_after"] = hashes; data[1]["source_and_binary_hashes_before"] = hashes
            data[1]["limits"] = {"child_wall_seconds": 120, "child_cpu_seconds": 60, "child_address_space_bytes": 768*1024**2, "disk_reserve_bytes": 1024**3, "max_child_file_bytes": 8*1024**2}
            data[1]["isolated_child_environment"] = {"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8", **{key: str(output / leaf) for key, leaf in [("HOME", "home"), ("XDG_CONFIG_HOME", "xdg-config"), ("XDG_CACHE_HOME", "xdg-cache"), ("XDG_DATA_HOME", "xdg-data"), ("TMPDIR", "tmp")]}}
            for name, spec in v.specs("functional").items():
                command, count, prefix, damage = spec; dataset = output / ("dataset-" + prefix); session = dataset / "session"
                if command == "prepare": change(data, name, "session_dir", str(session)); args = [command, str(dataset), str(count)]
                elif command in {"read", "rollback"}: args = [command, str(session), str(count)]
                else: args = [command, str(dataset), str(session), str(count)]
                if damage: args.append(damage)
                data[2][name]["command"] = [str(binary), *args]
                (output / (name + ".process.json")).write_text(json.dumps(data[2][name]))
                (output / (name + ".stdout.json")).write_text(json.dumps(data[3][name]))
            (output / "result.json").write_text(json.dumps(data[0])); (output / "environment.json").write_text(json.dumps(data[1]))
            self.assertEqual(v.verify(output, package, binary, "functional", v.digest(receipt))["status"], "verified")
            with self.assertRaisesRegex(ValueError, "trace observations unavailable"): v.verify(output, package, binary, "functional", v.digest(receipt), True)
            data[1]["limits"]["child_wall_seconds"] = 120.0
            (output / "environment.json").write_text(json.dumps(data[1]))
            with self.assertRaisesRegex(ValueError, "changed child resource limits"): v.verify(output, package, binary, "functional", v.digest(receipt))
            data[1]["limits"]["child_wall_seconds"] = 120
            (output / "environment.json").write_text(json.dumps(data[1]))
            binary.write_text("changed synthetic bytes")
            with self.assertRaisesRegex(ValueError, "current input bytes differ"): v.verify(output, package, binary, "functional", v.digest(receipt))


if __name__ == "__main__": unittest.main()
