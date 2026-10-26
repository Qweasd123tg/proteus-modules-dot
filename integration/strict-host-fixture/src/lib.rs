//! Test-only deterministic model and exact-args policy; never a production provider.
//! No filesystem, network, shell, approval transport, or host operation callbacks.
mod model;
mod policy;

pub use model::{ModelConfig, Scenario, scripted_response};
pub use policy::{PolicyConfig, evaluate, visibility};

use anyhow::{Result, bail, ensure};
use proteus_module_sdk::{
    Export,
    contracts::contracts::{
        ProcessComponentExportInitialize, ProcessComponentExportManifest,
        ProcessModelDescribeRequest, ProcessModelDescriptor, ProcessModelInput, ProcessModelOutput,
        ProcessModelTerminal, ProcessPolicyEvaluateInput, ProcessPolicyResponse,
        ProcessPolicyVisibilityInput,
    },
    contracts::domain::{ToolCall, ToolSafety, ToolSpec},
    contracts::model_standard::ModelCapabilities,
    hosts::HostBridge,
    protocol::process_contract_authority,
};
use serde::Serialize;
use serde_json::{Value, json};
use std::io::{Error, ErrorKind, Write};

pub const MODEL_ID: &str = "smoke.strict_scripted";
pub const POLICY_ID: &str = "smoke.strict_policy";
pub const WRITE_ID: &str = "strict-write";
pub const VERIFY_ID: &str = "strict-verify";
pub const VERIFIER: &str = "verification.json_contracts";
pub const RELATIVE_PATH: &str = "fixtures/release.json";
pub const CONTENT: &str = include_str!("../fixtures/release.json");
pub const CANDIDATE_TEXT: &str =
    "Authored fixture candidate; the host completion gate decides acceptance.";
pub const MAX_MESSAGES: usize = 64;
pub const MAX_PARTS: usize = 512;
pub const MAX_TOOLS: usize = 3;
pub const MAX_REQUEST_BYTES: usize = 256 * 1024;
pub const MAX_CONFIG_BYTES: usize = 2048;

pub fn write_call() -> ToolCall {
    ToolCall::new(
        WRITE_ID,
        "write_file",
        json!({"path": RELATIVE_PATH, "content": CONTENT}),
    )
}
pub fn verify_call() -> ToolCall {
    ToolCall::new(VERIFY_ID, VERIFIER, json!({}))
}
pub fn read_args() -> Value {
    json!({"path": RELATIVE_PATH})
}
pub fn expected_safety(name: &str) -> Option<ToolSafety> {
    match name {
        "write_file" => Some(ToolSafety::WritesFiles),
        "read_file" | VERIFIER => Some(ToolSafety::ReadOnly),
        _ => None,
    }
}
pub fn expected_spec(spec: &ToolSpec) -> bool {
    expected_safety(&spec.name).is_some_and(|safety| spec.safety == safety)
}

// Count serialized bytes without materializing a second full input string. The
// SDK has already parsed its Value; this is NOT a transport/global allocation cap.
struct Count {
    bytes: usize,
    limit: usize,
}
impl Write for Count {
    fn write(&mut self, bytes: &[u8]) -> std::io::Result<usize> {
        let next = self
            .bytes
            .checked_add(bytes.len())
            .ok_or_else(|| Error::new(ErrorKind::InvalidData, "fixture input size overflow"))?;
        if next > self.limit {
            return Err(Error::new(
                ErrorKind::InvalidData,
                "fixture input serialization bound",
            ));
        }
        self.bytes = next;
        Ok(bytes.len())
    }
    fn flush(&mut self) -> std::io::Result<()> {
        Ok(())
    }
}
pub fn bounded_json(value: &impl Serialize, limit: usize) -> Result<()> {
    serde_json::to_writer(Count { bytes: 0, limit }, value)?;
    Ok(())
}

enum Kind {
    Model(ModelConfig),
    Policy(PolicyConfig),
}
struct Fixture {
    binding: ProcessComponentExportInitialize,
    kind: Kind,
}

pub fn load(binding: ProcessComponentExportInitialize) -> Result<Box<dyn Export>> {
    let expected_contract = match (binding.slot.as_str(), binding.module_id.as_str()) {
        ("model", MODEL_ID) => "v12",
        ("policy", POLICY_ID) => "v2",
        _ => bail!("unsupported strict fixture identity"),
    };
    ensure!(
        binding.contract_version == expected_contract,
        "incorrect strict fixture contract"
    );
    let authority = process_contract_authority(&binding.slot, expected_contract)
        .ok_or_else(|| anyhow::anyhow!("missing fixture authority"))?;
    ensure!(
        binding.composition == authority.composition,
        "incorrect strict fixture composition"
    );
    bounded_json(&binding.module_config, MAX_CONFIG_BYTES)?;
    let kind = if binding.slot == "model" {
        Kind::Model(serde_json::from_value(binding.module_config.clone())?)
    } else {
        let config: PolicyConfig = serde_json::from_value(binding.module_config.clone())?;
        config.validate()?;
        Kind::Policy(config)
    };
    Ok(Box::new(Fixture { binding, kind }))
}

impl Export for Fixture {
    fn manifest(&self) -> ProcessComponentExportManifest {
        ProcessComponentExportManifest {
            slot: self.binding.slot.clone(),
            module_id: self.binding.module_id.clone(),
            contract_version: self.binding.contract_version.clone(),
            composition: self.binding.composition,
            module_features: vec![],
            config_schema: None,
        }
    }
    fn invoke(&self, method: &str, params: Value, host: &HostBridge) -> Result<Value> {
        ensure!(!host.is_cancelled(), "strict fixture canceled");
        bounded_json(&params, MAX_REQUEST_BYTES)?;
        let response = match (&self.kind, method) {
            (Kind::Model(_), "describe") => {
                let input: ProcessModelDescribeRequest = serde_json::from_value(params)?;
                model::check_model(&input.model)?;
                serde_json::to_value(ProcessModelDescriptor {
                    adapter_id: MODEL_ID.into(),
                    capabilities: ModelCapabilities::basic_text_and_tools(),
                    hosted_tools: vec![],
                })?
            }
            (Kind::Model(config), "stream") => {
                let input: ProcessModelInput = serde_json::from_value(params)?;
                let response = scripted_response(config, &input.request, || host.is_cancelled())?;
                serde_json::to_value(ProcessModelOutput {
                    event_count: 0,
                    terminal: ProcessModelTerminal::Response { response },
                })?
            }
            (Kind::Policy(config), "evaluate") => {
                let input: ProcessPolicyEvaluateInput = serde_json::from_value(params)?;
                serde_json::to_value(ProcessPolicyResponse::new(evaluate(config, &input)))?
            }
            (Kind::Policy(config), "evaluate_visibility") => {
                let input: ProcessPolicyVisibilityInput = serde_json::from_value(params)?;
                serde_json::to_value(ProcessPolicyResponse::new(visibility(config, &input)))?
            }
            _ => bail!("unsupported strict fixture method"),
        };
        ensure!(!host.is_cancelled(), "strict fixture canceled");
        Ok(response)
    }
}
