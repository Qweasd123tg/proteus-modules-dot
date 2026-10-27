"""Synthetic Cargo/libtest transcript checks; no subprocess or upstream code."""
import copy
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from qualify_diff import HERE, inspect_output

SOURCE = Path("/qualification/source")
TARGET = Path("/qualification/evidence/target")
EXPECTED = json.loads((HERE / "expected.json").read_text())


def messages(fresh=False):
    result = []
    for name, package in EXPECTED["registry_packages"].items():
        result.append({
            "reason": "compiler-artifact",
            "package_id": f"{package['source']}#{name}@{package['version']}",
            "target": {
                "name": name.replace("-", "_"),
                "kind": ["proc-macro"] if name == "serde_derive" else ["lib"],
            },
            "features": [], "profile": {"test": False}, "fresh": fresh,
        })
    result.append({
        "reason": "compiler-artifact",
        "package_id": f"path+file://{SOURCE}/crates/diff#proteus-diff@0.1.0-alpha.3",
        "target": {
            "name": "proteus_diff", "kind": ["lib"],
            "src_path": str(SOURCE / "crates/diff/src/lib.rs"),
        },
        "features": [], "profile": {"test": True}, "fresh": fresh,
        "executable": str(TARGET / "debug/deps/proteus_diff-test"),
    })
    result.append({"reason": "build-finished", "success": True})
    return result


def transcript(records=None, names=None, summary=None):
    if records is None:
        records = messages()
    if names is None:
        names = EXPECTED["test_names"]
    if summary is None:
        summary = "test result: ok. 8 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 0.00s"
    return "\n".join(
        [json.dumps(record) for record in records]
        + [f"     Running unittests crates/diff/src/lib.rs ({TARGET}/debug/deps/proteus_diff-test)", "running 8 tests"]
        + [f"test {name} ... ok" for name in names]
        + [summary, ""]
    )


class TranscriptTests(unittest.TestCase):
    def setUp(self):
        guard = patch("qualify_diff.command", side_effect=AssertionError("No subprocess in parser tests"))
        guard.start()
        self.addCleanup(guard.stop)

    def inspect(self, **kwargs):
        return inspect_output(transcript(**kwargs), SOURCE, TARGET, EXPECTED)

    def test_all_eight_and_only_audited_packages(self):
        result = self.inspect()
        self.assertEqual(result["test_names"], sorted(EXPECTED["test_names"]))
        self.assertEqual(len(result["artifacts"]), 8)

    def test_fresh_artifacts_are_still_evidence(self):
        self.assertEqual(len(self.inspect(records=messages(True))["artifacts"]), 8)

    def test_native_or_gpui_artifact_rejected(self):
        for package_id in (
            f"path+file://{SOURCE}#proteus-native@0.1.0-alpha.3",
            "registry+https://github.com/rust-lang/crates.io-index#gpui@0.2.0",
        ):
            records = messages()
            records[0]["package_id"] = package_id
            with self.subTest(package_id=package_id), self.assertRaises(ValueError):
                self.inspect(records=records)

    def test_wrong_diff_source_rejected(self):
        records = messages()
        records[-2]["package_id"] = "path+file:///other/crates/diff#proteus-diff@0.1.0-alpha.3"
        with self.assertRaises(ValueError):
            self.inspect(records=records)

    def test_wrong_locked_version_rejected(self):
        records = messages()
        records[0]["package_id"] = records[0]["package_id"].replace("@1.0.229", "@1.0.1")
        with self.assertRaises(ValueError):
            self.inspect(records=records)

    def test_missing_dependency_evidence_rejected(self):
        with self.assertRaises(ValueError):
            self.inspect(records=messages()[1:])

    def test_missing_or_duplicate_test_rejected(self):
        for names in (EXPECTED["test_names"][:-1], EXPECTED["test_names"][:-1] + EXPECTED["test_names"][:1]):
            with self.assertRaises(ValueError):
                self.inspect(names=names)

    def test_ignored_or_filtered_summary_rejected(self):
        for fragment in ("7 passed; 0 failed; 1 ignored", "8 passed; 0 failed; 0 ignored; 0 measured; 1 filtered out"):
            with self.assertRaises(ValueError):
                self.inspect(summary=f"test result: ok. {fragment}; finished in 0.00s")

    def test_failed_test_line_rejected(self):
        output = transcript().replace(f"test {EXPECTED['test_names'][0]} ... ok",
                                      f"test {EXPECTED['test_names'][0]} ... FAILED")
        with self.assertRaises(ValueError):
            inspect_output(output, SOURCE, TARGET, EXPECTED)

    def test_missing_or_failed_build_finish_rejected(self):
        for records in (messages()[:-1], messages()[:-1] + [{"reason": "build-finished", "success": False}]):
            with self.assertRaises(ValueError):
                self.inspect(records=records)

    def test_no_other_target_or_build_script(self):
        for kind in (["bin"], ["custom-build"]):
            records = messages()
            records[-2]["target"]["kind"] = kind
            with self.assertRaises(ValueError):
                self.inspect(records=records)
        with self.assertRaises(ValueError):
            self.inspect(records=messages() * 10)
        records = messages() + [{
            "reason": "build-script-executed", "package_id": messages()[-2]["package_id"]
        }]
        with self.assertRaises(ValueError):
            self.inspect(records=records)

    def test_executable_outside_target_rejected(self):
        records = messages()
        records[-2]["executable"] = "/other/proteus_diff"
        with self.assertRaises(ValueError):
            self.inspect(records=records)
        for output in (
            transcript().replace(f"     Running unittests crates/diff/src/lib.rs ({TARGET}/debug/deps/proteus_diff-test)\n", ""),
            transcript().replace(f"({TARGET}/debug/deps/proteus_diff-test)", "(/other/executable)"),
            transcript().replace("running 8 tests\n", ""),
            transcript().replace("running 8 tests", "running 7 tests"),
        ):
            with self.assertRaises(ValueError):
                inspect_output(output, SOURCE, TARGET, EXPECTED)

    def test_duplicate_test_executable_rejected(self):
        records = messages()
        records.insert(-1, copy.deepcopy(records[-2]))
        with self.assertRaises(ValueError):
            self.inspect(records=records)

    def test_unknown_json_or_malformed_package_id_rejected(self):
        for record in ({"reason": "unexpected-event"}, {"hello": "world"}):
            with self.assertRaises(ValueError):
                self.inspect(records=messages() + [record])
        records = messages()
        records[0]["package_id"] = "serde"
        with self.assertRaises(ValueError):
            self.inspect(records=records)


if __name__ == "__main__":
    unittest.main()
