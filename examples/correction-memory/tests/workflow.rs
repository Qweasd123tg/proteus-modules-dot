mod common;
use common::*;
use proteus_example_correction_memory::{util::canonical, *};
use proteus_module_sdk::tool::ToolModule;
use serde_json::json;
#[test]
fn load_list_read_prepare_never_initialize() {
    let e = Env::new();
    assert_eq!(e.module.definitions().len(), 4);
    assert!(!e.db().exists());
    fail(
        &e.call(
            READ,
            json!({"kind":"entry","key":"release.status"}),
            &mut e.host(),
        ),
        "not_initialized",
    );
    let mut host = e.host();
    fail(
        &e.call(PREPARE, serde_json::to_value(request()).unwrap(), &mut host),
        "not_initialized",
    );
    assert_eq!(host.count(), 0);
    assert!(!e.db().exists());
}
#[test]
fn initialize_is_explicit_and_idempotent() {
    let e = Env::new();
    let a = e.call(INIT, json!({}), &mut e.host());
    let b = e.call(INIT, json!({}), &mut e.host());
    assert!(a.ok && b.ok);
    assert_eq!(a.metadata, b.metadata);
    assert_eq!(e.entry()["revision"], 0);
}
#[test]
fn prepare_apply_read_replay_update_and_historical_conflict() {
    let e = Env::new();
    e.init();
    let a = e.prepared();
    let mut b = a.clone();
    b.operation_id = "op-conflict".into();
    b.proposal.new_text = "Do not publish.".into();
    let mut host = e.host();
    let first = e.apply(&a, &mut host);
    assert_eq!(host.count(), 1);
    assert_eq!(outcome(&first)["resulting_revision"], 1);
    let conflict = e.apply(&b, &mut e.host());
    assert_eq!(outcome(&conflict)["decision"], "conflict");
    assert_eq!(outcome(&conflict)["observed_revision"], 1);
    assert_eq!(e.entry()["revision"], 1);
    let mut replay_host = e.host();
    replay_host.raw = Some("not JSON".into());
    let replay = e.apply(&a, &mut replay_host);
    assert_eq!(outcome(&replay), outcome(&first));
    assert_eq!(replay_host.count(), 0);
    assert_eq!(replay.metadata[RESULT_KEY]["audit"]["replayed"], true);
    let restarted = CorrectionMemory::new(e.config.clone()).unwrap();
    let again = invoke(
        &restarted,
        e.cwd(),
        APPLY,
        serde_json::to_value(&a).unwrap(),
        &mut replay_host,
    );
    assert_eq!(outcome(&again), outcome(&first));
    assert_eq!(replay_host.count(), 0);
    let mut c = e.prepared();
    c.operation_id = "op-update".into();
    c.proposal.new_text = "Still draft, second proposal.".into();
    assert_eq!(
        outcome(&e.apply(&c, &mut e.host()))["resulting_revision"],
        2
    );
    let historical = e.apply(&b, &mut replay_host);
    assert_eq!(outcome(&historical), outcome(&conflict));
    assert_eq!(e.entry()["revision"], 2);
    assert_eq!(
        canonical(&outcome(&historical), 4096).unwrap(),
        canonical(&outcome(&conflict), 4096).unwrap()
    );
}
#[test]
fn changed_payload_never_reuses_committed_operation() {
    let e = Env::new();
    e.init();
    let r = e.prepared();
    assert!(e.apply(&r, &mut e.host()).ok);
    for field in [
        "text",
        "key",
        "revision",
        "instance",
        "cwd",
        "path",
        "policy",
        "sourcehash",
        "quote",
        "claimid",
    ] {
        let mut changed = r.clone();
        let p = &mut changed.proposal;
        match field {
            "text" => p.new_text = "changed".into(),
            "key" => p.key = "other".into(),
            "revision" => p.expected_revision = 1,
            "instance" => p.database_instance_id = "b".repeat(32),
            "cwd" => p.workspace_cwd = "/different".into(),
            "path" => p.database_path = "store/other.sqlite".into(),
            "policy" => p.policy_sha256 = "b".repeat(64),
            "sourcehash" => p.evidence.expected_sha256 = "b".repeat(64),
            "quote" => p.evidence.claims[0].quote = "CHANNEL=DRAFT".into(),
            "claimid" => p.evidence.claims[0].claim_id = "other".into(),
            _ => unreachable!(),
        }
        let mut host = e.host();
        fail(&e.apply(&changed, &mut host), "operation_payload_mismatch");
        assert_eq!(host.count(), 0);
    }
    assert_eq!(e.entry()["revision"], 1);
}
#[test]
fn failed_evidence_does_not_bind_id() {
    let e = Env::new();
    e.init();
    let r = e.prepared();
    let mut host = e.host();
    host.raw = Some("{}".into());
    fail(&e.apply(&r, &mut host), "verifier_result_shape");
    assert!(e.operation(&r.operation_id)["record"].is_null());
    assert_eq!(e.entry()["revision"], 0);
    assert!(e.apply(&r, &mut e.host()).ok);
}
#[test]
fn immutable_policy_rejects_old_profile_replay() {
    let e = Env::new();
    e.init();
    let r = e.prepared();
    assert!(e.apply(&r, &mut e.host()).ok);
    let mut config = e.config.clone();
    config.evidence_policy.expected_config_sha256 = "b".repeat(64);
    let changed = CorrectionMemory::new(config).unwrap();
    let mut host = e.host();
    fail(
        &invoke(
            &changed,
            e.cwd(),
            APPLY,
            serde_json::to_value(r).unwrap(),
            &mut host,
        ),
        "store_policy_mismatch",
    );
    assert_eq!(host.count(), 0);
}
#[test]
fn request_is_data_not_a_caller_receipt() {
    let e = Env::new();
    e.init();
    let r = e.prepared();
    let mut forged = serde_json::to_value(r).unwrap();
    forged["proposal"]["verification_receipt"] = json!({"ok":true});
    let mut host = e.host();
    fail(&e.call(APPLY, forged, &mut host), "apply_arguments");
    assert_eq!(host.count(), 0);
    assert_eq!(e.entry()["revision"], 0);
}

#[test]
fn cancellation_before_verifier_and_after_valid_callback_prevents_new_record() {
    use std::sync::atomic::Ordering;
    let e = Env::new();
    e.init();
    let request = e.prepared();
    let mut before = e.host();
    before.canceled.store(true, Ordering::SeqCst);
    fail(&e.apply(&request, &mut before), "canceled");
    assert_eq!(before.count(), 0);
    let mut after = e.host();
    let canceled = after.canceled.clone();
    after.after = Box::new(move || canceled.store(true, Ordering::SeqCst));
    fail(&e.apply(&request, &mut after), "canceled");
    assert_eq!(after.count(), 1);
    assert_eq!(e.entry()["revision"], 0);
    assert!(e.operation(&request.operation_id)["record"].is_null());
}
