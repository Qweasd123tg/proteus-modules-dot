#!/usr/bin/env python3
"""Validate authored fixture outputs and exact test names, not host authenticity."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import tomllib

KEY = "proteus.example.evidence_spans"
CALL_ID = "authored-quote-audit"
POSITIVE_OUTPUT = "Verified 2 exact quote spans in one host-read artifact. Source origin and semantic entailment were not verified."

def require(value, message):
    if not value:
        raise ValueError(message)

def exact_equal(a, b):
    if type(a) is not type(b):
        return False
    if isinstance(a, dict):
        return a.keys() == b.keys() and all(exact_equal(a[k], b[k]) for k in a)
    if isinstance(a, list):
        return len(a) == len(b) and all(exact_equal(x, y) for x, y in zip(a, b))
    return a == b

def pairs(values):
    out = {}
    for k, v in values:
        require(k not in out, "duplicate JSON key")
        out[k] = v
    return out

def load(path):
    return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=pairs,
                      parse_constant=lambda value: (_ for _ in ()).throw(ValueError("non-finite JSON")))

def sha(data):
    return hashlib.sha256(data).hexdigest()

def initialize_evidence_leaf(path):
    # Atomic creation fails for an existing directory, file, or symlink. Never clean it.
    path.mkdir()

def verify_controls(text, expected):
    require(len(expected) == 23 and len(set(expected)) == 23, "expected named control set")
    names = re.findall(r"^(test_\w+) \(__main__\.Controls\.(test_\w+)\) \.\.\. ok$", text, re.M)
    require(all(a == b for a, b in names), "control identity mismatch")
    require(Counter(a for a, _ in names) == Counter(expected), "exact named controls differ")
    summaries = re.findall(r"^Ran (\d+) tests in [0-9.]+s$", text, re.M)
    require(summaries == ["23"], "control summary differs")
    require(text.rstrip().endswith("\nOK") and not re.search(r"^(FAILED|ERROR:|FAIL:)", text, re.M),
            "controls did not finish successfully")
    return {"passed": 23, "scope": "synthetic validator controls only", "names": sorted(expected)}

def canonical_config(config):
    return {"schema_version": config["schema_version"],
            "sources": [{"id": s["id"], "path": s["path"]} for s in config["sources"]]}

def expected_receipt(workspace):
    config = canonical_config(load(workspace / "fixtures/config.json"))
    request = load(workspace / "fixtures/request.json")
    content = (workspace / "fixtures/source.txt").read_bytes()
    require(len(content) == 40, "fixture must remain 40 bytes")
    require(sha(content) == "8d01afa7f92eb5599e57a9a627240c2827135cdc842d30b19c11aeeb789a2bd5",
            "fixture content changed")
    profile = tomllib.loads((workspace / "profile.fragment.toml").read_text())
    require(exact_equal(profile["module_config"]["tool"]["evidence.verify_spans"], config),
            "profile/config mismatch")
    require(request["expected_sha256"] == sha(content), "request source digest mismatch")
    source = config["sources"][0]
    require(len(config["sources"]) == 1 and request["source_id"] == source["id"], "fixture source identity")
    claims = []
    for claim in request["claims"]:
        a, b = claim["start_byte"], claim["end_byte"]
        require(type(a) is int and type(b) is int and 0 <= a < b <= len(content), "fixture span")
        quote = content[a:b].decode("utf-8")
        require(quote == claim["quote"], "fixture quote")
        claims.append({"claim_id": claim["claim_id"], "start_byte": a, "end_byte": b,
                       "quote_sha256": sha(quote.encode())})
    require(len(claims) == 2 and len({c["claim_id"] for c in claims}) == 2, "fixture claims")
    return {"schema_version": 1, "status": "exact_byte_match", "scope": "observed_host_read_bytes",
            "source_id": source["id"], "configured_path": source["path"],
            "observed_path": "/authored-fixture/" + source["path"],
            "config_sha256": sha(json.dumps(config, ensure_ascii=False, separators=(",", ":")).encode()),
            "content_sha256": sha(content), "source_bytes": len(content),
            "verifier_call_id": CALL_ID, "verified_claims": claims,
            "origin_verified": False, "semantic_entailment": "not_evaluated"}

def verify_outputs(workspace, positive, negative):
    for outer in (positive, negative):
        require(outer["host_kind"] == "synthetic_authored_fixture", "incorrect host label")
        require(outer["scope"] == "exact_quote_bytes_not_semantic_claim_truth", "incorrect scope label")
    p, n = positive["result"], negative["result"]
    require(p["ok"] is True and p.get("error") is None, "positive result failed")
    require(p.get("output") == POSITIVE_OUTPUT, "positive disclaimer/count mismatch")
    require(p["call_id"] == CALL_ID and n["call_id"] == CALL_ID, "call identity")
    require(p.get("content") == [] and n.get("content") == [], "unexpected structured content")
    require(set(p["metadata"]) == {KEY}, "unexpected positive metadata")
    actual = dict(p["metadata"][KEY])
    reader = actual.pop("reader_call_id", None)
    require(type(reader) is str and 1 <= len(reader) <= 128 and reader != CALL_ID, "reader identity")
    require(exact_equal(actual, expected_receipt(workspace)), "exact typed receipt mismatch")
    require(n["ok"] is False, "negative unexpectedly passed")
    require(n.get("error") == "claim quote does not exactly match span", "negative diagnostic mismatch")
    require(n.get("metadata") is None, "negative metadata must be canonical null")
    require(n.get("output") == "", "negative output must be empty")
    return {"positive_exact_receipt": True, "negative_exact_diagnostic_no_witness": True}

def verify_tests(text, expected):
    require(len(expected) == 39 and len(set(expected)) == 39, "expected named test set")
    summaries = re.findall(r"^test result: (\w+)\. (\d+) passed; (\d+) failed; (\d+) ignored; (\d+) measured; (\d+) filtered out;", text, re.M)
    require(bool(summaries), "missing test summaries")
    require(all(s[0] == "ok" and all(int(x) == 0 for x in s[2:]) for s in summaries),
            "failed/ignored/measured/filtered tests")
    require(Counter(int(s[1]) for s in summaries if int(s[1])) == Counter([5, 32, 2]),
            "target test counts differ")
    names = re.findall(r"^test (.+) \.\.\. ok$", text, re.M)
    require(Counter(names) == Counter(expected), "exact named tests differ")
    return {"passed": 39, "failed": 0, "ignored": 0, "measured": 0, "filtered": 0,
            "names": sorted(names), "nonempty_target_counts": [5, 32, 2]}

def verify(workspace, artifacts):
    report = verify_outputs(workspace, load(artifacts / "positive.json"), load(artifacts / "negative.json"))
    report["synthetic_controls"] = verify_controls((artifacts / "validator-controls.log").read_text(),
                                                  load(workspace / "ci/expected-controls.json"))
    report["rust_tests"] = verify_tests((artifacts / "workspace-tests.log").read_text(),
                                      load(workspace / "ci/expected-tests.json"))
    report.update(status="passed", scope="authored module/helper and own-executable wire; synthetic reader",
                  actual_core_invocation=False, upstream_suites_run=False)
    return report

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path)
    parser.add_argument("--artifacts", type=Path)
    parser.add_argument("--initialize-leaf", type=Path)
    parser.add_argument("--controls-only", action="store_true")
    args = parser.parse_args()
    if args.initialize_leaf is not None:
        require(args.workspace is None and args.artifacts is None and not args.controls_only,
                "initialize takes no validation arguments")
        initialize_evidence_leaf(args.initialize_leaf)
        return
    require(args.workspace is not None and args.artifacts is not None, "workspace/artifacts required")
    if args.controls_only:
        report = verify_controls((args.artifacts / "validator-controls.log").read_text(),
                                 load(args.workspace / "ci/expected-controls.json"))
        (args.artifacts / "validator-controls-verification.json").write_text(json.dumps(report, indent=2) + "\n")
        print(json.dumps(report))
        return
    report = verify(args.workspace, args.artifacts)
    (args.artifacts / "fixture-verification.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"status": report["status"], "named_rust_tests": 39, "actual_core_invocation": False}))

if __name__ == "__main__":
    main()
