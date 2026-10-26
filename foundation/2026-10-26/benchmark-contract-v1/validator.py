#!/usr/bin/env python3
"""Offline consistency validator; no adapters, execution, authenticity or speed proof.
Input: {"manifest": {...}, "result": {...}} on stdin; requires caller-owned
--expected-manifest-sha256 HASH, never taken from or refreshed from input.
Distinct trace events use unique ordinal sequences. Cancellation settlement
aliases generic settlement. Effects and tool terminals are distinct events.
The final process count is after case teardown, not during a warm turn.
Counters/resources are signed-64-bit nonnegative integers; input <= 8 MiB.
Exit: PASS=0 FAIL=1 INVALID=2 NOT_RUN=3 UNSUPPORTED=4.
--self-test runs authored in-memory controls; --example prints synthetic JSON.
All timing is report-only in v1. Hashes use canonical UTF-8 JSON, sorted keys,
no whitespace, ensure_ascii=False, allow_nan=False.
"""
import copy
import hashlib
import json
import math
import re
import sys

M_SCHEMA = "proteus.harness.manifest/v1"
R_SCHEMA = "proteus.harness.result/v1"
C_SCHEMA = "proteus.harness.validation/v1"
STATUSES = ("PASS", "FAIL", "INVALID", "NOT_RUN", "UNSUPPORTED")
EXIT = dict(zip(STATUSES, (0, 1, 2, 3, 4)))
MAX_INPUT = 8 * 1024 * 1024
MAX_INT = (1 << 63) - 1
IDENTITY = ("source_repository", "source_commit", "build_sha256",
            "lock_sha256", "adapter_sha256", "fixture_sha256", "config_sha256",
            "parameters_sha256", "environment_sha256", "route_id", "toolchain", "build_profile")
COUNTS = ("model_requests", "model_attempts", "model_completed", "model_failed",
          "model_cancelled", "model_inflight", "tools_started", "tools_completed",
          "tools_failed", "tools_cancelled", "tools_inflight",
          "effects_committed", "effects_unknown")
ASSERTIONS = ("terminal", "counts", "effects", "cancellation", "egress", "settlement")
RESOURCES = ("cpu_ns", "rss_peak_bytes", "pss_swappss_peak_bytes", "io_read_bytes",
             "io_write_bytes", "protocol_tx_bytes", "protocol_rx_bytes")

class Invalid(ValueError):
    pass

def need(ok, message):
    if not ok:
        raise Invalid(message)

def fields(value, names, where):
    need(type(value) is dict, where + ": expected object")
    need(set(value) == set(names), where + ": missing or unknown fields")

def integer(value):
    return type(value) is int and 0 <= value <= MAX_INT

def nonempty(value):
    return type(value) is str and bool(value.strip())

def hash_ok(value, digits=64):
    return type(value) is str and re.fullmatch("[0-9a-f]{" + str(digits) + "}", value) is not None

def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")

def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()

def strict_loads(text):
    need(type(text) is str and len(text.encode("utf-8")) <= MAX_INPUT, "input exceeds 8 MiB")
    def pairs(items):
        out = {}
        for key, value in items:
            need(key not in out, "duplicate JSON key: " + key)
            out[key] = value
        return out
    def constant(value):
        raise Invalid("nonfinite JSON number: " + value)
    return json.loads(text, object_pairs_hook=pairs, parse_constant=constant)

def unique(items, where):
    need(len(items) == len(set(items)), where + ": duplicate identity")

def identity(value):
    fields(value, IDENTITY, "identity")
    need(all(nonempty(value[k]) for k in ("source_repository", "route_id", "toolchain", "build_profile")),
         "identity: missing repository, route, toolchain or build profile")
    need(hash_ok(value["source_commit"], 40), "identity: invalid source commit")
    for key in IDENTITY:
        if key.endswith("_sha256"):
            need(hash_ok(value[key]), "identity: invalid " + key)

def counts(value, where):
    fields(value, COUNTS, where)
    need(all(integer(x) for x in value.values()), where + ": invalid counter")

def effects(value, where, oracle=False):
    need(type(value) is list, where + ": expected list")
    for entry in value:
        fields(entry, ("operation_id", "payload_sha256", "outcome") if oracle else
               ("operation_id", "payload_sha256", "outcome", "commit_seq"), where)
        need(nonempty(entry["operation_id"]) and hash_ok(entry["payload_sha256"]),
             where + ": invalid effect identity")
        need(entry["outcome"] in ("committed", "unknown"), where + ": invalid outcome")
        if oracle:
            need(entry["outcome"] == "committed", where + ": unknown oracle effect")
        else:
            need(integer(entry["commit_seq"]) if entry["outcome"] == "committed" else
                 entry["commit_seq"] is None, where + ": effect sequence/unknown mismatch")
    if oracle:
        unique([x["operation_id"] for x in value], where)

def manifest_check(m):
    fields(m, ("schema", "evidence_kind", "scope", "experiment_id", "variant_id",
               "identity", "parameters", "timing_policy", "cases"), "manifest")
    need(m["schema"] == M_SCHEMA, "manifest: unsupported schema")
    need(m["evidence_kind"] in ("synthetic-control", "R-scoped"), "manifest: evidence kind")
    need(all(nonempty(m[x]) for x in ("scope", "experiment_id", "variant_id")),
         "manifest: missing scope or identity")
    identity(m["identity"])
    need(type(m["parameters"]) is dict, "manifest: parameters must be object")
    need(digest(m["parameters"]) == m["identity"]["parameters_sha256"],
         "manifest: parameters hash mismatch")
    need(m["timing_policy"] == "report-only", "v1 supports report-only timing only")
    need(type(m["cases"]) is list and len(m["cases"]) > 0, "manifest: empty case list")
    for c in m["cases"]:
        fields(c, ("id", "support", "unsupported_reason", "expected_terminal",
                   "cancel_requested", "expected_counts", "expected_effects",
                   "assertions"), "manifest case")
        need(nonempty(c["id"]), "manifest case: empty id")
        need(c["support"] in ("required", "unsupported"), "manifest case: support")
        need((c["support"] == "unsupported" and nonempty(c["unsupported_reason"])) or
             (c["support"] == "required" and c["unsupported_reason"] is None),
             "manifest case: unsupported declaration")
        need(c["expected_terminal"] in ("completed", "cancelled", "failed"),
             "manifest case: terminal")
        need(type(c["cancel_requested"]) is bool, "manifest case: cancel boolean")
        need(c["cancel_requested"] or c["expected_terminal"] != "cancelled",
             "manifest case: cancelled without request")
        counts(c["expected_counts"], "manifest counts")
        effects(c["expected_effects"], "manifest effects", oracle=True)
        need(c["expected_counts"]["effects_committed"] == len(c["expected_effects"]),
             "manifest: effect count differs from oracle")
        need(c["expected_counts"]["effects_unknown"] == 0 and
             c["expected_counts"]["tools_inflight"] == 0 and
             c["expected_counts"]["model_inflight"] == 0, "manifest: unsettled oracle")
        need(c["expected_counts"]["tools_started"] ==
             sum(c["expected_counts"][x] for x in ("tools_completed", "tools_failed", "tools_cancelled")),
             "manifest: tool conservation")
        need(c["expected_counts"]["model_attempts"] ==
             sum(c["expected_counts"][x] for x in ("model_completed", "model_failed", "model_cancelled")),
             "manifest: model attempt conservation")
        need(c["expected_counts"]["model_requests"] <= c["expected_counts"]["model_attempts"],
             "manifest: logical requests exceed attempts")
        need(type(c["assertions"]) is list and sorted(c["assertions"]) == sorted(ASSERTIONS),
             "manifest: exact required assertion names missing")
    unique([c["id"] for c in m["cases"]], "manifest cases")

def observation_check(o):
    fields(o, ("terminal", "settled", "settled_seq", "owned_processes_alive", "external_api_calls",
               "cancellation", "model_attempts", "tool_calls", "effects", "counters",
               "evidence_refs", "resources"), "observation")
    need(o["terminal"] in ("completed", "cancelled", "failed", "unsettled"), "observation: terminal")
    need(type(o["settled"]) is bool and integer(o["owned_processes_alive"]) and
         integer(o["external_api_calls"]), "observation: invalid scalar")
    need(integer(o["settled_seq"]) if o["settled"] else o["settled_seq"] is None,
         "observation: settlement sequence mismatch")
    fields(o["resources"], RESOURCES, "resources")
    need(all(v is None or integer(v) for v in o["resources"].values()),
         "resources: expected null or nonnegative integer, not bool")
    cc = o["cancellation"]
    fields(cc, ("requested", "acknowledged", "settled", "request_seq", "ack_seq", "settled_seq"), "cancellation")
    for flag, seq in (("requested", "request_seq"), ("acknowledged", "ack_seq"), ("settled", "settled_seq")):
        need(type(cc[flag]) is bool and
             ((cc[flag] and integer(cc[seq])) or (not cc[flag] and cc[seq] is None)),
             "cancellation: flag/sequence mismatch")
    need(cc["requested"] or not (cc["acknowledged"] or cc["settled"]),
         "cancellation: acknowledgment/settlement without request")
    seqs = [cc[x] for x in ("request_seq", "ack_seq", "settled_seq") if cc[x] is not None]
    need(all(a < b for a, b in zip(seqs, seqs[1:])), "cancellation: invalid causal order")
    need(not cc["settled"] or (o["settled"] and cc["settled_seq"] == o["settled_seq"]),
         "cancellation: settlement must alias generic settlement")
    need(type(o["model_attempts"]) is list and type(o["tool_calls"]) is list, "observation: call lists")
    for a in o["model_attempts"]:
        fields(a, ("logical_id", "attempt_id", "start_seq", "terminal_seq", "outcome"), "model attempt")
        need(nonempty(a["logical_id"]) and nonempty(a["attempt_id"]) and integer(a["start_seq"]),
             "model attempt: invalid identity")
        need(a["outcome"] in ("completed", "failed", "cancelled", "inflight"), "model attempt: outcome")
        need((a["terminal_seq"] is None) if a["outcome"] == "inflight" else
             (integer(a["terminal_seq"]) and a["terminal_seq"] > a["start_seq"]),
             "model attempt: invalid terminal sequence")
    unique([a["attempt_id"] for a in o["model_attempts"]], "model attempts")
    unique([a["start_seq"] for a in o["model_attempts"]], "model start sequences")
    need(not set(a["start_seq"] for a in o["model_attempts"]).intersection(seqs),
         "model attempt: sequence collides with cancellation event")
    for t in o["tool_calls"]:
        fields(t, ("call_id", "outcome", "start_seq", "terminal_seq"), "tool call")
        need(nonempty(t["call_id"]) and t["outcome"] in ("completed", "failed", "cancelled", "inflight"),
             "tool call: invalid identity/outcome")
        need(integer(t["start_seq"]) and ((t["terminal_seq"] is None) if t["outcome"] == "inflight" else
             (integer(t["terminal_seq"]) and t["terminal_seq"] > t["start_seq"])),
             "tool call: invalid event sequence")
    unique([t["call_id"] for t in o["tool_calls"]], "tool calls")
    effects(o["effects"], "effects")
    event_seqs = [cc[k] for k in ("request_seq", "ack_seq") if cc[k] is not None]
    if o["settled_seq"] is not None:
        event_seqs.append(o["settled_seq"])
    for record in o["model_attempts"] + o["tool_calls"]:
        event_seqs.append(record["start_seq"])
        if record["terminal_seq"] is not None:
            event_seqs.append(record["terminal_seq"])
    event_seqs.extend(e["commit_seq"] for e in o["effects"] if e["commit_seq"] is not None)
    unique(event_seqs, "distinct trace events")
    counts(o["counters"], "observed counters")
    derived = {
        "model_requests": len(set(a["logical_id"] for a in o["model_attempts"])),
        "model_attempts": len(o["model_attempts"]), "tools_started": len(o["tool_calls"]),
        **{"model_" + k: sum(a["outcome"] == k for a in o["model_attempts"])
           for k in ("completed", "failed", "cancelled", "inflight")},
        **{"tools_" + k: sum(t["outcome"] == k for t in o["tool_calls"])
           for k in ("completed", "failed", "cancelled", "inflight")},
        **{"effects_" + k: sum(e["outcome"] == k for e in o["effects"])
           for k in ("committed", "unknown")}
    }
    need(o["counters"] == derived, "observation: counters do not conserve records")
    fields(o["evidence_refs"], ("trace_sha256", "network_sha256", "effects_sha256", "process_sha256"),
           "evidence refs")
    need(all(hash_ok(x) for x in o["evidence_refs"].values()), "evidence refs: invalid hash")
    need(o["evidence_refs"]["effects_sha256"] == digest(o["effects"]),
         "evidence refs: effect ledger hash mismatch")

def validate(m, r, expected_manifest_sha256):
    need(hash_ok(expected_manifest_sha256), "caller must supply expected manifest SHA256")
    manifest_check(m)
    need(digest(m) == expected_manifest_sha256, "manifest differs from caller-pinned contract")
    fields(r, ("schema", "manifest_sha256", "identity", "evidence_kind", "cases"), "result")
    need(r["schema"] == R_SCHEMA and r["evidence_kind"] == m["evidence_kind"], "result: schema/kind mismatch")
    identity(r["identity"])
    need(r["identity"] == m["identity"] and r["manifest_sha256"] == digest(m),
         "result: source/build/fixture/config/environment binding mismatch")
    need(type(r["cases"]) is list, "result: cases must be list")
    for c in r["cases"]:
        fields(c, ("id", "status", "executed", "reason", "assertions", "observation", "timing_samples_ms"),
               "result case")
        need(nonempty(c["id"]), "result case: empty id")
    unique([c["id"] for c in r["cases"]], "result cases")
    need(set(c["id"] for c in r["cases"]) == set(c["id"] for c in m["cases"]),
         "result: missing or extra named cases")
    expected = {c["id"]: c for c in m["cases"]}
    for c in r["cases"]:
        e = expected[c["id"]]
        need(c["status"] in STATUSES and type(c["executed"]) is bool, "result case: status/executed")
        need(c["reason"] is None if c["status"] == "PASS" else nonempty(c["reason"]),
             "result case: reason required except PASS")
        need((e["support"] == "unsupported") == (c["status"] == "UNSUPPORTED"),
             "result case: unsupported must be predeclared, never a renamed failure")
        if c["status"] in ("PASS", "FAIL"):
            need(c["executed"], "result case: unexecuted PASS/FAIL")
        if c["status"] in ("NOT_RUN", "UNSUPPORTED"):
            need(not c["executed"], "result case: executed NOT_RUN/UNSUPPORTED")
        if not c["executed"]:
            need(c["observation"] is None and c["timing_samples_ms"] is None and c["assertions"] == [],
                 "unexecuted case: fabricated observations or timing")
            continue
        observation_check(c["observation"])
        need(type(c["assertions"]) is list, "result assertions: expected list")
        for a in c["assertions"]:
            fields(a, ("id", "passed"), "assertion")
            need(nonempty(a["id"]) and type(a["passed"]) is bool, "assertion: invalid value")
        unique([a["id"] for a in c["assertions"]], "assertions")
        need(set(a["id"] for a in c["assertions"]) == set(e["assertions"]),
             "result: missing or extra assertions")
        ts = c["timing_samples_ms"]
        need(ts is None or (type(ts) is list and len(ts) > 0 and
             all(type(x) in (int, float) and math.isfinite(x) and x >= 0 for x in ts)),
             "timing: expected null or nonempty finite nonnegative samples")
        if c["status"] != "PASS":
            continue
        o, cc = c["observation"], c["observation"]["cancellation"]
        need(all(a["passed"] for a in c["assertions"]), "PASS: failed assertion")
        need(o["terminal"] == e["expected_terminal"] and o["terminal"] != "unsettled", "PASS: terminal mismatch")
        need(o["counters"] == e["expected_counts"], "PASS: expected counts mismatch")
        need([{k: v for k, v in x.items() if k != "commit_seq"} for x in o["effects"]] ==
             e["expected_effects"] and o["counters"]["effects_unknown"] == 0,
             "PASS: effect oracle mismatch or unknown effect")
        unique([x["operation_id"] for x in o["effects"]], "PASS effects")
        commit_order = [x["commit_seq"] for x in o["effects"]]
        need(commit_order == sorted(commit_order), "PASS: effect ledger not in commit order")
        need(o["external_api_calls"] == 0, "PASS: external API call observed")
        need(o["settled"] and o["owned_processes_alive"] == 0 and o["counters"]["tools_inflight"] == 0 and
             o["counters"]["model_inflight"] == 0,
             "PASS: work or owned processes not settled")
        need(all(x["terminal_seq"] is not None and x["terminal_seq"] < o["settled_seq"]
                 for x in o["model_attempts"] + o["tool_calls"]), "PASS: call not terminal before settlement")
        need(all(x["commit_seq"] is not None and x["commit_seq"] < o["settled_seq"]
                 for x in o["effects"]), "PASS: effect not known before settlement")
        need(cc["requested"] == e["cancel_requested"], "PASS: cancellation request mismatch")
        if cc["requested"]:
            need(cc["settled"], "PASS: cancellation acknowledgment is not settlement")
            need(all(a["start_seq"] <= cc["settled_seq"] for a in o["model_attempts"]),
                 "PASS: model attempt after terminal cancellation")
    states = [c["status"] for c in r["cases"]]
    status = next((s for s in ("INVALID", "FAIL", "NOT_RUN", "UNSUPPORTED") if s in states), "PASS")
    return {"schema": C_SCHEMA, "status": status, "evidence_kind": m["evidence_kind"],
            "case_count": len(states), "timing_policy": "report-only",
            "scope": m["scope"], "claim": "contract-consistency-only",
            "manifest_trust": "caller-pinned", "evidence_authenticity": "unverified",
            "qualification": "NOT_EVALUATED",
            "warning": "Consistency only: execution, artifact authenticity, egress and effects require independent evidence review."}

def check(document, expected_manifest_sha256=None):
    try:
        fields(document, ("manifest", "result"), "input")
        return validate(document["manifest"], document["result"], expected_manifest_sha256)
    except (Invalid, ValueError, TypeError, OverflowError, RecursionError) as exc:
        return {"schema": C_SCHEMA, "status": "INVALID", "error": str(exc)}

def check_text(text, expected_manifest_sha256=None):
    try:
        return check(strict_loads(text), expected_manifest_sha256)
    except (Invalid, ValueError, TypeError, OverflowError, RecursionError) as exc:
        return {"schema": C_SCHEMA, "status": "INVALID", "error": str(exc)}

def example():
    h = "a" * 64
    params = {"fixture": "authored-contract-control", "seed": 17}
    ident = {key: h for key in IDENTITY}
    ident.update(source_repository="https://example.invalid/authored-control",
                 source_commit="b" * 40, route_id="synthetic-not-a-harness",
                 parameters_sha256=digest(params), toolchain="authored-control-only", build_profile="not-built")
    zero = {k: 0 for k in COUNTS}
    expected = {"id": "cancel_before_effect", "support": "required", "unsupported_reason": None,
                "expected_terminal": "cancelled", "cancel_requested": True,
                "expected_counts": zero, "expected_effects": [], "assertions": list(ASSERTIONS)}
    m = {"schema": M_SCHEMA, "evidence_kind": "synthetic-control",
         "scope": "Validator self-test only; no harness executed or measured",
         "experiment_id": "contract-control-v1", "variant_id": "authored",
         "identity": ident, "parameters": params, "timing_policy": "report-only", "cases": [expected]}
    o = {"terminal": "cancelled", "settled": True, "settled_seq": 3, "owned_processes_alive": 0, "external_api_calls": 0,
         "cancellation": {"requested": True, "acknowledged": True, "settled": True,
                          "request_seq": 1, "ack_seq": 2, "settled_seq": 3},
         "model_attempts": [], "tool_calls": [], "effects": [], "counters": zero.copy(),
         "evidence_refs": {"trace_sha256": h, "network_sha256": h, "process_sha256": h,
                           "effects_sha256": digest([])}, "resources": {k: None for k in RESOURCES}}
    c = {"id": expected["id"], "status": "PASS", "executed": True, "reason": None,
         "assertions": [{"id": x, "passed": True} for x in ASSERTIONS],
         "observation": o, "timing_samples_ms": None}
    r = {"schema": R_SCHEMA, "manifest_sha256": digest(m), "identity": copy.deepcopy(ident),
         "evidence_kind": m["evidence_kind"], "cases": [c]}
    return {"manifest": m, "result": r}

def self_test():
    passed = []
    def run(name, edit=None, want="INVALID", rebind=False, retain_pin=False):
        d = copy.deepcopy(example())
        expected_pin = digest(d["manifest"])
        if edit:
            edit(d)
        if rebind:
            d["result"]["manifest_sha256"] = digest(d["manifest"])
            if not retain_pin:
                expected_pin = digest(d["manifest"])
        actual = check(d, expected_pin)["status"]
        need(actual == want, name + ": expected " + want + ", got " + actual)
        passed.append(name)
    def case(d):
        return d["result"]["cases"][0]
    def obs(d):
        return case(d)["observation"]
    run("valid_synthetic_control", want="PASS")
    run("missing_case", lambda d: d["result"]["cases"].clear())
    run("duplicate_case", lambda d: d["result"]["cases"].append(copy.deepcopy(case(d))))
    run("extra_case", lambda d: d["result"]["cases"].append({**copy.deepcopy(case(d)), "id": "extra"}))
    run("unknown_field", lambda d: case(d).update(skipped=True))
    run("empty_assertions", lambda d: case(d)["assertions"].clear())
    run("false_assertion", lambda d: case(d)["assertions"][0].update(passed=False))
    run("bool_counter", lambda d: obs(d)["counters"].update(model_attempts=True))
    run("negative_counter", lambda d: obs(d)["counters"].update(model_attempts=-1))
    run("nan_timing", lambda d: case(d).update(timing_samples_ms=[float("nan")]))
    run("infinite_timing", lambda d: case(d).update(timing_samples_ms=[float("inf")]))
    run("bool_timing", lambda d: case(d).update(timing_samples_ms=[True]))
    run("unexecuted_pass", lambda d: case(d).update(executed=False))
    run("absent_observation", lambda d: case(d).update(observation=None))
    run("external_api", lambda d: obs(d).update(external_api_calls=1))
    run("ack_not_settlement", lambda d: obs(d)["cancellation"].update(settled=False, settled_seq=None))
    run("owned_process_alive", lambda d: obs(d).update(owned_processes_alive=1))
    run("counter_conservation", lambda d: obs(d)["counters"].update(tools_started=1))
    run("wrong_binary", lambda d: d["result"]["identity"].update(build_sha256="c" * 64))
    run("missing_source_pin", lambda d: d["manifest"]["identity"].pop("source_commit"))
    run("changed_parameters", lambda d: d["manifest"]["parameters"].update(seed=18), rebind=True)
    run("missing_evidence", lambda d: obs(d)["evidence_refs"].pop("network_sha256"))
    run("unsupported_posthoc", lambda d: case(d).update(status="UNSUPPORTED", reason="no adapter", executed=False,
                                                       observation=None, assertions=[], timing_samples_ms=None))
    run("timing_gate_rejected", lambda d: d["manifest"].update(timing_policy="calibrated-gate"), rebind=True)
    run("p99_field_rejected", lambda d: case(d).update(p99_ms=1))
    run("unknown_status", lambda d: case(d).update(status="SKIPPED", reason="skipped"))
    run("unknown_schema", lambda d: d["result"].update(schema="proteus.harness.result/v2"))
    run("missing_fixture_pin", lambda d: d["manifest"]["identity"].pop("fixture_sha256"))
    run("missing_toolchain", lambda d: d["manifest"]["identity"].pop("toolchain"))
    run("bool_resource", lambda d: obs(d)["resources"].update(cpu_ns=True))
    run("negative_resource", lambda d: obs(d)["resources"].update(rss_peak_bytes=-1))
    run("wrong_environment", lambda d: d["result"]["identity"].update(environment_sha256="c" * 64))
    run("wrong_route", lambda d: d["result"]["identity"].update(route_id="other-route"))
    run("wrong_manifest_hash", lambda d: d["result"].update(manifest_sha256="c" * 64))
    run("empty_timing", lambda d: case(d).update(timing_samples_ms=[]))
    run("negative_timing", lambda d: case(d).update(timing_samples_ms=[-1]))
    run("false_settlement", lambda d: obs(d).update(settled=False))
    run("noncausal_cancel", lambda d: obs(d)["cancellation"].update(ack_seq=4))
    run("colliding_cancel_events", lambda d: obs(d)["cancellation"].update(ack_seq=1))
    run("duplicate_assertion", lambda d: case(d)["assertions"].append(copy.deepcopy(case(d)["assertions"][0])))
    run("missing_terminal_assertion", lambda d: case(d)["assertions"].pop(0))
    run("effect_hash_mismatch", lambda d: obs(d)["evidence_refs"].update(effects_sha256="c" * 64))
    run("wrong_terminal", lambda d: obs(d).update(terminal="completed"))
    run("wrong_cancel_request", lambda d: d["manifest"]["cases"][0].update(
        cancel_requested=False, expected_terminal="completed"), rebind=True)
    def no_run(d):
        case(d).update(status="NOT_RUN", executed=False, reason="not executed",
                       observation=None, assertions=[], timing_samples_ms=None)
    run("not_run_not_pass", no_run, want="NOT_RUN")
    run("failed_run_preserved", lambda d: case(d).update(status="FAIL", reason="authored failure"), want="FAIL")
    run("invalid_run_preserved", lambda d: case(d).update(status="INVALID", reason="invalid capture"), want="INVALID")
    def unsupported(d):
        no_run(d)
        d["manifest"]["cases"][0].update(support="unsupported", unsupported_reason="no equivalent route")
        case(d).update(status="UNSUPPORTED", reason="no equivalent route")
    run("predeclared_unsupported", unsupported, want="UNSUPPORTED", rebind=True)
    def duplicate_effect(d):
        e = {"operation_id": "write-1", "payload_sha256": "d" * 64, "outcome": "committed", "commit_seq": 0}
        obs(d)["effects"] = [e, {**e, "commit_seq": 4}]
        obs(d)["counters"]["effects_committed"] = 2
        obs(d)["evidence_refs"]["effects_sha256"] = digest(obs(d)["effects"])
    run("same_terminal_duplicate_effect", duplicate_effect)
    def unknown_effect(d):
        obs(d)["effects"] = [{"operation_id": "write-1", "payload_sha256": "d" * 64, "outcome": "unknown", "commit_seq": None}]
        obs(d)["counters"]["effects_unknown"] = 1
        obs(d)["evidence_refs"]["effects_sha256"] = digest(obs(d)["effects"])
    run("unknown_not_zero", unknown_effect)
    def observed_failure(d):
        duplicate_effect(d)
        case(d).update(status="FAIL", reason="duplicate effect observed")
    run("failed_duplicate_effect_preserved", observed_failure, want="FAIL")
    def unknown_failure(d):
        unknown_effect(d)
        case(d).update(status="FAIL", reason="effect unresolved")
    run("failed_unknown_effect_preserved", unknown_failure, want="FAIL")
    def committed_cancel(d):
        e = {"operation_id": "write-1", "payload_sha256": "d" * 64, "outcome": "committed", "commit_seq": 0}
        obs(d)["effects"] = [e]
        obs(d)["counters"]["effects_committed"] = 1
        obs(d)["evidence_refs"]["effects_sha256"] = digest([e])
        d["manifest"]["cases"][0]["expected_effects"] = [{k: v for k, v in e.items() if k != "commit_seq"}]
        d["manifest"]["cases"][0]["expected_counts"]["effects_committed"] = 1
    run("postcommit_cancel_preserves_effect", committed_cancel, want="PASS", rebind=True)
    def ordered_effects(d):
        a = {"operation_id": "A", "payload_sha256": "d" * 64, "outcome": "committed"}
        b = {"operation_id": "B", "payload_sha256": "e" * 64, "outcome": "committed"}
        d["manifest"]["cases"][0]["expected_effects"] = [a, b]
        d["manifest"]["cases"][0]["expected_counts"]["effects_committed"] = 2
        obs(d)["effects"] = [{**a, "commit_seq": 4}, {**b, "commit_seq": 8}]
        obs(d)["counters"]["effects_committed"] = 2
        obs(d)["evidence_refs"]["effects_sha256"] = digest(obs(d)["effects"])
        obs(d)["settled_seq"] = 10
        obs(d)["cancellation"]["settled_seq"] = 10
    run("ordered_effect_commit_sequence", ordered_effects, want="PASS", rebind=True)
    def reversed_effects(d):
        ordered_effects(d)
        obs(d)["effects"][0]["commit_seq"] = 8
        obs(d)["effects"][1]["commit_seq"] = 4
        obs(d)["evidence_refs"]["effects_sha256"] = digest(obs(d)["effects"])
    run("reverse_commit_order_not_pass", reversed_effects, rebind=True)
    def reversed_effect_failure(d):
        reversed_effects(d)
        case(d).update(status="FAIL", reason="effect commit order differs from oracle")
    run("reverse_commit_order_failure_preserved", reversed_effect_failure, want="FAIL", rebind=True)
    def retry(d):
        obs(d)["cancellation"].update(request_seq=5, ack_seq=6, settled_seq=7)
        obs(d)["settled_seq"] = 7
        obs(d)["model_attempts"] = [
            {"logical_id": "r1", "attempt_id": "a1", "start_seq": 1, "terminal_seq": 2, "outcome": "completed"},
            {"logical_id": "r1", "attempt_id": "a2", "start_seq": 3, "terminal_seq": 4, "outcome": "completed"}]
        obs(d)["counters"].update(model_requests=1, model_attempts=2, model_completed=2)
        d["manifest"]["cases"][0]["expected_counts"].update(model_requests=1, model_attempts=2, model_completed=2)
    run("retry_attempt_multiplicity", retry, want="PASS", rebind=True)
    def duplicate_attempt(d):
        retry(d)
        obs(d)["model_attempts"][1]["attempt_id"] = "a1"
    run("duplicate_attempt_id", duplicate_attempt, rebind=True)
    def duplicate_tool(d):
        obs(d)["tool_calls"] = [{"call_id": "t1", "outcome": "completed", "start_seq": 4, "terminal_seq": 5},
                                {"call_id": "t1", "outcome": "cancelled", "start_seq": 6, "terminal_seq": 7}]
        obs(d)["counters"].update(tools_started=2, tools_completed=1, tools_cancelled=1)
    run("duplicate_tool_terminal", duplicate_tool)
    def no_cases(d):
        d["manifest"]["cases"].clear()
        d["result"]["cases"].clear()
    run("empty_manifest", no_cases, rebind=True)
    run("not_run_with_observations", lambda d: case(d).update(
        status="NOT_RUN", executed=False, reason="not executed"))
    run("failed_without_execution", lambda d: case(d).update(
        status="FAIL", executed=False, reason="build failed"))
    def late_attempt(d):
        obs(d)["model_attempts"] = [{"logical_id": "r1", "attempt_id": "a1", "start_seq": 4, "terminal_seq": 5, "outcome": "completed"}]
        obs(d)["counters"].update(model_requests=1, model_attempts=1, model_completed=1)
        d["manifest"]["cases"][0]["expected_counts"].update(model_requests=1, model_attempts=1, model_completed=1)
    run("attempt_after_cancel_terminal", late_attempt, rebind=True)
    def suite_rewrite(d):
        d["manifest"]["cases"][0]["id"] = "replacement-suite"
        case(d)["id"] = "replacement-suite"
    run("caller_pin_blocks_suite_rewrite", suite_rewrite, rebind=True, retain_pin=True)
    def relabel(d):
        d["manifest"]["evidence_kind"] = "R-scoped"
        d["result"]["evidence_kind"] = "R-scoped"
    run("caller_pin_blocks_evidence_relabel", relabel, rebind=True, retain_pin=True)
    run("caller_pin_blocks_unsupported_rewrite", unsupported, rebind=True, retain_pin=True)
    def replace_build(d):
        d["manifest"]["identity"]["build_sha256"] = "c" * 64
        d["result"]["identity"]["build_sha256"] = "c" * 64
    run("caller_pin_blocks_build_rewrite", replace_build, rebind=True, retain_pin=True)
    run("resource_integer_overflow", lambda d: obs(d)["resources"].update(cpu_ns=MAX_INT + 1))
    run("counter_integer_overflow", lambda d: obs(d)["counters"].update(model_attempts=MAX_INT + 1))
    run("cancel_settlement_alias", lambda d: obs(d)["cancellation"].update(settled_seq=4))
    def unfinished_model(d):
        retry(d)
        obs(d)["model_attempts"][1].update(outcome="inflight", terminal_seq=None)
        obs(d)["counters"].update(model_completed=1, model_inflight=1)
    run("unterminated_model_not_pass", unfinished_model, rebind=True)
    def unfinished_failure(d):
        unfinished_model(d)
        obs(d).update(terminal="unsettled", settled=False, settled_seq=None)
        obs(d)["cancellation"].update(settled=False, settled_seq=None)
        case(d).update(status="FAIL", reason="model still inflight")
    run("inflight_failure_preserved", unfinished_failure, want="FAIL", rebind=True)
    def late_tool(d):
        obs(d)["tool_calls"] = [{"call_id": "late", "outcome": "completed",
                                "start_seq": 4, "terminal_seq": 5}]
        obs(d)["counters"].update(tools_started=1, tools_completed=1)
        d["manifest"]["cases"][0]["expected_counts"].update(tools_started=1, tools_completed=1)
    run("tool_after_settlement", late_tool, rebind=True)
    def late_effect(d):
        committed_cancel(d)
        obs(d)["effects"][0]["commit_seq"] = 4
        obs(d)["evidence_refs"]["effects_sha256"] = digest(obs(d)["effects"])
    run("effect_after_settlement", late_effect, rebind=True)
    def reversed_model(d):
        retry(d)
        obs(d)["model_attempts"][0]["terminal_seq"] = 0
    run("model_terminal_before_start", reversed_model, rebind=True)
    def colliding_events(d):
        retry(d)
        obs(d)["model_attempts"][1]["start_seq"] = 2
    run("distinct_event_collision", colliding_events, rebind=True)
    base = example()
    for name, pin in (("missing_caller_pin", None), ("wrong_caller_pin", "c" * 64)):
        need(check(base, pin)["status"] == "INVALID", name + ": accepted")
        passed.append(name)
    for name, raw in (("oversize_input", " " * (MAX_INPUT + 1)),
                      ("deep_json", '{"a":' * 1500 + '0' + '}' * 1500),
                      ("overflow_json_float", '{"manifest":{"parameters":{"x":1e9999}},"result":{}}')):
        need(check_text(raw, digest(base["manifest"]))["status"] == "INVALID", name + ": accepted")
        passed.append(name)
    for name, text in (("duplicate_json_key", '{"x":1,"x":2}'),
                       ("nan_json", '{"x":NaN}'), ("infinity_json", '{"x":Infinity}')):
        try:
            strict_loads(text)
        except (Invalid, ValueError):
            passed.append(name)
        else:
            raise Invalid(name + ": parser accepted invalid JSON")
    return {"status": "PASS", "control_count": len(passed), "controls": passed,
            "scope": "Authored validator controls only; no harness, APIs or filesystem writes."}

def main():
    if sys.argv[1:] == ["--self-test"]:
        output = self_test()
        print(json.dumps(output, sort_keys=True))
        return 0
    if sys.argv[1:] == ["--example"]:
        print(json.dumps(example(), indent=2, sort_keys=True))
        return 0
    if len(sys.argv) != 3 or sys.argv[1] != "--expected-manifest-sha256":
        print(json.dumps({"status": "INVALID", "error": "require --expected-manifest-sha256 HASH"}))
        return 2
    try:
        output = check_text(sys.stdin.read(MAX_INPUT + 1), sys.argv[2])
    except (Invalid, ValueError, TypeError, OverflowError, RecursionError) as exc:
        output = {"schema": C_SCHEMA, "status": "INVALID", "error": str(exc)}
    print(json.dumps(output, sort_keys=True))
    return EXIT[output["status"]]

if __name__ == "__main__":
    raise SystemExit(main())
