#!/usr/bin/env python3
"""Pure synthetic gate controls, not parser language/budget execution."""
import importlib.util
import copy
import json
from pathlib import Path
import sys
import unittest

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent


def load(name):
    spec = importlib.util.spec_from_file_location(name, HERE / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


observations = load("verify_observations")
budget_gate = load("verify_budgets")
synthetic = load("synthetic_controls")
metadata_gate = load("verify_metadata")


class Controls(unittest.TestCase):
    def setUp(self):
        self.corpus, self.envelopes = synthetic.fixtures()
        self.rows = synthetic.rows()
        self.budgets = synthetic.budgets(self.rows)

    def semantic(self):
        return observations.verify(self.corpus, self.envelopes, self.rows)

    def budget(self):
        return budget_gate.verify(self.corpus, self.rows, self.budgets)

    def test_complete_observations_and_budgets(self):
        self.assertEqual(self.semantic()["observation_count"], 159)
        self.assertEqual(self.budget()["same_input_pairs"], 7)

    def test_observational_difference_not_migration_pass(self):
        result = self.semantic()
        self.assertEqual(result["migration_acceptance"], "not_granted")
        self.assertTrue(any(row["relation"] == "acceptance_difference" for row in result["comparisons"]))

    def test_missing_semantic_row(self):
        self.rows.pop()
        with self.assertRaisesRegex(ValueError, "exact 159"):
            self.semantic()

    def test_duplicate_semantic_row(self):
        self.rows[-1] = self.rows[0]
        with self.assertRaisesRegex(ValueError, "duplicate observation"):
            self.semantic()

    def test_boolean_schema_version(self):
        self.rows[0]["schema_version"] = True
        with self.assertRaisesRegex(ValueError, "observation version"):
            self.semantic()

    def test_wrong_rust_expanded_size(self):
        row = next(r for r in self.rows if r["parser"] == "baseline_typed" and r["case_id"] == "expanded_json_bytes_16384")
        row["outcome"]["serialized_fields_bytes"] -= 1
        with self.assertRaisesRegex(ValueError, "field-byte length inconsistent"):
            self.semantic()

    def test_wrong_module_body(self):
        row = next(r for r in self.rows if r["parser"] == "baseline_module" and r["case_id"] == "plain_valid")
        row["outcome"]["body"] += "modified"
        with self.assertRaisesRegex(ValueError, "body/fence"):
            self.semantic()

    def test_wrong_baseline_diagnostic(self):
        row = next(r for r in self.rows if r["parser"] == "baseline_typed" and r["case_id"] == "identical_metadata_duplicate")
        row["outcome"]["display"] = "unrelated directory mismatch"
        with self.assertRaisesRegex(ValueError, "wrong intended baseline error"):
            self.semantic()

    def test_json_ambiguities_rejected(self):
        for text in ('{"a":1,"a":1}', '{"a":NaN}', '{"a":Infinity}', '{"a":1e999}', '{"a":-1e999}'):
            with self.subTest(text=text), self.assertRaises(ValueError):
                observations.decode(text)

    def test_missing_budget_positive(self):
        self.budgets = [r for r in self.budgets if not (r["kind"] == "depth" and r["mode"] == "permissive")]
        with self.assertRaisesRegex(ValueError, "exact 15"):
            self.budget()

    def test_wrong_typed_budget_error(self):
        row = next(r for r in self.budgets if r["mode"] == "restrictive")
        row["typed_error_classification"] = None
        with self.assertRaisesRegex(ValueError, "intended typed budget error"):
            self.budget()

    def test_budget_input_changed(self):
        self.budgets[1]["yaml_sha256"] = "changed"
        with self.assertRaisesRegex(ValueError, "input identity changed"):
            self.budget()

    def test_budget_counter_not_exceeded(self):
        row = next(r for r in self.budgets if r["kind"] == "depth" and r["mode"] == "restrictive")
        row["budget_reports"][0]["max_depth"] = row["limit"]
        with self.assertRaisesRegex(ValueError, "counter did not exceed"):
            self.budget()

    def test_reader_api_not_string_api(self):
        row = next(r for r in self.budgets if r["kind"] == "reader_bytes")
        row["entrypoint"] = "typed Frontmatter from_str_with_options"
        with self.assertRaisesRegex(ValueError, "entry point changed"):
            self.budget()

    def test_disabled_comments_counter(self):
        row = next(r for r in self.budgets if r["mode"] == "comments_disabled")
        row["budget_reports"][0]["total_comment_bytes"] = 1
        with self.assertRaisesRegex(ValueError, "disabled comment retention"):
            self.budget()

    def test_unsupported_controls_remain_visible(self):
        result = self.budget()
        self.assertEqual(len(result["unsupported_configurable_controls"]), 2)
        self.assertEqual(result["migration_acceptance"], "not_granted")

    def metadata_fixture(self):
        pins = json.loads((HERE.parent / "SOURCE_PINS.json").read_text())
        packages = []
        locked = []
        nodes = []
        for name, pin in pins["parsers"].items():
            identifier = name + "@" + pin["version"]
            packages.append({"id": identifier, "name": name, "version": pin["version"], "source": pin["registry_source"]})
            locked.append({"name": name, "version": pin["version"], "checksum": pin["archive_sha256"]})
            nodes.append({"id": identifier, "features": ["comments", "deserialize"] if name == "serde-saphyr" else []})
        return {"packages": packages, "resolve": {"nodes": nodes}}, pins, {"package": locked}

    def test_metadata_positive(self):
        self.assertEqual(metadata_gate.verify(*self.metadata_fixture())["dependency_identity_and_features"], "passed")

    def test_metadata_forbidden_feature(self):
        metadata, pins, lock = self.metadata_fixture()
        node = next(n for n in metadata["resolve"]["nodes"] if n["id"].startswith("serde-saphyr@"))
        node["features"].append("include_fs")
        with self.assertRaisesRegex(ValueError, "unexpected saphyr feature"):
            metadata_gate.verify(metadata, pins, lock)

    def test_metadata_wrong_checksum(self):
        metadata, pins, lock = self.metadata_fixture()
        lock["package"][0]["checksum"] = "wrong"
        with self.assertRaisesRegex(ValueError, "pin/checksum drift"):
            metadata_gate.verify(metadata, pins, lock)

    def test_metadata_duplicate_identity(self):
        metadata, pins, lock = self.metadata_fixture()
        metadata["packages"].append(copy.deepcopy(metadata["packages"][0]))
        with self.assertRaisesRegex(ValueError, "identity ambiguous"):
            metadata_gate.verify(metadata, pins, lock)


if __name__ == "__main__":
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Controls))
    raise SystemExit(0 if result.wasSuccessful() and result.testsRun == 20 and not result.skipped else 1)
