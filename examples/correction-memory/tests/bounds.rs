mod common;
use common::*;
use proteus_example_correction_memory::{
    config::*,
    store::Store,
    types::*,
    util::{canonical, sha256},
    *,
};
use serde_json::json;

#[test]
fn config_and_request_exact_limits_and_one_over() {
    let mut c = config();
    c.store_id = "s".repeat(64);
    c.evidence_policy.sources = (0..64)
        .map(|n| Source {
            source_id: format!("s{n}"),
            path: format!("evidence/{n}.txt"),
        })
        .collect();
    assert!(CorrectionMemory::new(c.clone()).is_ok());
    c.evidence_policy.sources.push(Source {
        source_id: "extra".into(),
        path: "extra.txt".into(),
    });
    assert_eq!(
        CorrectionMemory::new(c).err().unwrap().to_string(),
        "config_sources_count"
    );
    let c = config();
    let mut r = request();
    r.key = "k".repeat(128);
    r.new_text = "t".repeat(4096);
    r.evidence.claims = (0..32)
        .map(|n| Claim {
            claim_id: format!("claim{n}"),
            start_byte: 0,
            end_byte: 512,
            quote: "a".repeat(512),
        })
        .collect();
    r.validate(&c).unwrap();
    r.evidence.claims.push(r.evidence.claims[0].clone());
    assert_eq!(
        r.validate(&c).unwrap_err().to_string(),
        "evidence_claim_count"
    );
    r.evidence.claims.pop();
    r.new_text.push('x');
    assert_eq!(r.validate(&c).unwrap_err().to_string(), "new_text_size");
}
#[test]
fn full_quote_count_and_bytes_have_a_valid_receipt_control() {
    let e = Env::new();
    let mut r = request().evidence;
    r.claims = (0..32)
        .map(|n| Claim {
            claim_id: format!("c{n}"),
            start_byte: 0,
            end_byte: 512,
            quote: "a".repeat(512),
        })
        .collect();
    r.validate(&e.config).unwrap();
    let mut o = observation(e.cwd(), &r, "current-call");
    o.source_bytes = 65536;
    proteus_example_correction_memory::evidence::validate_observation(
        &e.config,
        e.cwd(),
        &r,
        "current-call",
        &o,
    )
    .unwrap();
    r.claims[0].quote.push('a');
    r.claims[0].end_byte += 1;
    assert_eq!(
        r.validate(&e.config).unwrap_err().to_string(),
        "evidence_total_quote_size"
    );
}
#[test]
fn operation_capacity_preserves_existing_replay() {
    let e = Env::new();
    e.init();
    let mut request = e.prepared();
    let store = Store::resolve(&e.config, e.module.policy_sha256(), e.cwd()).unwrap();
    let o = observation(e.cwd(), &request.proposal.evidence, "verified-now");
    for n in 0..MAX_OPERATIONS {
        request.operation_id = format!("op-{n}");
        store
            .apply(&request, &o, |_| Ok(()), |r, _| Ok(r.outcome.clone()))
            .unwrap();
    }
    request.operation_id = "one-over".into();
    let error = store
        .apply(&request, &o, |_| Ok(()), |_, _| Ok(()))
        .unwrap_err();
    assert_eq!(error.to_string(), "operation_capacity");
    assert!(e.operation("one-over")["record"].is_null());
    request.operation_id = "op-0".into();
    assert!(store.before_verify(&request).unwrap().is_some());
    assert_eq!(e.entry()["revision"], 1);
}
#[test]
fn key_capacity_has_exact_maximum_positive_control() {
    let e = Env::new();
    e.init();
    let mut request = e.prepared();
    let store = Store::resolve(&e.config, e.module.policy_sha256(), e.cwd()).unwrap();
    let o = observation(e.cwd(), &request.proposal.evidence, "verified-now");
    for n in 0..MAX_KEYS {
        request.operation_id = format!("op-{n}");
        request.proposal.key = format!("key-{n}");
        let outcome = store
            .apply(&request, &o, |_| Ok(()), |r, _| Ok(r.outcome.clone()))
            .unwrap();
        assert_eq!(outcome.resulting_revision, Some(1));
    }
    request.operation_id = "over-key".into();
    request.proposal.key = "one-over".into();
    assert_eq!(
        store
            .apply(&request, &o, |_| Ok(()), |_, _| Ok(()))
            .unwrap_err()
            .to_string(),
        "key_capacity"
    );
    assert!(e.operation("over-key")["record"].is_null());
}
#[test]
fn revision_exhaustion_uses_a_consistent_max_revision_fixture() {
    let e = Env::new();
    e.init();
    let first = e.prepared();
    assert!(e.apply(&first, &mut e.host()).ok);
    // Authored historical fixture representing MAX-1 -> MAX; every stored
    // request/outcome digest and entry link is kept internally consistent.
    let mut record: store::Record =
        serde_json::from_value(e.operation(&first.operation_id)["record"].clone()).unwrap();
    record.request.proposal.expected_revision = MAX_REVISION - 1;
    record.outcome.expected_revision = MAX_REVISION - 1;
    record.outcome.observed_revision = MAX_REVISION - 1;
    record.outcome.resulting_revision = Some(MAX_REVISION);
    record.outcome.proposal_sha256 =
        sha256(&canonical(&record.request.proposal, MAX_PROPOSAL).unwrap());
    let bytes = canonical(&record.request, MAX_PROPOSAL + 128).unwrap();
    record.outcome.request_sha256 = sha256(&bytes);
    let mut conn = rusqlite::Connection::open(e.db()).unwrap();
    let tx = conn.transaction().unwrap();
    tx.execute(
        "UPDATE operations SET request=?1,request_sha256=?2,outcome=?3 WHERE operation_id=?4",
        rusqlite::params![
            bytes,
            record.outcome.request_sha256,
            serde_json::to_string(&record.outcome).unwrap(),
            first.operation_id
        ],
    )
    .unwrap();
    tx.execute("UPDATE entries SET revision=?1", [MAX_REVISION])
        .unwrap();
    tx.commit().unwrap();
    drop(conn);
    assert_eq!(e.entry()["revision"], json!(MAX_REVISION));
    let mut request = e.prepared();
    request.operation_id = "at-max".into();
    assert_eq!(request.proposal.expected_revision, MAX_REVISION);
    fail(&e.apply(&request, &mut e.host()), "revision_exhausted");
    assert!(e.operation("at-max")["record"].is_null());
}
