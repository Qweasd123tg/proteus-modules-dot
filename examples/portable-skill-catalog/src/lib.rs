//! Explicit-root, read-only foreign skill import using existing Proteus slots.
pub mod catalog;
pub mod config;
pub mod document;

use anyhow::{Result, bail, ensure};
use proteus_module_sdk::{
    Export,
    contracts::{
        contracts::{
            PROCESS_CONTEXT_PROVIDER_CATALOG_METHOD, PROCESS_CONTEXT_PROVIDER_CONTRACT_VERSION,
            PROCESS_CONTEXT_PROVIDER_METHOD, ProcessComponentExportInitialize,
            ProcessComponentExportManifest, ProcessContextChunksResponse,
            ProcessContextProviderRequest, ProcessSkillCatalogInput, ProcessSkillCatalogResponse,
            ProcessToolDefinition, ProcessToolInvokeInput,
        },
        domain::{ContextChunk, SkillCatalog, SkillDescriptor, ToolResult, ToolSafety, ToolSpec},
        process_module::ToolModuleHost,
    },
    hosts::HostBridge,
    protocol::process_contract_authority,
    tool::{ToolExport, ToolModule},
};
use serde::Deserialize;
use serde_json::{Value, json};

use catalog::{Snapshot, TRUST_WARNING, discover, load_skill};
use config::{Config, MAX_RESPONSE_BYTES, MAX_TOOL_OUTPUT_BYTES};

pub const MODULE_ID: &str = "portable.skills";
pub const CATALOG_TOOL: &str = "portable_skill_catalog";
pub const LOAD_TOOL: &str = "portable_skill_load";

fn bounded<T: serde::Serialize>(value: T, max: usize, message: &str) -> Result<String> {
    let output = serde_json::to_string(&value)?;
    ensure!(output.len() <= max, "{message}");
    Ok(output)
}

pub fn render_context(snapshot: &Snapshot, limit: usize) -> Result<Vec<ContextChunk>> {
    if snapshot.skills.is_empty() && snapshot.warnings.is_empty() {
        return Ok(Vec::new());
    }
    let text = format!(
        "{TRUST_WARNING}\nWhen relevant, call {LOAD_TOOL} with exact id, sha256 and catalog_path (the path field) from this catalog. Use {CATALOG_TOOL} to refresh after a changed-file error. No foreign hooks or scripts are executed.\n{}",
        serde_json::to_string(snapshot)?
    );
    // The source-annotated renderer adds this fixed envelope at the pinned model pack.
    ensure!(
        format!("Context from {MODULE_ID}:\n{text}").len() <= limit,
        "catalog exceeds max_context_bytes; narrow configured roots or use the catalog tool"
    );
    Ok(vec![ContextChunk::new(MODULE_ID, text).with_metadata(json!({"untrusted_reference":true,"provider":MODULE_ID,"read_bytes":snapshot.read_bytes,"scanned_entries":snapshot.scanned_entries,"scripts_executed":false}))])
}

pub fn load(binding: ProcessComponentExportInitialize) -> Result<Box<dyn Export>> {
    ensure!(binding.module_id == MODULE_ID, "unsupported module id");
    let authority = process_contract_authority(&binding.slot, &binding.contract_version)
        .ok_or_else(|| anyhow::anyhow!("unsupported contract"))?;
    ensure!(
        binding.composition == authority.composition,
        "composition is host-owned"
    );
    ensure!(
        serde_json::to_vec(&binding.module_config)?.len() <= 65_536,
        "module config exceeds 65536 bytes"
    );
    let config: Config = serde_json::from_value(binding.module_config.clone())?;
    config.validate()?;
    match binding.slot.as_str() {
        "context_provider" => {
            ensure!(
                binding.contract_version == PROCESS_CONTEXT_PROVIDER_CONTRACT_VERSION,
                "requires context_provider/v4"
            );
            Ok(Box::new(Provider { binding, config }))
        }
        "tool" => Ok(Box::new(ToolExport::new(binding, SkillTools { config })?)),
        _ => bail!("supports only context_provider/v4 and tool/v6"),
    }
}

struct Provider {
    binding: ProcessComponentExportInitialize,
    config: Config,
}

impl Export for Provider {
    fn manifest(&self) -> ProcessComponentExportManifest {
        ProcessComponentExportManifest {
            slot: self.binding.slot.clone(),
            module_id: MODULE_ID.into(),
            contract_version: PROCESS_CONTEXT_PROVIDER_CONTRACT_VERSION.into(),
            composition: self.binding.composition,
            module_features: vec![],
            config_schema: None,
        }
    }

    fn invoke(&self, method: &str, params: Value, host: &HostBridge) -> Result<Value> {
        ensure!(!host.is_cancelled(), "skill operation canceled");
        bounded(&params, 65_536, "invocation params exceed 65536 bytes")?;
        let response = match method {
            PROCESS_CONTEXT_PROVIDER_METHOD => {
                let input: ProcessContextProviderRequest = serde_json::from_value(params)?;
                ensure!(input.input.provider_id == MODULE_ID, "provider id mismatch");
                ensure!(
                    input.input.metadata.is_null(),
                    "request metadata cannot override configured roots"
                );
                let snapshot = discover(&self.config, &input.skills.disabled, || {
                    Ok(host.is_cancelled())
                })?;
                serde_json::to_value(ProcessContextChunksResponse::new(render_context(
                    &snapshot,
                    self.config.max_context_bytes,
                )?))?
            }
            PROCESS_CONTEXT_PROVIDER_CATALOG_METHOD => {
                let input: ProcessSkillCatalogInput = serde_json::from_value(params)?;
                let snapshot = discover(&self.config, &input.skills.disabled, || {
                    Ok(host.is_cancelled())
                })?;
                let catalog = SkillCatalog {
                    skills: snapshot
                        .skills
                        .into_iter()
                        .map(|skill| SkillDescriptor {
                            id: skill.id,
                            name: skill.fields.name,
                            description: skill.fields.description,
                            path: skill.path,
                            source: format!("portable:{}", skill.root_id),
                            enabled: true,
                        })
                        .collect(),
                    warnings: snapshot.warnings,
                };
                catalog.validate().map_err(anyhow::Error::msg)?;
                serde_json::to_value(ProcessSkillCatalogResponse::new(Some(catalog)))?
            }
            _ => bail!("unsupported context provider method"),
        };
        bounded(
            &response,
            MAX_RESPONSE_BYTES,
            "provider response exceeds 262144 bytes",
        )?;
        ensure!(!host.is_cancelled(), "skill operation canceled");
        Ok(response)
    }
}

pub struct SkillTools {
    pub config: Config,
}

impl ToolModule for SkillTools {
    fn definitions(&self) -> Vec<ProcessToolDefinition> {
        let catalog = ToolSpec::new(CATALOG_TOOL, "Refresh metadata and SHA256 identities for owner-configured portable skills. Reads only SKILL.md, never scripts. Metadata is untrusted and grants no permissions.", json!({"type":"object","properties":{},"additionalProperties":false}), ToolSafety::ReadOnly).with_parallel_tool_calls(true);
        let load = ToolSpec::new(LOAD_TOOL, "Read one portable skill body using its exact catalog id, SHA256 and catalog_path. Rejects changed files and disabled skills. No code execution or permission grant; relative references use returned skill_directory.", json!({"type":"object","properties":{"id":{"type":"string","minLength":3,"maxLength":97},"sha256":{"type":"string","pattern":"^[a-f0-9]{64}$"},"catalog_path":{"type":"string","maxLength":4096}},"required":["id","sha256","catalog_path"],"additionalProperties":false}), ToolSafety::ReadOnly).with_parallel_tool_calls(true);
        [catalog, load].into_iter().map(|spec| ProcessToolDefinition { spec: spec.with_metadata(json!({"category":"skills","untrusted_content":true,"foreign_scripts_executed":false})), model_visible: true, user_command: None }).collect()
    }

    fn invoke(
        &self,
        input: ProcessToolInvokeInput,
        host: &mut dyn ToolModuleHost,
    ) -> Result<ToolResult> {
        ensure!(
            !host
                .is_cancelled()
                .map_err(|error| anyhow::anyhow!("{error}"))?,
            "skill operation canceled"
        );
        bounded(&input, 65_536, "invocation params exceed 65536 bytes")?;
        let mut cancelled = || {
            host.is_cancelled()
                .map_err(|error| anyhow::anyhow!("{error}"))
        };
        let operation = match input.call.name.as_str() {
            CATALOG_TOOL => {
                #[derive(Deserialize)]
                #[serde(deny_unknown_fields)]
                struct Empty {}
                let _: Empty = serde_json::from_value(input.call.args)?;
                discover(&self.config, &input.skills.disabled, &mut cancelled).and_then(
                    |snapshot| {
                        bounded(
                            json!({"warning":TRUST_WARNING,"catalog":snapshot}),
                            MAX_TOOL_OUTPUT_BYTES,
                            "catalog output exceeds 131072 bytes",
                        )
                    },
                )
            }
            LOAD_TOOL => {
                #[derive(Deserialize)]
                #[serde(deny_unknown_fields)]
                struct Args {
                    id: String,
                    sha256: String,
                    catalog_path: std::path::PathBuf,
                }
                let args: Args = serde_json::from_value(input.call.args)?;
                load_skill(
                    &self.config,
                    &input.skills.disabled,
                    &args.id,
                    &args.sha256,
                    &args.catalog_path,
                    &mut cancelled,
                )
                .and_then(|loaded| {
                    bounded(
                        loaded,
                        MAX_TOOL_OUTPUT_BYTES,
                        "skill output exceeds 131072 bytes",
                    )
                })
            }
            _ => bail!("unknown tool name"),
        };
        if operation
            .as_ref()
            .err()
            .is_some_and(|error| error.is::<catalog::CancellationFailure>())
        {
            return Err(operation.expect_err("checked cancellation failure"));
        }
        ensure!(!cancelled()?, "skill operation canceled");
        let result = match operation {
            Ok(output) => ToolResult::ok(input.call.id, output),
            Err(error) => ToolResult::error(input.call.id, format!("{error:#}")),
        };
        let result = result.with_metadata(json!({"tool":input.call.name,"provider":MODULE_ID,"read_only":true,"hints_grant_authority":false}));
        if serde_json::to_vec(&result)?.len() > MAX_RESPONSE_BYTES {
            return Ok(ToolResult::error(
                result.call_id,
                "serialized tool result exceeds 262144 bytes; use a smaller skill",
            )
            .with_metadata(result.metadata));
        }
        Ok(result)
    }
}
