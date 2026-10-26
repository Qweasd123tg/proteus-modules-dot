"""Authored synthetic/controller tests only; no Core, Cargo or live child runs."""
import copy
import importlib.util
import json
from pathlib import Path
import signal
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch

SPEC = importlib.util.spec_from_file_location("group_runner", Path(__file__).with_name("run_group_probe.py"))
r = importlib.util.module_from_spec(SPEC); SPEC.loader.exec_module(r)


def workload(count=256, batch=8):
    return {"event": "append_groups", "core_pin": r.PIN, "messages": count, "batch_size": batch, "transaction_boundaries_differ": True,
        "validation": {"history_matches_exact_corpus": True, "consecutive_sequences": True, "all_payloads_inline": True,
            "records": count//batch, "revision": count//batch, "default_blob_threshold_bytes": 256*1024,
            "payload_bytes": [1024]*(count//batch), "journal_bytes": 65536},
        "append_samples": [{"append_index": index+1, "messages_in_group": batch, "cold_writer_initialization": index==0,
            "elapsed_ns": 10, "allocations": {"allocation_calls": 1, "requested_bytes": 8, "deallocation_calls": 1, "released_bytes": 8}}
            for index in range(count//batch)]}


def rollback(kind="active"):
    target="11111111-1111-4111-8111-000000000000" if kind=="active" else "11111111-1111-4111-8111-000000000001"
    expected="active history contains duplicate message id "+target
    return {"event": "rollback", "core_pin": r.PIN, "kind": kind, "expected_diagnostic": expected, "error": expected, "error_leaf": expected,
        "rejected_journal_and_projection_unchanged": True, "valid_prefix_reused_same_ids": True, "final_messages": 3, "final_records": 2,
        "final_revision": 2, "final_sequences": [1,2]}


class SemanticControls(unittest.TestCase):
    def test_all_authored_workload_shapes(self):
        for count, batch in [(64,8), *[(256,n) for n in [1,8,64,256]]]:
            summary = r.validate_workload(workload(count,batch),count,batch)
            self.assertEqual(summary["append_calls"],count//batch)
            self.assertEqual(summary["requested_bytes_sum"],8*(count//batch))

    def test_wrong_pin(self):
        value=workload(); value["core_pin"]="wrong"
        with self.assertRaisesRegex(ValueError,"wrong workload event/pin"): r.validate_workload(value,256,8)

    def test_float_dimension_rejected(self):
        value=workload(); value["batch_size"]=8.0
        with self.assertRaisesRegex(ValueError,"wrong workload dimensions"): r.validate_workload(value,256,8)

    def test_missing_sample(self):
        value=workload(); value["append_samples"].pop()
        with self.assertRaisesRegex(ValueError,"wrong append sample count"): r.validate_workload(value,256,8)

    def test_boolean_allocation_rejected(self):
        value=workload(); value["append_samples"][0]["allocations"]["requested_bytes"]=True
        with self.assertRaisesRegex(ValueError,"invalid requested-allocation counters"): r.validate_workload(value,256,8)

    def test_wrong_cold_label(self):
        value=workload(); value["append_samples"][-1]["cold_writer_initialization"]=True
        with self.assertRaisesRegex(ValueError,"incorrect cold-writer label"): r.validate_workload(value,256,8)

    def test_blob_threshold_confound(self):
        value=workload(); value["validation"]["payload_bytes"][0]=256*1024
        with self.assertRaisesRegex(ValueError,"invalid payload sizes or blob confound"): r.validate_workload(value,256,8)

    def test_wrong_revision_count(self):
        value=workload(); value["validation"]["revision"]=256
        with self.assertRaisesRegex(ValueError,"wrong revision or record count"): r.validate_workload(value,256,8)

    def test_both_rollback_shapes(self):
        for kind in ["active","incoming"]: r.validate_rollback(rollback(kind),kind)

    def test_unrelated_rollback_error(self):
        value=rollback(); value["error"]="permission denied"
        with self.assertRaisesRegex(ValueError,"unrelated rollback rejection"): r.validate_rollback(value,"active")

    def test_wrong_duplicate_target_rejected(self):
        value=rollback("active"); r.validate_rollback(value,"active")
        wrong=rollback("incoming")
        for key in ["expected_diagnostic","error","error_leaf"]: value[key]=wrong[key]
        with self.assertRaisesRegex(ValueError,"unrelated rollback rejection"): r.validate_rollback(value,"active")

    def test_rejected_group_cannot_consume_revision(self):
        value=rollback(); value["final_revision"]=3
        with self.assertRaisesRegex(ValueError,"rollback consumed state: final_revision"): r.validate_rollback(value,"active")

    def test_id_reuse_control_required(self):
        value=rollback(); value["valid_prefix_reused_same_ids"]=False
        with self.assertRaisesRegex(ValueError,"missing rollback/ID reuse control"): r.validate_rollback(value,"active")

    def test_recursive_equality_distinguishes_number_types(self):
        self.assertFalse(r.same({"x":[1]}, {"x":[True]})); self.assertFalse(r.same({"x":[1]}, {"x":[1.0]}))


class ControllerControls(unittest.TestCase):
    def setUp(self):
        self.temporary=tempfile.TemporaryDirectory(prefix="append-group-controller-")
        self.output=Path(self.temporary.name)
        self.run=r.Run(Path("/nonexecuted-authored-binary"), self.output)

    def tearDown(self): self.temporary.cleanup()

    def test_isolated_child_environment(self):
        self.assertEqual(set(self.run.env),{"PATH","LANG","HOME","XDG_CONFIG_HOME","XDG_CACHE_HOME","XDG_DATA_HOME","TMPDIR"})
        for key in ["HOME","XDG_CONFIG_HOME","XDG_CACHE_HOME","XDG_DATA_HOME","TMPDIR"]:
            self.assertTrue(Path(self.run.env[key]).is_relative_to(self.output))

    def test_timeout_owned_group_and_receipt(self):
        process=Mock(pid=424251,returncode=-9)
        process.communicate.side_effect=[subprocess.TimeoutExpired(["mock"],60),("partial","error")]
        with patch.object(r.subprocess,"Popen",return_value=process) as popen, patch.object(r.os,"killpg") as kill:
            with self.assertRaisesRegex(RuntimeError,"owned group killed"): self.run.execute("timeout",["run"])
            self.assertTrue(popen.call_args.kwargs["start_new_session"]); kill.assert_called_once_with(424251,signal.SIGKILL)
        self.assertTrue(json.loads((self.output/"timeout.process.json").read_text())["timed_out"])

    def test_second_drain_timeout_bounded_and_retained(self):
        process=Mock(pid=424252,returncode=-9)
        process.communicate.side_effect=[subprocess.TimeoutExpired(["mock"],60),subprocess.TimeoutExpired(["mock"],10,output=b"partial")]
        process.wait.return_value=-9
        with patch.object(r.subprocess,"Popen",return_value=process), patch.object(r.os,"killpg"):
            with self.assertRaisesRegex(RuntimeError,"owned group killed"): self.run.execute("drain",["run"])
        process.wait.assert_called_once_with(timeout=5)
        self.assertEqual((self.output/"drain.stdout.json").read_text(),"partial")
        self.assertTrue(json.loads((self.output/"drain.process.json").read_text())["drain_timed_out"])

    def test_spawn_failure_retains_target(self):
        with patch.object(r.subprocess,"Popen",side_effect=FileNotFoundError("mock absent")):
            with self.assertRaises(FileNotFoundError): self.run.execute("missing",["run"])
        self.assertEqual(json.loads((self.output/"missing.process.json").read_text())["status"],"spawn_failed")

    def test_child_failure_not_passed(self):
        process=Mock(returncode=1); process.communicate.return_value=("","Error: invalid history")
        with patch.object(r.subprocess,"Popen",return_value=process):
            with self.assertRaisesRegex(ValueError,"failed rc=1"): self.run.execute("failed",["run"])
        self.assertEqual(self.run.checks,[])

    def test_valid_synthetic_child_is_recorded_not_executed(self):
        process=Mock(returncode=0); process.communicate.return_value=(json.dumps({"core_pin":r.PIN,"event":"synthetic"}),"")
        with patch.object(r.subprocess,"Popen",return_value=process): self.run.execute("synthetic",["run"])
        self.assertEqual(self.run.checks[0]["value"]["event"],"synthetic")


if __name__ == "__main__": unittest.main()
