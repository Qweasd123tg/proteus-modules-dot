#![allow(dead_code)]
use rmcp::{
    RoleClient,
    model::{
        CallToolRequestParams, ClientCapabilities, ClientInfo, Implementation, ProtocolVersion,
    },
    service::{ClientInitializeError, ClientLifecycleMode, ClientServiceExt, RunningService},
};
use serde_json::Value;
use std::{process::Stdio, time::Duration};
use tokio::{
    io::{AsyncBufReadExt, BufReader},
    process::{Child, ChildStdin, ChildStdout, Command},
    sync::mpsc,
    task::JoinHandle,
    time::timeout,
};

pub type Client = RunningService<RoleClient, ClientInfo>;
pub type Pipes = (ChildStdout, ChildStdin);
#[derive(Debug)]
pub enum ConnectFailure {
    Deadline,
    Sdk(ClientInitializeError),
}

pub struct Fixture {
    child: Child,
    pipes: Option<Pipes>,
    trace: JoinHandle<Vec<Value>>,
    observed: mpsc::UnboundedReceiver<Value>,
}
impl Fixture {
    pub fn spawn(scenario: &str) -> Self {
        let mut command = Command::new(env!("CARGO_BIN_EXE_authored-mcp-fixture"));
        command
            .arg(scenario)
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::piped())
            .kill_on_drop(true);
        let mut child = command.spawn().expect("spawn only authored fixture binary");
        let pipes = Some((child.stdout.take().unwrap(), child.stdin.take().unwrap()));
        let stderr = child.stderr.take().unwrap();
        let (sender, observed) = mpsc::unbounded_channel();
        let trace = tokio::spawn(async move {
            let mut lines = BufReader::new(stderr).lines();
            let mut frames = Vec::new();
            while let Some(line) = lines.next_line().await.expect("read authored trace") {
                assert!(line.len() <= 65_544, "bounded trace frame");
                let body = line
                    .strip_prefix("TRACE ")
                    .unwrap_or_else(|| panic!("authored server failed: {line}"));
                let frame: Value = serde_json::from_str(body).expect("authored trace JSON");
                assert!(frames.len() < 32, "bounded trace count");
                let _ = sender.send(frame.clone());
                frames.push(frame);
            }
            frames
        });
        Self {
            child,
            pipes,
            trace,
            observed,
        }
    }
    pub fn pipes(&mut self) -> Pipes {
        self.pipes.take().expect("stdio transport consumed once")
    }
    pub async fn observed_method(&mut self, method: &str) -> Value {
        timeout(Duration::from_secs(5), async {
            while let Some(frame) = self.observed.recv().await {
                if frame["method"] == method {
                    return frame;
                }
            }
            panic!("fixture closed before expected {method}")
        })
        .await
        .expect("bounded wait for actual wire method")
    }
    pub async fn finish(mut self) -> Vec<Value> {
        // Fixture-owned cleanup only. This is not proof of Proteus generation settlement.
        let _ = self.child.start_kill();
        timeout(Duration::from_secs(3), self.child.wait())
            .await
            .expect("bounded child wait")
            .expect("reap authored child");
        timeout(Duration::from_secs(3), self.trace)
            .await
            .expect("bounded trace drain")
            .expect("trace reader must not fail")
    }
}

pub fn info(version: ProtocolVersion) -> ClientInfo {
    ClientInfo::new(
        ClientCapabilities::default(),
        Implementation::new("authored-sdk-probe", "0.1.0"),
    )
    .with_protocol_version(version)
}
pub fn auto() -> ClientLifecycleMode {
    ClientLifecycleMode::Auto {
        preferred_versions: vec![ProtocolVersion::V_2026_07_28],
        legacy_version: Some(ProtocolVersion::V_2025_11_25),
    }
}
pub fn discover() -> ClientLifecycleMode {
    ClientLifecycleMode::Discover {
        preferred_versions: vec![ProtocolVersion::V_2026_07_28],
    }
}
pub async fn connect(
    fixture: &mut Fixture,
    lifecycle: ClientLifecycleMode,
    version: ProtocolVersion,
    budget: Duration,
) -> Result<Client, ConnectFailure> {
    match timeout(
        budget,
        info(version).serve_with_lifecycle(fixture.pipes(), lifecycle),
    )
    .await
    {
        Ok(Ok(client)) => Ok(client),
        Ok(Err(error)) => Err(ConnectFailure::Sdk(error)),
        Err(_) => Err(ConnectFailure::Deadline),
    }
}
pub async fn shutdown(client: Client) {
    timeout(Duration::from_secs(3), client.cancel())
        .await
        .expect("bounded SDK shutdown")
        .expect("SDK task joins");
}
pub fn methods(trace: &[Value]) -> Vec<&str> {
    trace
        .iter()
        .map(|frame| frame["method"].as_str().unwrap())
        .collect()
}
pub fn assert_distinct_request_ids(trace: &[Value]) {
    let ids: Vec<_> = trace.iter().filter_map(|frame| frame.get("id")).collect();
    let keys: std::collections::BTreeSet<_> = ids
        .iter()
        .map(|id| serde_json::to_string(id).unwrap())
        .collect();
    assert_eq!(
        keys.len(),
        ids.len(),
        "each request has a distinct JSON-RPC identity"
    );
}
pub fn assert_modern_metadata(trace: &[Value]) {
    for frame in trace.iter().filter(|frame| frame.get("id").is_some()) {
        assert!(
            proteus_mcp_sdk_probes::fixture::modern_metadata_valid(frame),
            "missing actual modern metadata: {frame}"
        );
    }
}

pub fn call_params() -> CallToolRequestParams {
    CallToolRequestParams::new("lookup.record").with_arguments(
        serde_json::json!({"id":"fixture-42"})
            .as_object()
            .unwrap()
            .clone(),
    )
}
