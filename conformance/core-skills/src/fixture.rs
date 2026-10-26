//! Authored context relay and narrow policy; no model, shell or file access.
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
            ("context", "skills_probe.context") | ("policy", "skills_probe.read_only")
        ),
        "unknown probe export"
    );
    let authority = process_contract_authority(&binding.slot, &binding.contract_version)
        .ok_or_else(|| anyhow::anyhow!("unknown contract"))?;
    ensure!(
        binding.composition == authority.composition,
        "composition is host-owned"
    );
    ensure!(
        binding.module_config == json!({}),
        "probe export has no configuration"
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
        ensure!(!host.is_cancelled(), "probe fixture canceled");
        match (self.0.slot.as_str(), method) {
            ("context", "build") => {
                let request: ProcessContextInput = serde_json::from_value(params)?;
                let output = ContextHostBridge(host.clone()).context_provider_json(
                    "portable.skills".into(),
                    serde_json::to_string(&json!({"task":request.task,"metadata":null}))?,
                )?;
                let chunks: Vec<ContextChunk> = serde_json::from_str(&output)?;
                Ok(serde_json::to_value(ProcessContextResponse::new(
                    ContextBundle::new(chunks),
                ))?)
            }
            ("policy", "evaluate") => {
                let request: ProcessPolicyEvaluateInput = serde_json::from_value(params)?;
                let allowed = request.tool_spec.is_some_and(|spec| {
                    spec.name == request.call.name && permitted(&spec.name, &spec.safety)
                });
                Ok(serde_json::to_value(ProcessPolicyResponse::new(decision(
                    allowed,
                )))?)
            }
            ("policy", "evaluate_visibility") => {
                let request: ProcessPolicyVisibilityInput = serde_json::from_value(params)?;
                Ok(serde_json::to_value(ProcessPolicyResponse::new(decision(
                    permitted(&request.tool_spec.name, &request.tool_spec.safety),
                )))?)
            }
            _ => bail!("unsupported probe method"),
        }
    }
}
fn permitted(name: &str, safety: &ToolSafety) -> bool {
    matches!(name, "portable_skill_catalog" | "portable_skill_load")
        && *safety == ToolSafety::ReadOnly
}
fn decision(allowed: bool) -> PolicyDecision {
    if allowed {
        PolicyDecision::Allow
    } else {
        PolicyDecision::Deny {
            reason: "probe allows only two portable ReadOnly tools".into(),
        }
    }
}
