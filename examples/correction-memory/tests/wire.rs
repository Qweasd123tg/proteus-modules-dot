//! Own executable/real SDK framing and SQLite; synthetic verifier callback.
//! No Core routing, official reader, approval transport or live model.
mod common;
use common::*;
use proteus_example_correction_memory::{evidence::EVIDENCE_KEY, types::ApplyRequest, *};
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
    io::{BufRead, BufReader, Read, Write},
    path::Path,
    process::{Child, ChildStdin, Command, Stdio},
    sync::mpsc::{self, Receiver},
    thread,
    time::{Duration, Instant},
};
struct Worker {
    child: Child,
    input: Option<ChildStdin>,
    output: Receiver<Value>,
}
impl Worker {
    fn new() -> Self {
        let mut child = Command::new(env!("CARGO_BIN_EXE_proteus-example-correction-memory"))
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::inherit())
            .spawn()
            .unwrap();
        let input = child.stdin.take();
        let output = child.stdout.take().unwrap();
        let (sender, receiver) = mpsc::sync_channel(4);
        thread::spawn(move || {
            let mut reader = BufReader::new(output);
            while let Some(value) = bounded_frame(&mut reader) {
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
        let input = self.input.as_mut().unwrap();
        serde_json::to_writer(&mut *input, &value).unwrap();
        input.write_all(b"\n").unwrap();
        input.flush().unwrap();
    }
    fn read(&self) -> Value {
        self.output
            .recv_timeout(Duration::from_secs(10))
            .expect("bounded own-binary response")
    }
    fn initialize(&mut self) {
        let binding = ProcessComponentExportInitialize::new(
            "tool",
            MODULE_ID,
            "v6",
            ProcessModuleComposition::OrderedMany,
            serde_json::to_value(config()).unwrap(),
            Vec::<String>::new(),
        );
        self.send(json!({"jsonrpc":"2.0","id":"h:1:0","method":"initialize","params":ProcessComponentInitialize::new("authored-fixture-host",[binding])}));
        assert_eq!(self.read()["result"]["protocol_version"], "v3");
    }
    fn invoke(&mut self, id: &str, name: &str, args: Value, cwd: &Path) {
        self.invoke_raw(id, name, args, cwd, None);
    }
    fn invoke_raw(&mut self, id: &str, name: &str, args: Value, cwd: &Path, raw: Option<&str>) {
        let mut call = ToolCall::new(format!("call-{id}"), name, args);
        call.raw_arguments = raw.map(str::to_owned);
        let input = ProcessToolInvokeInput {
            call,
            cwd: cwd.into(),
            attribution: ExecutionAttribution::detached(new_execution_id()),
            skills: Default::default(),
        };
        self.send(json!({"jsonrpc":"2.0","id":id,"method":"invoke","params":{"export":{"slot":"tool","module_id":MODULE_ID},"lineage":ProcessInvocationLineage::root(id),"params":input}}));
    }
    fn result(&self, id: &str) -> ToolResult {
        let frame = self.read();
        assert_eq!(frame["id"], id, "{frame}");
        assert!(frame.get("error").is_none(), "{frame}");
        serde_json::from_value(frame["result"]["result"].clone()).unwrap()
    }
    fn callback(&self, id: &str) -> Value {
        let frame = self.read();
        assert_eq!(frame["method"], OPERATION_HOST_EXECUTE_TOOL_METHOD);
        assert_eq!(frame["params"]["invocation_id"], id);
        assert_eq!(
            frame["params"]["params"]["call"]["name"],
            "evidence.verify_spans"
        );
        frame
    }
    fn reply(&mut self, frame: &Value, cwd: &Path) {
        let call: ToolCall =
            serde_json::from_value(frame["params"]["params"]["call"].clone()).unwrap();
        let request = serde_json::from_value(call.args).unwrap();
        let o = observation(cwd, &request, &call.id);
        let result = ToolResult::ok(call.id, "authored synthetic verifier")
            .with_metadata(json!({EVIDENCE_KEY:o,"duration_ms":0}));
        self.send(json!({"jsonrpc":"2.0","id":frame["id"],"result":result}));
    }
    fn setup(&mut self, cwd: &Path) -> ApplyRequest {
        self.initialize();
        self.invoke("h:1:1", INIT, json!({}), cwd);
        assert!(self.result("h:1:1").ok);
        self.invoke(
            "h:1:2",
            PREPARE,
            serde_json::to_value(request()).unwrap(),
            cwd,
        );
        let callback = self.callback("h:1:2");
        self.reply(&callback, cwd);
        let prepared = self.result("h:1:2");
        assert!(prepared.ok, "{prepared:?}");
        ApplyRequest {
            operation_id: "wire-op".into(),
            proposal: serde_json::from_value(
                prepared.metadata[RESULT_KEY]["result"]["proposal"].clone(),
            )
            .unwrap(),
        }
    }
}
impl Drop for Worker {
    fn drop(&mut self) {
        self.input.take();
        let _ = self.child.kill();
        let until = Instant::now() + Duration::from_secs(2);
        loop {
            match self.child.try_wait() {
                Ok(Some(_)) => return,
                Ok(None) if Instant::now() < until => thread::sleep(Duration::from_millis(10)),
                _ => break,
            }
        }
        // No blocking wait on an unresponsive worker. The outer CI command also
        // needs a wall-clock timeout; this failure does not claim successful reap.
        if !thread::panicking() {
            panic!("own worker was not reaped within cleanup deadline");
        }
        eprintln!("own worker cleanup deadline exceeded during test panic");
    }
}
fn bounded_frame(reader: &mut impl BufRead) -> Option<Value> {
    let mut bytes = Vec::new();
    let mut limited = reader.take(256 * 1024 + 1);
    limited.read_until(b'\n', &mut bytes).ok()?;
    if bytes.len() > 256 * 1024 || bytes.last() != Some(&b'\n') {
        return None;
    }
    serde_json::from_slice(&bytes).ok()
}
#[test]
fn wire_reader_refuses_oversized_or_incomplete_frames_before_unbounded_read() {
    let mut valid = std::io::Cursor::new(b"{\"ok\":true}\n".to_vec());
    assert_eq!(bounded_frame(&mut valid), Some(json!({"ok":true})));
    let mut maximum = b"{\"ok\":true}".to_vec();
    maximum.resize(256 * 1024 - 1, b' ');
    maximum.push(b'\n');
    assert_eq!(
        bounded_frame(&mut std::io::Cursor::new(maximum)),
        Some(json!({"ok":true}))
    );
    let mut valid_over = b"{\"ok\":true}".to_vec();
    valid_over.resize(256 * 1024, b' ');
    valid_over.push(b'\n');
    assert!(bounded_frame(&mut std::io::Cursor::new(valid_over)).is_none());
    let mut over = std::io::Cursor::new(vec![b' '; 256 * 1024 + 2]);
    assert!(bounded_frame(&mut over).is_none());
    assert_eq!(over.position(), 256 * 1024 + 1);
    let mut incomplete = std::io::Cursor::new(b"{\"ok\":true}".to_vec());
    assert!(bounded_frame(&mut incomplete).is_none());
}
#[test]
fn actual_binary_restart_recovers_same_outcome_without_callback() {
    let e = Env::new();
    let mut first = Worker::new();
    let request = first.setup(e.cwd());
    first.invoke(
        "h:1:3",
        APPLY,
        serde_json::to_value(&request).unwrap(),
        e.cwd(),
    );
    let callback = first.callback("h:1:3");
    first.reply(&callback, e.cwd());
    let committed = first.result("h:1:3");
    assert!(committed.ok, "{committed:?}");
    drop(first);
    let mut restarted = Worker::new();
    restarted.initialize();
    restarted.invoke(
        "h:1:4",
        APPLY,
        serde_json::to_value(&request).unwrap(),
        e.cwd(),
    );
    let replay = restarted.result("h:1:4");
    assert_eq!(outcome(&committed), outcome(&replay));
    assert_eq!(replay.metadata[RESULT_KEY]["audit"]["replayed"], true);
    assert_eq!(e.entry()["revision"], 1);
    let mut changed = request;
    changed.proposal.new_text = "changed after restart".into();
    restarted.invoke(
        "h:1:5",
        APPLY,
        serde_json::to_value(changed).unwrap(),
        e.cwd(),
    );
    fail(&restarted.result("h:1:5"), "operation_payload_mismatch");
}
#[test]
fn wire_cancellation_while_verifier_pending_does_not_bind_operation() {
    let e = Env::new();
    let mut worker = Worker::new();
    let request = worker.setup(e.cwd());
    worker.invoke(
        "h:1:3",
        APPLY,
        serde_json::to_value(&request).unwrap(),
        e.cwd(),
    );
    let callback = worker.callback("h:1:3");
    worker.send(json!({"jsonrpc":"2.0","method":"$/cancelRequest","params":ProcessModuleCancel::new("h:1:3",ProcessModuleCancelCause::User)}));
    worker.reply(&callback, e.cwd());
    let canceled = worker.read();
    assert_eq!(canceled["id"], "h:1:3");
    assert_eq!(canceled["error"]["code"], -32800);
    assert!(e.operation(&request.operation_id)["record"].is_null());
    assert_eq!(e.entry()["revision"], 0);
    worker.invoke(
        "h:1:4",
        APPLY,
        serde_json::to_value(request).unwrap(),
        e.cwd(),
    );
    let callback = worker.callback("h:1:4");
    worker.reply(&callback, e.cwd());
    assert!(worker.result("h:1:4").ok);
}

#[test]
fn wire_valid_raw_init_and_unchanged_null_raw_read_succeed() {
    let e = Env::new();
    let mut worker = Worker::new();
    worker.initialize();
    worker.invoke_raw("h:1:1", INIT, json!({}), e.cwd(), Some(" \n{}\t"));
    assert!(worker.result("h:1:1").ok);
    assert!(e.db().is_file());
    worker.invoke(
        "h:1:2",
        READ,
        json!({"kind":"entry","key":"release.status"}),
        e.cwd(),
    );
    let result = worker.result("h:1:2");
    assert!(result.ok);
    assert_eq!(result.metadata[RESULT_KEY]["result"]["revision"], 0);
}
#[test]
fn wire_raw_is_canonical_before_sdk_schema_and_module_not_original_args() {
    let e = Env::new();
    let mut worker = Worker::new();
    worker.initialize();
    // SDK normalizes before schema validation. This proves only that wire seam,
    // not real Core policy/approval. Core order is a separate pinned source trace.
    worker.invoke_raw(
        "h:1:1",
        INIT,
        json!({"not_allowed_by_init_schema":true}),
        e.cwd(),
        Some("{}"),
    );
    assert!(worker.result("h:1:1").ok);
    assert!(e.db().is_file());
    worker.invoke_raw(
        "h:1:2",
        READ,
        json!({"kind":"entry","key":"parsed-B"}),
        e.cwd(),
        Some(r#"{"kind":"entry","key":"raw-A"}"#),
    );
    let result = worker.result("h:1:2");
    assert!(result.ok);
    assert_eq!(result.metadata[RESULT_KEY]["result"]["key"], "raw-A");
}
#[test]
fn wire_duplicate_raw_keys_reject_before_database_or_callback() {
    let e = Env::new();
    let mut worker = Worker::new();
    worker.initialize();
    worker.invoke_raw(
        "h:1:1",
        READ,
        json!({"kind":"entry","key":"A"}),
        e.cwd(),
        Some(r#"{"kind":"entry","key":"B","key":"A"}"#),
    );
    // result() requires this invocation's terminal frame: an unexpected callback
    // is neither serviced nor mistaken for the required duplicate-key diagnostic.
    fail(
        &worker.result("h:1:1"),
        "raw_arguments_json: duplicate JSON object key",
    );
    assert!(!e.db().exists());
    assert_eq!(std::fs::read_dir(e.cwd().join("store")).unwrap().count(), 0);
}
#[test]
fn wire_malformed_raw_remains_sdk_error_without_database_or_callback() {
    let e = Env::new();
    let mut worker = Worker::new();
    worker.initialize();
    worker.invoke_raw("h:1:1", INIT, json!({}), e.cwd(), Some("{"));
    let response = worker.read();
    assert_eq!(response["id"], "h:1:1");
    assert_eq!(response["error"]["code"], -32000);
    assert!(
        response["error"]["message"]
            .as_str()
            .unwrap()
            .contains("EOF while parsing an object")
    );
    assert!(response.get("result").is_none());
    assert!(!e.db().exists());
    assert_eq!(std::fs::read_dir(e.cwd().join("store")).unwrap().count(), 0);
}
