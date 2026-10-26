//! Proposed corrections, observed byte evidence and real SQLite compare-and-set.
//! Receipts are historical business outcomes, not write authority or semantic truth.
pub mod config;
pub mod evidence;
pub mod store;
mod strict_json;
pub mod types;
pub mod util;

use anyhow::{Result, ensure};
use config::*;
use proteus_module_sdk::{
    Export,
    contracts::{
        contracts::{
            ProcessComponentExportInitialize, ProcessModuleComposition, ProcessToolDefinition,
            ProcessToolInvokeInput,
        },
        domain::{ToolCallSurface, ToolResult, ToolSafety, ToolSpec},
        process_module::ToolModuleHost,
    },
    tool::{ToolExport, ToolModule},
};
use serde::Serialize;
use serde_json::{Value, json};
use store::{Record, Store};
use types::*;
use util::{canonical, sha256};
pub const MODULE_ID: &str = "memory.correction_cas";
pub const RESULT_KEY: &str = "proteus.example.correction_cas";
pub const INIT: &str = "memory.correction_init";
pub const READ: &str = "memory.correction_read";
pub const PREPARE: &str = "memory.correction_prepare";
pub const APPLY: &str = "memory.correction_apply";

pub struct CorrectionMemory {
    config: Config,
    policy_hash: String,
}
impl CorrectionMemory {
    /// Intentionally pure: no directory/file/SQLite activity at registration.
    pub fn new(config: Config) -> Result<Self> {
        config.validate()?;
        let policy_hash = sha256(&canonical(&config, 64 * 1024)?);
        Ok(Self {
            config,
            policy_hash,
        })
    }
    pub fn policy_sha256(&self) -> &str {
        &self.policy_hash
    }
    fn run(&self, input: &ProcessToolInvokeInput, host: &dyn ToolModuleHost) -> Result<ToolResult> {
        evidence::check_cancel(host)?;
        ensure!(call_id(&input.call.id), "invalid_outer_call_id");
        ensure!(
            input.call.surface == ToolCallSurface::Function,
            "unsupported_call_surface"
        );
        // SDK/Core normalize raw provider JSON into args but retain raw. Require
        // that precondition at direct-trait entry too; do not normalize silently
        // after an embedding may already have made an authority decision.
        if let Some(raw) = input.call.raw_arguments.as_deref() {
            ensure!(raw.len() <= MAX_PROPOSAL + 256, "raw_arguments_size");
            let parsed = strict_json::parse(raw)
                .map_err(|error| anyhow::anyhow!("raw_arguments_json: {error}"))?;
            ensure!(
                parsed == input.call.args,
                "raw_arguments_normalization_mismatch"
            );
        }
        canonical(&input.call.args, MAX_PROPOSAL + 256)?;
        ensure!(
            [INIT, READ, PREPARE, APPLY].contains(&input.call.name.as_str()),
            "unknown_tool"
        );
        let store = Store::resolve(&self.config, &self.policy_hash, &input.cwd)?;
        match input.call.name.as_str() {
            INIT => {
                ensure!(input.call.args == json!({}), "init_arguments");
                store.init(
                    |_| evidence::check_cancel(host),
                    |identity| response(&input.call.id, "initialized", identity, false),
                )
            }
            READ => {
                let request: ReadRequest = serde_json::from_value(input.call.args.clone())
                    .map_err(|_| anyhow::anyhow!("read_arguments"))?;
                let value = match request {
                    ReadRequest::Entry { key } => serde_json::to_value(store.read_entry(&key)?)?,
                    ReadRequest::Operation { operation_id } => {
                        serde_json::to_value(store.read_operation(&operation_id)?)?
                    }
                };
                evidence::check_cancel(host)?;
                response(&input.call.id, "read", &value, false)
            }
            PREPARE => {
                let request: PrepareRequest = serde_json::from_value(input.call.args.clone())
                    .map_err(|_| anyhow::anyhow!("prepare_arguments"))?;
                request.validate(&self.config)?;
                let entry = store.read_entry(&request.key)?;
                // read_entry's connection/transaction is already dropped here.
                let observation = evidence::verify(
                    &self.config,
                    &input.cwd,
                    &request.evidence,
                    &input.call.id,
                    host,
                )?;
                let proposal = Proposal::new(&entry.identity, entry.revision, request);
                proposal.validate(&self.config)?;
                let value = json!({"proposal_sha256":sha256(&canonical(&proposal,MAX_PROPOSAL)?),"proposal":proposal,"preparation_observation":observation,"reserves_revision":false,"grants_write_authority":false});
                evidence::check_cancel(host)?;
                response(&input.call.id, "prepared", &value, false)
            }
            APPLY => {
                let request: ApplyRequest = serde_json::from_value(input.call.args.clone())
                    .map_err(|_| anyhow::anyhow!("apply_arguments"))?;
                request.validate(&self.config)?;
                if let Some(record) = store.before_verify(&request)? {
                    evidence::check_cancel(host)?;
                    return operation_response(&input.call.id, &record, true);
                }
                let observation = evidence::verify(
                    &self.config,
                    &input.cwd,
                    &request.proposal.evidence,
                    &input.call.id,
                    host,
                )?;
                store.apply(
                    &request,
                    &observation,
                    |_| evidence::check_cancel(host),
                    |record, replayed| operation_response(&input.call.id, record, replayed),
                )
            }
            _ => unreachable!(),
        }
    }
}
fn response<T: Serialize>(
    call_id: &str,
    kind: &str,
    value: &T,
    replayed: bool,
) -> Result<ToolResult> {
    let result=ToolResult::ok(call_id.into(),format!("Correction memory: {kind}. Stored text is a proposal, not a verified fact."))
        .with_metadata(json!({RESULT_KEY:{"kind":kind,"result":value,"audit":{"replayed":replayed,"semantic_entailment":"not_evaluated","grants_write_authority":false}}}));
    canonical(&result, MAX_RESPONSE)?;
    Ok(result)
}
fn operation_response(call_id: &str, record: &Record, replayed: bool) -> Result<ToolResult> {
    response(call_id, "operation", record, replayed)
}
fn evidence_schema() -> Value {
    json!({"type":"object","additionalProperties":false,"required":["source_id","expected_sha256","claims"],"properties":{"source_id":{"type":"string","maxLength":64},"expected_sha256":{"type":"string","pattern":"^[0-9a-f]{64}$"},"claims":{"type":"array","minItems":1,"maxItems":32,"items":{"type":"object","additionalProperties":false,"required":["claim_id","start_byte","end_byte","quote"],"properties":{"claim_id":{"type":"string","maxLength":64},"start_byte":{"type":"integer","minimum":0},"end_byte":{"type":"integer","minimum":1,"maximum":65536},"quote":{"type":"string","maxLength":4096}}}}}})
}
impl ToolModule for CorrectionMemory {
    fn definitions(&self) -> Vec<ProcessToolDefinition> {
        let evidence = evidence_schema();
        let proposal = json!({"type":"object","additionalProperties":false,"required":["schema_version","store_id","database_instance_id","workspace_cwd","database_path","policy_sha256","key","expected_revision","new_text","evidence"],"properties":{"schema_version":{"const":1},"store_id":{"type":"string"},"database_instance_id":{"type":"string"},"workspace_cwd":{"type":"string"},"database_path":{"type":"string"},"policy_sha256":{"type":"string"},"key":{"type":"string","maxLength":128},"expected_revision":{"type":"integer","minimum":0},"new_text":{"type":"string","maxLength":4096},"evidence":evidence.clone()}});
        let specs = [
            (
                INIT,
                ToolSafety::WritesFiles,
                "Explicitly initialize only the configured new correction database; no migration or repair.",
                json!({"type":"object","properties":{},"additionalProperties":false}),
            ),
            (
                READ,
                ToolSafety::ReadOnly,
                "Read a proposed correction/revision or historical operation outcome; never initializes a store.",
                json!({"oneOf":[{"type":"object","additionalProperties":false,"required":["kind","key"],"properties":{"kind":{"const":"entry"},"key":{"type":"string"}}},{"type":"object","additionalProperties":false,"required":["kind","operation_id"],"properties":{"kind":{"const":"operation"},"operation_id":{"type":"string"}}}]}),
            ),
            (
                PREPARE,
                ToolSafety::ReadOnly,
                "Observe exact quoted evidence through the host verifier and prepare a revision-bound proposal. No reservation, semantic proof or write grant.",
                json!({"type":"object","additionalProperties":false,"required":["key","new_text","evidence"],"properties":{"key":{"type":"string","maxLength":128},"new_text":{"type":"string","maxLength":4096},"evidence":evidence}}),
            ),
            (
                APPLY,
                ToolSafety::WritesFiles,
                "Re-verify evidence, then transactionally compare revision and commit a proposal or durable conflict. Same operation ID/payload recovers its historical result.",
                json!({"type":"object","additionalProperties":false,"required":["operation_id","proposal"],"properties":{"operation_id":{"type":"string","maxLength":64},"proposal":proposal}}),
            ),
        ];
        specs
            .into_iter()
            .map(
                |(name, safety, description, schema)| ProcessToolDefinition {
                    spec: ToolSpec::new(
                        name,
                        format!(
                            "{description} Configured database: {}",
                            self.config.database_path
                        ),
                        schema,
                        safety,
                    )
                    .with_timeout(120_000)
                    .with_parallel_tool_calls(false),
                    model_visible: true,
                    user_command: None,
                },
            )
            .collect()
    }
    fn invoke(
        &self,
        input: ProcessToolInvokeInput,
        host: &mut dyn ToolModuleHost,
    ) -> Result<ToolResult> {
        let result = self.run(&input, host).and_then(|result| {
            // Includes historical replay/idempotent-init/read responses. A late
            // cancellation can hide a committed effect; retry the same payload.
            evidence::check_cancel(host)?;
            Ok(result)
        });
        match result {
            Ok(result) => Ok(result),
            Err(error) => Ok(ToolResult::error(
                input.call.id,
                format!("correction_memory: {error}"),
            )),
        }
    }
}
pub fn load(binding: ProcessComponentExportInitialize) -> Result<Box<dyn Export>> {
    ensure!(
        binding.slot == "tool"
            && binding.module_id == MODULE_ID
            && binding.composition == ProcessModuleComposition::OrderedMany,
        "unsupported export binding"
    );
    canonical(&binding.module_config, 64 * 1024)?;
    let config = serde_json::from_value(binding.module_config.clone())?;
    Ok(Box::new(ToolExport::new(
        binding,
        CorrectionMemory::new(config)?,
    )?))
}
