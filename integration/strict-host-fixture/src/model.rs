use std::collections::BTreeSet;

use anyhow::{Result, bail, ensure};
use proteus_module_sdk::contracts::{
    domain::{ModelRef, ToolCall, ToolChoice},
    model_standard::{
        CanonicalMessage, CanonicalModelRequest, CanonicalModelResponse, ContentPart, FinishReason,
        MessageRole, PartProvenance, PartScope,
    },
};
use serde::Deserialize;

use crate::{
    CANDIDATE_TEXT, MAX_MESSAGES, MAX_PARTS, MAX_REQUEST_BYTES, MAX_TOOLS, MODEL_ID, VERIFY_ID,
    WRITE_ID, bounded_json, expected_spec, verify_call, write_call,
};

#[derive(Debug, Clone, Copy, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum Scenario {
    WriteVerify,
    WriteThenStop,
}
#[derive(Debug, Clone, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct ModelConfig {
    pub scenario: Scenario,
}

pub(crate) fn check_model(model: &ModelRef) -> Result<()> {
    ensure!(
        model.provider == MODEL_ID && model.model == MODEL_ID,
        "unexpected strict fixture model reference"
    );
    Ok(())
}
#[derive(Debug, Clone, Copy)]
enum State {
    Start,
    WritePending,
    Written(bool),
    VerifyPending,
    Verified,
}

pub fn scripted_response(
    config: &ModelConfig,
    request: &CanonicalModelRequest,
    cancelled: impl Fn() -> bool,
) -> Result<CanonicalModelResponse> {
    ensure!(!cancelled(), "strict fixture canceled");
    check_model(&request.model)?;
    ensure!(
        request.messages.len() <= MAX_MESSAGES,
        "strict fixture message bound"
    );
    ensure!(
        request.tools.len() <= MAX_TOOLS,
        "strict fixture tool bound"
    );
    let count = request
        .messages
        .iter()
        .try_fold(0usize, |n, m| n.checked_add(m.parts.len()))
        .ok_or_else(|| anyhow::anyhow!("strict fixture part count overflow"))?;
    ensure!(count <= MAX_PARTS, "strict fixture part bound");
    bounded_json(request, MAX_REQUEST_BYTES)?;
    let mut names = BTreeSet::new();
    for spec in &request.tools {
        ensure!(
            names.insert(&spec.name),
            "duplicate strict fixture exposed tool"
        );
        ensure!(
            expected_spec(spec),
            "unexpected strict fixture exposed tool/safety"
        );
    }
    let mut state = State::Start;
    let mut message_ids = BTreeSet::new();
    let mut part_ids = BTreeSet::new();
    for message in &request.messages {
        ensure!(!cancelled(), "strict fixture canceled");
        ensure!(
            message_ids.insert(message.id),
            "duplicate strict fixture message identity"
        );
        for part in &message.parts {
            ensure!(!cancelled(), "strict fixture canceled");
            ensure!(
                part_ids.insert(part.part_id),
                "duplicate strict fixture part identity"
            );
            match &part.payload {
                ContentPart::ToolCall { call } => {
                    ensure!(
                        message.role == MessageRole::Assistant
                            && part.provenance == PartProvenance::Model
                            && part.scope == PartScope::Conversation,
                        "invalid strict fixture call provenance"
                    );
                    state = match state {
                        State::Start if *call == write_call() => State::WritePending,
                        State::Written(true)
                            if config.scenario == Scenario::WriteVerify
                                && *call == verify_call() =>
                        {
                            State::VerifyPending
                        }
                        _ => bail!("unexpected strict fixture call sequence or arguments"),
                    };
                }
                ContentPart::ToolResult { result } => {
                    ensure!(
                        message.role == MessageRole::Tool
                            && part.provenance == PartProvenance::Tool
                            && part.scope == PartScope::Conversation,
                        "invalid strict fixture result provenance"
                    );
                    ensure!(
                        message
                            .tool_call_id
                            .as_ref()
                            .is_none_or(|id| id == &result.call_id),
                        "strict fixture result owner mismatch"
                    );
                    state = match state {
                        State::WritePending if result.call_id == WRITE_ID => {
                            State::Written(result.ok && result.error.is_none())
                        }
                        State::VerifyPending if result.call_id == VERIFY_ID => State::Verified,
                        _ => bail!("unexpected strict fixture result sequence or call id"),
                    };
                }
                _ => {}
            }
        }
    }
    let next = match state {
        State::Start => Some(write_call()),
        State::Written(true) if config.scenario == Scenario::WriteVerify => Some(verify_call()),
        State::WritePending | State::VerifyPending => bail!("strict fixture has an unsettled call"),
        State::Written(_) | State::Verified => None,
    };
    let response = if let Some(call) = next {
        tool_response(request, call)?
    } else {
        {
            ensure!(
                matches!(request.tool_choice, ToolChoice::Auto | ToolChoice::None),
                "strict fixture final conflicts with tool choice"
            );
            CanonicalModelResponse::new(
                CanonicalMessage::text(MessageRole::Assistant, CANDIDATE_TEXT),
                vec![],
                FinishReason::Stop,
            )
        }
    };
    ensure!(!cancelled(), "strict fixture canceled");
    Ok(response)
}
fn tool_response(
    request: &CanonicalModelRequest,
    call: ToolCall,
) -> Result<CanonicalModelResponse> {
    ensure!(
        match &request.tool_choice {
            ToolChoice::Auto | ToolChoice::Required => true,
            ToolChoice::Tool(name) => name == &call.name,
            _ => false,
        },
        "strict fixture tool choice forbids required call"
    );
    ensure!(
        request
            .tools
            .iter()
            .any(|spec| spec.name == call.name && expected_spec(spec)),
        "required strict fixture tool not exposed"
    );
    Ok(CanonicalModelResponse::new(
        CanonicalMessage::new(
            MessageRole::Assistant,
            vec![ContentPart::ToolCall { call: call.clone() }],
        ),
        vec![call],
        FinishReason::ToolCalls,
    ))
}
