#!/usr/bin/env python3
"""Independent authored controls for the pinned benchmark-contract v1 validator.

Synthetic contract-consistency checks only: no harness, provider, performance,
authenticity, egress or effect truth is established. run_controls(source_bytes)
supports memory-only execution. CLI reads only the sibling validator.py and
verifies its fixed byte count and SHA256 before executing that authored source.
Run with Python -B, without optimization. No files or network are written.
"""
import contextlib
import copy
import hashlib
import io
import json
import sys

EXPECTED_SHA256 = "35ec9a0c06c6f6878dd082e103c68bb2cc2a2696bd2a332a9258342dd1380935"
EXPECTED_BYTES = 35798

def run_controls(source_bytes):
    if sys.flags.optimize:
        raise RuntimeError("Reviewer controls require Python without optimization")
    if type(source_bytes) is not bytes or len(source_bytes) != EXPECTED_BYTES:
        raise ValueError("Validator byte count differs from reviewed artifact")
    if hashlib.sha256(source_bytes).hexdigest() != EXPECTED_SHA256:
        raise ValueError("Validator SHA256 differs from reviewed artifact")
    ns = {"__name__": "reviewed_validator"}
    exec(compile(source_bytes, "<reviewed-pinned-validator>", "exec"), ns)
    author = ns["self_test"]()
    check, check_text, digest, example = map(ns.__getitem__, ("check", "check_text", "digest", "example"))
    d=example(); m=d["manifest"]; r=d["result"]; e=m["cases"][0]; c=r["cases"][0]; o=c["observation"]
    e.update(expected_terminal="completed",cancel_requested=False)
    o.update(terminal="completed",settled_seq=10,cancellation={"requested":False,"acknowledged":False,"settled":False,"request_seq":None,"ack_seq":None,"settled_seq":None})
    o["model_attempts"]=[{"logical_id":"logical-1","attempt_id":"attempt-1","start_seq":1,"terminal_seq":2,"outcome":"completed"}]
    o["tool_calls"]=[{"call_id":"tool-1","start_seq":3,"terminal_seq":5,"outcome":"completed"}]
    o["effects"]=[{"operation_id":"effect-1","payload_sha256":"d"*64,"outcome":"committed","commit_seq":4}]
    o["counters"].update(model_requests=1,model_attempts=1,model_completed=1,tools_started=1,tools_completed=1,effects_committed=1)
    e["expected_counts"]=copy.deepcopy(o["counters"])
    e["expected_effects"]=[{k:v for k,v in x.items() if k!="commit_seq"} for x in o["effects"]]
    o["evidence_refs"]["effects_sha256"]=digest(o["effects"])
    r["manifest_sha256"]=digest(m); pin=digest(m)
    results=[]
    def test(name,fn=None,want="INVALID"):
        x=copy.deepcopy(d)
        if fn: fn(x)
        got=check(x,pin)
        assert got["status"]==want,(name,got)
        results.append({"name":name,"status":got["status"]})
        return got
    def obs(x): return x["result"]["cases"][0]["observation"]
    def cas(x): return x["result"]["cases"][0]
    def effect_hash(x): obs(x)["evidence_refs"]["effects_sha256"]=digest(obs(x)["effects"])
    test("independent_rich_positive",want="PASS")
    test("missing_model_terminal",lambda x:obs(x)["model_attempts"][0].pop("terminal_seq"))
    test("bool_model_start",lambda x:obs(x)["model_attempts"][0].update(start_seq=True))
    test("bool_model_terminal",lambda x:obs(x)["model_attempts"][0].update(terminal_seq=True))
    test("null_completed_model_terminal",lambda x:obs(x)["model_attempts"][0].update(terminal_seq=None))
    test("model_terminal_after_settlement",lambda x:obs(x)["model_attempts"][0].update(terminal_seq=11))
    test("model_terminal_equals_settlement",lambda x:obs(x)["model_attempts"][0].update(terminal_seq=10))
    test("model_terminal_before_start",lambda x:obs(x)["model_attempts"][0].update(terminal_seq=0))
    test("tool_terminal_after_settlement",lambda x:obs(x)["tool_calls"][0].update(terminal_seq=11))
    test("tool_start_after_settlement",lambda x:obs(x)["tool_calls"][0].update(start_seq=11,terminal_seq=12))
    test("tool_start_collides_model_terminal",lambda x:obs(x)["tool_calls"][0].update(start_seq=2))
    def late_effect(x):
        obs(x)["effects"][0]["commit_seq"]=11
        effect_hash(x)
    test("effect_after_settlement",late_effect)
    def effect_collision(x):
        obs(x)["effects"][0]["commit_seq"]=5
        effect_hash(x)
    test("effect_collides_tool_terminal",effect_collision)
    def duplicate_effect(x):
        obs(x)["effects"].append({**obs(x)["effects"][0],"commit_seq":6})
        obs(x)["counters"]["effects_committed"]=2
        effect_hash(x)
    test("duplicate_effect_multiplicity",duplicate_effect)
    def unknown_effect(x):
        obs(x)["effects"][0].update(outcome="unknown",commit_seq=None)
        obs(x)["counters"].update(effects_committed=0,effects_unknown=1)
        effect_hash(x)
    test("unknown_effect_not_zero",unknown_effect)
    def unknown_failure(x):
        unknown_effect(x); cas(x).update(status="FAIL",reason="unknown effect receipt")
    test("unknown_effect_failure_preserved",unknown_failure,want="FAIL")
    def unfinished(x):
        obs(x)["model_attempts"][0].update(outcome="inflight",terminal_seq=None)
        obs(x)["counters"].update(model_completed=0,model_inflight=1)
    test("inflight_model_not_pass",unfinished)
    def unfinished_failure(x):
        unfinished(x); obs(x).update(settled=False,settled_seq=None,terminal="unsettled")
        cas(x).update(status="FAIL",reason="model never settled")
    test("inflight_model_failure_preserved",unfinished_failure,want="FAIL")
    for field in ("cpu_ns","rss_peak_bytes"):
        for value,label in ((True,"bool"),(-1,"negative"),(1<<63,"overflow")):
            test(field+"_"+label,lambda x,k=field,v=value:obs(x)["resources"].update({k:v}))
    for value,label in ((float("nan"),"nan"),(float("inf"),"inf"),(-1,"negative"),(True,"bool"),(10**400,"hugeint")):
        test("timing_"+label,lambda x,v=value:cas(x).update(timing_samples_ms=[v]))
    test("zero_timing_report_only",lambda x:cas(x).update(timing_samples_ms=[0]),want="PASS")
    test("forged_calibrated_flag",lambda x:cas(x).update(calibrated=True))
    def rebind(x): x["result"]["manifest_sha256"]=digest(x["manifest"])
    def rewrite_build(x):
        for k in ("manifest","result"): x[k]["identity"]["build_sha256"]="e"*64
        rebind(x)
    test("rewritten_both_build_pins_old_external_pin",rewrite_build)
    def relabel(x):
        for k in ("manifest","result"): x[k]["evidence_kind"]="R-scoped"
        rebind(x)
    test("synthetic_relabel_old_external_pin",relabel)
    def no_run(x):
        cas(x).update(status="NOT_RUN",executed=False,reason="never run",observation=None,assertions=[],timing_samples_ms=None)
    test("not_run_not_pass",no_run,want="NOT_RUN")
    def predeclare_skip_rewrite(x):
        no_run(x); x["manifest"]["cases"][0].update(support="unsupported",unsupported_reason="skip required")
        cas(x).update(status="UNSUPPORTED",reason="skip required")
        rebind(x)
    test("unsupported_manifest_rewrite_old_pin",predeclare_skip_rewrite)
    two=copy.deepcopy(d)
    for key in ("manifest","result"):
        extra=copy.deepcopy(two[key]["cases"][0]); extra["id"]="critical-required-case"; two[key]["cases"].append(extra)
    two["result"]["manifest_sha256"]=digest(two["manifest"]); twopin=digest(two["manifest"])
    assert check(two,twopin)["status"]=="PASS"
    for key in ("manifest","result"): two[key]["cases"].pop()
    two["result"]["manifest_sha256"]=digest(two["manifest"])
    assert check(two,twopin)["status"]=="INVALID"; results.append({"name":"remove_case_from_both_old_external_pin","status":"INVALID"})
    for p,label in ((None,"missing"),("f"*64,"wrong"),(True,"bool")):
        assert check(d,p)["status"]=="INVALID";results.append({"name":label+"_external_pin","status":"INVALID"})
    for raw,label in (('{"manifest":{},"manifest":{},"result":{}}',"duplicate_json_keys"),('{"a":'*1500+'0'+'}'*1500,"deep_json"),(" "*(ns["MAX_INPUT"]+1),"oversize_json")):
        assert check_text(raw,pin)["status"]=="INVALID";results.append({"name":label,"status":"INVALID"})
    summary=check(d,pin)
    assert summary["claim"]=="contract-consistency-only" and summary["timing_policy"]=="report-only"
    assert summary["evidence_authenticity"]=="unverified" and summary["qualification"]=="NOT_EVALUATED"

    structural_results = results
    n = ns
    results=[]
    def case_status(d,status):
        c=d["result"]["cases"][0]
        if status=="PASS": return
        c.update(status=status,reason="reviewer control")
        if status in ("NOT_RUN","UNSUPPORTED"):
            c.update(executed=False,observation=None,timing_samples_ms=None,assertions=[])
        if status=="UNSUPPORTED":
            d["manifest"]["cases"][0].update(support="unsupported",unsupported_reason="reviewer predeclared capability gap")
    def cli(d,args=None,text=None):
        pin=n["digest"](d["manifest"]);d["result"]["manifest_sha256"]=pin
        old_argv,old_in=n["sys"].argv,n["sys"].stdin
        out=io.StringIO()
        try:
            n["sys"].argv=["validator","--expected-manifest-sha256",pin] if args is None else ["validator"]+args
            n["sys"].stdin=io.StringIO(json.dumps(d) if text is None else text)
            with contextlib.redirect_stdout(out): exitcode=n["main"]()
        finally:
            n["sys"].argv, n["sys"].stdin=old_argv,old_in
        return exitcode,json.loads(out.getvalue())
    for status,exitcode in n["EXIT"].items():
        d=n["example"]();case_status(d,status)
        got_exit,got=cli(d);assert got_exit==exitcode and got["status"]==status,(status,got_exit,got)
        results.append({"test":"cli_"+status,"exit":got_exit,"status":got["status"]})
    for states,want in ((["PASS","NOT_RUN"],"NOT_RUN"),(["PASS","UNSUPPORTED"],"UNSUPPORTED"),(["FAIL","NOT_RUN"],"FAIL"),(["FAIL","INVALID"],"INVALID"),(["UNSUPPORTED","NOT_RUN"],"NOT_RUN")):
        d=n["example"]();d["manifest"]["cases"]=[];d["result"]["cases"]=[]
        for idx,status in enumerate(states):
            sub=n["example"]();case_status(sub,status)
            for k in ("manifest","result"):
                sub[k]["cases"][0]["id"]="case-"+str(idx);d[k]["cases"].append(sub[k]["cases"][0])
        got_exit,got=cli(d);assert got_exit==n["EXIT"][want] and got["status"]==want,(states,got_exit,got)
        results.append({"test":"aggregate_"+"_".join(states),"exit":got_exit,"status":got["status"]})
    for args in ([],["--expected-manifest-sha256"],["--expected-manifest-sha256","bad"],["--unknown"]):
        got_exit,got=cli(n["example"](),args=args);assert got_exit==2 and got["status"]=="INVALID"
        results.append({"test":"bad_cli_"+str(args),"exit":got_exit,"status":got["status"]})
    for raw,label in ((" "*(n["MAX_INPUT"]+1),"oversize"),('{"a":'*1500+'0'+'}'*1500,"deep")):
        got_exit,got=cli(n["example"](),text=raw);assert got_exit==2 and got["status"]=="INVALID"
        results.append({"test":"cli_"+label,"exit":got_exit,"status":got["status"]})

    cli_results = results
    d=n["example"]();o=d["result"]["cases"][0]["observation"];e=d["manifest"]["cases"][0]
    o["settled_seq"]=10;o["cancellation"]["settled_seq"]=10
    o["effects"]=[{"operation_id":"A","payload_sha256":"d"*64,"outcome":"committed","commit_seq":4},{"operation_id":"B","payload_sha256":"e"*64,"outcome":"committed","commit_seq":8}]
    o["counters"]["effects_committed"]=2;e["expected_counts"]["effects_committed"]=2
    e["expected_effects"]=[{k:v for k,v in x.items() if k!="commit_seq"} for x in o["effects"]]
    pin=n["digest"](d["manifest"]);d["result"]["manifest_sha256"]=pin
    results=[]
    def run(name,edit=None,want="INVALID"):
        x=copy.deepcopy(d)
        if edit:edit(x)
        ob=x["result"]["cases"][0]["observation"]
        if ob is not None:ob["evidence_refs"]["effects_sha256"]=n["digest"](ob["effects"])
        actual=n["check"](x,pin)["status"];assert actual==want,(name,actual)
        results.append({"name":name,"status":actual})
    def reverse_seq(x):
        effects=x["result"]["cases"][0]["observation"]["effects"]
        effects[0]["commit_seq"],effects[1]["commit_seq"]=8,4
    run("ordered_effects_positive",want="PASS")
    run("reverse_actual_commits_not_pass",reverse_seq)
    def reverse_semantic_order(x):
        reverse_seq(x);x["result"]["cases"][0]["observation"]["effects"].reverse()
    run("chronological_but_wrong_oracle_order",reverse_semantic_order)
    run("out_of_order_list_not_silently_sorted",lambda x:x["result"]["cases"][0]["observation"]["effects"].reverse())
    def failing_reverse(x):
        reverse_seq(x);x["result"]["cases"][0].update(status="FAIL",reason="wrong effect commit order")
    run("wrong_order_failure_preserved",failing_reverse,want="FAIL")
    unsupported=copy.deepcopy(d)
    unsupported["manifest"]["cases"][0].update(support="unsupported",unsupported_reason="unordered effect oracle unsupported in v1")
    unsupported["result"]["cases"][0].update(status="UNSUPPORTED",executed=False,reason="unordered effect oracle unsupported in v1",observation=None,assertions=[],timing_samples_ms=None)
    upin=n["digest"](unsupported["manifest"]);unsupported["result"]["manifest_sha256"]=upin
    assert n["check"](unsupported,upin)["status"]=="UNSUPPORTED"
    results.append({"name":"predeclared_unordered_oracle_unsupported","status":"UNSUPPORTED"})

    ordered_effect_results = results
    control_count = len(structural_results) + len(cli_results) + len(ordered_effect_results)
    if control_count != 64:
        raise AssertionError("Expected exactly 64 reviewer controls")
    return {
        "schema": "proteus.harness.reviewer-controls/v1",
        "status": "PASS",
        "source_sha256": EXPECTED_SHA256,
        "source_bytes": EXPECTED_BYTES,
        "author_controls_rerun": author["control_count"],
        "reviewer_control_count": control_count,
        "structural_controls": structural_results,
        "cli_controls": cli_results,
        "ordered_effect_controls": ordered_effect_results,
        "evidence_kind": "synthetic-control",
        "claim": "contract-consistency-only",
        "evidence_authenticity": "unverified",
        "qualification": "NOT_EVALUATED",
        "scope": "Authored validator controls only; no harness, APIs, filesystem writes, or runtime truth validated."
    }

def main():
    if len(sys.argv) != 1:
        raise ValueError("Reviewer controls accept no arguments")
    from pathlib import Path
    source_bytes = Path(__file__).with_name("validator.py").read_bytes()
    print(json.dumps(run_controls(source_bytes), sort_keys=True))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
