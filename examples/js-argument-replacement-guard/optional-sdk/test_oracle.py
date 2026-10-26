"""Authored synthetic Python controls; no Node, SDK or subprocess invocation."""
import sys
sys.dont_write_bytecode = True
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import copy
import json
import unittest
from oracle import check_response, check_pure, check_initialize, payload_request
from strict_json import loads

PACKAGE = Path(__file__).resolve().parent.parent
CORPUS = loads((PACKAGE / "SDK_CASE_PROPOSAL.json").read_text())
CASES = CORPUS["cases"]
NAMES = loads((PACKAGE / "CONTROL_INVENTORY.json").read_text())["required_controls"]


def raw(value):
    return (json.dumps(value, separators=(",", ":"), allow_nan=False) + "\n").encode()


def terminal(case):
    frame = {"jsonrpc": "2.0", "id": case["wire_id"]}
    if case["expected_kind"] == "error":
        frame["error"] = {"code": -32000, "message": "argument replacement refused: unsafe_integer"}
    else:
        result = {"action": case["expected_kind"]}
        if case["expected_kind"] == "tool_arguments":
            result["args"] = loads(case["expected_args_json"])
        frame["result"] = {"result": result}
    return frame


def checked(case, response=None, request=None):
    return check_response(case, raw(request if request is not None else payload_request(case, "/owned")),
                          raw(response if response is not None else terminal(case)))


def pure():
    return {"schema_version": 1, "status": "passed", "controls": list(NAMES)}


class OracleTests(unittest.TestCase):
    def test_all_thirteen_authored_expected_terminals(self):
        self.assertEqual(len(CASES), 13)
        for case in CASES:
            self.assertEqual(checked(case)["name"], case["name"])

    def test_original_unsafe_request_must_be_exact(self):
        case = CASES[5]
        request = payload_request(case, "/owned")
        request["params"]["params"]["event"]["call"]["args"]["value"] = 9007199254740992
        with self.assertRaisesRegex(ValueError, "original request exact"):
            checked(case, request=request)

    def test_wrong_error_classification_rejected(self):
        frame = terminal(CASES[1]); frame["error"]["code"] = -32602
        with self.assertRaisesRegex(ValueError, "wrong error code"):
            checked(CASES[1], frame)

    def test_wrong_refusal_reason_rejected(self):
        frame = terminal(CASES[1]); frame["error"]["message"] = "argument replacement refused: budget_nodes"
        with self.assertRaisesRegex(ValueError, "wrong refusal diagnostic"):
            checked(CASES[1], frame)

    def test_even_null_error_data_rejected(self):
        frame = terminal(CASES[1]); frame["error"]["data"] = None
        with self.assertRaisesRegex(ValueError, "omit data"):
            checked(CASES[1], frame)

    def test_refusal_does_not_satisfy_safe_recovery(self):
        frame = terminal(CASES[1]); frame["id"] = CASES[2]["wire_id"]
        with self.assertRaisesRegex(ValueError, "terminal envelope"):
            checked(CASES[2], frame)

    def test_numeric_and_string_data_not_interchangeable(self):
        frame = terminal(CASES[7]); frame["result"]["result"]["args"]["value"] = 9007199254740993
        with self.assertRaisesRegex(ValueError, "value/type mismatch"):
            checked(CASES[7], frame)

    def test_boolean_cannot_satisfy_zero_limitation(self):
        frame = terminal(CASES[11]); frame["result"]["result"]["args"]["value"] = False
        with self.assertRaisesRegex(ValueError, "value/type mismatch"):
            checked(CASES[11], frame)

    def test_wrong_wire_id_rejected(self):
        frame = terminal(CASES[0]); frame["id"] = "h:7:99"
        with self.assertRaisesRegex(ValueError, "version/ID"):
            checked(CASES[0], frame)

    def test_unsolicited_callback_rejected(self):
        frame = {"jsonrpc": "2.0", "id": "m:7:1", "method": "host.tools.execute", "params": {}}
        with self.assertRaisesRegex(ValueError, "terminal envelope"):
            checked(CASES[0], frame)

    def test_continue_cannot_contain_replacement(self):
        frame = terminal(CASES[9]); frame["result"]["result"]["args"] = {"value": 0}
        with self.assertRaisesRegex(ValueError, "no replacement"):
            checked(CASES[9], frame)

    def test_declared_limit_cases_require_exact_observed_values(self):
        for case in CASES[11:13]:
            frame = terminal(case); frame["result"]["result"]["args"]["value"] = 1
            with self.assertRaisesRegex(ValueError, "value/type mismatch"):
                checked(case, frame)

    def test_pure_exact_inventory_accepts(self):
        self.assertEqual(check_pure(raw(pure()), NAMES)["controls"], NAMES)

    def test_pure_schema_bool_and_float_rejected(self):
        value = pure(); value["schema_version"] = True
        with self.assertRaisesRegex(ValueError, "schema type"):
            check_pure(raw(value), NAMES)
        value["schema_version"] = 1.0
        with self.assertRaisesRegex(ValueError, "non-integer"):
            check_pure(raw(value), NAMES)

    def test_pure_missing_duplicate_and_reordered_cases_rejected(self):
        mutations = [NAMES[:-1], NAMES[:-1] + [NAMES[0]], list(reversed(NAMES))]
        for names in mutations:
            value = pure(); value["controls"] = names
            with self.assertRaisesRegex(ValueError, "exact 38"):
                check_pure(raw(value), NAMES)

    def test_pure_failure_and_extra_fields_rejected(self):
        value = pure(); value["status"] = "failed"
        with self.assertRaisesRegex(ValueError, "did not pass"):
            check_pure(raw(value), NAMES)
        value = pure(); value["ignored"] = 0
        with self.assertRaisesRegex(ValueError, "shape"):
            check_pure(raw(value), NAMES)

    def test_duplicate_float_and_nonfinite_json_rejected(self):
        for text in ['{"x":1,"x":2}', '{"x":1.0}', '{"x":NaN}', '{"x":1e999}']:
            with self.assertRaises(ValueError):
                loads(text)

    def test_initialize_exact_exports_and_null_shape(self):
        frame = {"jsonrpc": "2.0", "id": "h:7:0", "result": {
            "protocol_version": "v3", "component_id": "authored.argument-guard", "exports": [
                {"slot": "hook", "module_id": row["module_id"], "contract_version": "v6",
                 "composition": "ordered_many", "module_features": [], "config_schema": None}
                for row in CORPUS["exports"]]}}
        check_initialize(raw(frame), CORPUS)
        del frame["result"]["exports"][0]["config_schema"]
        with self.assertRaisesRegex(ValueError, "initialize/export"):
            check_initialize(raw(frame), CORPUS)


if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(OracleTests)
    if suite.countTestCases() != 18:
        raise SystemExit("wrong authored oracle-control inventory")
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    raise SystemExit(0 if result.wasSuccessful() and result.testsRun == 18 and not result.skipped else 1)
