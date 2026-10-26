#[path = "../examples/support/mod.rs"]
mod support;
use proteus_example_correction_memory::*;
use serde_json::json;
use support::*;

#[test]
fn actual_modules_observe_owned_artifact_and_persist_cas() {
    let report = workflow().unwrap();
    assert_eq!(report["actual_core"], false);
    assert_eq!(report["nested_calls"].as_array().unwrap().len(), 8);
}
#[test]
fn artifact_changed_between_prepare_and_apply_refuses_fresh_commit() {
    let mut f = Fixture::new().unwrap();
    assert!(f.call(INIT, json!({})).unwrap().ok);
    let request = f
        .prepare("Still draft.", "channel", 0, "channel=draft")
        .unwrap();
    std::fs::write(
        f.dir.path().join("evidence/release.txt"),
        "channel=public\npublish=true\n",
    )
    .unwrap();
    let result = f.apply(&request).unwrap();
    assert!(!result.ok);
    assert!(result.error.unwrap().contains("verifier_failed"));
    let operation = f
        .call(
            READ,
            json!({"kind":"operation","operation_id":request.operation_id}),
        )
        .unwrap();
    assert!(operation.metadata[RESULT_KEY]["result"]["record"].is_null());
}
#[test]
fn actual_verifier_wrong_reader_method_and_id_cannot_mint_observation() {
    for fault in [ReaderFault::WrongMethod, ReaderFault::WrongCallId] {
        let mut f = Fixture::new().unwrap();
        assert!(f.call(INIT, json!({})).unwrap().ok);
        let request = f
            .prepare("Still draft.", "channel", 0, "channel=draft")
            .unwrap();
        f.router.fault = fault;
        let result = f.apply(&request).unwrap();
        assert!(!result.ok);
        assert!(result.error.unwrap().contains("verifier_failed"));
        let current = f
            .call(READ, json!({"kind":"entry","key":"release.status"}))
            .unwrap();
        assert_eq!(current.metadata[RESULT_KEY]["result"]["revision"], 0);
    }
}
#[test]
fn actual_nested_reader_cancellation_cannot_commit() {
    let mut f = Fixture::new().unwrap();
    assert!(f.call(INIT, json!({})).unwrap().ok);
    let request = f
        .prepare("Still draft.", "channel", 0, "channel=draft")
        .unwrap();
    f.router.fault = ReaderFault::CancelAfterRead;
    let result = f.apply(&request).unwrap();
    assert!(!result.ok);
    assert!(result.metadata.get(RESULT_KEY).is_none());
    f.router
        .canceled
        .store(false, std::sync::atomic::Ordering::SeqCst);
    let operation = f
        .call(
            READ,
            json!({"kind":"operation","operation_id":request.operation_id}),
        )
        .unwrap();
    assert!(operation.metadata[RESULT_KEY]["result"]["record"].is_null());
}
