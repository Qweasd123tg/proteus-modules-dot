#!/usr/bin/env python3
"""Probe an already-built module; performs no compilation or installation."""
import argparse
import json
from pathlib import Path
import subprocess
import tempfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--module", type=Path, required=True)
    parser.add_argument("--conformance", type=Path, required=True)
    args = parser.parse_args()
    module = args.module.resolve(strict=True)
    conformance = args.conformance.resolve(strict=True)
    binding = {
        "slot": "tool", "module_id": "planning.ready_steps",
        "contract_version": "v6", "module_config": {},
    }

    def probe(method, params, *, expected_error=None, export=None, return_report=False):
        export = binding if export is None else export
        target = f"{export['slot']}/{export['module_id']}"
        result = subprocess.run([
            str(conformance), "--component-id", "ready-steps-smoke",
            "--export", json.dumps(export), "--probe-export", target,
            "--probe-method", method, "--probe-params", json.dumps(params), "--", str(module),
        ], capture_output=True, text=True, timeout=20)
        if expected_error is not None:
            assert result.returncode == 1, (result.returncode, result.stdout, result.stderr)
            for fragment in expected_error:
                assert fragment in result.stderr, (fragment, result.stdout, result.stderr)
            return None
        assert result.returncode == 0, result.stderr
        report = json.loads(result.stdout)
        assert report["handshake"] == "success", report
        assert report["probe"]["terminal"] == "success", report
        return report if return_report else report["probe"]["result"]["result"]

    list_report = probe("list", None, return_report=True)
    definitions = list_report["probe"]["result"]["result"]
    assert len(definitions) == 1
    assert definitions[0]["spec"]["name"] == "planning.ready_steps"

    def rejected_initialize(export, expected_diagnostic):
        # The host drains worker stderr. Also inspect the direct wire initialize so
        # an unrelated startup failure cannot satisfy an expected factory rejection.
        authority = list_report["exports"][0]
        request = {
            "jsonrpc": "2.0", "id": "h:1:0", "method": "initialize",
            "params": {
                "protocol_version": "v3", "component_id": "ready-steps-smoke",
                "exports": [{**export, "composition": authority["composition"],
                             "host_features": authority["host_features"]}],
            },
        }
        result = subprocess.run([str(module)], input=json.dumps(request) + "\n",
                                capture_output=True, text=True, timeout=10)
        assert result.returncode == 1, (result.returncode, result.stdout, result.stderr)
        assert not result.stdout.strip(), ("unexpected initialize response", result.stdout)
        assert expected_diagnostic in result.stderr, (expected_diagnostic, result.stderr)
        probe("list", None, export=export,
              expected_error=("component-v3 initialize request failed",))

    plan = {
        "nodes": [
            {"id": "first", "dependencies": [], "status": "succeeded"},
            {"id": "next", "dependencies": ["first"], "status": "pending"},
        ], "failure_policy": "all_settled",
    }
    with tempfile.TemporaryDirectory(prefix="ready-steps-") as cwd:
        invocation = {
            "call": {"id": "ready-smoke", "name": "planning.ready_steps", "args": plan,
                     "surface": "function", "raw_arguments": None},
            "cwd": cwd,
            "attribution": {"execution_id": "00000000-0000-4000-8000-000000000001", "agent": None},
            "skills": {"disabled": [], "packages": []},
        }
        result = probe("invoke", invocation)
        assert result["ok"] and result["call_id"] == "ready-smoke", result
        output = json.loads(result["output"])
        assert output["ready"] == ["next"] and output["advisory_only"] is True
        assert output["status_source"] == "caller_supplied_unverified"
        invocation["call"]["args"] = {
            "nodes": [{"id": "a", "dependencies": ["missing"], "status": "pending"}],
            "failure_policy": "all_settled",
        }
        invalid_graph = probe("invoke", invocation)
        assert invalid_graph["ok"] is False and invalid_graph["call_id"] == "ready-smoke"
        assert "references missing dependency missing" in json.dumps(invalid_graph), invalid_graph
        # The wire adapter must use raw provider arguments, not the conflicting parsed field.
        invocation["call"]["raw_arguments"] = json.dumps(plan)
        assert probe("invoke", invocation)["ok"] is True
        invocation["call"]["raw_arguments"] = None
        invocation["call"]["args"] = {"nodes": [], "failure_policy": "invented"}
        probe("invoke", invocation, expected_error=(
            "conformance probe returned a module error",
            "arguments violate schema at '/failure_policy'",
        ))
    rejected_initialize({**binding, "module_id": "wrong"}, "unsupported export tool/wrong")
    rejected_initialize({**binding, "module_config": {"execute": True}}, "unknown field `execute`")
    print("planning.ready_steps protocol smoke passed")


if __name__ == "__main__":
    main()
