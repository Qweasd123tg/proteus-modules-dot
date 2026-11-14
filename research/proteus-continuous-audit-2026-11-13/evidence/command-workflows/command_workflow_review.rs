//! Isolated audit regression: real task facade and process runner; fake model, no network.
#[path = "support/agent_context.rs"]
mod agent_context;
#[path = "support/model.rs"]
mod test_model;

use proteus_contracts::{
    contracts::{
        AgentControl, AgentControlRequest, AgentControlResult, AgentControlToolHost,
        AgentWorkflowContext, ExecutionAttribution, ToolContext, ToolRegistry,
    },
    domain::{AgentTask, Event, ToolCall, new_execution_id},
};
use proteus_core::core::{AgentControlConfig, AgentControlRuntime, InMemoryEventStore};
use serde_json::json;
use std::{
    path::{Path, PathBuf},
    process::Command,
    sync::{Arc, Mutex},
};

struct ForwardingHost {
    service: Arc<dyn AgentControl>,
    ctx: AgentWorkflowContext,
    cwd: Mutex<Option<PathBuf>>,
}
#[async_trait::async_trait]
impl AgentControlToolHost for ForwardingHost {
    fn session_id(&self) -> Option<proteus_contracts::domain::SessionId> {
        Some(self.ctx.session_id)
    }
    async fn run_agent(&self, request: AgentControlRequest) -> anyhow::Result<AgentControlResult> {
        // Fixture keeps the first checkout dirty, so production finalization offers task_id.
        if request.metadata.get("task_id").is_none() {
            std::fs::write(
                request.task.cwd.join("retained-result.txt"),
                "synthetic result\n",
            )?;
            *self.cwd.lock().unwrap() = Some(request.task.cwd.clone());
        }
        self.service.run(request, self.ctx.clone()).await
    }
}
fn git(cwd: &Path, args: &[&str]) {
    let output = Command::new("git")
        .arg("-C")
        .arg(cwd)
        .args(args)
        .output()
        .unwrap();
    assert!(
        output.status.success(),
        "{}",
        String::from_utf8_lossy(&output.stderr)
    );
}
fn child_config(home: &Path) -> PathBuf {
    let path = home.join("configs/config.toml");
    std::fs::create_dir_all(path.parent().unwrap()).unwrap();
    std::fs::write(&path, format!("active_provider = \"fake\"\n[providers.fake]\nprovider = \"fake\"\nmodel = \"fake-tool-model\"\n{}", test_model::toml_component())).unwrap();
    path
}

#[tokio::test]
async fn repro_worktree_wrong_role_must_not_destroy_valid_resume() {
    let home = tempfile::tempdir().unwrap();
    let repo = tempfile::tempdir().unwrap();
    for args in [
        vec!["init", "-q", "-b", "main"],
        vec!["config", "user.email", "test@example.com"],
        vec!["config", "user.name", "Audit Fixture"],
    ] {
        git(repo.path(), &args);
    }
    std::fs::write(repo.path().join("base.txt"), "base\n").unwrap();
    git(repo.path(), &["add", "."]);
    git(repo.path(), &["commit", "-q", "-m", "fixture"]);
    let config_path = child_config(home.path());
    let config: AgentControlConfig = serde_json::from_value(json!({
        "binary":std::env::var("PROTEUS_TEST_BINARY").unwrap(), "surface":"task",
        "roles":[
            {"name":"coder_a","description":"a","config":config_path,"isolation":"worktree","timeout_ms":30000},
            {"name":"coder_b","description":"b","config":config_path,"isolation":"worktree","timeout_ms":30000},
            {"name":"shared","description":"shared","config":config_path,"timeout_ms":30000}
        ]
    })).unwrap();
    let runtime = AgentControlRuntime::from_config(&config).unwrap();
    let mut tools = ToolRegistry::new();
    runtime.register_tools(&mut tools, 60000).unwrap();
    let task_tool = tools.get("task").unwrap();
    let events = Arc::new(InMemoryEventStore::new());
    let ctx = agent_context::test_runtime_context(events.clone());
    let host = Arc::new(ForwardingHost {
        service: runtime.service().unwrap(),
        ctx: ctx.clone(),
        cwd: Mutex::new(None),
    });
    let mut tool_ctx = ToolContext::new(
        repo.path().into(),
        ExecutionAttribution::detached(new_execution_id()),
    );
    tool_ctx.task = Some(AgentTask::new("parent", repo.path().into()));
    tool_ctx.agent_control = Some(host.clone());
    let first = task_tool
        .invoke(
            &ToolCall::new(
                "first",
                "task",
                json!({"agent_type":"coder_a","prompt":"initial fixture"}),
            ),
            tool_ctx.clone(),
        )
        .await
        .unwrap();
    assert!(first.ok, "{first:?}");
    let task_id = first.metadata["child_thread_id"]
        .as_str()
        .unwrap()
        .to_owned();
    assert!(first.output.contains("[task_id:"));
    println!(
        "first task: ok={}, resumable={}, task_id={task_id}",
        first.ok, first.metadata["resumable"]
    );
    // Control: a wrong non-worktree role is rejected before facade owns checkout.
    let wrong_shared = task_tool
        .invoke(
            &ToolCall::new(
                "wrong-shared",
                "task",
                json!({"agent_type":"shared","prompt":"invalid role","task_id":task_id}),
            ),
            tool_ctx.clone(),
        )
        .await
        .unwrap();
    assert!(!wrong_shared.ok);
    assert!(
        wrong_shared
            .error
            .as_ref()
            .unwrap()
            .contains("profile coder_a")
    );
    let control = task_tool
        .invoke(
            &ToolCall::new(
                "control",
                "task",
                json!({"agent_type":"coder_a","prompt":"control resume","task_id":task_id}),
            ),
            tool_ctx.clone(),
        )
        .await
        .unwrap();
    assert!(control.ok, "control corrected resume: {control:?}");
    println!(
        "control wrong shared-role then corrected resume: ok={}",
        control.ok
    );
    let starts_before = events
        .envelopes()
        .await
        .iter()
        .filter(|e| matches!(e.event, Event::SubagentStarted { .. }))
        .count();
    let wrong = task_tool
        .invoke(
            &ToolCall::new(
                "wrong-worktree",
                "task",
                json!({"agent_type":"coder_b","prompt":"invalid role","task_id":task_id}),
            ),
            tool_ctx.clone(),
        )
        .await
        .unwrap();
    println!(
        "wrong worktree role: ok={}, error={:?}",
        wrong.ok, wrong.error
    );
    assert!(!wrong.ok);
    assert!(wrong.error.as_ref().unwrap().contains("profile coder_a"));
    let starts_after = events
        .envelopes()
        .await
        .iter()
        .filter(|e| matches!(e.event, Event::SubagentStarted { .. }))
        .count();
    assert_eq!(
        starts_before, starts_after,
        "invalid role must never dispatch child"
    );
    let corrected = task_tool.invoke(&ToolCall::new("corrected", "task", json!({"agent_type":"coder_a","prompt":"continue after correction","task_id":task_id})), tool_ctx.clone()).await.unwrap();
    println!(
        "corrected worktree role: ok={}, error={:?}",
        corrected.ok, corrected.error
    );
    let cwd = host.cwd.lock().unwrap().clone().unwrap();
    assert_eq!(
        std::fs::read_to_string(cwd.join("retained-result.txt")).unwrap(),
        "synthetic result\n"
    );
    // The same production process pool still accepts the same original task_id.
    let backend = host
        .service
        .run(
            AgentControlRequest::new(
                "coder_a",
                "backend control",
                AgentTask::new("parent", cwd.clone()),
            )
            .with_metadata(json!({"task_id":task_id})),
            ctx,
        )
        .await;
    println!(
        "same backend task_id remains resumable={}, checkout_present={}, new_children_on_rejection={}",
        backend.is_ok(),
        cwd.is_dir(),
        starts_after - starts_before
    );
    assert!(backend.is_ok(), "backend control {backend:?}");
    assert!(
        corrected.ok,
        "pre-dispatch validation failure must not consume the worktree resume mapping: {corrected:?}"
    );
}

struct StartGate {
    entered: tokio::sync::Notify,
    release: proteus_contracts::contracts::CancellationToken,
}
#[async_trait::async_trait]
impl proteus_contracts::contracts::EventSink for StartGate {
    async fn append(
        &self,
        envelope: proteus_contracts::domain::EventEnvelope,
    ) -> anyhow::Result<()> {
        if matches!(envelope.event, Event::SubagentStarted { .. }) {
            self.entered.notify_one();
            self.release.cancelled().await;
        }
        Ok(())
    }
}

#[tokio::test]
async fn repro_worktree_capacity_rejection_must_not_destroy_valid_resume() {
    let home = tempfile::tempdir().unwrap();
    let repo = tempfile::tempdir().unwrap();
    for args in [
        vec!["init", "-q", "-b", "main"],
        vec!["config", "user.email", "test@example.com"],
        vec!["config", "user.name", "Audit Fixture"],
    ] {
        git(repo.path(), &args);
    }
    std::fs::write(repo.path().join("base.txt"), "base\n").unwrap();
    git(repo.path(), &["add", "."]);
    git(repo.path(), &["commit", "-q", "-m", "fixture"]);
    let config_path = child_config(home.path());
    let config: AgentControlConfig = serde_json::from_value(json!({
        "binary":std::env::var("PROTEUS_TEST_BINARY").unwrap(), "surface":"task", "max_parallel":1,
        "roles":[
            {"name":"coder_a","description":"a","config":config_path,"isolation":"worktree","timeout_ms":30000},
            {"name":"shared","description":"shared","config":config_path,"timeout_ms":30000}
        ]
    })).unwrap();
    let runtime = AgentControlRuntime::from_config(&config).unwrap();
    let mut tools = ToolRegistry::new();
    runtime.register_tools(&mut tools, 60000).unwrap();
    let task_tool = tools.get("task").unwrap();
    let events = Arc::new(InMemoryEventStore::new());
    let ctx = agent_context::test_runtime_context(events.clone());
    let host = Arc::new(ForwardingHost {
        service: runtime.service().unwrap(),
        ctx: ctx.clone(),
        cwd: Mutex::new(None),
    });
    let mut tool_ctx = ToolContext::new(
        repo.path().into(),
        ExecutionAttribution::detached(new_execution_id()),
    );
    tool_ctx.task = Some(AgentTask::new("parent", repo.path().into()));
    tool_ctx.agent_control = Some(host.clone());
    let first = task_tool
        .invoke(
            &ToolCall::new(
                "capacity-first",
                "task",
                json!({"agent_type":"coder_a","prompt":"initial fixture"}),
            ),
            tool_ctx.clone(),
        )
        .await
        .unwrap();
    assert!(first.ok, "{first:?}");
    let task_id = first.metadata["child_thread_id"]
        .as_str()
        .unwrap()
        .to_owned();
    assert!(first.output.contains("[task_id:"));
    let gate = Arc::new(StartGate {
        entered: tokio::sync::Notify::new(),
        release: Default::default(),
    });
    let mut blocker_ctx = ctx.clone();
    blocker_ctx.events = Arc::new(proteus_contracts::contracts::EventEmitter::new(
        gate.clone(),
    ));
    let service = host.service.clone();
    let request = AgentControlRequest::new(
        "shared",
        "capacity holder",
        AgentTask::new("parent", repo.path().into()),
    );
    // Deterministically pause a real spawn after reserve_pending but before child dispatch.
    let spawning = tokio::spawn(async move { service.spawn(request, blocker_ctx).await });
    tokio::time::timeout(std::time::Duration::from_secs(10), gate.entered.notified())
        .await
        .unwrap();
    let rejected = task_tool.invoke(&ToolCall::new("capacity-reject", "task", json!({"agent_type":"coder_a","prompt":"resume while slot occupied","task_id":task_id})), tool_ctx.clone()).await.unwrap();
    println!(
        "capacity full: ok={}, error={:?}",
        rejected.ok, rejected.error
    );
    assert!(!rejected.ok);
    assert!(rejected.error.as_ref().unwrap().contains("max_parallel 1"));
    gate.release.cancel();
    let blocker = spawning.await.unwrap().unwrap();
    assert!(host.service.wait(&blocker).await.is_ok());
    let corrected = task_tool.invoke(&ToolCall::new("capacity-retry", "task", json!({"agent_type":"coder_a","prompt":"resume after capacity free","task_id":task_id})), tool_ctx.clone()).await.unwrap();
    println!(
        "capacity freed: retry ok={}, error={:?}",
        corrected.ok, corrected.error
    );
    let cwd = host.cwd.lock().unwrap().clone().unwrap();
    let backend = host
        .service
        .run(
            AgentControlRequest::new(
                "coder_a",
                "backend control",
                AgentTask::new("parent", cwd.clone()),
            )
            .with_metadata(json!({"task_id":task_id})),
            ctx,
        )
        .await;
    println!(
        "after capacity reject: same backend resume ok={}, checkout_present={}",
        backend.is_ok(),
        cwd.is_dir()
    );
    assert!(backend.is_ok(), "backend control {backend:?}");
    assert!(
        corrected.ok,
        "temporary capacity failure must not consume the worktree resume mapping: {corrected:?}"
    );
}
