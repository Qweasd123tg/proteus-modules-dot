"""Red regression expectations; no real providers or agent binaries are invoked."""
import json
from pathlib import Path
import subprocess
import sys
import unittest

class AccountingRegressions(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.evidence = json.loads(subprocess.check_output(
            [sys.executable,'-B',str(Path(__file__).with_name('reproduce_accounting.py'))],text=True))

    def test_successfully_recovered_native_pi_has_same_pipeline_status_as_proteus(self):
        row = self.evidence['retry_asymmetry']
        self.assertEqual(row['native_pi_pipeline_ok'],row['proteus_pipeline_ok'])

    def test_final_length_stop_is_not_silently_clean_pipeline(self):
        row = self.evidence['native_pi_truncation']
        self.assertFalse(row['pipeline_ok'])

    def test_short_report_does_not_claim_full_usage_for_timed_out_run(self):
        row = self.evidence['partial_timeout_totals']
        self.assertIsNone(row['short_report_complete_input'])

    def test_whole_missing_usage_row_makes_total_unknown(self):
        row = self.evidence['missing_pi_usage']
        self.assertIsNone(row['actual_reported_totals']['input_tokens'])

if __name__ == '__main__':
    unittest.main()
