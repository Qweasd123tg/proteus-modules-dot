"""Negative controls for exact offline source reconstruction, without processes."""
import importlib.util
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("selected_package_checker", HERE / "check.py")
check = importlib.util.module_from_spec(spec)
spec.loader.exec_module(check)


class ReconstructionTests(unittest.TestCase):
    def setUp(self):
        source = json.loads((HERE / "source-bundle.json").read_text())
        self.original = {name: source["files"][name]["content"] for name in ("package.py", "README.md")}
        self.diff = (HERE / "extension-selective-packaging.patch").read_text()

    def test_exact_candidate_and_inventory_are_bound(self):
        candidate, manifest = check.load_candidate()
        self.assertEqual(len(manifest["test_names"]), 37)
        self.assertEqual(set(candidate), {"package.py", "README.md", "tests/test_package_selection.py"})

    def test_context_drift_fails_without_fuzz(self):
        original = dict(self.original)
        original["package.py"] = original["package.py"].replace("import os\n", "import os # changed\n")
        with self.assertRaisesRegex(ValueError, "context mismatch"):
            check.apply_exact(original, self.diff)

    def test_path_escape_is_rejected(self):
        diff = self.diff.replace("+++ b/package.py\n", "+++ b/../../escape\n", 1)
        with self.assertRaisesRegex(ValueError, "patch path"):
            check.apply_exact(self.original, diff)

    def test_missing_test_patch_is_rejected(self):
        diff = self.diff.split("--- /dev/null\n", 1)[0]
        with self.assertRaisesRegex(ValueError, "incomplete patch"):
            check.apply_exact(self.original, diff)

    def test_duplicate_patch_file_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "duplicate patch file"):
            check.apply_exact(self.original, self.diff + self.diff)

    def test_truncated_hunk_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "truncated hunk"):
            check.apply_exact(self.original, self.diff.rsplit("\n", 3)[0] + "\n")

    def test_source_bundle_tampering_fails_before_execution(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ("manifest.json", "source-bundle.json", "extension-selective-packaging.patch"):
                (root / name).write_bytes((HERE / name).read_bytes())
            path = root / "source-bundle.json"
            path.write_bytes(path.read_bytes() + b" ")
            with patch.object(check, "HERE", root):
                with self.assertRaisesRegex(ValueError, "source bundle digest"):
                    check.load_candidate()

    def test_patch_tampering_fails_before_execution(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ("manifest.json", "source-bundle.json", "extension-selective-packaging.patch"):
                (root / name).write_bytes((HERE / name).read_bytes())
            path = root / "extension-selective-packaging.patch"
            path.write_bytes(path.read_bytes() + b" ")
            with patch.object(check, "HERE", root):
                with self.assertRaisesRegex(ValueError, "patch digest"):
                    check.load_candidate()

    def test_self_consistent_extra_baseline_path_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ("manifest.json", "source-bundle.json", "extension-selective-packaging.patch"):
                (root / name).write_bytes((HERE / name).read_bytes())
            source_path = root / "source-bundle.json"
            source = json.loads(source_path.read_text())
            data = b"outside fixture\n"
            source["files"]["../outside"] = {
                "content": data.decode(), "sha256": hashlib.sha256(data).hexdigest(),
                "git_blob_sha": hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest(),
            }
            source_path.write_text(json.dumps(source))
            manifest_path = root / "manifest.json"
            manifest = json.loads(manifest_path.read_text())
            manifest["baseline_files"].append("../outside")
            manifest["candidate_sha256"]["../outside"] = hashlib.sha256(data).hexdigest()
            manifest["source_bundle_sha256"] = hashlib.sha256(source_path.read_bytes()).hexdigest()
            manifest_path.write_text(json.dumps(manifest))
            with patch.object(check, "HERE", root):
                with self.assertRaisesRegex(ValueError, "baseline paths"):
                    check.load_candidate()

    def test_candidate_path_guard_precedes_materialization(self):
        candidate, manifest = check.load_candidate()
        candidate["../outside"] = "unexpected fixture"
        with patch.object(check.tempfile, "TemporaryDirectory", side_effect=AssertionError("must not materialize")):
            with self.assertRaisesRegex(ValueError, "candidate paths"):
                check.run_controls(candidate, manifest)


if __name__ == "__main__":
    unittest.main(verbosity=2)
