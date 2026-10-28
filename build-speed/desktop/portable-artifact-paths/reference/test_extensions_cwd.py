"""Check the pinned extension packager's relative-target behavior with mocked Cargo."""
import contextlib
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("pinned_extensions", HERE / "extensions-package.py")
packager = importlib.util.module_from_spec(spec)
spec.loader.exec_module(packager)


class ExtensionsCwdTests(unittest.TestCase):
    def exercise(self, target):
        with tempfile.TemporaryDirectory(prefix="extension cwd mock ") as temporary:
            root = Path(temporary)
            extensions = root / "extensions source"
            package = extensions / "packages/files"
            package.mkdir(parents=True)
            (package / "Cargo.toml").write_text("# inert manifest")
            (package / "extension.json").write_text(json.dumps({"command": ["bin/files"]}))
            target = target if isinstance(target, Path) else extensions / target
            target.mkdir(parents=True, exist_ok=True)
            output = target / "release/files"
            output.parent.mkdir(parents=True)
            output.write_text("new synthetic output")
            previous_cwd = Path.cwd()
            try:
                os.chdir(extensions)
                value = str(target) if isinstance(self.target_mode, Path) else self.target_mode
                with patch.object(packager, "ROOT", extensions), \
                     patch.object(packager, "PACKAGES", extensions / "packages"), \
                     patch.dict(os.environ, {"CARGO_TARGET_DIR": value}), \
                     patch.object(packager.subprocess, "run") as cargo:
                    built = packager.binaries()
                    self.assertEqual(built[package][0].resolve(), output)
                    destination = root / "bundle/files"
                    packager.place(built, package, destination)
                    self.assertEqual((destination / "bin/files").read_text(), "new synthetic output")
                    self.assertEqual(cargo.call_args.kwargs["cwd"], extensions)
                    self.assertEqual(os.environ["CARGO_TARGET_DIR"], value)
            finally:
                os.chdir(previous_cwd)

    def test_relative_target_with_correct_extensions_cwd(self):
        self.target_mode = "relative cache"
        self.exercise(self.target_mode)

    def test_absolute_target_still_supported(self):
        with tempfile.TemporaryDirectory(prefix="absolute cache mock ") as temporary:
            self.target_mode = Path(temporary)
            self.exercise(self.target_mode)


if __name__ == "__main__":
    unittest.main()
