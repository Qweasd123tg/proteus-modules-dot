mod common;
use common::*;
use proteus_example_correction_memory::{evidence::EVIDENCE_KEY, *};
use serde_json::{Value, json};

fn reject(mutator: impl Fn(&mut Value) + Send + Sync + 'static, reason: &str) {
    let e = Env::new();
    e.init();
    let request = e.prepared();
    let mut host = e.host();
    host.mutate = Box::new(move |_, r| mutator(&mut r.metadata));
    fail(&e.apply(&request, &mut host), reason);
    assert_eq!(host.count(), 1);
    assert_eq!(e.entry()["revision"], 0);
    assert!(e.operation(&request.operation_id)["record"].is_null());
}
#[test]
fn valid_host_duration_and_false_flags_are_accepted() {
    let e = Env::new();
    e.init();
    let request = e.prepared();
    let mut h = e.host();
    h.mutate = Box::new(|_, r| {
        for flag in [
            "output_truncated",
            "error_truncated",
            "canceled",
            "timed_out",
        ] {
            r.metadata[flag] = json!(false);
        }
    });
    assert!(e.apply(&request, &mut h).ok);
}
#[test]
fn wrong_receipt_call_id() {
    reject(
        |m| m[EVIDENCE_KEY]["verifier_call_id"] = json!("wrong-current-call"),
        "evidence_call_id",
    )
}
#[test]
fn wrong_config_digest() {
    reject(
        |m| m[EVIDENCE_KEY]["config_sha256"] = json!("b".repeat(64)),
        "evidence_config_digest",
    )
}
#[test]
fn wrong_source() {
    reject(
        |m| m[EVIDENCE_KEY]["source_id"] = json!("wrong-source"),
        "evidence_source",
    )
}
#[test]
fn wrong_configured_path() {
    reject(
        |m| m[EVIDENCE_KEY]["configured_path"] = json!("evidence/wrong.txt"),
        "evidence_path",
    )
}
#[test]
fn wrong_observed_path() {
    reject(
        |m| m[EVIDENCE_KEY]["observed_path"] = json!("/elsewhere/release.txt"),
        "evidence_path",
    )
}
#[test]
fn wrong_content_digest() {
    reject(
        |m| m[EVIDENCE_KEY]["content_sha256"] = json!("b".repeat(64)),
        "evidence_content_digest",
    )
}
#[test]
fn wrong_quote_digest() {
    reject(
        |m| m[EVIDENCE_KEY]["verified_claims"][0]["quote_sha256"] = json!("b".repeat(64)),
        "evidence_quote_digest",
    )
}
#[test]
fn wrong_offsets() {
    reject(
        |m| m[EVIDENCE_KEY]["verified_claims"][0]["end_byte"] = json!(12),
        "evidence_claim_span",
    )
}
#[test]
fn omitted_claim() {
    reject(
        |m| m[EVIDENCE_KEY]["verified_claims"] = json!([]),
        "evidence_claim_coverage",
    )
}
#[test]
fn extra_claim() {
    reject(
        |m| {
            let extra = m[EVIDENCE_KEY]["verified_claims"][0].clone();
            m[EVIDENCE_KEY]["verified_claims"]
                .as_array_mut()
                .unwrap()
                .push(extra);
        },
        "evidence_claim_coverage",
    )
}
#[test]
fn overclaimed_origin() {
    reject(
        |m| m[EVIDENCE_KEY]["origin_verified"] = json!(true),
        "evidence_scope",
    )
}
#[test]
fn overclaimed_semantics() {
    reject(
        |m| m[EVIDENCE_KEY]["semantic_entailment"] = json!("proven"),
        "evidence_scope",
    )
}
#[test]
fn null_duration() {
    reject(|m| m["duration_ms"] = Value::Null, "verifier_duration")
}
#[test]
fn unknown_metadata() {
    reject(
        |m| m["unrecognized"] = json!(false),
        "verifier_unknown_metadata",
    )
}
#[test]
fn truncated_flag() {
    reject(|m| m["output_truncated"] = json!(true), "verifier_flag")
}
#[test]
fn null_flag() {
    reject(|m| m["canceled"] = Value::Null, "verifier_flag")
}
#[test]
fn fractional_integer_field() {
    reject(
        |m| m[EVIDENCE_KEY]["source_bytes"] = json!(26.0),
        "verifier_evidence_shape",
    )
}
#[test]
fn callback_wrong_outer_id_with_valid_receipt_rejects() {
    let e = Env::new();
    e.init();
    let request = e.prepared();
    let mut h = e.host();
    h.mutate = Box::new(|_, r| r.call_id = "wrong-outer".into());
    fail(&e.apply(&request, &mut h), "verifier_result_call_id");
    assert_eq!(e.entry()["revision"], 0);
}
#[test]
fn duplicate_claim_and_permutation_use_otherwise_valid_two_claims() {
    let e = Env::new();
    e.init();
    let mut request = e.prepared();
    request.proposal.evidence.claims.push(
        serde_json::from_value(
            json!({"claim_id":"publish","start_byte":14,"end_byte":27,"quote":"publish=false"}),
        )
        .unwrap(),
    );
    let mut duplicate = e.host();
    duplicate.mutate = Box::new(|_, r| {
        r.metadata[EVIDENCE_KEY]["verified_claims"][1] =
            r.metadata[EVIDENCE_KEY]["verified_claims"][0].clone();
    });
    fail(
        &e.apply(&request, &mut duplicate),
        "evidence_duplicate_claim",
    );
    let mut permuted = e.host();
    permuted.mutate = Box::new(|_, r| {
        r.metadata[EVIDENCE_KEY]["verified_claims"]
            .as_array_mut()
            .unwrap()
            .reverse()
    });
    assert!(e.apply(&request, &mut permuted).ok);
}
#[test]
fn duplicate_json_keys_are_not_silently_selected() {
    let e = Env::new();
    e.init();
    let request = e.prepared();
    let o = observation(e.cwd(), &request.proposal.evidence, "some-call");
    let receipt = serde_json::to_string(&o).unwrap();
    let raw = format!(
        "{{\"call_id\":\"some-call\",\"ok\":true,\"output\":\"\",\"content\":[],\"error\":null,\"metadata\":{{\"{EVIDENCE_KEY}\":{receipt},\"duration_ms\":1,\"duration_ms\":2}}}}"
    );
    let error = proteus_example_correction_memory::evidence::validate(
        &e.config,
        e.cwd(),
        &request.proposal.evidence,
        "some-call",
        &raw,
    )
    .unwrap_err();
    assert_eq!(error.to_string(), "verifier_json");
}
