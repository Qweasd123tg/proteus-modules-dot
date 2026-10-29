//! Opt-in byte budgeting after an existing tool selector, not a permission policy.
//! ToolSpec values and their relative order are never changed. The budget covers
//! the compact JSON array of those canonical values, not provider tokens.

use std::{collections::BTreeSet, io};

use anyhow::{Context, Result, ensure};
use proteus_module_sdk::{
    Export,
    contracts::{
        contracts::{
            HookEvent, HookInput, HookResponse, PROCESS_HOOK_CONTRACT_VERSION,
            PROCESS_HOOK_INVOKE_METHOD, ProcessComponentExportInitialize,
            ProcessComponentExportManifest, ProcessHookResponse, ProcessModuleComposition,
            ToolSelectionOutput,
        },
        domain::{ToolSpec, ToolSurface},
    },
    hosts::HostBridge,
};
use serde::Deserialize;
use serde_json::{Value, json};

pub const MODULE_ID: &str = "tool_selection.schema_budget";

#[derive(Debug, Clone, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Config {
    /// Compact JSON bytes of the entire selected Vec<ToolSpec>, including [,].
    pub max_schema_bytes: usize,
    /// These names are mandatory only if present in the preceding selection.
    pub always_include: BTreeSet<String>,
    /// Explicitly opt in only phases whose workflow supports hidden-tool discovery.
    pub enabled_phases: BTreeSet<String>,
    #[serde(default)]
    pub on_mandatory_overflow: MandatoryOverflow,
    #[serde(default = "default_max_input_tools")]
    pub max_input_tools: usize,
    #[serde(default = "default_max_scan_bytes")]
    pub max_scan_bytes: usize,
}

#[derive(Debug, Clone, Copy, Default, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum MandatoryOverflow {
    /// Preserve the whole mandatory group and report the budget exception.
    #[default]
    Preserve,
    /// Explicit opt-in: fail this hook rather than hiding a mandatory tool.
    Error,
}

fn default_max_input_tools() -> usize {
    1024
}

fn default_max_scan_bytes() -> usize {
    8 * 1024 * 1024
}

impl Config {
    pub fn validate(&self) -> Result<()> {
        ensure!(
            (2..=1024 * 1024).contains(&self.max_schema_bytes),
            "max_schema_bytes must be 2..=1048576"
        );
        ensure!(
            (1..=4096).contains(&self.max_input_tools),
            "max_input_tools must be 1..=4096"
        );
        ensure!(
            (self.max_schema_bytes..=16 * 1024 * 1024).contains(&self.max_scan_bytes),
            "max_scan_bytes must be at least max_schema_bytes and at most 16777216"
        );
        ensure!(self.always_include.len() <= 128, "too many mandatory names");
        ensure!(
            !self.enabled_phases.is_empty() && self.enabled_phases.len() <= 32,
            "enabled_phases must contain 1..=32 explicit phases"
        );
        for name in self.always_include.iter().chain(&self.enabled_phases) {
            ensure!(
                !name.trim().is_empty() && name.len() <= 256,
                "configured names must be nonblank and at most 256 bytes"
            );
        }
        Ok(())
    }
}

pub struct SchemaBudget {
    binding: ProcessComponentExportInitialize,
    config: Config,
}

impl SchemaBudget {
    pub fn new(binding: ProcessComponentExportInitialize) -> Result<Self> {
        ensure!(binding.slot == "hook", "requires hook slot");
        ensure!(binding.module_id == MODULE_ID, "unsupported module id");
        ensure!(
            binding.contract_version == PROCESS_HOOK_CONTRACT_VERSION,
            "requires hook/v6"
        );
        ensure!(
            binding.composition == ProcessModuleComposition::OrderedMany,
            "requires host-owned ordered_many composition"
        );
        let config: Config = serde_json::from_value(binding.module_config.clone())?;
        config.validate()?;
        Ok(Self { binding, config })
    }

    pub fn evaluate(
        &self,
        input: HookInput,
        cancelled: impl Fn() -> bool,
    ) -> Result<HookResponse> {
        ensure!(!cancelled(), "schema budget canceled");
        let HookEvent::BeforeToolSelection { input, output } = input.event else {
            return Ok(HookResponse::Continue);
        };
        if !input
            .request
            .phase
            .as_ref()
            .is_some_and(|phase| self.config.enabled_phases.contains(phase))
        {
            return Ok(HookResponse::Continue);
        }
        // Deliberately use the preceding output, never restore input.candidates.
        // Core validates every accepted response against both sets independently.
        drop(input);
        select(output, &self.config, cancelled)
    }
}

fn mandatory(tool: &ToolSpec, config: &Config) -> bool {
    config.always_include.contains(&tool.name)
        || tool.metadata.get("category").and_then(Value::as_str)
            == Some("proteus_agent_control")
        // Reference deferred calls synthesize a Function ToolCall. Preserve all
        // other surfaces, including provider-hosted, freeform, workflow-owned
        // and any future unknown surface. Metadata never grants new authority.
        || !matches!(&tool.surface, ToolSurface::Function { .. })
        // The deferred meta-tool requires object-valued inner args, while Core
        // also accepts scalar/array/union schemas. Only an explicit object root
        // is known to fit that bridge; do not infer through $ref or combinators.
        || tool.input_schema.get("type").and_then(Value::as_str) != Some("object")
        // Older drafts can ignore siblings of $ref, including type: object.
        // Conservatively retain any root reference rather than resolve schemas.
        || ["$ref", "$dynamicRef", "$recursiveRef"]
            .iter()
            .any(|key| tool.input_schema.get(*key).is_some())
}

fn select(
    output: ToolSelectionOutput,
    config: &Config,
    cancelled: impl Fn() -> bool,
) -> Result<HookResponse> {
    let count = output.tools.len();
    ensure!(
        count <= config.max_input_tools,
        "input tool count exceeds scan limit"
    );

    let mut names = BTreeSet::new();
    let mut costs = Vec::with_capacity(count);
    let mut keep = Vec::with_capacity(count);
    let mut counter = ByteCounter {
        bytes: 2 + count.saturating_sub(1), // JSON array brackets and commas.
        limit: config.max_scan_bytes,
        cancelled: &cancelled,
    };
    ensure!(
        counter.bytes <= counter.limit,
        "schema scan byte limit exceeded"
    );
    let mut selected_bytes = 2;
    let mut selected_count = 0;
    for tool in &output.tools {
        ensure!(!cancelled(), "schema budget canceled");
        ensure!(names.insert(&tool.name), "duplicate preceding tool name");
        let before = counter.bytes;
        serde_json::to_writer(&mut counter, tool).context("counting canonical ToolSpec bytes")?;
        let cost = counter.bytes - before;
        let required = mandatory(tool, config);
        if required {
            selected_bytes += cost + usize::from(selected_count > 0);
            selected_count += 1;
        }
        costs.push(cost);
        keep.push(required);
    }
    drop(names);
    let input_bytes = counter.bytes;
    // No schema copy, reordering or metadata churn for a small catalog.
    if input_bytes <= config.max_schema_bytes {
        ensure!(!cancelled(), "schema budget canceled");
        return Ok(HookResponse::Continue);
    }

    let mandatory_count = selected_count;
    let mandatory_bytes = selected_bytes;
    let mandatory_overflow = mandatory_bytes > config.max_schema_bytes;
    ensure!(
        !mandatory_overflow || matches!(config.on_mandatory_overflow, MandatoryOverflow::Preserve),
        "mandatory tools require {mandatory_bytes} canonical JSON bytes; budget is {}; \
         no tool was removed and no response was accepted (on_mandatory_overflow=error)",
        config.max_schema_bytes
    );

    // Reserve the complete mandatory group first, then admit optional tools in
    // their previous relevance order. A large optional tool does not block later
    // small tools. The final filter preserves the order of every retained tool.
    for (required, cost) in keep.iter_mut().zip(costs) {
        ensure!(!cancelled(), "schema budget canceled");
        if !*required {
            let candidate_bytes = selected_bytes + cost + usize::from(selected_count > 0);
            if candidate_bytes <= config.max_schema_bytes {
                *required = true;
                selected_bytes = candidate_bytes;
                selected_count += 1;
            }
        }
    }

    let tools = output
        .tools
        .into_iter()
        .zip(keep)
        .filter_map(|(tool, keep)| keep.then_some(tool))
        .collect();
    let mut selected = ToolSelectionOutput::new(tools);
    // Preserve arbitrary upstream metadata as a value, without overwriting its
    // keys or presenting the previous selector's counts as this final result.
    selected.metadata = json!({
        "upstream": output.metadata,
        "schema_budget": {
            "selector": MODULE_ID,
            "metric": "compact_json_vec_tool_spec_bytes",
            "max_schema_bytes": config.max_schema_bytes,
            "input_bytes": input_bytes,
            "selected_bytes": selected_bytes,
            "input_count": count,
            "selected_count": selected_count,
            "hidden_by_budget_count": count - selected_count,
            "mandatory_count": mandatory_count,
            "mandatory_bytes": mandatory_bytes,
            "mandatory_overflow": mandatory_overflow,
            "provider_tokens_measured": false,
        },
    });
    ensure!(!cancelled(), "schema budget canceled");
    Ok(HookResponse::ToolSelection { output: selected })
}

/// Count encoded bytes without allocating another serialized schema buffer.
/// This bounds this scan only: SDK input JSON has already been received/decoded.
struct ByteCounter<'a, F> {
    bytes: usize,
    limit: usize,
    cancelled: &'a F,
}

impl<F: Fn() -> bool> io::Write for ByteCounter<'_, F> {
    fn write(&mut self, bytes: &[u8]) -> io::Result<usize> {
        if (self.cancelled)() {
            // Interrupted may be retried by write_all; cancellation must stop it.
            return Err(io::Error::other("schema budget canceled"));
        }
        let next = self
            .bytes
            .checked_add(bytes.len())
            .filter(|next| *next <= self.limit)
            .ok_or_else(|| io::Error::other("schema scan byte limit exceeded"))?;
        self.bytes = next;
        Ok(bytes.len())
    }

    fn flush(&mut self) -> io::Result<()> {
        Ok(())
    }
}

impl Export for SchemaBudget {
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
        ensure!(
            method == PROCESS_HOOK_INVOKE_METHOD,
            "unsupported hook method"
        );
        ensure!(!host.is_cancelled(), "schema budget canceled");
        let input: HookInput = serde_json::from_value(params)?;
        let result = self.evaluate(input, || host.is_cancelled())?;
        Ok(serde_json::to_value(ProcessHookResponse { result })?)
    }
}

pub fn load(binding: ProcessComponentExportInitialize) -> Result<Box<dyn Export>> {
    Ok(Box::new(SchemaBudget::new(binding)?))
}
