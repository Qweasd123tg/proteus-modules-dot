use crate::approval::ExactApproval;
use anyhow::Result;
use async_trait::async_trait;
use proteus_core::core::{AppConfig, BoundTools, RuntimeRegistry, ToolExecutionBinding};
use proteus_module_sdk::contracts::{
    contracts::{
        CancellationToken, ExecutionAttribution, ExecutionScope, OperationOwner,
        ToolExecutionRecorder,
    },
    domain::{ToolCall, ToolCallResolution, ToolResult},
};
use serde_json::{Value, json};
use std::{
    path::PathBuf,
    sync::{Arc, Mutex},
};
#[derive(Default)]
struct Recorder(Mutex<Vec<Value>>);
#[async_trait]
impl ToolExecutionRecorder for Recorder {
    async fn tool_call_requested(
        &self,
        a: ExecutionAttribution,
        o: OperationOwner,
        c: &ToolCall,
    ) -> Result<()> {
        self.0
            .lock()
            .unwrap()
            .push(json!({"phase":"requested","attribution":a,"owner":o,"call":c}));
        Ok(())
    }
    async fn tool_call_resolved(
        &self,
        a: ExecutionAttribution,
        c: &ToolCall,
        r: &ToolCallResolution,
    ) -> Result<()> {
        self.0
            .lock()
            .unwrap()
            .push(json!({"phase":"resolved","attribution":a,"call":c,"resolution":r}));
        Ok(())
    }
    async fn tool_approval_requested(
        &self,
        a: ExecutionAttribution,
        c: &ToolCall,
        r: &str,
    ) -> Result<()> {
        self.0
            .lock()
            .unwrap()
            .push(json!({"phase":"approval_requested","attribution":a,"call":c,"reason":r}));
        Ok(())
    }
    async fn tool_result_recorded(&self, a: ExecutionAttribution, r: &ToolResult) -> Result<()> {
        self.0
            .lock()
            .unwrap()
            .push(json!({"phase":"result","attribution":a,"result":r}));
        Ok(())
    }
}
pub async fn run(config: AppConfig, cwd: PathBuf) -> Result<Value> {
    let build_cwd = cwd.clone();
    let registry =
        tokio::task::spawn_blocking(move || RuntimeRegistry::from_config(&config, build_cwd))
            .await??;
    let recorder = Arc::new(Recorder::default());
    let approval = Arc::new(ExactApproval::new(cwd.clone(), true));
    let binding = ToolExecutionBinding::detached(ExecutionScope::fresh(CancellationToken::new()))
        .with_recorder(recorder.clone());
    let tools = BoundTools::new(
        registry.tools.clone(),
        registry.policy.clone(),
        approval.clone(),
        Arc::default(),
        binding,
    );
    let result = tools
        .execute(cwd, proteus_strict_host_fixture::write_call())
        .await?;
    Ok(
        json!({"result":result,"records":recorder.0.lock().unwrap().clone(),"approvals":approval.snapshot()}),
    )
}
