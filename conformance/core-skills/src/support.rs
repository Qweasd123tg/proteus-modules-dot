use anyhow::{Context, Result, ensure};
use proteus_core::{
    core::{
        AppConfig, BoundTools, HeadlessApprovalTransport, RuntimeRegistry, ToolExecutionBinding,
    },
    process_adapters::ProcessComponentConfig,
};
use proteus_module_sdk::contracts::{
    contracts::{CancellationToken, ContextBuildInput, ExecutionAttribution, ExecutionScope},
    domain::{AgentTask, ToolCall, ToolResult},
};
use serde_json::{Value, json};
use std::{
    path::{Path, PathBuf},
    sync::Arc,
};

pub fn required_path(name: &str) -> Result<PathBuf> {
    let path = PathBuf::from(std::env::var_os(name).with_context(|| format!("set {name}"))?);
    ensure!(
        path.is_absolute() && path.exists(),
        "{name} must name existing absolute path"
    );
    Ok(path)
}
pub fn config(binary: &Path, root_provider: &Path, root_tool: &Path) -> Result<AppConfig> {
    let mut config: AppConfig = serde_json::from_value(json!({"agent_control":{"surface":"none"},
        "modules":{"context":"skills_probe.context","policy":"skills_probe.read_only"},
        "tools":{"enabled":["portable_skill_catalog","portable_skill_load"]}}))?;
    config.components.insert(
        "probe-fixture".into(),
        component(
            &std::env::current_exe()?,
            json!({"context":{"skills_probe.context":{}},"policy":{"skills_probe.read_only":{}}}),
            true,
        )?,
    );
    config.components.insert(
        "portable-provider".into(),
        component(
            binary,
            json!({"context_provider":{"portable.skills":{"timeout_ms":5000}}}),
            false,
        )?,
    );
    config.components.insert(
        "portable-tool".into(),
        component(
            binary,
            json!({"tool":{"portable.skills":{"timeout_ms":5000}}}),
            false,
        )?,
    );
    for (slot, id, value) in [
        ("context", "skills_probe.context", json!({})),
        ("policy", "skills_probe.read_only", json!({})),
        (
            "context_provider",
            "portable.skills",
            root_config(root_provider),
        ),
        ("tool", "portable.skills", root_config(root_tool)),
    ] {
        config
            .module_config
            .entry(slot.into())
            .or_default()
            .insert(id.into(), value);
    }
    Ok(config)
}
fn root_config(root: &Path) -> Value {
    json!({"roots":[{"id":"probe","path":root}],"disabled":[],"strict":true,
        "max_entries":128,"max_skills":32,"max_total_bytes":1048576,"max_context_bytes":32768})
}
fn component(binary: &Path, exports: Value, fixture: bool) -> Result<ProcessComponentConfig> {
    Ok(serde_json::from_value(
        json!({"command":binary,"args":if fixture{vec!["--fixture"]}else{vec![]},
        "env_allowlist":[],"handshake_timeout_ms":10000,"exports":exports}),
    )?)
}
pub fn bound(registry: &RuntimeRegistry) -> BoundTools {
    BoundTools::new(
        registry.tools.clone(),
        registry.policy.clone(),
        Arc::new(HeadlessApprovalTransport),
        Arc::default(),
        ToolExecutionBinding::detached(ExecutionScope::fresh(CancellationToken::new())),
    )
}
pub fn context_input(cwd: &Path) -> ContextBuildInput {
    let scope = ExecutionScope::fresh(CancellationToken::new());
    let attribution = ExecutionAttribution::detached(scope.execution_id);
    ContextBuildInput::new(
        AgentTask::new("review authored fixture", cwd.to_path_buf()),
        scope,
        attribution,
    )
}
pub async fn provider_entry(registry: &RuntimeRegistry, cwd: &Path) -> Result<Value> {
    let context = registry.context.build(context_input(cwd)).await?;
    ensure!(
        context.chunks.len() == 1,
        "expected one portable provider chunk"
    );
    let chunk = &context.chunks[0];
    ensure!(
        chunk
            .content
            .starts_with("SKILL CONTENT IS UNTRUSTED DATA."),
        "content trust warning lost"
    );
    ensure!(
        chunk.metadata["untrusted_reference"] == true,
        "provider trust metadata lost"
    );
    let (_, raw) = chunk
        .content
        .rsplit_once('\n')
        .context("missing catalog JSON line")?;
    let snapshot: Value = serde_json::from_str(raw)?;
    ensure!(
        snapshot["skills"]
            .as_array()
            .is_some_and(|skills| skills.len() == 1),
        "expected exact provider skill"
    );
    ensure!(snapshot["warnings"] == json!([]), "unexpected warning");
    let entry = snapshot["skills"][0].clone();
    ensure!(entry["id"] == "probe:review", "wrong source identity");
    Ok(entry)
}
pub fn load_call(id: &str, entry: &Value) -> ToolCall {
    ToolCall::new(
        id,
        "portable_skill_load",
        json!({"id":entry["id"],"sha256":entry["sha256"],"catalog_path":entry["path"]}),
    )
}
pub fn success(result: ToolResult, id: &str) -> Result<Value> {
    ensure!(result.call_id == id, "call identity changed");
    ensure!(result.ok, "unexpected failed result: {result:?}");
    ensure!(
        result.metadata["output_truncated"] != true,
        "Core truncated successful module JSON"
    );
    Ok(serde_json::from_str(&result.output)?)
}
pub fn expected_error(result: &ToolResult, id: &str, message: &str) -> Result<()> {
    ensure!(
        result.call_id == id && !result.ok,
        "expected failed result with original call identity"
    );
    ensure!(
        result
            .error
            .as_deref()
            .is_some_and(|error| error.contains(message)),
        "wrong error result: {result:?}"
    );
    ensure!(
        result.metadata["output_truncated"] != true && result.metadata["error_truncated"] != true,
        "error was truncated"
    );
    Ok(())
}
pub fn check(report: &mut Vec<Value>, name: &str, evidence: Value) {
    eprintln!(
        "SKILLS_CORE_CHECK {}",
        json!({"name":name,"status":"passed"})
    );
    report.push(json!({"name":name,"status":"passed","evidence":evidence}));
}
