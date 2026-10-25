"""Authored negative controls for CI evidence parsing; never invokes Cargo."""
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from verify_results import EvidenceError, verify

REQUIRED = json.loads((Path(__file__).parent / "required-tests.json").read_text())
BEFORE = {"files": {"fixture.rs": "same-authored-hash"}}


def valid_output():
    lines = [f"test {name} ... ok" for name in REQUIRED["test_names"]]
    lines.extend(f"test result: ok. {count} passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 0.00s"
                 for count in (0, 0, 2, 19, 12))
    return "\n".join(lines) + "\n"


class EvidenceControls(unittest.TestCase):
    def test_valid_complete_positive_control(self):
        self.assertEqual(verify(valid_output(), REQUIRED, BEFORE, BEFORE)["passed"], 33)

    def test_ignored_case_cannot_be_green_cargo_false_pass(self):
        raw = valid_output().replace(" ... ok", " ... ignored", 1)
        with self.assertRaisesRegex(EvidenceError, "individual case did not pass"):
            verify(raw, REQUIRED, BEFORE, BEFORE)

    def test_failed_case_rejected(self):
        raw = valid_output().replace(" ... ok", " ... FAILED", 1)
        with self.assertRaisesRegex(EvidenceError, "individual case did not pass"):
            verify(raw, REQUIRED, BEFORE, BEFORE)

    def test_missing_or_renamed_required_case_rejected(self):
        raw = valid_output().replace(REQUIRED["test_names"][0], "unreviewed_replacement", 1)
        with self.assertRaisesRegex(EvidenceError, "individual case names"):
            verify(raw, REQUIRED, BEFORE, BEFORE)

    def test_truncated_summary_rejected(self):
        raw = valid_output().rsplit("test result:", 1)[0]
        with self.assertRaisesRegex(EvidenceError, "five complete"):
            verify(raw, REQUIRED, BEFORE, BEFORE)

    def test_nonzero_ignored_or_filtered_summary_rejected(self):
        for field in ("failed", "ignored", "measured", "filtered out"):
            with self.subTest(field=field):
                raw = valid_output().replace(f"0 {field}", f"1 {field}", 1)
                with self.assertRaisesRegex(EvidenceError, "summary contains"):
                    verify(raw, REQUIRED, BEFORE, BEFORE)

    def test_incorrect_suite_totals_rejected(self):
        raw = valid_output().replace("19 passed", "18 passed")
        with self.assertRaisesRegex(EvidenceError, "suite totals"):
            verify(raw, REQUIRED, BEFORE, BEFORE)

    def test_source_drift_rejected_even_with_all_tests_green(self):
        after = {"files": {"fixture.rs": "changed-authored-hash"}}
        with self.assertRaisesRegex(EvidenceError, "source manifest changed"):
            verify(valid_output(), REQUIRED, BEFORE, after)


if __name__ == "__main__":
    unittest.main()
