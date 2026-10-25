use anyhow::{Context, Result, ensure};
use proteus_core::{
    core::{
        AppConfig, BoundTools, HeadlessApprovalTransport, RuntimeRegistry, ToolExecutionBinding,
    },
    process_adapters::ProcessComponentConfig,
};
use proteus_module_sdk::contracts::{
    contracts::{CancellationToken, ExecutionAttribution, ExecutionScope, HookEvent, HookInput},
    domain::{AgentOutput, AgentTask, ToolCall, ToolResult},
    model_standard::{CanonicalMessage, ContentPart, MessageRole},
};
use serde_json::{Value, json};
use std::{
    path::{Path, PathBuf},
    sync::Arc,
};

pub fn required_path(name: &str) -> Result<PathBuf> {
    let path =
        PathBuf::from(std::env::var_os(name).with_context(|| format!("set {name} explicitly"))?);
    ensure!(
        path.is_absolute() && path.exists(),
        "{name} must name an existing absolute path"
    );
    Ok(path)
}
pub fn base() -> AppConfig {
    serde_json::from_value(json!({"agent_control":{"surface":"none"},"tools":{"enabled":[]}}))
        .unwrap()
}
pub fn component(binary: &Path, exports: Value, fixture: bool) -> ProcessComponentConfig {
    serde_json::from_value(
        json!({"command": binary,"args":if fixture {vec!["--fixture"]} else {vec![]},
        "env_allowlist":[],"handshake_timeout_ms":5000,"exports":exports}),
    )
    .unwrap()
}
pub fn config_value(config: &mut AppConfig, slot: &str, id: &str, value: Value) {
    config
        .module_config
        .entry(slot.into())
        .or_default()
        .insert(id.into(), value);
}
pub fn scope() -> ExecutionScope {
    ExecutionScope::fresh(CancellationToken::new())
}
pub fn tools(registry: &RuntimeRegistry, scope: ExecutionScope) -> BoundTools {
    BoundTools::new(
        registry.tools.clone(),
        registry.policy.clone(),
        Arc::new(HeadlessApprovalTransport),
        Arc::default(),
        ToolExecutionBinding::detached(scope),
    )
}
pub fn plan_call(id: &str) -> ToolCall {
    ToolCall::new(
        id,
        "planning.ready_steps",
        json!({"nodes":[
        {"id":"compile","dependencies":[],"status":"succeeded"},
        {"id":"review","dependencies":["compile"],"status":"pending"}],"failure_policy":"fail_fast"}),
    )
}
pub fn before_stop(
    cwd: &Path,
    scope: &ExecutionScope,
    history: Vec<CanonicalMessage>,
    attempt: u32,
) -> HookInput {
    HookInput {
        event: HookEvent::BeforeStop {
            task: AgentTask::new("offline fixture", cwd.to_path_buf()),
            history,
            output: AgentOutput::text("fixture"),
            attempt,
            continuation: None,
        },
        attribution: ExecutionAttribution::detached(scope.execution_id),
        cwd: cwd.to_path_buf(),
        conversation: None,
    }
}
pub fn call_message(id: &str, name: &str) -> CanonicalMessage {
    CanonicalMessage::new(
        MessageRole::Assistant,
        vec![ContentPart::ToolCall {
            call: ToolCall::new(id, name, json!({})),
        }],
    )
}
pub fn result_message(id: &str, metadata: Value) -> CanonicalMessage {
    CanonicalMessage::new(
        MessageRole::Tool,
        vec![ContentPart::ToolResult {
            result: ToolResult::ok(id.into(), "synthetic history; no effect executed")
                .with_metadata(metadata),
        }],
    )
    .with_tool_call_id(id.into())
}
pub fn check(report: &mut Vec<Value>, name: &str, evidence: Value) {
    eprintln!("SMOKE_CHECK {}", json!({"name":name,"status":"passed"}));
    report.push(json!({"name":name,"status":"passed","evidence":evidence}));
}
