use proteus_example_hermes_verify_evidence::{
    Config, MODULE_ID, RECEIPT_KEY, VerifyEvidence, inspect_history,
};
use proteus_module_sdk::{
    Export,
    contracts::{
        contracts::{
            ExecutionAttribution, HookEvent, HookInput, HookResponse,
            ProcessComponentExportInitialize, ProcessModuleComposition,
        },
        domain::{AgentOutput, AgentTask, ToolCall, ToolResult, new_execution_id},
        model_standard::{CanonicalMessage, ContentPart, MessageRole, PartProvenance, PartScope},
    },
};
use serde_json::json;

fn config() -> serde_json::Value {
    json!({"mutating_tools":["write_file"], "verification_tools":["verify_tests"],
        "max_nudges":2, "max_history_parts":100, "on_exhaustion":"error"})
}
fn binding(config: serde_json::Value) -> ProcessComponentExportInitialize {
    ProcessComponentExportInitialize::new(
        "hook",
        MODULE_ID,
        "v6",
        ProcessModuleComposition::OrderedMany,
        config,
        Vec::<String>::new(),
    )
}
fn module() -> VerifyEvidence {
    VerifyEvidence::new(binding(config())).unwrap()
}
fn call(id: &str, name: &str) -> CanonicalMessage {
    CanonicalMessage::new(
        MessageRole::Assistant,
        vec![ContentPart::ToolCall {
            call: ToolCall::new(id, name, json!({})),
        }],
    )
}
fn result(id: &str, ok: bool, receipt: bool) -> CanonicalMessage {
    let metadata = if receipt {
        json!({RECEIPT_KEY:{"schema_version":1,"status":"passed",
        "cwd":"/workspace","checks_executed":["unit:parser"]}})
    } else {
        json!({})
    };
    let value = if ok {
        ToolResult::ok(id.into(), "All tests passed")
    } else {
        ToolResult::error(id.into(), "failed")
    }
    .with_metadata(metadata);
    CanonicalMessage::new(
        MessageRole::Tool,
        vec![ContentPart::ToolResult { result: value }],
    )
    .with_tool_call_id(id.into())
}
fn dirty() -> Vec<CanonicalMessage> {
    vec![call("w", "write_file"), result("w", true, false)]
}
fn good() -> Vec<CanonicalMessage> {
    let mut history = dirty();
    history.extend([call("v", "verify_tests"), result("v", true, true)]);
    history
}
fn input(history: Vec<CanonicalMessage>, attempt: u32) -> HookInput {
    HookInput {
        event: HookEvent::BeforeStop {
            task: AgentTask::new("task", "/workspace".into()),
            history,
            output: AgentOutput::text("done"),
            attempt,
            continuation: None,
        },
        attribution: ExecutionAttribution::detached(new_execution_id()),
        cwd: "/workspace".into(),
        conversation: None,
    }
}
fn evaluate(history: Vec<CanonicalMessage>) -> HookResponse {
    module().evaluate(&input(history, 0), || false).unwrap()
}
fn continues(response: HookResponse) {
    assert!(matches!(response, HookResponse::ContinueTurn { .. }));
}

#[test]
fn no_mutation_has_no_gate() {
    assert_eq!(
        evaluate(vec![CanonicalMessage::text(MessageRole::User, "hello")]),
        HookResponse::Continue
    );
}
#[test]
fn host_shaped_fresh_receipt_fixture_releases_gate() {
    assert_eq!(evaluate(good()), HookResponse::Continue);
}
#[test]
fn mutation_without_evidence_continues() {
    continues(evaluate(dirty()));
}
#[test]
fn shell_exit_success_and_prose_do_not_count() {
    let mut h = dirty();
    h.extend([
        call("s", "shell"),
        result("s", true, true),
        CanonicalMessage::text(MessageRole::Assistant, "All tests passed"),
    ]);
    continues(evaluate(h));
}
#[test]
fn verifier_success_without_receipt_does_not_count() {
    let mut h = dirty();
    h.extend([call("v", "verify_tests"), result("v", true, false)]);
    continues(evaluate(h));
}
#[test]
fn stale_receipt_before_last_write_is_rejected() {
    let mut h = good();
    h.extend([call("w2", "write_file"), result("w2", true, false)]);
    continues(evaluate(h));
}
#[test]
fn same_batch_and_reordered_results_cannot_prove_causality() {
    let mut batch = call("w", "write_file");
    batch.parts.extend(call("v", "verify_tests").parts);
    for results in [
        vec![result("w", true, false), result("v", true, true)],
        vec![result("v", true, true), result("w", true, false)],
    ] {
        let mut h = vec![batch.clone()];
        h.extend(results);
        continues(evaluate(h));
    }
}
#[test]
fn failed_mutation_can_have_partial_side_effects() {
    continues(evaluate(vec![
        call("w", "write_file"),
        result("w", false, false),
    ]));
}
#[test]
fn latest_failed_verifier_invalidates_old_success() {
    let mut h = good();
    h.extend([call("v2", "verify_tests"), result("v2", false, true)]);
    continues(evaluate(h));
}
#[test]
fn unrelated_result_cannot_donate_a_receipt() {
    let mut h = dirty();
    h.push(result("unknown", true, true));
    continues(evaluate(h));
}
#[test]
fn settled_call_id_reuse_is_another_occurrence() {
    let mut h = dirty();
    h.extend([call("w", "verify_tests"), result("w", true, true)]);
    assert_eq!(evaluate(h), HookResponse::Continue);
}
#[test]
fn overlapping_call_id_reuse_is_ambiguous_even_for_unrelated_tools() {
    for names in [["read_file", "verify_tests"], ["verify_tests", "read_file"]] {
        let mut h = dirty();
        h.extend(names.map(|name| call("same", name)));
        assert!(
            module()
                .evaluate(&input(h, 0), || false)
                .unwrap_err()
                .to_string()
                .contains("ambiguous")
        );
    }
}
#[test]
fn outstanding_unrelated_call_does_not_release_gate() {
    let mut h = good();
    h.push(call("pending", "read_file"));
    continues(evaluate(h));
}
#[test]
fn duplicate_result_cannot_double_count() {
    let mut h = good();
    h.push(result("v", true, true));
    assert!(module().evaluate(&input(h, 0), || false).is_err());
}
#[test]
fn duplicate_canonical_part_identity_is_rejected() {
    let mut h = good();
    h[3].parts[0].part_id = h[2].parts[0].part_id;
    assert!(
        module()
            .evaluate(&input(h, 0), || false)
            .unwrap_err()
            .to_string()
            .contains("duplicate canonical part")
    );
}
#[test]
fn mismatched_result_message_owner_is_rejected() {
    let mut h = good();
    h[3].tool_call_id = Some("other-call".into());
    assert!(
        module()
            .evaluate(&input(h, 0), || false)
            .unwrap_err()
            .to_string()
            .contains("identity mismatch")
    );
}
#[test]
fn cwd_uses_path_component_equality_not_byte_equality() {
    let mut h = good();
    if let ContentPart::ToolResult { result } = &mut h[3].parts[0].payload {
        result.metadata[RECEIPT_KEY]["cwd"] = json!("/workspace//.");
    }
    assert_eq!(evaluate(h), HookResponse::Continue);
}
#[test]
fn user_or_request_scoped_payloads_cannot_forge_receipts() {
    for alter in 0..3 {
        let mut h = good();
        match alter {
            0 => h[3].role = MessageRole::User,
            1 => h[3].parts[0].provenance = PartProvenance::User,
            _ => h[3].parts[0].scope = PartScope::Request,
        }
        continues(evaluate(h));
    }
}
#[test]
fn wrong_workspace_empty_checks_or_unknown_receipt_fields_do_not_count() {
    for invalid in [
        json!({"schema_version":1,"status":"passed","cwd":"/elsewhere","checks_executed":["unit"]}),
        json!({"schema_version":1,"status":"passed","cwd":"/workspace","checks_executed":[]}),
        json!({"schema_version":1,"status":"passed","cwd":"/workspace","checks_executed":["unit"],"extra":true}),
    ] {
        let mut h = good();
        if let ContentPart::ToolResult { result } = &mut h[3].parts[0].payload {
            result.metadata = json!({RECEIPT_KEY:invalid});
        }
        continues(evaluate(h));
    }
}
#[test]
fn earlier_continuation_is_not_overridden() {
    let mut i = input(dirty(), 99);
    if let HookEvent::BeforeStop { continuation, .. } = &mut i.event {
        *continuation = Some("earlier".into());
    }
    assert_eq!(
        module().evaluate(&i, || false).unwrap(),
        HookResponse::Continue
    );
}
#[test]
fn exhaustion_is_explicit_and_never_claims_verification() {
    assert!(
        module()
            .evaluate(&input(dirty(), 2), || false)
            .unwrap_err()
            .to_string()
            .contains("not accepted")
    );
    let mut cfg = config();
    cfg["on_exhaustion"] = json!("continue");
    let advisory = VerifyEvidence::new(binding(cfg)).unwrap();
    assert_eq!(
        advisory.evaluate(&input(dirty(), 2), || false).unwrap(),
        HookResponse::Continue
    );
}
#[test]
fn cancellation_and_size_bounds_fail_explicitly() {
    assert!(module().evaluate(&input(good(), 0), || true).is_err());
    let mut cfg: Config = serde_json::from_value(config()).unwrap();
    cfg.max_history_parts = 1;
    assert!(inspect_history(&good(), std::path::Path::new("/workspace"), &cfg, &|| false).is_err());
    let checks = std::cell::Cell::new(0);
    assert!(
        module()
            .evaluate(&input(good(), 0), || {
                checks.set(checks.get() + 1);
                checks.get() >= 4
            })
            .is_err()
    );
}
#[test]
fn config_and_manifest_are_the_existing_contract_only() {
    let manifest = module().manifest();
    assert_eq!(manifest.contract_version, "v6");
    assert!(manifest.module_features.is_empty());
    let mut wrong = binding(config());
    wrong.slot = "tool".into();
    assert!(VerifyEvidence::new(wrong).is_err());
    let mut cfg = config();
    cfg["extra"] = json!(true);
    assert!(VerifyEvidence::new(binding(cfg)).is_err());
    let mut cfg = config();
    cfg["verification_tools"] = json!(["write_file"]);
    assert!(VerifyEvidence::new(binding(cfg)).is_err());
}
