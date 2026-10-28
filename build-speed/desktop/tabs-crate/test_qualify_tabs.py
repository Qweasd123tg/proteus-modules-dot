"""Synthetic tabs/configuration controls; no product or subprocess execution."""
import copy
import hashlib
import json
from pathlib import Path
import unittest

from qualify_tabs import HERE, inspect_output, validate_expected

SOURCE = Path("/qualification/source")
TARGET = Path("/qualification/evidence/target")
EXPECTED = json.loads((HERE / "expected.json").read_text())
DIFF_EXPECTED = json.loads((HERE.parent / "diff-crate" / "expected.json").read_text())


def messages(expected=EXPECTED, fresh=False):
    records = []
    for name, package in expected["registry_packages"].items():
        records.append({
            "reason": "compiler-artifact",
            "package_id": f"{package['source']}#{name}@{package['version']}",
            "target": {"name": name.replace("-", "_"),
                       "kind": ["proc-macro"] if name == "serde_derive" else ["lib"]},
            "features": [], "profile": {"test": False}, "fresh": fresh,
        })
    component = expected["component"]
    records.append({
        "reason": "compiler-artifact",
        "package_id": f"path+file://{SOURCE}/{component['crate_dir']}#{component['name']}@{expected['package_version']}",
        "target": {"name": component["target"], "kind": ["lib"],
                   "src_path": str(SOURCE / component["crate_dir"] / "src/lib.rs")},
        "features": [], "profile": {"test": True}, "fresh": fresh,
        "executable": str(TARGET / "debug/deps" / (component["target"] + "-test")),
    })
    return records + [{"reason": "build-finished", "success": True}]


def transcript(expected=EXPECTED, records=None, names=None, summary=None):
    records = messages(expected) if records is None else records
    names = expected["test_names"] if names is None else names
    count = len(expected["test_names"])
    component = expected["component"]
    if summary is None:
        summary = f"test result: ok. {count} passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 0.00s"
    header = f"Running unittests {component['crate_dir']}/src/lib.rs ({TARGET}/debug/deps/{component['target']}-test)"
    return "\n".join([json.dumps(record) for record in records]
                     + [header, f"running {count} tests"]
                     + [f"test {name} ... ok" for name in names] + [summary, ""])


class TabsAndConfigurationTests(unittest.TestCase):
    def inspect(self, **kwargs):
        return inspect_output(transcript(**kwargs), SOURCE, TARGET, EXPECTED)

    def test_all_38_names_and_serde_json_closure(self):
        result = self.inspect()
        self.assertEqual(result["test_names"], sorted(EXPECTED["test_names"]))
        self.assertEqual(len(result["test_names"]), 38)
        self.assertEqual(len(result["artifacts"]), 12)
        self.assertIn("tests::tree::layouts_round_trip_and_reject_other_shapes", result["test_names"])

    def test_mixed_json_text_and_fresh_artifacts(self):
        records = messages(fresh=True)
        records.insert(0, {"reason": "compiler-message",
                          "package_id": records[0]["package_id"],
                          "message": {"level": "warning"}})
        records.insert(1, {"reason": "build-script-executed",
                          "package_id": records[1]["package_id"]})
        output = "   Compiling pure dependencies\n" + transcript(records=records)
        result = inspect_output(output, SOURCE, TARGET, EXPECTED)
        self.assertTrue(all(record["fresh"] for record in result["artifacts"]))

    def test_missing_duplicate_or_foreign_nested_test(self):
        for names in (EXPECTED["test_names"][:-1],
                      EXPECTED["test_names"][:-1] + EXPECTED["test_names"][:1],
                      EXPECTED["test_names"][:-1] + ["tests::tree::foreign"]):
            with self.assertRaises(ValueError):
                self.inspect(names=names)

    def test_failed_ignored_filtered_or_wrong_summary(self):
        for summary in (
            "test result: ok. 37 passed; 0 failed; 1 ignored; 0 measured; 0 filtered out; finished in 0.00s",
            "test result: ok. 38 passed; 0 failed; 0 ignored; 0 measured; 1 filtered out; finished in 0.00s",
            "test result: ok. 8 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 0.00s",
        ):
            with self.assertRaises(ValueError):
                self.inspect(summary=summary)
        with self.assertRaises(ValueError):
            inspect_output(transcript().replace(" ... ok", " ... FAILED", 1), SOURCE, TARGET, EXPECTED)

    def test_execution_header_and_count_binding(self):
        output = transcript()
        header = f"Running unittests crates/tabs/src/lib.rs ({TARGET}/debug/deps/proteus_tabs-test)\n"
        for changed in (output.replace(header, ""),
                        output.replace("proteus_tabs-test)", "foreign-test)"),
                        output.replace("crates/tabs/src/lib.rs (", "crates/diff/src/lib.rs ("),
                        output.replace("running 38 tests", "running 37 tests")):
            with self.assertRaises(ValueError):
                inspect_output(changed, SOURCE, TARGET, EXPECTED)

    def test_foreign_native_gpui_core_and_diff_rejected(self):
        for package_id in (
            f"path+file://{SOURCE}#proteus-native@0.1.0-alpha.3",
            "registry+https://github.com/rust-lang/crates.io-index#gpui@0.2.0",
            "git+https://github.com/Proteus-harness/Proteus-core.git#proteus-core@0.1.0",
            f"path+file://{SOURCE}/crates/diff#proteus-diff@0.1.0-alpha.3",
        ):
            records = messages()
            records[0]["package_id"] = package_id
            with self.assertRaises(ValueError):
                self.inspect(records=records)

    def test_missing_json_dependency_or_wrong_pin(self):
        records = messages()
        index = next(i for i, record in enumerate(records) if "#serde_json@" in record.get("package_id", ""))
        wrong = copy.deepcopy(records)
        wrong[index]["package_id"] = wrong[index]["package_id"].replace("@1.0.152", "@1.0.151")
        for changed in (records[:index] + records[index + 1:], wrong):
            with self.assertRaises(ValueError):
                self.inspect(records=changed)

    def test_selected_target_and_build_script_rejected(self):
        for key, value in (("name", "proteus_native"), ("kind", ["bin"]),
                           ("src_path", str(SOURCE / "src/main.rs"))):
            records = messages()
            records[-2]["target"][key] = value
            with self.assertRaises(ValueError):
                self.inspect(records=records)
        with self.assertRaises(ValueError):
            self.inspect(records=messages() + [{"reason": "build-script-executed",
                                               "package_id": messages()[-2]["package_id"]}])

    def test_component_manifest_defaults_and_inventory_paths(self):
        mutations = [
            lambda value: value["component"].update(name="proteus-native"),
            lambda value: value["component"].update(crate_dir="../tabs"),
            lambda value: value["component"]["manifest"].update(build="build.rs"),
            lambda value: value["component"]["manifest"]["dev-dependencies"].update(gpui="1"),
            lambda value: value.update(default_members=[".", "crates/tabs"]),
            lambda value: value["registry_packages"].update(gpui={}),
            lambda value: value["files"].update({"../outside": {}}),
            lambda value: value["deletes"].append("/outside"),
        ]
        for mutate in mutations:
            expected = copy.deepcopy(EXPECTED)
            mutate(expected)
            with self.assertRaises(ValueError):
                validate_expected(expected)

    def test_empty_duplicate_or_malformed_expected_names(self):
        for names in ([], EXPECTED["test_names"] + EXPECTED["test_names"][:1],
                      ["native::tests::foreign"], ["tests::tree::::foreign"]):
            expected = copy.deepcopy(EXPECTED)
            expected["test_names"] = names
            with self.assertRaises(ValueError):
                validate_expected(expected)

    def test_ordered_patch_stages_are_exactly_bound(self):
        mutations = [
            lambda value: value["patches"].reverse(),
            lambda value: value["patches"].pop(),
            lambda value: value["patches"][0].update(path="../arbitrary.patch"),
            lambda value: value["patches"][0].update(sha256="not-a-hash"),
            lambda value: value["patches"][1].update(input_tree="0" * 40),
            lambda value: value["patches"][1].update(output_tree="0" * 40),
        ]
        for mutate in mutations:
            expected = copy.deepcopy(EXPECTED)
            mutate(expected)
            with self.assertRaises(ValueError):
                validate_expected(expected)

    def test_original_diff_configuration_and_eight_names_replay(self):
        # Reconstitute the immutable PR41 config bytes, not a second runner.
        keys = ("schema", "source", "toolchain", "package_version", "patch_sha256",
                "files", "deletes", "test_names", "registry_packages",
                "source_review_sha256", "qualification")
        overrides = {"schema": 1, "patch_sha256": DIFF_EXPECTED["patches"][0]["sha256"],
                     "qualification": "NOT_RUN"}
        original = {key: overrides[key] if key in overrides else DIFF_EXPECTED[key] for key in keys}
        serialized = (json.dumps(original, indent=2) + "\n").encode()
        self.assertEqual(hashlib.sha256(serialized).hexdigest(),
                         "930e2305a62b378b371411b9eea741d9f82ca96a195dd58dcf0be080517166fa")
        result = inspect_output(transcript(DIFF_EXPECTED), SOURCE, TARGET, DIFF_EXPECTED)
        self.assertEqual(len(result["test_names"]), 8)
        self.assertEqual(result["test_names"], sorted(DIFF_EXPECTED["test_names"]))


if __name__ == "__main__":
    unittest.main()
