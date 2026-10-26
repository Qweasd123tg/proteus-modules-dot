//! Synthetic transport smoke only: no real verifier, shell, model, or Core agent.
use proteus_example_hermes_verify_evidence::{MODULE_ID, RECEIPT_KEY};
use proteus_module_sdk::contracts::{
    contracts::{
        ExecutionAttribution, HookEvent, HookInput, ProcessComponentExportInitialize,
        ProcessComponentInitialize, ProcessInvocationLineage, ProcessModuleComposition,
    },
    domain::{AgentOutput, AgentTask, ToolCall, ToolResult, new_execution_id},
    model_standard::{CanonicalMessage, ContentPart, MessageRole},
};
use serde_json::{Value, json};
use std::{
    io::{BufRead, BufReader, Write},
    process::{Child, ChildStdin, Command, Stdio},
    sync::mpsc::{self, Receiver},
    thread,
    time::Duration,
};

struct Worker {
    child: Child,
    input: Option<ChildStdin>,
    output: Receiver<Value>,
}
impl Worker {
    fn new() -> Self {
        let mut child = Command::new(env!(
            "CARGO_BIN_EXE_proteus-example-hermes-verify-evidence-strict"
        ))
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::inherit())
        .spawn()
        .unwrap();
        let input = child.stdin.take();
        let output = child.stdout.take().unwrap();
        let (sender, receiver) = mpsc::channel();
        thread::spawn(move || {
            for line in BufReader::new(output).lines() {
                let Ok(line) = line else {
                    break;
                };
                let Ok(value) = serde_json::from_str(&line) else {
                    break;
                };
                if sender.send(value).is_err() {
                    break;
                }
            }
        });
        Self {
            child,
            input,
            output: receiver,
        }
    }
    fn request(&mut self, id: &str, method: &str, params: Value) -> Value {
        let input = self.input.as_mut().unwrap();
        serde_json::to_writer(
            &mut *input,
            &json!({"jsonrpc":"2.0","id":id,
            "method":method,"params":params}),
        )
        .unwrap();
        input.write_all(b"\n").unwrap();
        input.flush().unwrap();
        let result = self
            .output
            .recv_timeout(Duration::from_secs(10))
            .expect("bounded wire response");
        assert_eq!(result["id"], id);
        result
    }
}
impl Drop for Worker {
    fn drop(&mut self) {
        self.input.take();
        let _ = self.child.kill();
        let _ = self.child.wait();
    }
}
fn call(id: &str, name: &str) -> CanonicalMessage {
    CanonicalMessage::new(
        MessageRole::Assistant,
        vec![ContentPart::ToolCall {
            call: ToolCall::new(id, name, json!({})),
        }],
    )
}
fn result(id: &str, receipt: bool) -> CanonicalMessage {
    let metadata = if receipt {
        json!({RECEIPT_KEY:{"schema_version":1,"status":"passed",
        "cwd":"/workspace","checks_executed":["fixture:synthetic-only"]}})
    } else {
        json!({})
    };
    CanonicalMessage::new(
        MessageRole::Tool,
        vec![ContentPart::ToolResult {
            result: ToolResult::ok(id.into(), "synthetic fixture, no tests executed")
                .with_metadata(metadata),
        }],
    )
    .with_tool_call_id(id.into())
}
fn input(history: Vec<CanonicalMessage>) -> HookInput {
    HookInput {
        event: HookEvent::BeforeStop {
            task: AgentTask::new("fixture", "/workspace".into()),
            history,
            output: AgentOutput::text("fixture"),
            attempt: 0,
            continuation: None,
        },
        attribution: ExecutionAttribution::detached(new_execution_id()),
        cwd: "/workspace".into(),
        conversation: None,
    }
}
#[test]
fn external_binary_wire_v3_hook_v6_and_fixture_evidence() {
    let mut worker = Worker::new();
    let binding = ProcessComponentExportInitialize::new(
        "hook",
        MODULE_ID,
        "v6",
        ProcessModuleComposition::OrderedMany,
        json!({"mutating_tools":["write_file"],"verification_tools":["verify_tests"],
            "max_nudges":2,"max_history_parts":100,"on_exhaustion":"error","receipt_policy":{"mode":"advisory_v1"}}),
        Vec::<String>::new(),
    );
    let initialized = worker.request(
        "h:7:0",
        "initialize",
        serde_json::to_value(ProcessComponentInitialize::new("fixture-host", [binding])).unwrap(),
    );
    assert_eq!(initialized["result"]["protocol_version"], "v3");
    assert_eq!(initialized["result"]["exports"][0]["module_id"], MODULE_ID);
    let mut history = vec![call("w", "write_file"), result("w", false)];
    for (sequence, action) in [(1, "continue_turn"), (2, "continue")] {
        if sequence == 2 {
            history.extend([call("v", "verify_tests"), result("v", true)]);
        }
        let id = format!("h:7:{sequence}");
        let response = worker.request(
            &id,
            "hook.invoke",
            json!({
            "export":{"slot":"hook","module_id":MODULE_ID},
            "lineage":ProcessInvocationLineage::root(&id), "params":input(history.clone())}),
        );
        assert_eq!(response["result"]["result"]["action"], action, "{response}");
    }
    let id = "h:7:3";
    let invalid = worker.request(
        id,
        "hook.invoke",
        json!({
        "export":{"slot":"hook","module_id":MODULE_ID},
        "lineage":ProcessInvocationLineage::root(id), "params":{"unexpected":true}}),
    );
    assert!(
        invalid.get("error").is_some(),
        "invalid HookInput must fail: {invalid}"
    );
}

#[test]
fn actual_gate_binary_requires_explicit_v2_policy_identity() {
    use proteus_example_json_receipt::{
        AssertionEvidence, DocumentEvidence, ExpectedAssertion, ExpectedDocument, ExpectedPolicy,
        KIND, Receipt, check_id,
    };
    let expected = ExpectedPolicy {
        expected_suite_id: "release-policy".into(),
        expected_config_sha256: "a".repeat(64),
        documents: vec![ExpectedDocument {
            document_id: "release".into(),
            path: "release.json".into(),
            assertions: vec![ExpectedAssertion {
                assertion_id: "no-publish".into(),
                pointer: "/publish".into(),
            }],
        }],
    };
    let receipt = Receipt {
        schema_version: 2,
        status: "passed".into(),
        kind: KIND.into(),
        cwd: "/workspace".into(),
        verifier_call_id: "v".into(),
        suite_id: expected.expected_suite_id.clone(),
        config_sha256: expected.expected_config_sha256.clone(),
        documents: vec![DocumentEvidence {
            document_id: "release".into(),
            configured_path: "release.json".into(),
            observed_path: "/workspace/release.json".into(),
            reader_call_id: "reader-v".into(),
            content_sha256: "b".repeat(64),
            bytes: 17,
            assertions_executed: vec![AssertionEvidence {
                assertion_id: "no-publish".into(),
                pointer: "/publish".into(),
                check_id: check_id(
                    "release-policy",
                    &"a".repeat(64),
                    &"b".repeat(64),
                    "release",
                    "no-publish",
                ),
            }],
        }],
    };
    let binding = ProcessComponentExportInitialize::new(
        "hook",
        MODULE_ID,
        "v6",
        ProcessModuleComposition::OrderedMany,
        json!({"mutating_tools":["write_file"],"verification_tools":["verify_json"],"max_nudges":2,"max_history_parts":100,"on_exhaustion":"error","receipt_policy":{"mode":"strict_json_contracts","expected":expected}}),
        Vec::<String>::new(),
    );
    let mut worker = Worker::new();
    let initialized = worker.request(
        "h:7:0",
        "initialize",
        serde_json::to_value(ProcessComponentInitialize::new("fixture-host", [binding])).unwrap(),
    );
    assert_eq!(initialized["result"]["protocol_version"], "v3");
    for (sequence, mutation, action) in [
        (1, "wrong_suite", "continue_turn"),
        (2, "none", "continue"),
        (3, "wrong_call", "continue_turn"),
    ] {
        let mut value = serde_json::to_value(&receipt).unwrap();
        if mutation == "wrong_suite" {
            value["suite_id"] = json!("easier-suite");
        }
        if mutation == "wrong_call" {
            value["verifier_call_id"] = json!("other-call");
        }
        let verified = ToolResult::ok(
            "v".into(),
            "synthetic v2 receipt; no filesystem or checks executed here",
        )
        .with_metadata(json!({RECEIPT_KEY:value}));
        let history = vec![
            call("w", "write_file"),
            result("w", false),
            call("v", "verify_json"),
            CanonicalMessage::new(
                MessageRole::Tool,
                vec![ContentPart::ToolResult { result: verified }],
            )
            .with_tool_call_id("v".into()),
        ];
        let id = format!("h:7:{sequence}");
        let response = worker.request(&id, "hook.invoke", json!({"export":{"slot":"hook","module_id":MODULE_ID},"lineage":ProcessInvocationLineage::root(&id),"params":input(history)}));
        assert_eq!(response["result"]["result"]["action"], action, "{response}");
    }
}
