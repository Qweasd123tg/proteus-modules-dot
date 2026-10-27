#!/usr/bin/env python3
"""Pure planner tests: synthetic text only, no Cargo, source fixture or subprocess."""
import importlib.util
import json
from pathlib import Path
import unittest

SPEC = importlib.util.spec_from_file_location(
    "extension_build_plan", Path(__file__).with_name("plan_extension_build.py"))
PLANNER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PLANNER)

FILES = {"package": "extension-files", "binary": "files", "folder": "packages/files"}
GIT = {"package": "extension-git", "binary": "git", "folder": "packages/git"}
CARGO = '[package]\nname = "extension-files"\n[[bin]]\nname = "files"\npath = "src/main.rs"\n'


class PlanTests(unittest.TestCase):
    def test_audited_workspace_is_accepted(self):
        for members in ('["sdk", "packages/*"]', '["packages/*", "sdk"]'):
            PLANNER.validate_workspace("[workspace]\nmembers = " + members + "\n")

    def test_missing_sdk_extra_duplicate_or_malformed_members_are_rejected(self):
        for members in ('["packages/*"]', '["sdk", "packages/*", "other"]',
                        '["packages/*", "packages/*"]', '"packages/*"',
                        '[1, "packages/*"]'):
            with self.subTest(members=members), self.assertRaises(ValueError):
                PLANNER.validate_workspace("[workspace]\nmembers = " + members + "\n")
        with self.assertRaises(ValueError):
            PLANNER.validate_workspace('[workspace]\nmembers=["sdk","packages/*"]\nexclude=["packages/files"]\n')
        with self.assertRaises(ValueError):
            PLANNER.validate_workspace('[package]\nname="not-a-workspace"\n')

    def test_one_package_does_not_select_workspace(self):
        plan = PLANNER.create_plan([FILES, GIT], package="extension-files")
        self.assertEqual(plan["expected_artifacts"], [FILES])
        self.assertNotIn("--workspace", plan["build_argv"])
        self.assertNotIn("--workspace", plan["test_argv"])
        self.assertEqual(plan["build_argv"][-4:], ["-p", "extension-files", "--bin", "files"])
        self.assertNotIn("--bin", plan["test_argv"])
        self.assertIn("extension-files", plan["test_argv"])
        self.assertFalse(plan["execution_performed"])
        self.assertEqual(plan["packaging"]["status"], "not-implemented")

    def test_full_workspace_keeps_sdk_test_scope(self):
        plan = PLANNER.create_plan([FILES, GIT], all_packages=True)
        self.assertEqual(plan["expected_artifacts"], [FILES, GIT])
        self.assertIn("--workspace", plan["build_argv"])
        self.assertIn("--workspace", plan["test_argv"])
        self.assertNotIn("--bins", plan["test_argv"])

    def test_profiles_remain_explicitly_distinct(self):
        plan = PLANNER.create_plan([FILES], package="extension-files")
        self.assertIn("--release", plan["build_argv"])
        self.assertNotIn("--release", plan["test_argv"])
        self.assertIn("--locked", plan["build_argv"])
        self.assertEqual(plan["test_argv"][-2:], ["--", "--test-threads=4"])

    def test_invalid_selection_is_rejected(self):
        for kwargs in ({}, {"package": "missing"},
                       {"package": "extension-files", "all_packages": True}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                PLANNER.create_plan([FILES], **kwargs)
        with self.assertRaises(ValueError):
            PLANNER.create_plan([FILES, FILES], package="extension-files")

    def test_manifest_target_matches_extension_command(self):
        result = PLANNER.parse_extension(CARGO, '{"command":["bin/files"]}', "packages/files")
        self.assertEqual(result, FILES)

    def test_unknown_or_non_binary_command_is_rejected(self):
        for command in (["bin/missing"], ["python3", "main.py"], ["../files"], []):
            with self.subTest(command=command), self.assertRaises(ValueError):
                PLANNER.parse_extension(CARGO, json.dumps({"command": command}), "packages/files")

    def test_duplicate_explicit_binary_is_rejected(self):
        duplicate = CARGO + '[[bin]]\nname = "files"\npath = "other.rs"\n'
        with self.assertRaises(ValueError):
            PLANNER.parse_extension(duplicate, '{"command":["bin/files"]}', "packages/files")


if __name__ == "__main__":
    unittest.main()
