//! Advisory-only hook/v6 process module; never blocks, retries or executes tools.
mod config;
mod signature;
mod state;

use std::{sync::Mutex, time::Instant};

use anyhow::{Result, anyhow, ensure};
use proteus_module_sdk::{
    Export,
    contracts::{
        contracts::{
            HookEvent, HookInput, HookResponse, ModelCallOrigin, PROCESS_HOOK_CONTRACT_VERSION,
            PROCESS_HOOK_INVOKE_METHOD, ProcessComponentExportInitialize,
            ProcessComponentExportManifest, ProcessHookResponse, ProcessModuleComposition,
        },
        model_standard::{InstructionBlock, InstructionKind},
    },
    hosts::HostBridge,
};
use serde_json::Value;

pub use config::Config;
pub const MODULE_ID: &str = "loop_observer.repeated_result";

pub struct LoopObserver {
    config: Config,
    state: Mutex<state::State>,
}

impl LoopObserver {
    pub fn new(binding: ProcessComponentExportInitialize) -> Result<Self> {
        ensure!(
            binding.slot == "hook" && binding.module_id == MODULE_ID,
            "unsupported export identity"
        );
        ensure!(
            binding.contract_version == PROCESS_HOOK_CONTRACT_VERSION,
            "requires hook/v6"
        );
        ensure!(
            binding.composition == ProcessModuleComposition::OrderedMany,
            "requires host-owned ordered_many composition"
        );
        let config: Config = serde_json::from_value(binding.module_config)?;
        config.validate()?;
        Ok(Self {
            config,
            state: Mutex::new(state::State::default()),
        })
    }

    pub fn evaluate(&self, input: HookInput, cancelled: impl Fn() -> bool) -> Result<HookResponse> {
        self.evaluate_at(input, cancelled, Instant::now())
    }

    fn evaluate_at(
        &self,
        input: HookInput,
        cancelled: impl Fn() -> bool,
        now: Instant,
    ) -> Result<HookResponse> {
        ensure!(!cancelled(), "loop observer canceled");
        // Keep short bounded state transitions serialized. No model/tool/file
        // callbacks and no locks held across external work or async waits.
        let mut state = self
            .state
            .lock()
            .map_err(|_| anyhow!("loop observer state poisoned"))?;
        ensure!(!cancelled(), "loop observer canceled");
        state.prune(now, &self.config);
        let attribution = input.attribution;
        match input.event {
            HookEvent::TurnStarted { .. } | HookEvent::TurnSettled { .. } => {
                state.remove(attribution)
            }
            HookEvent::AfterTool { call, result } => {
                if !self.config.observed_tools.contains(&call.name)
                    || call.id.is_empty()
                    || call.id.len() > 128
                    || call.id != result.call_id
                {
                    state.gap(attribution, now);
                } else if let Some(signature) = signature::build(
                    &call,
                    &result,
                    self.config.max_observation_bytes,
                    &cancelled,
                )? {
                    state.observe(
                        attribution,
                        now,
                        &call.name,
                        &call.id,
                        signature,
                        &self.config,
                    );
                } else {
                    // Oversized/complex observations are not evidence of a loop.
                    // Also discard a pending nudge so it cannot bridge this gap.
                    state.gap(attribution, now);
                }
            }
            HookEvent::BeforeModel {
                origin: ModelCallOrigin::Direct,
                mut request,
            } => {
                if let Some(notice) = state.take_notice(attribution, now) {
                    request.instructions.push(InstructionBlock::new(
                        InstructionKind::Developer,
                        notice,
                        0,
                    ));
                    return Ok(HookResponse::ModelContext {
                        messages: request.messages,
                        instructions: request.instructions,
                    });
                }
            }
            _ => {}
        }
        Ok(HookResponse::Continue)
    }
}

impl Export for LoopObserver {
    fn manifest(&self) -> ProcessComponentExportManifest {
        ProcessComponentExportManifest {
            slot: "hook".into(),
            module_id: MODULE_ID.into(),
            contract_version: PROCESS_HOOK_CONTRACT_VERSION.into(),
            composition: ProcessModuleComposition::OrderedMany,
            module_features: vec![],
            config_schema: Some(Config::schema()),
        }
    }

    fn invoke(&self, method: &str, params: Value, host: &HostBridge) -> Result<Value> {
        ensure!(
            method == PROCESS_HOOK_INVOKE_METHOD,
            "unsupported hook method"
        );
        ensure!(!host.is_cancelled(), "loop observer canceled");
        let input = serde_json::from_value(params)?;
        let result = self.evaluate(input, || host.is_cancelled())?;
        Ok(serde_json::to_value(ProcessHookResponse { result })?)
    }
}

pub fn load(binding: ProcessComponentExportInitialize) -> Result<Box<dyn Export>> {
    Ok(Box::new(LoopObserver::new(binding)?))
}

#[cfg(test)]
mod tests;
