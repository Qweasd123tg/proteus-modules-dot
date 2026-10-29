"""Reuse-host controls with fake processes and inert temporary binary files only."""
import contextlib
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import types
import unittest
from unittest.mock import Mock, patch


SCRIPTS = Path(__file__).resolve().parent


def load_source(name, path, stubs):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, stubs):
        spec.loader.exec_module(module)
    return module


def dependency(name, **exports):
    module = types.ModuleType(name)
    vars(module).update(exports)
    return module


class ReuseHostsTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="proteus reuse-host controls ")
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.native = self.base / "desktop"
        self.sources = {name: self.base / name for name in ("harness", "modules", "extensions")}
        for root in (self.native, *self.sources.values()):
            root.mkdir()
        self.env = patch.dict(os.environ, {"CARGO_TARGET_DIR": "target"}, clear=True)
        self.env.start()
        self.addCleanup(self.env.stop)
        self.record = {"version": "0.1.0-test", "sources": {
            name: {"commit": name + "-pinned", "dirty": False}
            for name in ("desktop", *self.sources)
        }}
        self.process = dependency(
            "subprocess", PIPE=subprocess.PIPE, CalledProcessError=subprocess.CalledProcessError,
            run=Mock(side_effect=self.fake_packager),
            call=Mock(side_effect=AssertionError("Unexpected subprocess.call")),
            check_output=Mock(side_effect=AssertionError("Unexpected subprocess.check_output")),
            Popen=Mock(side_effect=AssertionError("Unexpected subprocess.Popen")),
        )
        metadata = dependency(
            "release_metadata", VERSION_PATTERN=r"\d+\.\d+\.\d+",
            install_notices=Mock(), version=Mock(return_value="0.1.0-test"),
            write_manifest=Mock(side_effect=self.write_manifest),
            manifest=Mock(side_effect=lambda *args: json.loads(json.dumps(self.record))),
        )
        cargo = load_source("reuse_control_cargo", SCRIPTS / "cargo_binary.py",
                            {"subprocess": self.process})
        cargo.build_binary = Mock(side_effect=AssertionError("Host Cargo build must not run"))
        stubs = {
            "subprocess": self.process,
            "cargo_binary": cargo,
            "sources": dependency("sources", resolve=Mock(side_effect=self.sources.__getitem__)),
            "limits": dependency("limits", limit=Mock()),
            "portable_modules": dependency("portable_modules", assemble=Mock()),
            "release_metadata": metadata,
        }
        self.portable = load_source("reuse_control_portable", SCRIPTS / "portable.py", stubs)
        self.release = load_source("reuse_control_release", SCRIPTS / "release.py", stubs)
        self.portable.NATIVE = self.native
        self.portable.BUILD = self.native / "build"
        self.portable.PORTABLE = self.portable.BUILD / "Proteus"
        self.portable.ASSETS = self.native / "scripts/portable"
        self.portable.ICON = self.native / "assets/icon.png"
        self.portable.tracked_configs = Mock(return_value=[])
        self.portable.archive = Mock(return_value=self.portable.BUILD / "inert-archive.tar.gz")
        self.portable.existing_binary = Mock(wraps=cargo.existing_binary)
        for relative in ("assets/icon.png", "assets/proteus-logo.svg",
                         "scripts/portable/proteus-native", "scripts/portable/system_proxy.py",
                         "scripts/portable/install-shortcut"):
            destination = self.native / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(b"inert asset, never executed\n")
        for profile in ("release", "debug"):
            self.host(self.sources["harness"], profile, "proteus")
        for profile in ("release", "fast", "debug"):
            self.host(self.native, profile, "proteus-native")

    def host(self, root, profile, name):
        target = Path(os.environ["CARGO_TARGET_DIR"])
        destination = (target if target.is_absolute() else root / target) / profile / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(f"inert existing {name} {profile}\n")
        return destination

    def write_manifest(self, staging, *roots):
        record = json.loads(json.dumps(self.record))
        path = staging / "share/release-sources.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(record))
        return record

    def fake_packager(self, command, *, cwd, check):
        """Accept only packaging requests; record inert outputs without any process."""
        self.assertTrue(check)
        self.assertEqual(command[:2], [sys.executable, str(cwd / "package.py")])
        self.assertIn(cwd, (self.sources["modules"], self.sources["extensions"]))
        destination = Path(command[command.index("--bundle") + 1])
        if cwd == self.sources["modules"]:
            output = destination / "bin/proteus-module-fixture"
        else:
            output = destination / "fixture/bin/fixture"
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(b"inert packaged output, never executed\n")

    def invoke(self, flags):
        with patch.object(sys, "argv", ["portable.py", *flags]), \
             contextlib.redirect_stdout(io.StringIO()), \
             contextlib.redirect_stderr(io.StringIO()):
            self.portable.main()

    def assert_reuse_hosts(self, flags, host_profile, client_profile, module_profile, archive):
        self.invoke(["--reuse-hosts", *flags])
        self.portable.build_binary.assert_not_called()
        self.portable.limit.assert_called_once_with()
        self.assertEqual([call.args for call in self.portable.existing_binary.call_args_list], [
            (self.sources["harness"], host_profile, "proteus"),
            (self.native, client_profile, "proteus-native"),
        ])
        staging = self.portable.BUILD / "Proteus.next"
        self.assertEqual([call.args[0] for call in self.process.run.call_args_list], [
            [sys.executable, str(self.sources["modules"] / "package.py"),
             "--profile", module_profile, "--bundle", str(staging)],
            [sys.executable, str(self.sources["extensions"] / "package.py"),
             "--bundle", str(staging / "share/extensions")],
        ])
        self.assertEqual([call.kwargs for call in self.process.run.call_args_list], [
            {"cwd": self.sources["modules"], "check": True},
            {"cwd": self.sources["extensions"], "check": True},
        ])
        self.assertEqual(self.portable.archive.call_count, int(archive))
        self.assertTrue((self.portable.PORTABLE / "bin/proteus-module-fixture").is_file())
        self.assertTrue((self.portable.PORTABLE / "share/extensions/fixture/bin/fixture").is_file())
        self.process.call.assert_not_called()
        self.process.check_output.assert_not_called()
        self.process.Popen.assert_not_called()

    def test_release_reuses_release_hosts_but_builds_packages(self):
        self.assert_reuse_hosts([], "release", "release", "release", True)

    def test_fast_reuses_fast_client_and_release_core_without_archive(self):
        self.assert_reuse_hosts(["--fast"], "release", "fast", "release", False)

    def test_debug_reuses_debug_hosts_and_builds_dev_modules(self):
        self.assert_reuse_hosts(["--debug"], "debug", "debug", "dev", True)

    def test_no_archive_does_not_change_release_profiles(self):
        self.assert_reuse_hosts(["--no-archive"], "release", "release", "release", False)

    def test_fast_with_no_archive_remains_valid(self):
        self.assert_reuse_hosts(["--fast", "--no-archive"], "release", "fast", "release", False)

    def test_relative_external_cache_uses_each_host_checkout(self):
        os.environ["CARGO_TARGET_DIR"] = "relative cache with spaces"
        agent = self.host(self.sources["harness"], "release", "proteus")
        client = self.host(self.native, "fast", "proteus-native")
        self.assertEqual(agent.parent.parent, self.sources["harness"] / os.environ["CARGO_TARGET_DIR"])
        self.assertEqual(client.parent.parent, self.native / os.environ["CARGO_TARGET_DIR"])
        self.assertNotEqual(agent.parent.parent, client.parent.parent)
        self.assert_reuse_hosts(["--fast"], "release", "fast", "release", False)
        self.assertEqual((self.portable.PORTABLE / "bin/proteus").read_bytes(), agent.read_bytes())
        self.assertEqual((self.portable.PORTABLE / "bin/proteus-native").read_bytes(), client.read_bytes())

    def test_absolute_external_cache_is_preserved(self):
        os.environ["CARGO_TARGET_DIR"] = str(self.base / "absolute cache")
        agent = self.host(self.sources["harness"], "release", "proteus")
        client = self.host(self.native, "fast", "proteus-native")
        self.assert_reuse_hosts(["--fast"], "release", "fast", "release", False)
        self.assertEqual((self.portable.PORTABLE / "bin/proteus").read_bytes(), agent.read_bytes())
        self.assertEqual((self.portable.PORTABLE / "bin/proteus-native").read_bytes(), client.read_bytes())

    def assert_missing_host(self, root, profile, name):
        self.host(root, profile, name).unlink()
        with patch.object(self.portable, "assemble", wraps=self.portable.assemble) as assemble:
            with self.assertRaisesRegex(SystemExit, "No existing binary to reuse"):
                self.invoke(["--fast", "--reuse-hosts"])
        assemble.assert_not_called()
        self.portable.build_binary.assert_not_called()
        self.process.run.assert_not_called()
        self.portable.archive.assert_not_called()
        self.portable.write_manifest.assert_not_called()
        self.assertFalse(self.portable.BUILD.exists())

    def test_missing_core_fails_before_any_assembly(self):
        self.assert_missing_host(self.sources["harness"], "release", "proteus")

    def test_missing_client_fails_before_any_assembly(self):
        self.assert_missing_host(self.native, "fast", "proteus-native")

    def test_reused_host_provenance_records_hashes_and_cannot_qualify_as_clean_release(self):
        self.invoke(["--fast", "--reuse-hosts"])
        portable = self.portable.PORTABLE
        record = json.loads((portable / "share/release-sources.json").read_text())
        self.assertEqual(record["build_mode"], "reuse-hosts")
        self.assertEqual(record["sources"], self.record["sources"])
        self.assertEqual(record["binary_sha256"], {
            path.name: hashlib.sha256(path.read_bytes()).hexdigest()
            for path in (portable / "bin").iterdir() if path.is_file()
        })
        self.assertEqual(set(record["binary_sha256"]),
                         {"proteus", "proteus-native", "proteus-module-fixture"})
        self.release.ROOT = self.native
        self.release.BUILD = self.portable.BUILD
        with patch.object(self.release, "check_sources", return_value=self.sources), \
             patch.object(self.release, "source_archive") as source_archive, \
             patch.object(self.release, "run") as release_run, \
             patch.object(self.release.shutil, "rmtree") as remove:
            with self.assertRaisesRegex(SystemExit, "provenance does not match"):
                self.release.assets()
        source_archive.assert_not_called()
        release_run.assert_not_called()
        remove.assert_not_called()
        self.assertFalse((self.portable.BUILD / "release").exists())

    def test_combined_reuse_flags_keep_existing_reuse_binaries_precedence(self):
        self.invoke(["--fast", "--reuse-hosts", "--reuse-binaries"])
        self.portable.build_binary.assert_not_called()
        self.portable.limit.assert_not_called()
        self.portable.archive.assert_not_called()
        self.assertEqual(self.process.run.call_count, 2)
        for call in self.process.run.call_args_list:
            self.assertEqual(call.args[0][-1], "--no-build")
        record = json.loads((self.portable.PORTABLE / "share/release-sources.json").read_text())
        self.assertEqual(record["build_mode"], "reuse-binaries")

    def test_fast_and_debug_still_conflict_before_side_effects(self):
        with self.assertRaises(SystemExit) as caught:
            self.invoke(["--reuse-hosts", "--fast", "--debug"])
        self.assertEqual(caught.exception.code, 2)
        self.portable.resolve.assert_not_called()
        self.portable.limit.assert_not_called()
        self.portable.existing_binary.assert_not_called()
        self.portable.build_binary.assert_not_called()
        self.process.run.assert_not_called()
        self.portable.archive.assert_not_called()


if __name__ == "__main__":
    unittest.main()
