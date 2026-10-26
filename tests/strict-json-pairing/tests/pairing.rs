//! Independent strict-v2 policy pairing; synthetic host and canonical history.
//! No filesystem, test runner, model, process or Core integration is asserted.
use proteus_example_hermes_verify_evidence::{MODULE_ID as GATE_ID, VerifyEvidence};
use proteus_example_json_contracts::{
    AUDIT_KEY, JsonContracts, RECEIPT_KEY, TOOL_NAME, config::Config,
};
use proteus_example_json_receipt::{ExpectedPolicy, verify_receipt};
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
use std::path::Path;

struct Reader {
    text: &'static str,
}
impl ToolModuleHost for Reader {
    fn is_cancelled(&self) -> Result<bool, ProcessModuleError> {
        Ok(false)
    }
    fn execute_tool_json(&self, request: String) -> Result<String, ProcessModuleError> {
        let call: ToolCall = serde_json::from_str(&request).unwrap();
        assert_eq!(call.name, "read_file");
        assert_eq!(call.args, json!({"path":"document.json"}));
        let result = ToolResult::ok(call.id, self.text).with_metadata(json!({
            "tool":"read_file", "path":"/workspace/document.json", "truncated":false,
            "total_lines":self.text.lines().count(), "returned_lines":self.text.lines().count(),
        }));
        Ok(serde_json::to_string(&result).unwrap())
    }
}

fn config() -> Config {
    serde_json::from_value(
        json!({"schema_version":1,"suite_id":"release-contract","documents":[{
        "id":"release","path":"document.json","assertions":[
            {"id":"version","pointer":"/version","rule":{"kind":"equals","expected":1}},
            {"id":"ready","pointer":"/ready","rule":{"kind":"equals","expected":true}}
        ]}]}),
    )
    .unwrap()
}

fn produce(config: Config, text: &'static str) -> ToolResult {
    JsonContracts::new(config)
        .unwrap()
        .invoke(
            ProcessToolInvokeInput {
                call: ToolCall::new("verification", TOOL_NAME, json!({})),
                cwd: "/workspace".into(),
                attribution: ExecutionAttribution::detached(new_execution_id()),
                skills: Default::default(),
            },
            &mut Reader { text },
        )
        .unwrap()
}

fn gate(policy: Value) -> VerifyEvidence {
    VerifyEvidence::new(ProcessComponentExportInitialize::new(
        "hook",
        GATE_ID,
        "v6",
        ProcessModuleComposition::OrderedMany,
        json!({"mutating_tools":["fixture_mutation"],"verification_tools":[TOOL_NAME],
            "max_nudges":2,"max_history_parts":100,"on_exhaustion":"error",
            "receipt_policy":policy}),
        Vec::<String>::new(),
    ))
    .unwrap()
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

fn mutation(id: &str) -> [CanonicalMessage; 2] {
    [
        call(id, "fixture_mutation"),
        result(ToolResult::ok(
            id.into(),
            "synthetic mutation; no files changed",
        )),
    ]
}

fn history(value: ToolResult) -> Vec<CanonicalMessage> {
    let mut messages = mutation("write").to_vec();
    messages.extend([call("verification", TOOL_NAME), result(value)]);
    messages
}

fn evaluate(history: Vec<CanonicalMessage>, policy: Value) -> HookResponse {
    let cwd = "/workspace";
    gate(policy)
        .evaluate(
            &HookInput {
                event: HookEvent::BeforeStop {
                    task: AgentTask::new("fixture", cwd.into()),
                    history,
                    output: AgentOutput::text("candidate"),
                    attempt: 0,
                    continuation: None,
                },
                attribution: ExecutionAttribution::detached(new_execution_id()),
                cwd: cwd.into(),
                conversation: None,
            },
            || false,
        )
        .unwrap()
}

fn missing(verdict: HookResponse) {
    let HookResponse::ContinueTurn { reason } = verdict else {
        panic!("missing-evidence continuation required, got {verdict:?}")
    };
    assert!(reason.contains("Verification evidence is missing"));
}

fn expected(config: Config) -> ExpectedPolicy {
    JsonContracts::new(config).unwrap().expected_policy()
}
fn strict(policy: &ExpectedPolicy) -> Value {
    json!({"mode":"strict_json_contracts", "expected":policy})
}
fn accepted(value: &ToolResult, policy: &ExpectedPolicy) {
    assert!(value.ok, "positive producer failed: {:?}", value.error);
    verify_receipt(
        &value.metadata[RECEIPT_KEY],
        policy,
        Path::new("/workspace"),
        "verification",
    )
    .unwrap();
    assert_eq!(
        evaluate(history(value.clone()), strict(policy)),
        HookResponse::Continue
    );
}
fn rejected_for(value: ToolResult, policy: &ExpectedPolicy, reason: &str) {
    let error = verify_receipt(
        &value.metadata[RECEIPT_KEY],
        policy,
        Path::new("/workspace"),
        "verification",
    )
    .unwrap_err();
    assert_eq!(error.to_string(), reason);
    missing(evaluate(history(value), strict(policy)));
}
fn good() -> ToolResult {
    produce(config(), r#"{"version":1,"ready":true}"#)
}

#[test]
fn actual_v2_producer_passes_and_assertion_order_is_not_authority() {
    let policy = expected(config());
    let mut value = good();
    accepted(&value, &policy);
    value.metadata[RECEIPT_KEY]["documents"][0]["assertions_executed"]
        .as_array_mut()
        .unwrap()
        .reverse();
    accepted(&value, &policy);
    let mut permuted = policy;
    permuted.documents[0].assertions.reverse();
    accepted(&value, &permuted);
}

#[test]
fn weaker_real_producer_is_not_upgraded_by_strong_sibling_audit() {
    let policy = expected(config());
    accepted(&good(), &policy);
    let mut weak = config();
    weak.documents[0].assertions.truncate(1);
    let mut value = produce(weak, r#"{"version":1,"ready":false}"#);
    assert!(value.ok);
    value.metadata[AUDIT_KEY] = json!({"schema_version":2,"suite_id":policy.expected_suite_id,
        "config_sha256":policy.expected_config_sha256,"documents":policy.documents});
    rejected_for(value, &policy, "receipt config digest mismatch");
}

#[test]
fn valid_receipt_with_wrong_suite_or_current_call_does_not_pass() {
    let policy = expected(config());
    let value = good();
    accepted(&value, &policy);
    let mut wrong_suite = value.clone();
    wrong_suite.metadata[RECEIPT_KEY]["suite_id"] = json!("another-suite");
    rejected_for(wrong_suite, &policy, "receipt suite mismatch");
    let mut wrong_call = value;
    wrong_call.metadata[RECEIPT_KEY]["verifier_call_id"] = json!("older-verification");
    rejected_for(wrong_call, &policy, "receipt verifier call id mismatch");
}

#[test]
fn exact_closed_set_checks_distinguish_coverage_duplicates_and_pointer_binding() {
    let policy = expected(config());
    let value = good();
    accepted(&value, &policy);
    let mut absent = value.clone();
    absent.metadata[RECEIPT_KEY]["documents"][0]["assertions_executed"]
        .as_array_mut()
        .unwrap()
        .pop();
    rejected_for(absent, &policy, "receipt assertion coverage mismatch");
    let mut duplicate = value.clone();
    duplicate.metadata[RECEIPT_KEY]["documents"][0]["assertions_executed"][1] =
        duplicate.metadata[RECEIPT_KEY]["documents"][0]["assertions_executed"][0].clone();
    rejected_for(duplicate, &policy, "duplicate receipt assertion");
    let mut wrong_pointer = value;
    wrong_pointer.metadata[RECEIPT_KEY]["documents"][0]["assertions_executed"][1]["pointer"] =
        json!("/version");
    rejected_for(wrong_pointer, &policy, "receipt assertion pointer mismatch");
}

#[test]
fn same_bytes_do_not_override_configured_or_observed_source_path() {
    let policy = expected(config());
    let value = good();
    accepted(&value, &policy);
    let mut configured = value.clone();
    configured.metadata[RECEIPT_KEY]["documents"][0]["configured_path"] = json!("other.json");
    rejected_for(configured, &policy, "receipt path mismatch or duplicate");
    let mut observed = value;
    observed.metadata[RECEIPT_KEY]["documents"][0]["observed_path"] = json!("/other/document.json");
    rejected_for(observed, &policy, "receipt observed path mismatch");
}

#[test]
fn outer_cancellation_or_truncation_is_not_repaired_by_valid_inner_receipt() {
    let policy = expected(config());
    let value = good();
    accepted(&value, &policy);
    for flag in [
        "canceled",
        "timed_out",
        "output_truncated",
        "error_truncated",
    ] {
        for invalid in [json!(true), Value::Null, json!("false")] {
            let mut changed = value.clone();
            changed.metadata[flag] = invalid;
            verify_receipt(
                &changed.metadata[RECEIPT_KEY],
                &policy,
                Path::new("/workspace"),
                "verification",
            )
            .unwrap();
            missing(evaluate(history(changed), strict(&policy)));
        }
        let mut false_flag = value.clone();
        false_flag.metadata[flag] = json!(false);
        accepted(&false_flag, &policy);
    }
}

#[test]
fn v1_and_v2_require_explicit_noninterchangeable_policy_modes() {
    let policy = expected(config());
    let value = good();
    accepted(&value, &policy);
    missing(evaluate(
        history(value.clone()),
        json!({"mode":"advisory_v1"}),
    ));
    let mut v1 = value;
    v1.metadata[RECEIPT_KEY] = json!({"schema_version":1,"status":"passed","cwd":"/workspace", "checks_executed":["legacy-check"]});
    assert_eq!(
        evaluate(history(v1.clone()), json!({"mode":"advisory_v1"})),
        HookResponse::Continue
    );
    missing(evaluate(history(v1), strict(&policy)));
}

#[test]
fn strict_pin_still_does_not_prove_checks_are_meaningful_or_a_test_suite() {
    let mut weak = config();
    weak.documents[0].assertions.truncate(1);
    weak.documents[0].assertions[0].pointer = "".into();
    weak.documents[0].assertions[0].rule = proteus_example_json_contracts::config::Rule::Exists;
    let policy = expected(weak.clone());
    let value = produce(weak, "null");
    accepted(&value, &policy);
    // This is the configured rule, not evidence of code tests or useful project coverage.
}
