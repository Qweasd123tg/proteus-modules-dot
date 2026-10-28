#!/usr/bin/env python3
"""Negative/positive tests of this offline verifier, not Proteus tests."""
from pathlib import Path
import copy
import json
import unittest

import verify_static as verifier

ROOT = Path(__file__).resolve().parent


class StaticVerifierTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.before = (ROOT / "preimage.rs").read_text()
        cls.after = (ROOT / "postimage.rs").read_text()
        cls.fragment = (ROOT / "restricted-components.toml").read_text()
        cls.patch = (ROOT / "fix.patch").read_text()
        cls.inventory = json.loads((ROOT / "module-inventory.json").read_text())

    def check_source(self, after=None, fragment=None):
        verifier.validate_source_contract(
            self.before, self.after if after is None else after,
            self.fragment if fragment is None else fragment,
        )

    def test_accepts_pinned_source_repair(self):
        self.check_source()

    def test_rejects_arbitrary_command(self):
        with self.assertRaisesRegex(ValueError, "mappings changed"):
            self.check_source(self.after.replace(
                '"proteus-coding-workflow-module"', '"arbitrary-worker"', 1))

    def test_rejects_missing_binding(self):
        row = '''        (
            "reference-search-provider",
            "proteus-rg-search-module",
            "context_provider",
            "rg_search",
            true,
        ),
'''
        self.assertIn(row, self.after)
        with self.assertRaisesRegex(ValueError, "mappings changed"):
            self.check_source(self.after.replace(row, "", 1))

    def test_rejects_weakened_sandbox_assertion(self):
        with self.assertRaisesRegex(ValueError, "assertions changed"):
            self.check_source(self.after.replace("        assert!(!sandbox.network);\n", "", 1))

    def test_rejects_five_binary_copies(self):
        with self.assertRaisesRegex(ValueError, "fixture operations"):
            self.check_source(self.after.replace(
                "std::fs::hard_link(&fixture, path)", "std::fs::copy(&fixture, path)", 1))

    def test_rejects_fragment_network_grant(self):
        with self.assertRaisesRegex(ValueError, "sandbox grants mismatch"):
            self.check_source(fragment=self.fragment.replace("network = false", "network = true", 1))

    def test_rejects_edits_outside_corrected_test(self):
        with self.assertRaisesRegex(ValueError, "outside corrected test changed"):
            self.check_source("// unrelated edit\n" + self.after)

    def test_rejects_corrupt_patch(self):
        with self.assertRaisesRegex(ValueError, "canonical"):
            verifier.validate_patch(self.before, self.after, self.patch + "\n")

    def test_accepts_pinned_module_inventory(self):
        verifier.validate_inventory(self.inventory)

    def test_rejects_missing_inventory_export_even_with_rehashed_blob(self):
        inventory = copy.deepcopy(self.inventory)
        record = inventory["packages"]["coding-workflow"]["exports.json"]
        record["content"] = json.dumps({"workflow": ["coding.single_loop"]}) + "\n"
        record["git_blob_sha1"] = verifier.blob_sha1(record["content"].encode())
        with self.assertRaisesRegex(ValueError, "missing selected export"):
            verifier.validate_inventory(inventory)


if __name__ == "__main__":
    unittest.main(verbosity=2)
