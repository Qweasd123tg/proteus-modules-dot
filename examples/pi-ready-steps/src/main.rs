use anyhow::{Result, bail};
use proteus_module_sdk::{
    contracts::{
        contracts::{
            ProcessComponentExportInitialize, ProcessToolDefinition, ProcessToolInvokeInput,
        },
        domain::{ToolResult, ToolSafety, ToolSpec},
        process_module::ToolModuleHost,
    },
    tool::{ToolExport, ToolModule},
};
use proteus_pi_ready_steps::{
    AnalysisError, Input, MAX_ID_BYTES, MAX_NODES, analyze, encode_output,
};
use serde::Deserialize;
use serde_json::json;

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Config {}

struct ReadySteps;

impl ToolModule for ReadySteps {
    fn definitions(&self) -> Vec<ProcessToolDefinition> {
        let id = json!({"type": "string", "minLength": 1, "maxLength": MAX_ID_BYTES, "pattern": "^[A-Za-z0-9_.-]+$"});
        vec![ProcessToolDefinition {
            spec: ToolSpec::new(
                "planning.ready_steps",
                "Analyze a bounded DAG using caller-supplied, unverified statuses. Advisory only: never executes, authorizes, persists, or verifies steps. fail_fast suppresses all new readiness after any failed/canceled node; all_settled waits for all immediate dependencies to become terminal, including failures.",
                json!({
                    "type": "object", "additionalProperties": false,
                    "properties": {
                        "nodes": {"type": "array", "maxItems": MAX_NODES, "items": {
                            "type": "object", "additionalProperties": false,
                            "properties": {
                                "id": id.clone(),
                                "dependencies": {"type": "array", "maxItems": MAX_NODES, "uniqueItems": true, "items": id},
                                "status": {"enum": ["pending", "running", "succeeded", "failed", "canceled"]}
                            },
                            "required": ["id", "dependencies", "status"]
                        }},
                        "failure_policy": {"enum": ["fail_fast", "all_settled"]}
                    },
                    "required": ["nodes", "failure_policy"]
                }),
                ToolSafety::ReadOnly,
            ),
            model_visible: true,
            user_command: None,
        }]
    }

    fn invoke(
        &self,
        input: ProcessToolInvokeInput,
        host: &mut dyn ToolModuleHost,
    ) -> Result<ToolResult> {
        // ToolExport normalizes raw_arguments and validates the same schema before this call.
        if host.is_cancelled()? {
            bail!("planning canceled");
        }
        let plan: Input = serde_json::from_value(input.call.args)?;
        let result = analyze(&plan, || {
            host.is_cancelled().map_err(|error| error.to_string())
        })
        .and_then(|result| encode_output(&result));
        if host.is_cancelled()? {
            bail!("planning canceled");
        }
        match result {
            Ok(text) => Ok(ToolResult::ok(input.call.id, text)),
            Err(AnalysisError::Invalid(message)) => Ok(ToolResult::error(
                input.call.id,
                format!("invalid plan: {message}"),
            )),
            Err(error) => Err(error.into()),
        }
    }
}

fn load(binding: ProcessComponentExportInitialize) -> Result<Box<dyn proteus_module_sdk::Export>> {
    if binding.slot != "tool" || binding.module_id != "planning.ready_steps" {
        bail!("unsupported export {}/{}", binding.slot, binding.module_id);
    }
    let _: Config = serde_json::from_value(binding.module_config.clone())?;
    Ok(Box::new(ToolExport::new(binding, ReadySteps)?))
}

fn main() {
    if let Err(error) = proteus_module_sdk::run(load) {
        eprintln!("proteus-pi-ready-steps: {error:#}");
        std::process::exit(1);
    }
}
