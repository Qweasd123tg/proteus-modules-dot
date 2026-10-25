//! A bounded completion policy inspired by Hermes, not a Hermes-compatible runtime.
//! The only effect is a hook/v6 continuation (or explicit failure); no tool is run.

mod evidence;
mod receipt;
pub use evidence::{Evidence, inspect_history};
pub use receipt::ReceiptPolicy;

use std::collections::BTreeSet;

use anyhow::{Result, bail, ensure};
use proteus_module_sdk::{
    Export,
    contracts::contracts::{
        HookEvent, HookInput, HookResponse, PROCESS_HOOK_CONTRACT_VERSION,
        PROCESS_HOOK_INVOKE_METHOD, ProcessComponentExportInitialize,
        ProcessComponentExportManifest, ProcessHookResponse, ProcessModuleComposition,
    },
    hosts::HostBridge,
};
use serde::Deserialize;
use serde_json::Value;

pub const MODULE_ID: &str = "hermes.verify_evidence";
pub use proteus_example_json_receipt::RECEIPT_KEY;

#[derive(Debug, Clone, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Config {
    pub mutating_tools: BTreeSet<String>,
    pub verification_tools: BTreeSet<String>,
    pub max_nudges: u32,
    pub max_history_parts: usize,
    pub on_exhaustion: Exhaustion,
    pub receipt_policy: ReceiptPolicy,
}

#[derive(Debug, Clone, Copy, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum Exhaustion {
    Error,
    Continue,
}

impl Config {
    pub fn validate(&self) -> Result<()> {
        ensure!(
            (1..=8).contains(&self.max_nudges),
            "max_nudges must be 1..=8"
        );
        ensure!(
            (1..=100_000).contains(&self.max_history_parts),
            "max_history_parts must be 1..=100000"
        );
        for names in [&self.mutating_tools, &self.verification_tools] {
            ensure!(
                !names.is_empty() && names.len() <= 64,
                "tool sets need 1..=64 names"
            );
            ensure!(
                names
                    .iter()
                    .all(|name| !name.trim().is_empty() && name.len() <= 256),
                "tool names must be nonblank and at most 256 bytes"
            );
        }
        ensure!(
            self.mutating_tools.is_disjoint(&self.verification_tools),
            "a tool cannot be both a mutator and a verifier"
        );
        self.receipt_policy.validate()?;
        if matches!(
            self.receipt_policy,
            ReceiptPolicy::StrictJsonContracts { .. }
        ) {
            ensure!(
                matches!(self.on_exhaustion, Exhaustion::Error),
                "strict receipt policy requires on_exhaustion=error"
            );
        }
        Ok(())
    }
}

pub struct VerifyEvidence {
    binding: ProcessComponentExportInitialize,
    config: Config,
}

impl VerifyEvidence {
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

    /// Public pure-policy seam for tests. Production only supplies SDK cancellation.
    pub fn evaluate(
        &self,
        input: &HookInput,
        cancelled: impl Fn() -> bool,
    ) -> Result<HookResponse> {
        ensure!(!cancelled(), "verification gate canceled");
        let HookEvent::BeforeStop {
            history,
            attempt,
            continuation,
            ..
        } = &input.event
        else {
            return Ok(HookResponse::Continue);
        };
        // Never replace an earlier chain participant's decision.
        if continuation.is_some() {
            return Ok(HookResponse::Continue);
        }
        let evidence = inspect_history(history, &input.cwd, &self.config, &cancelled)?;
        ensure!(!cancelled(), "verification gate canceled");
        if !evidence.saw_mutation || evidence.fresh_verification {
            return Ok(HookResponse::Continue);
        }
        if *attempt >= self.config.max_nudges {
            if matches!(self.config.on_exhaustion, Exhaustion::Continue) {
                // Explicitly advisory policy: release is not a positive verification verdict.
                return Ok(HookResponse::Continue);
            }
            bail!(
                "verification evidence remains missing after {} continuation attempts; \
                 completion is not accepted (the tool's checks were not proved)",
                self.config.max_nudges
            );
        }
        Ok(HookResponse::ContinueTurn {
            reason: format!(
                "Verification evidence is missing after the latest configured mutation in retained \
                 canonical history. Run an authorized configured verifier ({}) after mutations \
                 settle. A successful shell exit or a prose claim is not verification evidence. \
                 If checks cannot run, explain the blocker; this policy does not grant permission \
                 or execute checks. Evidence scope: retained history, not a complete filesystem audit.",
                self.config
                    .verification_tools
                    .iter()
                    .cloned()
                    .collect::<Vec<_>>()
                    .join(", ")
            ),
        })
    }
}

impl Export for VerifyEvidence {
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
        let input: HookInput = serde_json::from_value(params)?;
        let result = self.evaluate(&input, || host.is_cancelled())?;
        Ok(serde_json::to_value(ProcessHookResponse { result })?)
    }
}

pub fn load(binding: ProcessComponentExportInitialize) -> Result<Box<dyn Export>> {
    Ok(Box::new(VerifyEvidence::new(binding)?))
}
