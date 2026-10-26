use anyhow::{Result, ensure};
use proteus_module_sdk::contracts::{
    contracts::{ProcessPolicyEvaluateInput, ProcessPolicyVisibilityInput},
    domain::{PolicyDecision, ToolCallSurface},
};
use serde::Deserialize;
use std::path::{Component, PathBuf};

use crate::{VERIFIER, expected_spec, read_args, write_call};

#[derive(Debug, Clone, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct PolicyConfig {
    pub cwd: PathBuf,
    pub deny_reader: bool,
}
impl PolicyConfig {
    pub fn validate(&self) -> Result<()> {
        let text = self
            .cwd
            .to_str()
            .ok_or_else(|| anyhow::anyhow!("fixture cwd must be UTF-8"))?;
        ensure!(
            self.cwd.is_absolute() && text.len() <= 1024 && !text.chars().any(char::is_control),
            "fixture cwd must be bounded and absolute"
        );
        ensure!(
            self.cwd
                .components()
                .any(|c| matches!(c, Component::Normal(_))),
            "fixture cwd cannot be root"
        );
        ensure!(
            !self
                .cwd
                .components()
                .any(|c| matches!(c, Component::ParentDir)),
            "fixture cwd cannot contain parent traversal"
        );
        let lexical: PathBuf = self.cwd.components().collect();
        ensure!(
            lexical.as_os_str() == self.cwd.as_os_str(),
            "fixture cwd must use exact normalized spelling"
        );
        Ok(())
    }
}
fn deny(reason: &str) -> PolicyDecision {
    PolicyDecision::Deny {
        reason: reason.into(),
    }
}

pub fn visibility(config: &PolicyConfig, input: &ProcessPolicyVisibilityInput) -> PolicyDecision {
    if input.cwd.as_os_str() == config.cwd.as_os_str() && expected_spec(&input.tool_spec) {
        // Visibility never approves execution. The exact write invocation must Ask.
        PolicyDecision::Allow
    } else {
        deny("strict fixture visibility rejects cwd/name/safety")
    }
}

pub fn evaluate(config: &PolicyConfig, input: &ProcessPolicyEvaluateInput) -> PolicyDecision {
    if input.cwd.as_os_str() != config.cwd.as_os_str()
        || input.call.surface != ToolCallSurface::Function
        || input.call.raw_arguments.is_some()
        || !input
            .tool_spec
            .as_ref()
            .is_some_and(|spec| spec.name == input.call.name && expected_spec(spec))
    {
        return deny("strict fixture rejects cwd/name/safety");
    }
    // Any cached/granted permission is intentionally irrelevant to this fixture.
    // The host still owns permissions, requested approval, admission and effects.
    match input.call.name.as_str() {
        "write_file" if input.call.args == write_call().args => PolicyDecision::Ask {
            reason: "approve only the exact authored fixture write, once and uncached".into(),
        },
        "read_file" if input.call.args == read_args() && config.deny_reader => {
            deny("strict fixture read deliberately denied")
        }
        "read_file" if input.call.args == read_args() => PolicyDecision::Allow,
        VERIFIER if input.call.args == serde_json::json!({}) => PolicyDecision::Allow,
        _ => deny("strict fixture rejects non-exact arguments or tool"),
    }
}
