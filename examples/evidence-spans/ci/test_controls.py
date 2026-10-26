#!/usr/bin/env python3
"""Explicitly SYNTHETIC validator controls; these are not Rust/host execution evidence."""
from copy import deepcopy
from pathlib import Path
import runpy
import tempfile
import unittest

WORKSPACE = Path(__file__).resolve().parents[1]
V = runpy.run_path(str(WORKSPACE / "ci/verify_artifacts.py"))
KEY = V["KEY"]
CALL_ID = V["CALL_ID"]

class Controls(unittest.TestCase):
    def setUp(self):
        receipt = V["expected_receipt"](WORKSPACE)
        receipt["reader_call_id"] = "synthetic-reader-control"
        self.positive = {"host_kind": "synthetic_authored_fixture",
                         "scope": "exact_quote_bytes_not_semantic_claim_truth",
                         "result": {"call_id": CALL_ID, "ok": True, "output": V["POSITIVE_OUTPUT"],
                                    "content": [], "error": None, "metadata": {KEY: receipt}}}
        self.negative = {"host_kind": "synthetic_authored_fixture",
                         "scope": "exact_quote_bytes_not_semantic_claim_truth",
                         "result": {"call_id": CALL_ID, "ok": False, "output": "", "content": [],
                                    "error": "claim quote does not exactly match span", "metadata": None}}
        self.names = V["load"](WORKSPACE / "ci/expected-tests.json")
        self.log = "".join("test " + name + " ... ok\n" for name in self.names)
        self.log += "".join(f"test result: ok. {n} passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 0.00s\n"
                            for n in [5, 32, 2])
        V["verify_outputs"](WORKSPACE, self.positive, self.negative)
        V["verify_tests"](self.log, self.names)

    def reject_receipt(self, field, value):
        p = deepcopy(self.positive)
        p["result"]["metadata"][KEY][field] = value
        with self.assertRaisesRegex(ValueError, "typed receipt mismatch"):
            V["verify_outputs"](WORKSPACE, p, self.negative)

    def test_synthetic_valid_baseline(self):
        self.assertEqual(V["verify_tests"](self.log, self.names)["passed"], 39)

    def test_origin_true(self):
        self.reject_receipt("origin_verified", True)

    def test_origin_numeric_zero_not_false(self):
        self.reject_receipt("origin_verified", 0)

    def test_source_bytes_float_not_integer(self):
        self.reject_receipt("source_bytes", 40.0)

    def test_semantic_truth_not_accepted(self):
        self.reject_receipt("semantic_entailment", "verified")

    def test_wrong_config_digest(self):
        self.reject_receipt("config_sha256", "0" * 64)

    def test_wrong_observed_path(self):
        self.reject_receipt("observed_path", "/other/fixtures/source.txt")

    def test_wrong_quote_hash(self):
        claims = deepcopy(self.positive["result"]["metadata"][KEY]["verified_claims"])
        claims[0]["quote_sha256"] = "0" * 64
        self.reject_receipt("verified_claims", claims)

    def test_wrong_span(self):
        claims = deepcopy(self.positive["result"]["metadata"][KEY]["verified_claims"])
        claims[0]["start_byte"] += 1
        self.reject_receipt("verified_claims", claims)

    def test_reader_id_cannot_equal_verifier(self):
        self.positive["result"]["metadata"][KEY]["reader_call_id"] = CALL_ID
        with self.assertRaisesRegex(ValueError, "reader identity"):
            V["verify_outputs"](WORKSPACE, self.positive, self.negative)

    def test_wrong_negative_error(self):
        self.negative["result"]["error"] = "unrelated cancellation"
        with self.assertRaisesRegex(ValueError, "negative diagnostic"):
            V["verify_outputs"](WORKSPACE, self.positive, self.negative)

    def test_negative_witness_rejected(self):
        self.negative["result"]["metadata"] = {KEY: self.positive["result"]["metadata"][KEY]}
        with self.assertRaisesRegex(ValueError, "canonical null"):
            V["verify_outputs"](WORKSPACE, self.positive, self.negative)

    def test_incorrect_host_label(self):
        self.positive["host_kind"] = "actual_core"
        with self.assertRaisesRegex(ValueError, "host label"):
            V["verify_outputs"](WORKSPACE, self.positive, self.negative)

    def test_missing_named_test(self):
        log = self.log.replace("test " + self.names[0] + " ... ok\n", "")
        with self.assertRaisesRegex(ValueError, "named tests"):
            V["verify_tests"](log, self.names)

    def test_duplicate_named_test(self):
        log = self.log.replace("test " + self.names[0] + " ... ok", "test " + self.names[1] + " ... ok")
        with self.assertRaisesRegex(ValueError, "named tests"):
            V["verify_tests"](log, self.names)

    def test_wrong_same_count_test_name(self):
        log = self.log.replace("test " + self.names[0] + " ... ok", "test unrelated ... ok")
        with self.assertRaisesRegex(ValueError, "named tests"):
            V["verify_tests"](log, self.names)

    def test_failed_ignored_filtered_measured_rejected(self):
        for phrase in ["failed", "ignored", "filtered out", "measured"]:
            with self.subTest(phrase=phrase):
                log = self.log.replace("0 " + phrase, "1 " + phrase, 1)
                with self.assertRaisesRegex(ValueError, "failed/ignored/measured/filtered"):
                    V["verify_tests"](log, self.names)

    def test_wrong_target_counts_rejected(self):
        log = self.log.replace("5 passed", "4 passed").replace("32 passed", "33 passed")
        with self.assertRaisesRegex(ValueError, "target test counts"):
            V["verify_tests"](log, self.names)

    def test_unknown_receipt_field_rejected(self):
        self.reject_receipt("authorization_granted", True)

    def test_duplicate_json_key_rejected(self):
        with self.assertRaisesRegex(ValueError, "duplicate JSON key"):
            V["pairs"]([("ok", True), ("ok", False)])

    def test_contradictory_positive_output_rejected(self):
        self.positive["result"]["output"] = "Origin and semantics verified"
        with self.assertRaisesRegex(ValueError, "positive disclaimer/count mismatch"):
            V["verify_outputs"](WORKSPACE, self.positive, self.negative)

    def test_control_omission_rejected(self):
        names = V["load"](WORKSPACE / "ci/expected-controls.json")
        log = "".join(f"{n} (__main__.Controls.{n}) ... ok\n" for n in names)
        log += "\n----------------------------------------------------------------------\nRan 23 tests in 0.001s\n\nOK\n"
        self.assertEqual(V["verify_controls"](log, names)["passed"], 23)
        omitted = log.replace(f"{names[0]} (__main__.Controls.{names[0]}) ... ok\n", "")
        with self.assertRaisesRegex(ValueError, "exact named controls differ"):
            V["verify_controls"](omitted, names)

    def test_stale_evidence_leaf_rejected(self):
        with tempfile.TemporaryDirectory(prefix="spans-validator-control-") as temp:
            leaf = Path(temp) / "evidence"
            V["initialize_evidence_leaf"](leaf)
            sentinel = leaf / "must-not-overwrite.txt"
            sentinel.write_text("previous evidence")
            with self.assertRaises(FileExistsError):
                V["initialize_evidence_leaf"](leaf)
            self.assertEqual(sentinel.read_text(), "previous evidence")

if __name__ == "__main__":
    unittest.main(verbosity=2)
