//! Actual authored producer/consumer code; synthetic host/history, no Core,
//! filesystem, external runner or model execution is claimed.
use proteus_example_hermes_verify_evidence::{MODULE_ID as GATE_ID, VerifyEvidence};
use proteus_example_json_contracts::{
    AUDIT_KEY, JsonContracts, RECEIPT_KEY, TOOL_NAME, config::Config,
};
use proteus_module_sdk::{
    contracts::{
        contracts::{
            ExecutionAttribution, HookEvent, HookInput, HookResponse,
            ProcessComponentExportInitialize, ProcessModuleComposition, ProcessToolInvokeInput,
        },
        domain::{AgentOutput, AgentTask, ToolCall, ToolResult, new_execution_id},
        model_standard::{CanonicalMessage, ContentPart, MessageRole},
        process_module::{ProcessModuleError, ToolModuleHost},
    },
    tool::ToolModule,
};
use serde_json::{Value, json};

struct Reader {
    publish: bool,
}
impl ToolModuleHost for Reader {
    fn is_cancelled(&self) -> Result<bool, ProcessModuleError> {
        Ok(false)
    }
    fn execute_tool_json(&self, request: String) -> Result<String, ProcessModuleError> {
        let call: ToolCall = serde_json::from_str(&request).unwrap();
        assert_eq!(call.name, "read_file");
        let path = call.args["path"].as_str().unwrap();
        let text = match path {
            "release.json" => format!("{{\"version\":1,\"publish\":{}}}", self.publish),
            "meta.json" => "{\"owner\":\"fixture\"}".into(),
            _ => panic!("unexpected fixture path"),
        };
        Ok(serde_json::to_string(&ToolResult::ok(call.id,text.clone()).with_metadata(json!({"tool":"read_file","path":format!("/workspace/{path}"),"total_lines":text.lines().count(),"returned_lines":text.lines().count(),"truncated":false}))).unwrap())
    }
}
fn config() -> Config {
    serde_json::from_value(json!({"schema_version":1,"suite_id":"release-policy","documents":[
        {"id":"release","path":"release.json","assertions":[{"id":"version","pointer":"/version","rule":{"kind":"equals","expected":1}},{"id":"no-publish","pointer":"/publish","rule":{"kind":"equals","expected":false}}]},
        {"id":"meta","path":"meta.json","assertions":[{"id":"owner","pointer":"/owner","rule":{"kind":"type","expected":"string"}}]}
    ]})).unwrap()
}
fn produce(c: Config, publish: bool) -> ToolResult {
    JsonContracts::new(c)
        .unwrap()
        .invoke(
            ProcessToolInvokeInput {
                call: ToolCall::new("v", TOOL_NAME, json!({})),
                cwd: "/workspace".into(),
                attribution: ExecutionAttribution::detached(new_execution_id()),
                skills: Default::default(),
            },
            &mut Reader { publish },
        )
        .unwrap()
}
fn gate_config() -> Value {
    let expected = JsonContracts::new(config()).unwrap().expected_policy();
    json!({"mutating_tools":["write_file"],"verification_tools":[TOOL_NAME],"max_nudges":2,"max_history_parts":1000,"on_exhaustion":"error","receipt_policy":{"mode":"strict_json_contracts","expected":expected}})
}
fn gate(cfg: Value) -> anyhow::Result<VerifyEvidence> {
    VerifyEvidence::new(ProcessComponentExportInitialize::new(
        "hook",
        GATE_ID,
        "v6",
        ProcessModuleComposition::OrderedMany,
        cfg,
        Vec::<String>::new(),
    ))
}
fn call(id: &str, name: &str) -> CanonicalMessage {
    CanonicalMessage::new(
        MessageRole::Assistant,
        vec![ContentPart::ToolCall {
            call: ToolCall::new(id, name, json!({})),
        }],
    )
}
fn result(value: ToolResult) -> CanonicalMessage {
    let id = value.call_id.clone();
    CanonicalMessage::new(
        MessageRole::Tool,
        vec![ContentPart::ToolResult { result: value }],
    )
    .with_tool_call_id(id)
}
fn input(value: ToolResult) -> HookInput {
    let verifier_id = value.call_id.clone();
    HookInput {
        event: HookEvent::BeforeStop {
            task: AgentTask::new("manifest policy", "/workspace".into()),
            history: vec![
                call("w", "write_file"),
                result(ToolResult::ok("w".into(), "synthetic mutation")),
                call(&verifier_id, TOOL_NAME),
                result(value),
            ],
            output: AgentOutput::text("candidate"),
            attempt: 0,
            continuation: None,
        },
        attribution: ExecutionAttribution::detached(new_execution_id()),
        cwd: "/workspace".into(),
        conversation: None,
    }
}
fn evaluate(value: ToolResult) -> HookResponse {
    gate(gate_config())
        .unwrap()
        .evaluate(&input(value), || false)
        .unwrap()
}
fn missing(value: ToolResult) {
    assert!(matches!(evaluate(value), HookResponse::ContinueTurn { .. }));
}
fn good() -> ToolResult {
    produce(config(), false)
}

#[test]
fn actual_v2_producer_and_exact_operator_policy_release_gate() {
    let result = good();
    assert!(result.ok);
    assert_eq!(result.metadata[RECEIPT_KEY]["schema_version"], 2);
    assert_eq!(evaluate(result), HookResponse::Continue);
}
#[test]
fn otherwise_valid_different_suite_and_changed_rule_config_are_rejected() {
    let mut c = config();
    c.suite_id = "different-suite".into();
    let result = produce(c, false);
    assert!(result.ok);
    missing(result);
    let mut c = config();
    c.documents[0].assertions[1].rule = proteus_example_json_contracts::config::Rule::Equals {
        expected: json!(true),
    };
    let result = produce(c, true);
    assert!(result.ok);
    missing(result);
}
#[test]
fn easier_actual_suite_cannot_satisfy_old_strict_policy() {
    let mut c = config();
    c.documents[0].assertions.pop();
    let result = produce(c, true);
    assert!(result.ok);
    missing(result);
}
#[test]
fn matching_identity_without_all_assertions_is_insufficient() {
    let mut result = good();
    result.metadata[RECEIPT_KEY]["documents"][0]["assertions_executed"]
        .as_array_mut()
        .unwrap()
        .pop();
    missing(result);
}
#[test]
fn extra_and_duplicate_assertions_are_not_coverage() {
    let mut result = good();
    let first = result.metadata[RECEIPT_KEY]["documents"][0]["assertions_executed"][0].clone();
    result.metadata[RECEIPT_KEY]["documents"][0]["assertions_executed"][1] = first;
    missing(result);
    let mut result = good();
    let first = result.metadata[RECEIPT_KEY]["documents"][0]["assertions_executed"][0].clone();
    result.metadata[RECEIPT_KEY]["documents"][0]["assertions_executed"]
        .as_array_mut()
        .unwrap()
        .push(first);
    missing(result);
}
#[test]
fn missing_extra_and_duplicate_documents_are_rejected() {
    let mut result = good();
    result.metadata[RECEIPT_KEY]["documents"]
        .as_array_mut()
        .unwrap()
        .pop();
    missing(result);
    let mut result = good();
    let first = result.metadata[RECEIPT_KEY]["documents"][0].clone();
    result.metadata[RECEIPT_KEY]["documents"]
        .as_array_mut()
        .unwrap()
        .push(first);
    missing(result);
    let mut result = good();
    result.metadata[RECEIPT_KEY]["documents"][1] =
        result.metadata[RECEIPT_KEY]["documents"][0].clone();
    missing(result);
}
#[test]
fn exact_coverage_is_a_set_not_an_accidental_order_requirement() {
    let mut result = good();
    let docs = result.metadata[RECEIPT_KEY]["documents"]
        .as_array_mut()
        .unwrap();
    docs.reverse();
    for doc in docs {
        doc["assertions_executed"].as_array_mut().unwrap().reverse();
    }
    assert_eq!(evaluate(result), HookResponse::Continue);
}
#[test]
fn same_assertion_id_with_wrong_pointer_and_same_bytes_wrong_path_fail() {
    let mut result = good();
    result.metadata[RECEIPT_KEY]["documents"][0]["assertions_executed"][0]["pointer"] =
        json!("/publish");
    missing(result);
    let mut result = good();
    result.metadata[RECEIPT_KEY]["documents"][0]["configured_path"] = json!("other.json");
    missing(result);
    let mut result = good();
    result.metadata[RECEIPT_KEY]["documents"][0]["observed_path"] = json!("/workspace/other.json");
    missing(result);
}
#[test]
fn receipt_call_identity_cannot_be_donated_to_different_outer_call() {
    let mut result = good();
    result.metadata[RECEIPT_KEY]["verifier_call_id"] = json!("old");
    missing(result);
    let mut result = good();
    result.call_id = "other-current-call".into();
    missing(result);
}
#[test]
fn duplicate_reader_mapping_and_inconsistent_check_hash_binding_fail() {
    let mut result = good();
    result.metadata[RECEIPT_KEY]["documents"][1]["reader_call_id"] =
        result.metadata[RECEIPT_KEY]["documents"][0]["reader_call_id"].clone();
    missing(result);
    let mut result = good();
    result.metadata[RECEIPT_KEY]["documents"][0]["content_sha256"] = json!("a".repeat(64));
    missing(result);
}
#[test]
fn no_implicit_schema_or_policy_mode_downgrade() {
    let mut v1 = good();
    v1.metadata[RECEIPT_KEY] = json!({"schema_version":1,"status":"passed","cwd":"/workspace","checks_executed":["anything"]});
    missing(v1.clone());
    let mut cfg = gate_config();
    cfg["receipt_policy"] = json!({"mode":"advisory_v1"});
    assert_eq!(
        gate(cfg.clone())
            .unwrap()
            .evaluate(&input(v1), || false)
            .unwrap(),
        HookResponse::Continue
    );
    assert!(matches!(
        gate(cfg)
            .unwrap()
            .evaluate(&input(good()), || false)
            .unwrap(),
        HookResponse::ContinueTurn { .. }
    ));
    let mut cfg = gate_config();
    cfg.as_object_mut().unwrap().remove("receipt_policy");
    assert!(gate(cfg).is_err());
}
#[test]
fn sibling_metadata_does_not_override_invalid_main_receipt() {
    let mut result = good();
    let valid = result.metadata[RECEIPT_KEY].clone();
    result.metadata[RECEIPT_KEY]["config_sha256"] = json!("b".repeat(64));
    result.metadata[AUDIT_KEY] = valid;
    missing(result);
}
#[test]
fn strict_policy_cannot_release_unverified_work_on_exhaustion() {
    let mut cfg = gate_config();
    cfg["on_exhaustion"] = json!("continue");
    assert!(gate(cfg).is_err());
    let mut i = input(produce(config(), true));
    if let HookEvent::BeforeStop { attempt, .. } = &mut i.event {
        *attempt = 2;
    }
    assert!(gate(gate_config()).unwrap().evaluate(&i, || false).is_err());
}
#[test]
fn failed_second_assertion_has_no_receipt_and_does_not_release() {
    let result = produce(config(), true);
    assert!(!result.ok);
    assert!(result.metadata.get(RECEIPT_KEY).is_none());
    missing(result);
}
#[test]
fn cancelled_timed_out_or_truncated_outer_success_is_not_accepted() {
    for flag in [
        "canceled",
        "timed_out",
        "output_truncated",
        "error_truncated",
    ] {
        let mut result = good();
        result.metadata[flag] = json!(true);
        missing(result);
    }
}
#[test]
fn zero_coverage_and_duplicate_expected_identities_are_configuration_errors() {
    let mut cfg = gate_config();
    cfg["receipt_policy"]["expected"]["documents"] = json!([]);
    assert!(gate(cfg).is_err());
    let mut cfg = gate_config();
    cfg["receipt_policy"]["expected"]["documents"][0]["assertions"] = json!([]);
    assert!(gate(cfg).is_err());
    let mut cfg = gate_config();
    cfg["receipt_policy"]["expected"]["documents"][1] =
        cfg["receipt_policy"]["expected"]["documents"][0].clone();
    assert!(gate(cfg).is_err());
}
#[test]
fn stale_and_wrong_cwd_receipts_still_fail_under_strict_policy() {
    let mut i = input(good());
    if let HookEvent::BeforeStop { history, .. } = &mut i.event {
        history.push(call("later", "write_file"));
        history.push(result(ToolResult::ok("later".into(), "synthetic mutation")));
    }
    assert!(matches!(
        gate(gate_config()).unwrap().evaluate(&i, || false).unwrap(),
        HookResponse::ContinueTurn { .. }
    ));
    let mut result = good();
    result.metadata[RECEIPT_KEY]["cwd"] = json!("/elsewhere");
    missing(result);
}
