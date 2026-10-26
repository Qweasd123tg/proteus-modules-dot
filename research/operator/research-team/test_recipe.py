"""Authored pure/static controls; no Core, module worker, model or child process."""
import copy
from pathlib import Path
import unittest
from unittest.mock import patch

from check_recipe import FILES, RecipeError, check, load_owned, merge_owned, same

ROOT = Path(__file__).resolve().parent


class RecipeControls(unittest.TestCase):
    def setUp(self):
        self.bundle = load_owned(ROOT)
        self.assertFalse(check(self.bundle)["runtime_validated"])

    def rejects(self, code, mutate):
        changed = copy.deepcopy(self.bundle)
        mutate(changed)
        with self.assertRaisesRegex(RecipeError, "^" + code.replace(".", r"\.") + "$"):
            check(changed)

    def test_baseline_is_explicitly_static(self):
        self.assertEqual(check(self.bundle), {"scope": "static_owned_fixture_checks_only", "profiles": 3, "role_capacities": [2, 1], "argument_examples": 11, "provider_include_resolved": False, "core_loaded": False, "agents_started": 0, "runtime_validated": False})

    def test_loader_reads_only_five_owned_leaves(self):
        seen = []
        original = Path.read_text
        def observed(path, *args, **kwargs):
            seen.append(path.relative_to(ROOT).as_posix())
            return original(path, *args, **kwargs)
        with patch.object(Path, "read_text", observed):
            load_owned(ROOT)
        self.assertEqual(seen, list(FILES.values()) + ["call-examples.json"])
        self.assertNotIn("configs/fragments/operator-provider.toml", seen)

    def test_unknown_shared_field(self):
        self.rejects("shared.fields", lambda b: b["shared"].update({"commands": {}}))

    def test_added_hook(self):
        self.rejects("shared.modules", lambda b: b["shared"]["modules"].update({"hooks": ["unreviewed"]}))

    def test_extra_component_export(self):
        self.rejects("shared.components", lambda b: b["shared"]["components"]["research-files"]["exports"].update({"hook": {"extra": {}}}))

    def test_write_tool_added(self):
        self.rejects("shared.tools", lambda b: b["shared"]["tools"]["enabled"].append("write_file"))

    def test_mcp_added(self):
        self.rejects("shared.tools", lambda b: b["shared"]["tools"]["mcp_servers"].append({"name": "extra"}))

    def test_plugin_added(self):
        self.rejects("shared.addons", lambda b: b["shared"]["addons"]["plugins"].append({"path": "extra"}))

    def test_child_roles_retained(self):
        self.rejects("shared.child_control", lambda b: b["shared"]["agent_control"]["roles"].append({"name": "nested"}))

    def test_permission_mode_changed(self):
        self.rejects("shared.permissions", lambda b: b["shared"]["permissions"].update({"mode": "allow_all"}))

    def test_context_provider_added(self):
        self.rejects("shared.module_config", lambda b: b["shared"]["module_config"]["context"]["codex_context"]["providers"].append("project_instructions"))

    def test_collaboration_name_in_ordinary_tools(self):
        self.rejects("parent.tools", lambda b: b["parent"]["tools"]["enabled"].append("spawn_agent"))

    def test_child_extra_cli_arguments(self):
        self.rejects("parent.role_fields", lambda b: b["parent"]["agent_control"]["roles"][0].update({"args": ["--allow-all"]}))

    def test_explicit_none_is_not_config_isolation_value(self):
        self.rejects("parent.role_fields", lambda b: b["parent"]["agent_control"]["roles"][0].update({"isolation": "none"}))

    def test_boolean_is_not_integer_limit(self):
        self.rejects("parent.limits", lambda b: b["parent"]["agent_control"].update({"max_depth": True}))

    def test_wrong_child_config_binding(self):
        self.rejects("parent.role_binding", lambda b: b["parent"]["agent_control"]["roles"][1].update({"config": "research-reader"}))

    def test_parent_spawn_autoapproval(self):
        self.rejects("parent.policy", lambda b: b["parent"]["module_config"]["policy"]["codex_policy"]["allow"].append("spawn_agent"))

    def test_duplicate_child_task(self):
        self.rejects("spawn.task", lambda b: b["calls"]["calls"][1]["args"].update({"task_name": "reader_a"}))

    def test_reader_task_cannot_select_verifier_role(self):
        self.rejects("spawn.recipe_role_binding", lambda b: b["calls"]["calls"][0]["args"].update({"agent_type": "source_verifier"}))

    def test_wait_boolean_timeout(self):
        self.rejects("wait.args", lambda b: b["calls"]["calls"][2]["args"].update({"timeout_ms": True}))

    def test_spawn_unknown_argument(self):
        self.rejects("spawn.fields", lambda b: b["calls"]["calls"][0]["args"].update({"fork_turns": "all"}))

    def test_read_path_not_in_recipe(self):
        self.rejects("read.recipe_path", lambda b: b["calls"]["calls"][8]["args"].update({"path": "../private"}))

    def test_unsupported_call_name(self):
        self.rejects("call.unsupported", lambda b: b["calls"]["calls"][2].update({"tool": "unrecognized"}))

    def test_owned_array_merge_replaces_not_appends(self):
        self.assertEqual(merge_owned({"roles": [1, 2], "nested": {"a": 1}}, {"roles": [], "nested": {"b": 2}}), {"roles": [], "nested": {"a": 1, "b": 2}})

    def test_recursive_comparison_preserves_types(self):
        self.assertFalse(same({"x": [True]}, {"x": [1]}))
        self.assertFalse(same({"x": [1.0]}, {"x": [1]}))
        self.assertTrue(same({"x": [1]}, {"x": [1]}))

    def test_child_override_cannot_add_control_fields(self):
        self.rejects("reader.fields", lambda b: b["reader"].update({"agent_control": {"surface": "collaboration"}}))

    def test_include_order_is_fixed_not_resolved(self):
        self.rejects("verifier.include", lambda b: b["verifier"]["include"].reverse())

    def test_followup_byte_limit_not_character_limit(self):
        self.rejects("followup.message", lambda b: b["calls"]["calls"][7]["args"].update({"message": "я" * 8001}))

    def test_missing_manual_gate(self):
        self.rejects("call.gate", lambda b: b["calls"]["calls"][4].update({"gate": ""}))


if __name__ == "__main__":
    unittest.main(verbosity=2)
