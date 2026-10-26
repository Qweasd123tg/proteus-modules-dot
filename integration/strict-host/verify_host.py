#!/usr/bin/env python3
"""Exact authored host scenario gate. Never launches Core or rewrites evidence."""
import argparse
import hashlib
import json
import math
from pathlib import Path

CASES = ("matching", "wrong_suite", "wrong_config", "missing_assertion", "omitted", "read_denied", "approval_denied", "default_deny")
KEY = "proteus.example.verification"
ERROR = "verification evidence remains missing after 1 continuation attempts; completion is not accepted (the tool's checks were not proved)"
WRITE, VERIFY = "strict-write", "strict-verify"

def require(condition, message):
    if not condition:
        raise ValueError(message)

def same(a, b):
    if type(a) is not type(b):
        return False
    if isinstance(a, dict):
        return a.keys() == b.keys() and all(same(a[k], b[k]) for k in a)
    if isinstance(a, list):
        return len(a) == len(b) and all(same(x, y) for x, y in zip(a, b))
    return a == b

def load(path):
    require(path.is_file() and not path.is_symlink() and path.stat().st_size <= 8 * 1024 * 1024, "missing/unsafe/oversized evidence file")
    def unique(pairs):
        value = {}
        for key, item in pairs:
            require(key not in value, "duplicate JSON key: " + key)
            value[key] = item
        return value
    def nonfinite(value):
        raise ValueError("nonfinite JSON number: " + value)
    def finite_float(value):
        parsed = float(value)
        require(math.isfinite(parsed), "nonfinite JSON number: " + value)
        return parsed
    return json.loads(path.read_text(), object_pairs_hook=unique, parse_constant=nonfinite, parse_float=finite_float)

def one(values, message):
    require(len(values) == 1, message)
    return values[0]

def history_results(history):
    found = []
    for message in history:
        for part in message["parts"]:
            if "ToolResult" in part["payload"]:
                require(message["role"] == "Tool" and part["provenance"] == "tool" and part["scope"] == "conversation", "noncanonical tool-result provenance")
                found.append(part["payload"]["ToolResult"]["result"])
    return found

def verify(case_dir, package):
    report = load(case_dir / "report.json")
    case = report["scenario"]
    require(case in CASES and case_dir.name == case, "scenario identity mismatch")
    cwd = Path(report["cwd"])
    # Artifact transport may relocate the directory. Original absolute strings
    # are compared internally; local file read uses only this owned artifact leaf.
    require(cwd.is_absolute() and cwd.name == "workspace", "invalid recorded workspace")
    content = (package / "fixtures/release.json").read_bytes()
    require(len(content) == 152, "fixture content length changed")
    fixture = case_dir / "workspace/fixtures/release.json"
    expected_file = case not in ("approval_denied", "default_deny")
    require(fixture.exists() is expected_file, "actual write/denial filesystem oracle mismatch")
    if expected_file:
        require(not fixture.is_symlink() and fixture.read_bytes() == content, "actual fixture content mismatch")
    if case == "default_deny":
        require(report["scope"] == "direct_admission_not_turn", "default-deny mislabeled full turn")
        facts = report["facts"]
        require(facts["approvals"] == [], "default deny requested approval")
        result = facts["result"]
        reason = "policy deny_all rejects tool 'write_file'"
        require(result["call_id"] == WRITE and result["ok"] is False and result["error"] == reason, "default-deny result diagnostic mismatch")
        records = facts["records"]
        require([r["phase"] for r in records] == ["requested", "resolved", "result"], "default-deny recorder lifecycle mismatch")
        require(records[1]["resolution"] == {"decision":"policy_denied", "reason":reason}, "default-deny exact resolution mismatch")
        expected_call = {"id":WRITE,"name":"write_file","args":{"path":"fixtures/release.json","content":content.decode()},"surface":"function","raw_arguments":None}
        require(same(records[0]["call"], expected_call) and same(records[1]["call"], expected_call), "default-deny recorded exact call mismatch")
        require(same(records[2]["result"], result), "default-deny recorded final result mismatch")
        execution = records[0]["attribution"]["execution_id"]
        require(type(execution) is str and bool(execution) and all(r["attribution"]["execution_id"] == execution for r in records), "default-deny detached execution mismatch")
        require(all(r["attribution"]["agent"] is None for r in records), "direct admission invented chat attribution")
        return {"scenario":case,"status":"passed","scope":report["scope"]}
    require(report["scope"] == "actual_agent_runtime_turn", "full-turn scope mismatch")
    config = load(case_dir / "config.json")
    compiled = load(package / "fixtures/expected-policy.json")
    require(same(report["original_compiled_policy"], compiled), "compiled expected policy differs from reviewed fixture")
    require(same(config["module_config"]["tool"]["verification.json_contracts"], load(package / "fixtures/suite.json")), "producer suite changed")
    effective = json.loads(json.dumps(compiled))
    if case == "wrong_suite": effective["expected"]["expected_suite_id"] = "different-suite"
    if case == "wrong_config": effective["expected"]["expected_config_sha256"] = "0" * 64
    if case == "missing_assertion": effective["expected"]["documents"][0]["assertions"].append({"assertion_id":"extra-required","pointer":"/extra"})
    require(same(report["effective_gate_policy"], effective) and same(config["module_config"]["hook"]["hermes.verify_evidence"]["receipt_policy"], effective), "targeted gate policy mutation mismatch")
    records = load(case_dir / "records.json")
    history = load(case_dir / "history.json")
    projection = load(case_dir / "projection.json")
    require(same(projection["history"], history), "runtime history differs from durable projection")
    for name in ("interrupted_turns","interrupted_model_exchanges","interrupted_context_builds","unresolved_tool_calls","unsettled_turns"):
        require(projection[name] == [], "unsettled/interrupted journal: " + name)
    require(all(type(r["session_seq"]) is int for r in records) and [r["session_seq"] for r in records] == list(range(1, len(records)+1)), "nonsequential journal")
    require(all(type(r["schema_version"]) is int and r["schema_version"] == 21 and r["session_id"] == report["session_id"] for r in records), "journal schema/session mismatch")
    def select(kind): return [r for r in records if r["entry"]["kind"] == kind]
    opened = one(select("turn_opened"), "expected one actual root turn")
    settled = one(select("turn_settled"), "expected one actual settlement")
    snapshot = opened["entry"]["payload"]["config_snapshot"]
    require(type(snapshot["schema_version"]) is int and snapshot["schema_version"] == 8, "actual config snapshot schema mismatch")
    require(same(snapshot["modules"], {"workflow":"coding.single_loop","context":"simple","policy":"smoke.strict_policy","hooks":["hermes.verify_evidence"]}), "actual module assembly mismatch")
    require(snapshot["active_provider"] == "smoke.strict_scripted" and same(snapshot["model"], {"provider":"smoke.strict_scripted","model":"smoke.strict_scripted"}), "actual scripted model binding mismatch")
    require(snapshot["approval_available"] is True and snapshot["permission_mode_default"] == "normal" and snapshot["agent_control_surface"] == "none", "actual runtime authority mode mismatch")
    require(sorted(t["spec"]["name"] for t in snapshot["tools"]) == ["read_file","verification.json_contracts","write_file"], "actual registered tool set mismatch")
    identity = tuple(opened[k] for k in ("execution_id","thread_id","turn_id"))
    require(all(isinstance(x,str) and x for x in identity), "missing root attribution")
    for record in records:
        require((record["thread_id"], record["turn_id"]) == identity[1:], "inconsistent chat attribution")
        expected_execution = None if record["entry"]["kind"] in ("history_mutated", "turn_settled") else identity[0]
        require(record["execution_id"] == expected_execution, "inconsistent kind-specific execution attribution")
    require(opened["session_seq"] == 1 and settled["session_seq"] == len(records), "turn opening/settlement boundary ordering")
    success = case == "matching"
    require(report["outcome"]["status"] == ("success" if success else "error"), "unexpected runtime outcome")
    settlement = settled["entry"]["payload"]
    require(settlement["status"] == ("success" if success else "error"), "unexpected durable settlement")
    if not success:
        require(ERROR in report["outcome"].get("error", "") and ERROR in (settlement.get("error") or ""), "failure not exact strict gate exhaustion")
        require(settlement["output"] is None, "error settlement accepted output")
    model_count = 3 if case in ("matching","omitted","approval_denied") else 4
    requests, responses = select("model_request_recorded"), select("model_response_recorded")
    require(len(requests) == len(responses) == model_count, "actual model round count mismatch")
    require({r["entry"]["payload"]["exchange_id"] for r in requests} == {r["entry"]["payload"]["exchange_id"] for r in responses}, "model exchange correlation mismatch")
    require(len({r["entry"]["payload"]["exchange_id"] for r in requests}) == model_count and len({r["entry"]["payload"]["exchange_id"] for r in responses}) == model_count, "duplicate model exchange identity")
    response_by_exchange = {r["entry"]["payload"]["exchange_id"]: r for r in responses}
    require(all(r["session_seq"] < response_by_exchange[r["entry"]["payload"]["exchange_id"]]["session_seq"] for r in requests), "model response precedes request")
    require(all(r["entry"]["payload"]["outcome"]["status"] == "response" for r in responses), "model failed rather than strict gate")
    calls = select("tool_call_recorded")
    requested = [r for r in calls if r["entry"]["payload"]["phase"]["phase"] == "requested"]
    expected_names = ["write_file"] if case in ("omitted","approval_denied") else ["write_file","verification.json_contracts","read_file"]
    require([r["entry"]["payload"]["call"]["name"] for r in requested] == expected_names, "requested tool sequence/count mismatch")
    by_name = {r["entry"]["payload"]["call"]["name"]:r for r in requested}
    write = by_name["write_file"]["entry"]["payload"]
    require(write["call"]["id"] == WRITE and same(write["call"]["args"], {"path":"fixtures/release.json","content":content.decode()}), "actual write call mismatch")
    require(write["phase"]["owner"] == {"owner":"workflow"}, "write owner mismatch")
    def lifecycle(call_id):
        phases = [r for r in calls if r["entry"]["payload"]["call"]["id"] == call_id]
        raw = one([r for r in select("tool_effect_recorded") if r["entry"]["payload"]["result"]["call_id"] == call_id], "expected one raw terminal result")
        final = one([r for r in select("tool_result_recorded") if r["entry"]["payload"]["result"]["call_id"] == call_id], "expected one final tool result")
        require(phases[-1]["entry"]["payload"]["phase"]["phase"] == "resolved", "tool lacks resolved admission")
        require([r["session_seq"] for r in phases] == sorted(r["session_seq"] for r in phases) and phases[-1]["session_seq"] < raw["session_seq"] < final["session_seq"], "admission/raw/final ordering mismatch")
        return phases, raw, final
    wp, wr, wf = lifecycle(WRITE)
    require([r["entry"]["payload"]["phase"]["phase"] for r in wp] == ["requested","approval_requested","resolved"], "write approval lifecycle mismatch")
    resolution = wp[-1]["entry"]["payload"]["phase"]["resolution"]
    approved = case != "approval_denied"
    expected_resolution = {"decision":"approved"} if approved else {"decision":"approval_denied","reason":"strict fixture approval deliberately denied"}
    require(resolution == expected_resolution, "exact write resolution mismatch")
    approval = one(report["approvals"], "expected one uncached approval")
    require(approval["exact_match"] is True and approval["approved"] is approved and approval["cache"] == "none", "approval authority mismatch")
    require(tuple(approval["origin"][k] for k in ("execution_id","thread_id","turn_id")) == identity, "approval origin mismatch")
    require(same(approval["call"], write["call"]) and approval["cwd"] == str(cwd), "approval exact call/cwd mismatch")
    require(wf["entry"]["payload"]["result"]["ok"] is approved, "write terminal success mismatch")
    canonical_results = history_results(history)
    require([r["call_id"] for r in canonical_results] == ([WRITE] if len(expected_names)==1 else [WRITE,VERIFY]), "canonical outer tool-result sequence mismatch")
    final_by_id = {r["entry"]["payload"]["result"]["call_id"]: r["entry"]["payload"]["result"] for r in select("tool_result_recorded")}
    require(all(same(result, final_by_id.get(result["call_id"])) for result in canonical_results), "canonical result differs from final journal result")
    stop = [r for r in select("hook_invoked") if r["entry"]["payload"]["input"]["event"]["event"] == "before_stop"]
    require(len(stop) == (1 if success else 2), "BeforeStop actual count mismatch")
    for i, record in enumerate(stop):
        trace=record["entry"]["payload"]
        event=trace["input"]["event"]
        require(type(event["attempt"]) is int and event["attempt"] == i and event["continuation"] is None, "BeforeStop attempt/input mismatch")
        require(same(history_results(event["history"]), canonical_results), "gate did not see actual canonical results")
        step=one(trace["steps"], "gate hook chain not sole hook")
        require(step["module_id"] == "hermes.verify_evidence", "unexpected hook")
        outcome=step["outcome"]
        if success or i==0:
            action="continue" if success else "continue_turn"
            require(outcome["status"] == "accepted" and outcome["response"]["action"] == action, "gate response mismatch")
            require(trace["output"] is not None, "accepted gate trace missing output")
            continuation=trace["output"]["continuation"]
            require((continuation is None) if success else (isinstance(continuation,str) and "Verification evidence is missing" in continuation), "gate continuation mismatch")
        else:
            require(outcome["status"] == "failed" and ERROR in outcome["message"] and trace["output"] is None, "gate failed for unrelated reason")
    require(stop[-1]["session_seq"] < settled["session_seq"], "gate/settlement ordering mismatch")
    if len(expected_names)==1:
        require(report["receipt_checks"] == [], "omitted/denied write leaked receipt")
    else:
        v = by_name["verification.json_contracts"]["entry"]["payload"]
        read = by_name["read_file"]["entry"]["payload"]
        read_id=read["call"]["id"]
        require(v["call"]["id"] == VERIFY and v["call"]["args"] == {} and v["phase"]["owner"] == {"owner":"workflow"}, "verifier call/owner mismatch")
        require(read["phase"]["owner"] == {"owner":"tool","call_id":VERIFY} and read["call"]["args"] == {"path":"fixtures/release.json"}, "nested read ownership/args mismatch")
        vp, vr, vf=lifecycle(VERIFY)
        rp, rr, rf=lifecycle(read_id)
        require(vp[0]["session_seq"] < rp[0]["session_seq"] < rf["session_seq"] < vf["session_seq"], "nested result occurrence ordering mismatch")
        require([r["entry"]["payload"]["phase"]["phase"] for r in vp] == ["requested","resolved"] and vp[-1]["entry"]["payload"]["phase"]["resolution"] == {"decision":"allowed"}, "verifier resolution mismatch")
        deny=case=="read_denied"
        expected_read={"decision":"policy_denied","reason":"strict fixture read deliberately denied"} if deny else {"decision":"allowed"}
        require([r["entry"]["payload"]["phase"]["phase"] for r in rp] == ["requested","resolved"] and rp[-1]["entry"]["payload"]["phase"]["resolution"] == expected_read, "exact nested read resolution mismatch")
        final=vf["entry"]["payload"]["result"]
        require(final["ok"] is (not deny) and rf["entry"]["payload"]["result"]["ok"] is (not deny), "reader/producer result status mismatch")
        if deny:
            require(report["receipt_checks"] == [] and KEY not in (final["metadata"] or {}), "failed producer leaked receipt")
            require(rf["entry"]["payload"]["result"]["error"] == "strict fixture read deliberately denied", "reader denial diagnostic mismatch")
        else:
            reader=rf["entry"]["payload"]["result"]
            require(reader["output"].encode() == content and reader["error"] is None, "official reader returned different content")
            check=one(report["receipt_checks"], "expected one actual producer receipt")
            require(check["status"] == "valid" and same(check["receipt"], final["metadata"][KEY]), "shared original-policy validator rejected receipt")
            errors={"matching":None,"wrong_suite":"receipt suite mismatch","wrong_config":"receipt config digest mismatch","missing_assertion":"receipt assertion coverage mismatch"}
            require(check["effective_policy_error"] == errors[case], "targeted receipt-policy diagnostic mismatch")
            receipt=check["receipt"]
            doc=one(receipt["documents"], "expected one receipt document")
            require(doc["reader_call_id"] == read_id and type(doc["bytes"]) is int and doc["bytes"] == len(content) and doc["content_sha256"] == hashlib.sha256(content).hexdigest(), "receipt/file/read occurrence mismatch")
            require(receipt["verifier_call_id"] == VERIFY and receipt["cwd"] == str(cwd), "receipt current invocation mismatch")
    require(report["observed_content"] == (content.decode() if expected_file else None), "captured content differs from artifact")
    return {"scenario":case,"status":"passed","scope":report["scope"],"model_requests":model_count,"requested_tools":expected_names,"journal_records":len(records)}

def verify_capture(directory):
    before, after = load(directory/"inputs-before.json"), load(directory/"inputs-after.json")
    require(same(before, after), "captured binary/policy input hashes changed")
    names = ("host","official","fixture","producer","gate","policy")
    require(set(before) == set(names), "captured input set mismatch")
    for name in names:
        item = before[name]
        require(set(item) == {"path","sha256"} and Path(item["path"]).is_absolute(), "captured input path/schema mismatch")
        require(type(item["sha256"]) is str and len(item["sha256"]) == 64 and all(c in "0123456789abcdef" for c in item["sha256"]), "invalid captured input digest")
    processes = load(directory/"processes.json")
    require([p["scenario"] for p in processes] == list(CASES), "captured scenario order/count mismatch")
    for process in processes:
        case = process["scenario"]
        report = load(directory/case/"report.json")
        original_case = Path(report["cwd"]).parent
        expected_command = [before["host"]["path"], case, str(original_case), *[before[n]["path"] for n in names[1:]]]
        require(process["command"] == expected_command, "captured command/input mismatch")
        require(process["cwd"] == str(original_case.parent/(case+"-environment")), "captured isolated environment path mismatch")
        require(type(process["returncode"]) is int and process["returncode"] == 0 and process["timed_out"] is False, "child did not complete successfully")
        require(type(process["root_pid"]) is int and process["root_pid"] > 0, "captured root pid missing")
        root = one([p for p in process["owned_processes"] if p.get("direct_popen_child") is True], "captured direct child identity missing")
        require(type(root["pid"]) is int and root["pid"] == process["root_pid"] and type(root["start_time"]) is int and root["start_time"] > 0, "captured direct child identity mismatch")
        require(process["capture_error"] is None and process["cleanup_error"] is None and process["inspection_errors"] == [] and process["remaining_owned_children"] == [], "owned child cleanup not proved")
        require(process["disk_guard_stopped"] is False and process["direct_child_cleanup_fallback"] is False, "capture used failure fallback/guard")
        require(type(process["minimum_observed_free_bytes"]) is int and process["minimum_observed_free_bytes"] >= 1024**3, "captured disk reserve crossed")
        require(type(process["disk_stop_bytes"]) is int and type(process["disk_reserve_bytes"]) is int and process["disk_stop_bytes"] == 1024**3+128*1024**2 and process["disk_reserve_bytes"] == 1024**3, "captured disk policy mismatch")
        require(same(process["limits"], {"cpu_seconds":60,"address_space_bytes":1024**3,"file_bytes":8*1024**2,"wall_seconds":60,"cleanup_seconds":5.2}), "captured resource limits mismatch")
        require(type(process["wall_seconds"]) in (int,float) and 0 <= process["wall_seconds"] < 66, "captured wall bound mismatch")
        for stream in ("stdout","stderr"):
            path = directory/(case+"."+stream)
            require(path.is_file() and not path.is_symlink() and path.stat().st_size <= 8*1024**2, "captured output missing/unsafe/oversized")
            require(hashlib.sha256(path.read_bytes()).hexdigest() == process[stream+"_sha256"], "captured output digest mismatch")
    return {"status":"passed","scenarios":list(CASES),"process_scope":"owned child capture; binary hashes as observed by runner"}

if __name__ == "__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--directory",type=Path,required=True)
    parser.add_argument("--package",type=Path,default=Path(__file__).resolve().parent)
    args=parser.parse_args()
    process_gate=verify_capture(args.directory)
    summaries=[verify(args.directory/case,args.package) for case in CASES]
    print(json.dumps({"status":"passed","capture":process_gate,"checks":summaries},indent=2))
