//! Real example executable, synthetic host frames; not a complete Core/model smoke.
use std::{
    io::{BufRead, BufReader, Write},
    process::{Child, ChildStdin, Command, Stdio},
    sync::mpsc::{self, Receiver},
    thread,
    time::Duration,
};

use proteus_example_letta_evidence_blocks::MODULE_ID;
use proteus_module_sdk::contracts::{
    contracts::{
        ExecutionAttribution, ProcessComponentExportInitialize, ProcessComponentInitialize,
        ProcessContextProviderInput, ProcessContextProviderRequest, ProcessInvocationLineage,
        ProcessModuleComposition, ProcessSkillCatalogInput,
    },
    domain::{AgentTask, SkillRuntimeSettings, new_execution_id},
};
use serde_json::{Value, json};

struct Worker {
    child: Child,
    input: Option<ChildStdin>,
    output: Receiver<Value>,
}

impl Worker {
    fn new() -> Self {
        let mut child = Command::new(env!("CARGO_BIN_EXE_proteus-example-letta-evidence-blocks"))
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::inherit())
            .spawn()
            .expect("spawn authored example executable");
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

    fn send(&mut self, frame: Value) {
        let input = self.input.as_mut().unwrap();
        serde_json::to_writer(&mut *input, &frame).unwrap();
        input.write_all(b"\n").unwrap();
        input.flush().unwrap();
    }

    fn request(&mut self, id: &str, method: &str, params: Value) -> Value {
        self.send(json!({"jsonrpc":"2.0","id":id,"method":method,"params":params}));
        let reply = self
            .output
            .recv_timeout(Duration::from_secs(10))
            .expect("bounded wire response");
        assert_eq!(reply["id"], id, "unexpected callback or response: {reply}");
        reply
    }

    fn invoke(&mut self, sequence: u32, method: &str, params: Value) -> Value {
        let id = format!("h:7:{sequence}");
        self.request(
            &id,
            method,
            json!({
                "export":{"slot":"context_provider","module_id":MODULE_ID},
                "lineage":ProcessInvocationLineage::root(&id), "params":params,
            }),
        )
    }
}

impl Drop for Worker {
    fn drop(&mut self) {
        self.input.take();
        let _ = self.child.kill();
        let _ = self.child.wait();
    }
}

fn provide(text: &str) -> Value {
    serde_json::to_value(ProcessContextProviderRequest {
        input: ProcessContextProviderInput {
            provider_id: MODULE_ID.into(),
            task: AgentTask::new(text, "/synthetic/workspace".into()),
            metadata: Value::Null,
        },
        attribution: ExecutionAttribution::detached(new_execution_id()),
        skills: SkillRuntimeSettings::default(),
    })
    .unwrap()
}

#[test]
fn executable_wire_v3_provider_v4_selection_catalog_errors_and_late_cancel() {
    let mut worker = Worker::new();
    let config: Value = serde_json::from_str(include_str!("../module-config.json")).unwrap();
    let binding = ProcessComponentExportInitialize::new(
        "context_provider",
        MODULE_ID,
        "v4",
        ProcessModuleComposition::OrderedMany,
        config,
        Vec::<String>::new(),
    );
    let initialized = worker.request(
        "h:7:0",
        "initialize",
        serde_json::to_value(ProcessComponentInitialize::new("fixture-host", [binding])).unwrap(),
    );
    assert!(initialized.get("error").is_none(), "{initialized}");
    assert_eq!(initialized["result"]["protocol_version"], "v3");
    let manifest = &initialized["result"]["exports"][0];
    assert_eq!(manifest["slot"], "context_provider");
    assert_eq!(manifest["module_id"], MODULE_ID);
    assert_eq!(manifest["contract_version"], "v4");
    assert_eq!(manifest["composition"], "ordered_many");
    assert_eq!(manifest["module_features"], json!([]));

    let selected = worker.invoke(1, "provide", provide("storage database"));
    let chunks = selected["result"]["result"]
        .as_array()
        .expect("context chunk array");
    assert_eq!(
        chunks.len(),
        1,
        "tombstones/other scope must not be returned: {selected}"
    );
    assert_eq!(chunks[0]["metadata"]["id"], "storage-decision");
    assert_eq!(chunks[0]["metadata"]["revision"], 1);
    assert_eq!(chunks[0]["metadata"]["provenance_verified"], false);
    assert_eq!(chunks[0]["source"], MODULE_ID);
    assert_eq!(chunks[0]["render_mode"], "source_annotated");
    let content = chunks[0]["content"].as_str().unwrap();
    assert!(content.starts_with("UNTRUSTED REFERENCE DATA."));
    assert!(!content.contains("JSONL"));
    let projected_bytes = format!("Context from {MODULE_ID}:\n{content}").len();
    assert_eq!(
        chunks[0]["metadata"]["projected_renderer_bytes"],
        projected_bytes
    );
    assert!(projected_bytes <= 8192);

    let catalog = worker.invoke(
        2,
        "catalog",
        serde_json::to_value(ProcessSkillCatalogInput {
            cwd: "/synthetic/workspace".into(),
            skills: SkillRuntimeSettings::default(),
        })
        .unwrap(),
    );
    assert!(catalog.get("error").is_none(), "{catalog}");
    assert!(catalog["result"]["result"].is_null());

    let mut wrong_scope = provide("storage");
    wrong_scope["input"]["metadata"] = json!({"scope":"project:other"});
    assert!(
        worker
            .invoke(3, "provide", wrong_scope)
            .get("error")
            .is_some()
    );
    let mut wrong_id = provide("storage");
    wrong_id["input"]["provider_id"] = json!("another_provider");
    assert!(worker.invoke(4, "provide", wrong_id).get("error").is_some());
    assert!(
        worker
            .invoke(5, "provide", json!({"unexpected":true}))
            .get("error")
            .is_some()
    );
    assert!(
        worker
            .invoke(6, "provide", provide(&"x".repeat(4097)))
            .get("error")
            .is_some()
    );
    assert!(
        worker
            .invoke(7, "not_allowed", Value::Null)
            .get("error")
            .is_some()
    );

    // Deterministic late-cancel case: completed calls may race with cancellation.
    // It must not poison the next invocation. In-flight preemption is separately
    // tested through the pure-policy cancellation seam, not timing assertions.
    worker.send(json!({"jsonrpc":"2.0","method":"$/cancelRequest",
        "params":{"invocation_id":"h:7:1","cause":"user"}}));
    let empty = worker.invoke(8, "provide", provide("! ?"));
    assert_eq!(empty["result"]["result"], json!([]), "{empty}");
    let again = worker.invoke(9, "provide", provide("storage database"));
    assert_eq!(again["result"]["result"], selected["result"]["result"]);
}
