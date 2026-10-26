//! Own executable + real SDK framing; synthetic fixture host, no Core or shell.
use proteus_example_json_contracts::{MODULE_ID, RECEIPT_KEY};
use proteus_module_sdk::contracts::{
    contracts::{
        ExecutionAttribution, OPERATION_HOST_EXECUTE_TOOL_METHOD, ProcessComponentExportInitialize,
        ProcessComponentInitialize, ProcessInvocationLineage, ProcessModuleCancel,
        ProcessModuleCancelCause, ProcessModuleComposition, ProcessToolInvokeInput,
    },
    domain::{ToolCall, ToolResult, new_execution_id},
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
        let mut child = Command::new(env!("CARGO_BIN_EXE_proteus-example-json-contracts-strict"))
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
            serde_json::from_str::<Value>(include_str!("../fixtures/suite.json")).unwrap(),
            Vec::<String>::new(),
        );
        self.send(json!({"jsonrpc":"2.0","id":"h:7:0","method":"initialize","params":ProcessComponentInitialize::new("fixture-host",[binding])}));
        let initialized = self.read();
        assert_eq!(initialized["result"]["protocol_version"], "v3");
    }
    fn invoke(&mut self, id: &str, args: Value) {
        let input = ProcessToolInvokeInput {
            call: ToolCall::new(format!("call-{id}"), MODULE_ID, args),
            cwd: "/workspace".into(),
            attribution: ExecutionAttribution::detached(new_execution_id()),
            skills: Default::default(),
        };
        self.send(json!({"jsonrpc":"2.0","id":id,"method":"invoke","params":{"export":{"slot":"tool","module_id":MODULE_ID},"lineage":ProcessInvocationLineage::root(id),"params":input}}));
    }
    fn callback(&self, invocation: &str) -> Value {
        let callback = self.read();
        assert_eq!(callback["method"], OPERATION_HOST_EXECUTE_TOOL_METHOD);
        assert_eq!(callback["params"]["invocation_id"], invocation);
        assert_eq!(callback["params"]["params"]["call"]["name"], "read_file");
        assert_eq!(
            callback["params"]["params"]["call"]["args"],
            json!({"path":"fixtures/release.json"})
        );
        callback
    }
    fn reply(&mut self, callback: Value, truncated: bool) {
        let text = include_str!("../fixtures/release.json");
        let result=ToolResult::ok(callback["params"]["params"]["call"]["id"].as_str().unwrap().into(),text).with_metadata(json!({"tool":"read_file","path":"/workspace/fixtures/release.json","total_lines":text.lines().count(),"returned_lines":text.lines().count(),"truncated":truncated}));
        self.send(json!({"jsonrpc":"2.0","id":callback["id"],"result":result}));
    }
}
impl Drop for Worker {
    fn drop(&mut self) {
        self.input.take();
        let _ = self.child.kill();
        let _ = self.child.wait();
    }
}

#[test]
fn executable_produces_receipt_only_from_successful_bound_reader_callback() {
    let mut worker = Worker::new();
    worker.init();
    worker.invoke("h:7:1", json!({}));
    let callback = worker.callback("h:7:1");
    worker.reply(callback, false);
    let result = worker.read();
    assert_eq!(result["id"], "h:7:1");
    assert_eq!(
        result["result"]["result"]["metadata"][RECEIPT_KEY]["documents"][0]["assertions_executed"]
            .as_array()
            .unwrap()
            .len(),
        5
    );
    worker.invoke("h:7:2", json!({}));
    let callback = worker.callback("h:7:2");
    worker.reply(callback, true);
    let result = worker.read();
    assert_eq!(result["result"]["result"]["ok"], false);
    assert!(
        result["result"]["result"]["metadata"]
            .get(RECEIPT_KEY)
            .is_none()
    );
    worker.invoke("h:7:3", json!({"passed":true}));
    assert!(worker.read().get("error").is_some());
}

#[test]
fn cancel_while_reader_is_pending_suppresses_late_positive_receipt() {
    let mut worker = Worker::new();
    worker.init();
    worker.invoke("h:7:1", json!({}));
    let callback = worker.callback("h:7:1");
    worker.send(json!({"jsonrpc":"2.0","method":"$/cancelRequest","params":ProcessModuleCancel::new("h:7:1",ProcessModuleCancelCause::User)}));
    worker.reply(callback, false);
    let result = worker.read();
    assert_eq!(result["id"], "h:7:1");
    assert_eq!(result["error"]["code"], -32800);
    worker.invoke("h:7:2", json!({}));
    let callback = worker.callback("h:7:2");
    worker.reply(callback, false);
    assert_eq!(worker.read()["result"]["result"]["ok"], true);
}
