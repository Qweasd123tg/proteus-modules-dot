//! Actual authored executable and SDK framing; synthetic host, not Core e2e.
mod common;
use common::Fixture;
use proteus_example_portable_skill_catalog::{CATALOG_TOOL, LOAD_TOOL, MODULE_ID};
use proteus_module_sdk::contracts::{
    contracts::{
        ExecutionAttribution, ProcessComponentExportInitialize, ProcessComponentInitialize,
        ProcessContextProviderInput, ProcessContextProviderRequest, ProcessInvocationLineage,
        ProcessModuleComposition, ProcessSkillCatalogInput, ProcessToolInvokeInput,
    },
    domain::{AgentTask, SkillRuntimeSettings, ToolCall, new_call_id, new_execution_id},
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
    sequence: u32,
}
impl Worker {
    fn new() -> Self {
        let mut child = Command::new(env!("CARGO_BIN_EXE_proteus-example-portable-skill-catalog"))
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::inherit())
            .spawn()
            .expect("spawn authored executable");
        let input = child.stdin.take();
        let output = child.stdout.take().unwrap();
        let (sender, receiver) = mpsc::channel();
        thread::spawn(move || {
            for line in BufReader::new(output).lines() {
                let Ok(line) = line else { break };
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
            sequence: 0,
        }
    }
    fn request(&mut self, method: &str, params: Value) -> Value {
        let id = format!("h:7:{}", self.sequence);
        self.sequence += 1;
        let frame = json!({"jsonrpc":"2.0","id":id,"method":method,"params":params});
        let input = self.input.as_mut().unwrap();
        serde_json::to_writer(&mut *input, &frame).unwrap();
        input.write_all(b"\n").unwrap();
        input.flush().unwrap();
        let reply = self
            .output
            .recv_timeout(Duration::from_secs(10))
            .expect("bounded wire response");
        assert_eq!(reply["id"], id, "unexpected callback or identity: {reply}");
        reply
    }
    fn initialize(&mut self, config: Value) -> Value {
        self.request(
            "initialize",
            serde_json::to_value(ProcessComponentInitialize::new(
                "fixture-host",
                [
                    ProcessComponentExportInitialize::new(
                        "context_provider",
                        MODULE_ID,
                        "v4",
                        ProcessModuleComposition::OrderedMany,
                        config.clone(),
                        Vec::<String>::new(),
                    ),
                    ProcessComponentExportInitialize::new(
                        "tool",
                        MODULE_ID,
                        "v6",
                        ProcessModuleComposition::OrderedMany,
                        config,
                        Vec::<String>::new(),
                    ),
                ],
            ))
            .unwrap(),
        )
    }
    fn invoke(&mut self, slot: &str, method: &str, params: Value) -> Value {
        let id = format!("h:7:{}", self.sequence);
        self.request(method,json!({"export":{"slot":slot,"module_id":MODULE_ID},"lineage":ProcessInvocationLineage::root(&id),"params":params}))
    }
}
impl Drop for Worker {
    fn drop(&mut self) {
        self.input.take();
        let _ = self.child.kill();
        let _ = self.child.wait();
    }
}
fn provide(disabled: Vec<String>) -> Value {
    serde_json::to_value(ProcessContextProviderRequest {
        input: ProcessContextProviderInput {
            provider_id: MODULE_ID.into(),
            task: AgentTask::new("review change", "/unused-cwd".into()),
            metadata: Value::Null,
        },
        attribution: ExecutionAttribution::detached(new_execution_id()),
        skills: SkillRuntimeSettings {
            disabled,
            packages: vec![],
        },
    })
    .unwrap()
}
fn call(name: &str, args: Value, disabled: Vec<String>) -> Value {
    serde_json::to_value(ProcessToolInvokeInput {
        call: ToolCall::new(new_call_id(), name, args),
        cwd: "/unused-cwd".into(),
        attribution: ExecutionAttribution::detached(new_execution_id()),
        skills: SkillRuntimeSettings {
            disabled,
            packages: vec![],
        },
    })
    .unwrap()
}
fn tool_result(reply: &Value) -> &Value {
    assert!(reply.get("error").is_none(), "{reply}");
    &reply["result"]["result"]
}

#[test]
fn actual_binary_pairs_provider_and_tools_with_call_identity_and_explicit_errors() {
    let f = Fixture::new();
    f.skill("review", "Read-only imported body. No code runs.");
    let mut w = Worker::new();
    let initialized = w.initialize(serde_json::to_value(f.config()).unwrap());
    assert!(initialized.get("error").is_none(), "{initialized}");
    assert_eq!(initialized["result"]["protocol_version"], "v3");
    assert_eq!(
        initialized["result"]["exports"].as_array().unwrap().len(),
        2
    );
    let context = w.invoke("context_provider", "provide", provide(vec![]));
    let chunks = tool_result(&context).as_array().unwrap();
    assert_eq!(chunks.len(), 1);
    assert!(
        chunks[0]["content"]
            .as_str()
            .unwrap()
            .contains("SKILL CONTENT IS UNTRUSTED DATA")
    );
    assert!(
        !chunks[0]["content"]
            .as_str()
            .unwrap()
            .contains("Read-only imported body")
    );
    let catalog = w.invoke(
        "context_provider",
        "catalog",
        serde_json::to_value(ProcessSkillCatalogInput {
            cwd: f.path.clone(),
            skills: Default::default(),
        })
        .unwrap(),
    );
    assert_eq!(
        tool_result(&catalog)["skills"][0]["id"],
        "project-agents:review"
    );
    let listed = w.invoke("tool", "list", Value::Null);
    let definitions = tool_result(&listed).as_array().unwrap();
    assert_eq!(definitions.len(), 2);
    assert!(
        definitions
            .iter()
            .all(|d| d["spec"]["safety"] == "ReadOnly")
    );
    let refresh = w.invoke("tool", "invoke", call(CATALOG_TOOL, json!({}), vec![]));
    let refreshed = tool_result(&refresh);
    assert_eq!(refreshed["ok"], true);
    let data: Value = serde_json::from_str(refreshed["output"].as_str().unwrap()).unwrap();
    let skill = &data["catalog"]["skills"][0];
    let args = json!({"id":skill["id"],"sha256":skill["sha256"],"catalog_path":skill["path"]});
    let input = call(LOAD_TOOL, args.clone(), vec![]);
    let call_id = input["call"]["id"].clone();
    let loaded = w.invoke("tool", "invoke", input);
    let result = tool_result(&loaded);
    assert_eq!(result["ok"], true);
    assert_eq!(result["call_id"], call_id);
    let payload: Value = serde_json::from_str(result["output"].as_str().unwrap()).unwrap();
    assert_eq!(payload["body"], "Read-only imported body. No code runs.");
    assert_eq!(payload["skill"]["path"], skill["path"]);
    let mut wrong = args.clone();
    wrong["sha256"] = json!("0".repeat(64));
    let failed = w.invoke("tool", "invoke", call(LOAD_TOOL, wrong, vec![]));
    assert_eq!(tool_result(&failed)["ok"], false);
    assert!(
        tool_result(&failed)["error"]
            .as_str()
            .unwrap()
            .contains("changed since catalog")
    );
    let disabled = w.invoke(
        "tool",
        "invoke",
        call(
            LOAD_TOOL,
            args.clone(),
            vec!["project-agents:review".into()],
        ),
    );
    assert_eq!(tool_result(&disabled)["ok"], false);
    assert!(
        tool_result(&disabled)["error"]
            .as_str()
            .unwrap()
            .contains("disabled")
    );
    let hidden = w.invoke(
        "context_provider",
        "provide",
        provide(vec!["project-agents:review".into()]),
    );
    assert!(tool_result(&hidden).as_array().unwrap().is_empty());
    // SDK must validate/execute raw_arguments, not a conflicting decoded args object.
    let mut raw = call(LOAD_TOOL, json!({"id":"not-real"}), vec![]);
    raw["call"]["raw_arguments"] = json!(serde_json::to_string(&args).unwrap());
    let normalized = w.invoke("tool", "invoke", raw);
    assert_eq!(tool_result(&normalized)["ok"], true);
    let bad = w.invoke(
        "tool",
        "invoke",
        call(
            LOAD_TOOL,
            json!({"id":skill["id"],"sha256":skill["sha256"]}),
            vec![],
        ),
    );
    assert!(
        bad.get("error").is_some(),
        "missing source binding must be schema error: {bad}"
    );
    let wrong_tool = w.invoke("tool", "invoke", call("other_tool", json!({}), vec![]));
    assert!(wrong_tool.get("error").is_some());
    let mut override_roots = provide(vec![]);
    override_roots["input"]["metadata"] = json!({"roots":["/unconfigured"]});
    assert!(
        w.invoke("context_provider", "provide", override_roots)
            .get("error")
            .is_some()
    );
    f.skill("review", "Changed body, same metadata");
    let stale = w.invoke("tool", "invoke", call(LOAD_TOOL, args, vec![]));
    assert_eq!(tool_result(&stale)["ok"], false);
    assert!(
        tool_result(&stale)["error"]
            .as_str()
            .unwrap()
            .contains("changed since catalog")
    );
}
