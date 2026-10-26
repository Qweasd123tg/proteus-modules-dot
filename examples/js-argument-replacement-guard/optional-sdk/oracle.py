"""Authored exact-integer/type oracle, not a JavaScript or Core implementation."""
from strict_json import loads


def require(condition, message):
    if not condition:
        raise ValueError(message)


def value_args(text):
    args = loads(text)
    require(type(args) is dict and set(args) == {"value"}, "fixture args shape")
    require(type(args["value"]) in (int, str), "fixture value must be exact int or string")
    return args


def payload_request(case, cwd):
    return {
        "jsonrpc": "2.0", "id": case["wire_id"], "method": "hook.invoke",
        "params": {
            "export": {"slot": "hook", "module_id": "argument.guard." + case["mode"]},
            "lineage": {"root_invocation_id": case["wire_id"], "parent_invocation_id": None, "depth": 0},
            "params": {
                "event": {"event": "before_tool", "call": {
                    "id": "guard-call", "name": "guard_fixture", "args": value_args(case["input_args_json"]),
                    "surface": "function", "raw_arguments": None}, "spec": None, "blocked": None},
                "attribution": {"execution_id": "00000000-0000-4000-8000-000000000001", "agent": None},
                "cwd": cwd, "conversation": None,
            },
        },
    }


def check_pure(raw, names):
    result = loads(raw.decode("utf-8"))
    require(type(result) is dict and set(result) == {"schema_version", "status", "controls"}, "pure result shape")
    require(type(result["schema_version"]) is int and result["schema_version"] == 1, "pure schema type/version")
    require(result["status"] == "passed", "pure controls did not pass")
    require(type(result["controls"]) is list and result["controls"] == names
            and len(names) == 38 and len(set(names)) == 38, "exact 38 pure controls required")
    return result


def check_initialize(raw, corpus):
    expected = {"jsonrpc": "2.0", "id": "h:7:0", "result": {
        "protocol_version": "v3", "component_id": "authored.argument-guard",
        "exports": [{"slot": "hook", "module_id": row["module_id"], "contract_version": "v6",
                     "composition": "ordered_many", "module_features": [], "config_schema": None}
                    for row in corpus["exports"]]}}
    require(loads(raw.decode("utf-8")) == expected, "exact initialize/export response mismatch")


def check_response(case, sent, received):
    request = loads(sent.decode("utf-8"))
    original = value_args(case["input_args_json"])["value"]
    actual_input = request["params"]["params"]["event"]["call"]["args"]["value"]
    require(type(actual_input) is type(original) and actual_input == original, "original request exact value/type changed")
    require(request["id"] == case["wire_id"], "request ID mismatch")
    frame = loads(received.decode("utf-8"))
    kind = case["expected_kind"]
    terminal = "error" if kind == "error" else "result"
    require(type(frame) is dict and set(frame) == {"jsonrpc", "id", terminal}, "unexpected terminal envelope or callback")
    require(frame["jsonrpc"] == "2.0" and frame["id"] == case["wire_id"], "response version/ID mismatch")
    row = {"name": case["name"], "mode": case["mode"], "input_type": type(original).__name__,
           "input_exact": str(original), "outcome": kind}
    if kind == "error":
        error = frame["error"]
        require(type(error) is dict and set(error) == {"code", "message"}, "ordinary error must omit data and extra fields")
        require(type(error["code"]) is int and error["code"] == -32000, "wrong error code")
        require(error["message"] == "argument replacement refused: unsafe_integer", "wrong refusal diagnostic")
        require(case["expected_error_code"] == -32000
                and case["expected_error_message"] == error["message"]
                and case["expected_error_data_present"] is False, "unexpected error case declaration")
        row["error"] = error
        return row
    result = frame["result"]
    require(type(result) is dict and set(result) == {"result"}, "invalid ProcessHookResponse")
    result = result["result"]
    if kind == "continue":
        require(result == {"action": "continue"}, "Continue must have no replacement")
        return row
    require(kind == "tool_arguments" and type(result) is dict
            and set(result) == {"action", "args"} and result["action"] == "tool_arguments", "expected argument replacement")
    require(type(result["args"]) is dict and set(result["args"]) == {"value"}, "replacement args shape")
    actual = result["args"]["value"]
    expected = value_args(case["expected_args_json"])["value"]
    require(type(actual) is type(expected) and actual == expected, "replacement exact value/type mismatch")
    row.update(output_type=type(actual).__name__, output_exact=str(actual),
               explicit_limitation=case["mode"] in ("computed_safe", "unguarded_later"))
    return row
