//! Test-only, offline exports. No filesystem access, model, shell, or network.
use anyhow::{Result, bail, ensure};
use proteus_module_sdk::{
    Export,
    contracts::{
        contracts::{
            ProcessComponentExportInitialize, ProcessComponentExportManifest, ProcessContextInput,
            ProcessContextResponse, ProcessPolicyEvaluateInput, ProcessPolicyResponse,
            ProcessPolicyVisibilityInput,
        },
        domain::{ContextBundle, ContextChunk, PolicyDecision, ToolSafety},
        process_module::ContextBuilderModuleHost,
    },
    hosts::{ContextHostBridge, HostBridge},
    protocol::process_contract_authority,
};
use serde_json::{Value, json};

struct Fixture(ProcessComponentExportInitialize);

pub fn load(binding: ProcessComponentExportInitialize) -> Result<Box<dyn Export>> {
    ensure!(
        matches!(
            (binding.slot.as_str(), binding.module_id.as_str()),
            ("context", "smoke.provider_relay") | ("policy", "smoke.read_only")
        ),
        "unsupported fixture export"
    );
    let authority = process_contract_authority(&binding.slot, &binding.contract_version)
        .ok_or_else(|| anyhow::anyhow!("unknown contract"))?;
    ensure!(
        binding.composition == authority.composition,
        "incorrect composition"
    );
    ensure!(
        binding.module_config == json!({}),
        "fixture config must be empty"
    );
    Ok(Box::new(Fixture(binding)))
}

impl Export for Fixture {
    fn manifest(&self) -> ProcessComponentExportManifest {
        ProcessComponentExportManifest {
            slot: self.0.slot.clone(),
            module_id: self.0.module_id.clone(),
            contract_version: self.0.contract_version.clone(),
            composition: self.0.composition,
            module_features: vec![],
            config_schema: None,
        }
    }
    fn invoke(&self, method: &str, params: Value, host: &HostBridge) -> Result<Value> {
        ensure!(!host.is_cancelled(), "fixture canceled");
        match (self.0.slot.as_str(), method) {
            ("context", "build") => {
                let request: ProcessContextInput = serde_json::from_value(params)?;
                let response = ContextHostBridge(host.clone()).context_provider_json(
                    "letta.evidence_blocks".into(),
                    serde_json::to_string(&json!({"task": request.task, "metadata": null}))?,
                )?;
                // host.context.provide returns the canonical bare chunk vector.
                let chunks: Vec<ContextChunk> = serde_json::from_str(&response)?;
                Ok(serde_json::to_value(ProcessContextResponse::new(
                    ContextBundle::new(chunks),
                ))?)
            }
            ("policy", "evaluate") => {
                let request: ProcessPolicyEvaluateInput = serde_json::from_value(params)?;
                let allowed = request.call.name == "planning.ready_steps"
                    && request.tool_spec.is_some_and(|spec| {
                        spec.name == request.call.name && spec.safety == ToolSafety::ReadOnly
                    });
                Ok(serde_json::to_value(ProcessPolicyResponse::new(decision(
                    allowed,
                )))?)
            }
            ("policy", "evaluate_visibility") => {
                let request: ProcessPolicyVisibilityInput = serde_json::from_value(params)?;
                let allowed = request.tool_spec.name == "planning.ready_steps"
                    && request.tool_spec.safety == ToolSafety::ReadOnly;
                Ok(serde_json::to_value(ProcessPolicyResponse::new(decision(
                    allowed,
                )))?)
            }
            _ => bail!("unsupported fixture method"),
        }
    }
}
fn decision(allowed: bool) -> PolicyDecision {
    if allowed {
        PolicyDecision::Allow
    } else {
        PolicyDecision::Deny {
            reason: "offline fixture permits only planning.ready_steps/ReadOnly".into(),
        }
    }
}
