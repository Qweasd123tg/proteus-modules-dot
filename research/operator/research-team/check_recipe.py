"""Check only this authored recipe scaffold. Never follow TOML includes or run Core.

This is NOT a general Proteus config validator, policy evaluator or deployment gate.
The provider include is intentionally unresolved. No module/provider is imported.
"""
import copy
import json
from pathlib import Path
import re
import tomllib

FILES = {
    "shared": "configs/fragments/research-runtime.toml",
    "parent": "configs/research-parent.config.toml",
    "reader": "configs/research-reader.config.toml",
    "verifier": "configs/research-verifier.config.toml",
}
INCLUDES = ["fragments/operator-provider.toml", "fragments/research-runtime.toml"]
PIN = "1fc3ef223d10322815dd9290a50d045bc95402bb"
SOURCES = {
    "crates/proteus-core/src/core/agent_control/process/child.rs",
    "crates/proteus-core/src/core/agent_control/collaboration/mod.rs",
}
DENY = ["shell", "exec_command", "write_stdin", "write_file", "apply_patch", "request_permissions"]


class RecipeError(ValueError):
    pass


def require(ok, code):
    if not ok:
        raise RecipeError(code)


def same(actual, expected):
    """Recursive type-aware comparison: True is not 1 and 1.0 is not 1."""
    if type(actual) is not type(expected):
        return False
    if isinstance(expected, dict):
        return actual.keys() == expected.keys() and all(same(actual[k], v) for k, v in expected.items())
    if isinstance(expected, list):
        return len(actual) == len(expected) and all(same(a, b) for a, b in zip(actual, expected))
    return actual == expected


def merge_owned(base, overlay):
    """The selected Core object's recursive-map/replace-other rule, for owned data only."""
    if isinstance(base, dict) and isinstance(overlay, dict):
        result = copy.deepcopy(base)
        for key, value in overlay.items():
            result[key] = merge_owned(result.get(key), value)
        return result
    return copy.deepcopy(overlay)


def load_owned(root):
    # Fixed leaf reads only. In particular, do not resolve/read any include path.
    result = {key: tomllib.loads((root / path).read_text(encoding="utf-8")) for key, path in FILES.items()}
    result["calls"] = json.loads((root / "call-examples.json").read_text(encoding="utf-8"))
    return result


def check(bundle):
    shared = bundle["shared"]
    require(set(shared) == {"modules", "components", "tools", "addons", "agent_control", "permissions", "module_config", "app_server", "runtime"}, "shared.fields")
    require(same(shared["modules"], {"hooks": [], "workflow": "coding.codex_loop", "context": "codex_context", "policy": "codex_policy"}), "shared.modules")
    expected_components = {}
    for name, slot, export in [("workflow", "workflow", "coding.codex_loop"), ("context", "context", "codex_context"), ("policy", "policy", "codex_policy"), ("files", "tool", "file_tools")]:
        expected_components["research-" + name] = {"command": "proteus-reference-module", "exports": {slot: {export: {}}}}
    require(same(shared["components"], expected_components), "shared.components")
    require(same(shared["tools"], {"enabled": ["read_file"], "mcp_servers": []}), "shared.tools")
    require(same(shared["addons"], {"plugins": []}), "shared.addons")
    require(same(shared["agent_control"], {"surface": "none", "roles": []}), "shared.child_control")
    require(same(shared["permissions"], {"mode": "normal"}), "shared.permissions")
    require(same(shared["module_config"], {
        "policy": {"codex_policy": {"allow": ["read_file"], "ask_before": [], "deny": DENY, "allow_sandboxed": []}},
        "context": {"codex_context": {"providers": [], "max_context_bytes": 16000, "max_bytes_per_file": 8000, "project_doc_max_bytes": 8000}},
        "workflow": {"coding.codex_loop": {"stream_max_retries": 0}},
    }), "shared.module_config")
    require(same(shared["app_server"], {"approval_timeout_ms": 60000}), "shared.approval")
    require(same(shared["runtime"], {"model_timeout_ms": 60000, "context_timeout_ms": 5000, "workflow_timeout_ms": 180000}), "shared.runtime")

    partial_profiles = {}
    for name in ["parent", "reader", "verifier"]:
        profile = bundle[name]
        allowed = {"include", "profile", "instructions"}
        if name == "parent":
            allowed |= {"tools", "agent_control", "module_config", "runtime"}
        require(set(profile) == allowed, name + ".fields")
        require(same(profile["include"], INCLUDES), name + ".include")
        require(same(profile["profile"], {"name": "research-" + name}), name + ".profile")
        instructions = profile["instructions"]
        require(isinstance(instructions, list) and len(instructions) == 1, name + ".instructions")
        instruction = instructions[0]
        require(isinstance(instruction, dict) and set(instruction) == {"kind", "text", "priority"}, name + ".instructions")
        require(same(instruction["kind"], "System") and same(instruction["priority"], 100) and type(instruction["text"]) is str and 1 <= len(instruction["text"].encode()) <= 4000, name + ".instructions")
        partial_profiles[name] = merge_owned(shared, {k: v for k, v in profile.items() if k != "include"})

    parent = bundle["parent"]
    require(same(parent["tools"], {"enabled": []}), "parent.tools")
    control = parent["agent_control"]
    require(set(control) == {"surface", "max_depth", "max_parallel", "max_idle_processes", "cancel_grace_ms", "roles"}, "parent.control_fields")
    require(same({k: v for k, v in control.items() if k != "roles"}, {"surface": "collaboration", "max_depth": 1, "max_parallel": 3, "max_idle_processes": 3, "cancel_grace_ms": 5000}), "parent.limits")
    roles = control["roles"]
    require(isinstance(roles, list) and len(roles) == 2, "parent.roles")
    for role, name, count in zip(roles, ["reader", "verifier"], [2, 1]):
        require(isinstance(role, dict) and set(role) == {"name", "description", "config", "parallel_safe", "max_processes", "timeout_ms", "max_summary_bytes"}, "parent.role_fields")
        require(type(role["description"]) is str and 1 <= len(role["description"].encode()) <= 1000, "parent.role_description")
        require(same({k: v for k, v in role.items() if k != "description"}, {"name": "source_" + name, "config": "research-" + name, "parallel_safe": True, "max_processes": count, "timeout_ms": 120000, "max_summary_bytes": 12000}), "parent.role_binding")
    require(same(parent["module_config"], {"policy": {"codex_policy": {"allow": ["list_agents", "wait_agent", "interrupt_agent"], "ask_before": ["spawn_agent", "send_message", "followup_task"], "deny": ["read_file"] + DENY, "allow_sandboxed": []}}}), "parent.policy")
    require(same(parent["runtime"], {"workflow_timeout_ms": 600000}), "parent.runtime")
    for name in ["reader", "verifier"]:
        require(same(partial_profiles[name]["agent_control"], {"surface": "none", "roles": []}), "partial.child_control")

    doc = bundle["calls"]
    require(set(doc) == {"scope", "core_pin", "calls"} and doc["core_pin"] == PIN, "calls.envelope")
    require(type(doc["scope"]) is str and "not a workflow engine" in doc["scope"], "calls.scope")
    require(isinstance(doc["calls"], list) and len(doc["calls"]) == 11, "calls.count")
    ids, tasks = set(), set()
    for call in doc["calls"]:
        require(isinstance(call, dict) and set(call) == {"id", "owner", "gate", "tool", "args"}, "call.fields")
        require(type(call["id"]) is str and call["id"] not in ids, "call.id")
        ids.add(call["id"])
        require(type(call["gate"]) is str and bool(call["gate"].strip()), "call.gate")
        tool, args = call["tool"], call["args"]
        require(isinstance(args, dict), "call.args")
        require(call["owner"] == ("child" if tool == "read_file" else "parent"), "call.owner")
        if tool == "spawn_agent":
            require(set(args) == {"task_name", "message", "agent_type"}, "spawn.fields")
            task = args["task_name"]
            require(type(task) is str and re.fullmatch(r"[a-z0-9_]{1,64}", task) is not None and task not in tasks, "spawn.task")
            tasks.add(task)
            require(args["agent_type"] in ["source_reader", "source_verifier"], "spawn.role")
            expected_role = {"reader_a": "source_reader", "reader_b": "source_reader", "verifier": "source_verifier"}.get(task)
            require(args["agent_type"] == expected_role, "spawn.recipe_role_binding")
            require(type(args["message"]) is str and 1 <= len(args["message"].encode()) <= 16000, "spawn.message_recipe_cap")
        elif tool == "wait_agent":
            require(set(args) == {"timeout_ms"} and type(args["timeout_ms"]) is int and 0 <= args["timeout_ms"] <= 300000, "wait.args")
        elif tool == "list_agents":
            require(same(args, {"path_prefix": "/root"}), "list.args")
        elif tool in ["interrupt_agent", "followup_task"]:
            require(set(args) == ({"target"} if tool == "interrupt_agent" else {"target", "message"}), "target.fields")
            require(args["target"] == "/root/verifier", "target.path")
            if tool == "followup_task":
                require(type(args["message"]) is str and 1 <= len(args["message"].encode()) <= 16000, "followup.message")
        elif tool == "read_file":
            require(set(args) == {"path", "start_line", "limit", "line_numbers"}, "read.fields")
            require(args["path"] in SOURCES, "read.recipe_path")
            require(type(args["start_line"]) is int and args["start_line"] > 0 and type(args["limit"]) is int and args["limit"] > 0 and args["line_numbers"] is True, "read.range")
        else:
            raise RecipeError("call.unsupported")
    require(tasks == {"reader_a", "reader_b", "verifier"}, "calls.task_set")
    return {"scope": "static_owned_fixture_checks_only", "profiles": 3, "role_capacities": [2, 1], "argument_examples": 11, "provider_include_resolved": False, "core_loaded": False, "agents_started": 0, "runtime_validated": False}


if __name__ == "__main__":
    print(json.dumps(check(load_owned(Path(__file__).resolve().parent)), sort_keys=True))
