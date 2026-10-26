use std::{cell::Cell, path::PathBuf};

use proteus_module_sdk::contracts::{
    contracts::{
        ProcessComponentExportInitialize, ProcessModuleComposition, ProcessPolicyEvaluateInput,
        ProcessPolicyVisibilityInput,
    },
    domain::{
        ModelRef, PolicyDecision, ToolCall, ToolCallSurface, ToolChoice, ToolResult, ToolSafety,
        ToolSpec,
    },
    model_standard::{
        CanonicalMessage, CanonicalModelRequest, ContentPart, FinishReason, MessageRole,
        PartProvenance,
    },
};
use proteus_strict_host_fixture::*;
use serde_json::{Value, json};

fn config() -> ModelConfig {
    ModelConfig {
        scenario: Scenario::WriteVerify,
    }
}
fn specs() -> Vec<ToolSpec> {
    ["write_file", "read_file", VERIFIER]
        .into_iter()
        .map(|name| {
            ToolSpec::new(
                name,
                "authored fixture",
                json!({}),
                expected_safety(name).unwrap(),
            )
        })
        .collect()
}
fn request(messages: Vec<CanonicalMessage>) -> CanonicalModelRequest {
    CanonicalModelRequest::new(ModelRef::new(MODEL_ID, MODEL_ID), messages).with_tools(specs())
}
fn call_message(call: ToolCall) -> CanonicalMessage {
    CanonicalMessage::new(MessageRole::Assistant, vec![ContentPart::ToolCall { call }])
}
fn result_message(id: &str, ok: bool) -> CanonicalMessage {
    let result = if ok {
        ToolResult::ok(id.into(), "fixture result")
    } else {
        ToolResult::error(id.into(), "fixture denied")
    };
    CanonicalMessage::new(MessageRole::Tool, vec![ContentPart::ToolResult { result }])
        .with_tool_call_id(id.into())
}
fn written() -> Vec<CanonicalMessage> {
    vec![call_message(write_call()), result_message(WRITE_ID, true)]
}
fn verified() -> Vec<CanonicalMessage> {
    let mut messages = written();
    messages.push(call_message(verify_call()));
    messages.push(result_message(VERIFY_ID, true));
    messages
}
fn response(
    r: &CanonicalModelRequest,
) -> proteus_module_sdk::contracts::model_standard::CanonicalModelResponse {
    scripted_response(&config(), r, || false).unwrap()
}
fn error(r: &CanonicalModelRequest, expected: &str) {
    let reason = scripted_response(&config(), r, || false)
        .unwrap_err()
        .to_string();
    assert!(
        reason.contains(expected),
        "expected {expected:?}, got {reason:?}"
    );
}
fn policy() -> PolicyConfig {
    PolicyConfig {
        cwd: PathBuf::from("/owned/fixture"),
        deny_reader: false,
    }
}
fn admission(call: ToolCall) -> ProcessPolicyEvaluateInput {
    let safety = expected_safety(&call.name).unwrap_or(ToolSafety::ReadOnly);
    ProcessPolicyEvaluateInput {
        cwd: policy().cwd,
        tool_spec: Some(ToolSpec::new(&call.name, "fixture", json!({}), safety)),
        call,
        granted_permissions: vec![],
    }
}
fn binding(slot: &str, id: &str, config: Value) -> ProcessComponentExportInitialize {
    ProcessComponentExportInitialize::new(
        slot,
        id,
        if slot == "model" { "v12" } else { "v2" },
        ProcessModuleComposition::SelectOne,
        config,
        Vec::<String>::new(),
    )
}
fn denied(decision: PolicyDecision, needle: &str) {
    match decision {
        PolicyDecision::Deny { reason } => assert!(reason.contains(needle), "{reason}"),
        other => panic!("expected deny, got {other:?}"),
    }
}

#[test]
fn exact_three_step_script_and_terminal_continuation() {
    let first = response(&request(vec![CanonicalMessage::text(
        MessageRole::User,
        "run authored case",
    )]));
    assert_eq!(first.finish_reason, FinishReason::ToolCalls);
    assert_eq!(first.tool_calls, vec![write_call()]);
    let second = response(&request(written()));
    assert_eq!(second.tool_calls, vec![verify_call()]);
    let third = response(&request(verified()));
    assert_eq!(third.finish_reason, FinishReason::Stop);
    assert!(third.tool_calls.is_empty());
    assert_eq!(third.messages[0].display_text(), CANDIDATE_TEXT);
    let mut continued = verified();
    continued.extend(third.messages);
    assert_eq!(
        response(&request(continued)).finish_reason,
        FinishReason::Stop
    );
}
#[test]
fn omission_scenario_stops_after_write_without_claiming_verification() {
    let cfg = ModelConfig {
        scenario: Scenario::WriteThenStop,
    };
    let output = scripted_response(&cfg, &request(written()), || false).unwrap();
    assert!(output.tool_calls.is_empty());
    assert_eq!(output.messages[0].display_text(), CANDIDATE_TEXT);
    assert_eq!(
        scripted_response(&cfg, &request(vec![]), || false)
            .unwrap()
            .tool_calls,
        vec![write_call()]
    );
}
#[test]
fn failed_write_does_not_verify_and_failed_verifier_does_not_fabricate_receipt() {
    let failed = vec![call_message(write_call()), result_message(WRITE_ID, false)];
    assert_eq!(response(&request(failed)).finish_reason, FinishReason::Stop);
    let mut failed = written();
    failed.push(call_message(verify_call()));
    failed.push(result_message(VERIFY_ID, false));
    let output = response(&request(failed));
    assert!(output.tool_calls.is_empty());
    assert_eq!(output.messages[0].display_text(), CANDIDATE_TEXT);
    assert_eq!(output.provider_metadata, Value::Null);
}
#[test]
fn orphan_pending_duplicate_and_reordered_calls_fail_for_targeted_reasons() {
    error(
        &request(vec![result_message(WRITE_ID, true)]),
        "result sequence",
    );
    error(&request(vec![call_message(write_call())]), "unsettled call");
    let mut duplicate = written();
    duplicate.push(result_message(WRITE_ID, true));
    error(&request(duplicate), "result sequence");
    error(&request(vec![call_message(verify_call())]), "call sequence");
    let mut duplicate = written();
    duplicate.push(call_message(write_call()));
    error(&request(duplicate), "call sequence");
}
#[test]
fn wrong_arguments_ids_provenance_and_owner_cannot_drive_script() {
    response(&request(written()));
    let mut call = write_call();
    call.args["content"] = json!("other");
    error(&request(vec![call_message(call)]), "call sequence");
    let mut call = write_call();
    call.id = "other".into();
    error(&request(vec![call_message(call)]), "call sequence");
    let mut history = written();
    history[0].parts[0].provenance = PartProvenance::User;
    error(&request(history), "call provenance");
    let mut history = written();
    history[1].parts[0].provenance = PartProvenance::Model;
    error(&request(history), "result provenance");
    let mut history = written();
    history[1].tool_call_id = Some("other".into());
    error(&request(history), "owner mismatch");
}
#[test]
fn duplicate_canonical_identities_fail_without_relying_on_call_sequence() {
    let text = CanonicalMessage::text(MessageRole::User, "fixture");
    error(
        &request(vec![text.clone(), text.clone()]),
        "message identity",
    );
    let mut second = CanonicalMessage::text(MessageRole::User, "fixture");
    second.parts[0].part_id = text.parts[0].part_id;
    error(&request(vec![text, second]), "part identity");
}
#[test]
fn tool_visibility_safety_duplicate_and_choice_are_enforced() {
    let mut r = request(vec![]);
    response(&r);
    r.tools.retain(|s| s.name != "write_file");
    error(&r, "not exposed");
    let mut r = request(vec![]);
    r.tools[0].safety = ToolSafety::ReadOnly;
    error(&r, "exposed tool/safety");
    let mut r = request(vec![]);
    r.tools[1] = r.tools[0].clone();
    error(&r, "duplicate strict fixture exposed tool");
    for choice in [ToolChoice::None, ToolChoice::Tool("read_file".into())] {
        let mut r = request(vec![]);
        r.tool_choice = choice;
        error(&r, "tool choice forbids");
    }
    let mut r = request(vec![]);
    r.tool_choice = ToolChoice::Tool("write_file".into());
    assert_eq!(response(&r).tool_calls, vec![write_call()]);
    let mut r = request(verified());
    r.tool_choice = ToolChoice::Required;
    error(&r, "final conflicts");
}
#[test]
fn model_reference_and_eager_and_late_cancellation_fail_closed() {
    let mut r = request(vec![]);
    r.model.model = "other".into();
    error(&r, "model reference");
    let r = request(vec![]);
    assert!(
        scripted_response(&config(), &r, || true)
            .unwrap_err()
            .to_string()
            .contains("canceled")
    );
    let checks = Cell::new(0);
    let err = scripted_response(&config(), &r, || {
        let n = checks.get();
        checks.set(n + 1);
        n == 1
    })
    .unwrap_err();
    assert!(err.to_string().contains("canceled"));
    assert_eq!(checks.get(), 2);
}
#[test]
fn exact_message_part_and_tool_bounds_have_valid_maximum_controls() {
    let mut r = request(
        (0..MAX_MESSAGES)
            .map(|_| CanonicalMessage::text(MessageRole::User, "x"))
            .collect(),
    );
    response(&r);
    r.messages
        .push(CanonicalMessage::text(MessageRole::User, "x"));
    error(&r, "message bound");
    let mut r = request(vec![CanonicalMessage::new(
        MessageRole::User,
        (0..MAX_PARTS)
            .map(|_| ContentPart::Text { text: "x".into() })
            .collect(),
    )]);
    response(&r);
    r.messages[0].parts.push(
        CanonicalMessage::text(MessageRole::User, "x")
            .parts
            .remove(0),
    );
    error(&r, "part bound");
    let mut r = request(vec![]);
    assert_eq!(r.tools.len(), MAX_TOOLS);
    response(&r);
    r.tools.push(r.tools[0].clone());
    error(&r, "tool bound");
}
#[test]
fn serialized_limit_counts_escaped_bytes_and_rejects_oversized_requests() {
    bounded_json(&json!("abc"), 5).unwrap();
    assert!(bounded_json(&json!("abc"), 4).is_err());
    bounded_json(&json!("\n"), 4).unwrap();
    assert!(bounded_json(&json!("\n"), 3).is_err());
    let r = request(vec![CanonicalMessage::text(
        MessageRole::User,
        "x".repeat(MAX_REQUEST_BYTES),
    )]);
    error(&r, "serialization bound");
}
#[test]
fn exact_policy_asks_write_allows_reader_verifier_and_denies_everything_else() {
    let cfg = policy();
    cfg.validate().unwrap();
    assert!(matches!(
        evaluate(&cfg, &admission(write_call())),
        PolicyDecision::Ask { .. }
    ));
    assert!(matches!(
        evaluate(&cfg, &admission(verify_call())),
        PolicyDecision::Allow
    ));
    assert!(matches!(
        evaluate(
            &cfg,
            &admission(ToolCall::new("read", "read_file", read_args()))
        ),
        PolicyDecision::Allow
    ));
    denied(
        evaluate(&cfg, &admission(ToolCall::new("other", "shell", json!({})))),
        "cwd/name/safety",
    );
    let mut input = admission(write_call());
    input.call.args["extra"] = json!(false);
    denied(evaluate(&cfg, &input), "non-exact arguments");
    let mut input = admission(write_call());
    input.call.args["content"] = json!("other");
    denied(evaluate(&cfg, &input), "non-exact arguments");
    let mut input = admission(verify_call());
    input.call.args = json!({"suite":"other"});
    denied(evaluate(&cfg, &input), "non-exact arguments");
}
#[test]
fn policy_checks_cwd_safety_surface_spec_and_ignores_permission_cache_claims() {
    let cfg = policy();
    let base = admission(write_call());
    assert!(matches!(evaluate(&cfg, &base), PolicyDecision::Ask { .. }));
    let mut input = base.clone();
    input.cwd = "/other".into();
    denied(evaluate(&cfg, &input), "cwd/name/safety");
    let mut input = base.clone();
    input.tool_spec = None;
    denied(evaluate(&cfg, &input), "cwd/name/safety");
    let mut input = base.clone();
    input.tool_spec.as_mut().unwrap().safety = ToolSafety::ReadOnly;
    denied(evaluate(&cfg, &input), "cwd/name/safety");
    let mut input = base.clone();
    input.call.surface = ToolCallSurface::Freeform;
    denied(evaluate(&cfg, &input), "cwd/name/safety");
    let mut input = base.clone();
    input.call.raw_arguments = Some("{}".into());
    denied(evaluate(&cfg, &input), "cwd/name/safety");
    let mut input = base;
    input.granted_permissions = vec!["workspace_write".into()];
    assert!(matches!(evaluate(&cfg, &input), PolicyDecision::Ask { .. }));
}
#[test]
fn denied_nested_reader_remains_visible_but_cannot_execute() {
    let mut cfg = policy();
    cfg.deny_reader = true;
    let input = admission(ToolCall::new("nested-read", "read_file", read_args()));
    assert!(matches!(
        visibility(
            &cfg,
            &ProcessPolicyVisibilityInput {
                cwd: cfg.cwd.clone(),
                tool_spec: input.tool_spec.clone().unwrap()
            }
        ),
        PolicyDecision::Allow
    ));
    denied(evaluate(&cfg, &input), "read deliberately denied");
    assert!(matches!(
        evaluate(&cfg, &admission(write_call())),
        PolicyDecision::Ask { .. }
    ));
    assert!(matches!(
        evaluate(&cfg, &admission(verify_call())),
        PolicyDecision::Allow
    ));
}
#[test]
fn visibility_does_not_widen_names_cwd_or_safety() {
    let cfg = policy();
    let mut input = ProcessPolicyVisibilityInput {
        cwd: cfg.cwd.clone(),
        tool_spec: specs()[0].clone(),
    };
    assert!(matches!(visibility(&cfg, &input), PolicyDecision::Allow));
    input.cwd = "/other".into();
    denied(visibility(&cfg, &input), "visibility");
    input.cwd = cfg.cwd.clone();
    input.tool_spec.safety = ToolSafety::ReadOnly;
    denied(visibility(&cfg, &input), "visibility");
    input.tool_spec = ToolSpec::new("shell", "other", json!({}), ToolSafety::ReadOnly);
    denied(visibility(&cfg, &input), "visibility");
}
#[test]
fn export_binding_and_config_are_exact_and_bounded() {
    let good = binding("model", MODEL_ID, json!({"scenario":"write_verify"}));
    assert_eq!(
        load(good.clone()).unwrap().manifest().module_features,
        Vec::<String>::new()
    );
    let mut wrong = good.clone();
    wrong.contract_version = "v11".into();
    assert!(load(wrong).err().unwrap().to_string().contains("contract"));
    let mut wrong = good.clone();
    wrong.composition = ProcessModuleComposition::OrderedMany;
    assert!(
        load(wrong)
            .err()
            .unwrap()
            .to_string()
            .contains("composition")
    );
    let mut wrong = good.clone();
    wrong.module_id = "other".into();
    assert!(load(wrong).err().unwrap().to_string().contains("identity"));
    for value in [
        json!({}),
        json!({"scenario":"arbitrary_script"}),
        json!({"scenario":"write_verify","script":[]}),
    ] {
        assert!(load(binding("model", MODEL_ID, value)).is_err());
    }
    let mut wrong = good;
    wrong.module_config = json!("x".repeat(MAX_CONFIG_BYTES));
    assert!(
        load(wrong)
            .err()
            .unwrap()
            .to_string()
            .contains("serialization bound")
    );
    assert!(
        load(binding(
            "policy",
            POLICY_ID,
            json!({"cwd":"/owned/fixture","deny_reader":false})
        ))
        .is_ok()
    );
    for cwd in [
        "relative",
        "/",
        "/owned/../other",
        "/owned/\n",
        "/owned/./fixture",
        "/owned//fixture",
    ] {
        assert!(
            load(binding(
                "policy",
                POLICY_ID,
                json!({"cwd":cwd,"deny_reader":false})
            ))
            .is_err(),
            "{cwd:?}"
        );
    }
    assert!(
        load(binding(
            "policy",
            POLICY_ID,
            json!({"cwd":"/owned/fixture"})
        ))
        .is_err()
    );
}
#[test]
fn fixture_bytes_match_reviewed_pr4_size_and_json_values() {
    assert_eq!(CONTENT.len(), 152);
    let value: Value = serde_json::from_str(CONTENT).unwrap();
    assert_eq!(value["schema_version"], 1);
    assert_eq!(value["release"]["channel"], "draft");
    assert_eq!(value["release"]["publish"], false);
    assert_eq!(write_call().args["content"], CONTENT);
    assert_eq!(write_call().args["path"], RELATIVE_PATH);
}
