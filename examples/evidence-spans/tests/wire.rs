//! Our executable + SDK v3 framing; authored reader callback, not actual Core.
use proteus_example_evidence_spans::{EVIDENCE_KEY, EvidenceSpans, MODULE_ID, config::Config};
use proteus_module_sdk::contracts::{
    contracts::{
        ExecutionAttribution, OPERATION_HOST_EXECUTE_TOOL_METHOD, ProcessComponentExportInitialize,
        ProcessComponentInitialize, ProcessInvocationLineage, ProcessModuleCancel,
        ProcessModuleCancelCause, ProcessModuleComposition, ProcessToolInvokeInput,
    },
    domain::{ToolCall, ToolResult, new_execution_id, tool_validation::validate_tool_call_args},
};
use proteus_module_sdk::tool::ToolModule;
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
        let mut child = Command::new(env!("CARGO_BIN_EXE_proteus-example-evidence-spans"))
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
        }
    }
    fn send(&mut self, value: Value) {
        let out = self.input.as_mut().unwrap();
        serde_json::to_writer(&mut *out, &value).unwrap();
        out.write_all(b"\n").unwrap();
        out.flush().unwrap();
    }
    fn read(&self) -> Value {
        self.output
            .recv_timeout(Duration::from_secs(10))
            .expect("bounded wire response")
    }
    fn init(&mut self) {
        let binding = ProcessComponentExportInitialize::new(
            "tool",
            MODULE_ID,
            "v6",
            ProcessModuleComposition::OrderedMany,
            serde_json::from_str::<Value>(include_str!("../fixtures/config.json")).unwrap(),
            Vec::<String>::new(),
        );
        self.send(json!({"jsonrpc":"2.0","id":"h:9:0","method":"initialize","params":ProcessComponentInitialize::new("quote-fixture-host",[binding])}));
        assert_eq!(self.read()["result"]["protocol_version"], "v3");
    }
    fn invoke(&mut self, id: &str, args: Value) {
        let input = ProcessToolInvokeInput {
            call: ToolCall::new(format!("call-{id}"), MODULE_ID, args),
            cwd: "/workspace".into(),
            attribution: ExecutionAttribution::detached(new_execution_id()),
            skills: Default::default(),
        };
        self.send(json!({"jsonrpc":"2.0","id":id,"method":"invoke","params":{
            "export":{"slot":"tool","module_id":MODULE_ID},"lineage":ProcessInvocationLineage::root(id),"params":input
        }}));
    }
    fn callback(&self, id: &str) -> Value {
        let c = self.read();
        assert_eq!(c["method"], OPERATION_HOST_EXECUTE_TOOL_METHOD);
        assert_eq!(c["params"]["invocation_id"], id);
        assert_eq!(c["params"]["params"]["call"]["name"], "read_file");
        assert_eq!(
            c["params"]["params"]["call"]["args"],
            json!({"path":"fixtures/source.txt"})
        );
        c
    }
    fn reply(&mut self, c: Value, truncated: bool) {
        let text = include_str!("../fixtures/source.txt");
        let result=ToolResult::ok(c["params"]["params"]["call"]["id"].as_str().unwrap().into(),text)
            .with_metadata(json!({"tool":"read_file","path":"/workspace/fixtures/source.txt",
                "total_lines":text.lines().count(),"returned_lines":text.lines().count(),"truncated":truncated}));
        self.send(json!({"jsonrpc":"2.0","id":c["id"],"result":result}));
    }
}
impl Drop for Worker {
    fn drop(&mut self) {
        self.input.take();
        let _ = self.child.kill();
        let _ = self.child.wait();
    }
}
fn request() -> Value {
    serde_json::from_str(include_str!("../fixtures/request.json")).unwrap()
}

#[test]
fn actual_executable_accepts_quotes_rejects_partial_reader_and_model_path() {
    let mut w = Worker::new();
    w.init();
    w.invoke("h:9:1", request());
    let c = w.callback("h:9:1");
    w.reply(c, false);
    let r = w.read();
    assert_eq!(r["id"], "h:9:1");
    assert_eq!(r["result"]["result"]["ok"], true);
    let e = &r["result"]["result"]["metadata"][EVIDENCE_KEY];
    assert_eq!(e["verified_claims"].as_array().unwrap().len(), 2);
    assert_eq!(e["origin_verified"], false);
    assert_eq!(e["semantic_entailment"], "not_evaluated");
    w.invoke("h:9:2", request());
    let c = w.callback("h:9:2");
    w.reply(c, true);
    let r = w.read();
    assert_eq!(r["id"], "h:9:2");
    assert_eq!(r["result"]["result"]["call_id"], "call-h:9:2");
    assert_eq!(r["result"]["result"]["ok"], false);
    assert_eq!(
        r["result"]["result"]["error"],
        "reader returned partial content"
    );
    assert!(
        r["result"]["result"]["metadata"]
            .get(EVIDENCE_KEY)
            .is_none()
    );
    let mut r = request();
    r["path"] = json!("/forbidden");
    let config: Config = serde_json::from_str(include_str!("../fixtures/config.json")).unwrap();
    let definition = EvidenceSpans::new(config).unwrap().definitions().remove(0);
    let expected = validate_tool_call_args(
        &ToolCall::new("call-h:9:3", MODULE_ID, r.clone()),
        &definition.spec,
    )
    .unwrap();
    assert!(expected.starts_with("tool 'evidence.verify_spans' arguments violate schema"));
    assert!(expected.ends_with("(schema '/additionalProperties')"));
    w.invoke("h:9:3", r);
    let r = w.read();
    assert_eq!(r["id"], "h:9:3");
    assert_eq!(r["error"]["code"], -32000);
    assert_eq!(r["error"]["message"], expected);
    assert!(r.get("result").is_none());
}

#[test]
fn callback_wait_cancellation_has_no_late_positive_witness() {
    let mut w = Worker::new();
    w.init();
    w.invoke("h:9:1", request());
    let c = w.callback("h:9:1");
    w.send(json!({"jsonrpc":"2.0","method":"$/cancelRequest","params":ProcessModuleCancel::new("h:9:1",ProcessModuleCancelCause::User)}));
    w.reply(c, false);
    let r = w.read();
    assert_eq!(r["id"], "h:9:1");
    assert_eq!(r["error"]["code"], -32800);
    w.invoke("h:9:2", request());
    let c = w.callback("h:9:2");
    w.reply(c, false);
    assert_eq!(w.read()["result"]["result"]["ok"], true);
}
