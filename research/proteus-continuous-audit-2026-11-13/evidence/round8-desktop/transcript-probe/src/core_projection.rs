use serde_json::Value;
use crate::{domain::{Citation, HostedToolActivity, HostedToolStatus, ToolCall, ToolResult}, model_standard::{CanonicalMessage, CanonicalPart, ContentPart, MessageRole}};
pub use proteus_contracts::app_protocol::{AppTranscriptMessage, AppTranscriptSubagent, AppTranscriptTool};
mod rows {
use std::collections::HashMap;

use super::{AppTranscriptMessage, AppTranscriptTool};

/// One render's append-only rows and the last card for each call identity.
/// Neither result/resolution nor citation/image updates change call IDs or row
/// positions. A display reset must clear both rows and their lookup together.
#[derive(Default)]
pub(super) struct TranscriptRows {
    pub(super) rows: Vec<AppTranscriptMessage>,
    latest_tools: HashMap<String, usize>,
}


impl TranscriptRows {
    pub(super) fn push(&mut self, row: AppTranscriptMessage) {
        if let Some(tool) = &row.tool {
            self.latest_tools
                .insert(tool.call_id.clone(), self.rows.len());
        }
        self.rows.push(row);
    }

    pub(super) fn clear(&mut self) {
        self.rows.clear();
        self.latest_tools.clear();
    }

    pub(super) fn tool_mut(&mut self, call_id: &str) -> Option<&mut AppTranscriptTool> {
        let index = *self.latest_tools.get(call_id)?;
        self.rows[index].tool.as_mut()
    }
}

}
use rows::TranscriptRows;
pub(super) fn transcript_messages(messages: &[CanonicalMessage]) -> Vec<AppTranscriptMessage> {
    let mut transcript = TranscriptRows::default();
    for message in messages {
        append_transcript_message(&mut transcript, message);
    }
    finalize_interrupted_tools(&mut transcript.rows);
    transcript.rows
}

fn append_transcript_message(transcript: &mut TranscriptRows, message: &CanonicalMessage) {
    append_transcript_parts(transcript, message, &message.parts);
}

fn append_transcript_parts<'a>(
    transcript: &mut TranscriptRows,
    message: &CanonicalMessage,
    parts: impl IntoIterator<Item = &'a CanonicalPart>,
) {
    let role = transcript_role(&message.role).to_owned();
    let mut text_parts = Vec::new();
    let mut images = Vec::new();
    for part in parts {
        match &part.payload {
            ContentPart::Image { image } => images.push(image.clone()),
            ContentPart::Text { text } if !text.trim().is_empty() => {
                text_parts.push(text.as_str());
            }
            ContentPart::ToolCall { call } => {
                flush_transcript_text(transcript, &role, message, &mut text_parts);
                append_transcript_tool_call(transcript, call);
            }
            ContentPart::ToolResult { result } => {
                flush_transcript_text(transcript, &role, message, &mut text_parts);
                append_transcript_tool_result(transcript, result);
            }
            ContentPart::HostedToolActivity { activity } => {
                flush_transcript_text(transcript, &role, message, &mut text_parts);
                append_hosted_tool_activity(transcript, activity);
            }
            ContentPart::Citation { citation } => {
                append_citation_metadata(&mut transcript.rows, citation);
            }
            _ => {}
        }
    }
    flush_transcript_text(transcript, &role, message, &mut text_parts);
    if !images.is_empty() {
        if let Some(item) = transcript
            .rows
            .last_mut()
            .filter(|item| item.message_id == Some(message.id))
        {
            item.images = images;
        } else {
            transcript.push(AppTranscriptMessage {
                timestamp_ms: None,
                message_id: Some(message.id),
                phase: message.phase,
                role,
                text: String::new(),
                images,
                tool: None,
                subagent: None,
                streaming: false,
            });
        }
    }
}

fn append_transcript_tool_call(transcript: &mut TranscriptRows, call: &ToolCall) {
    transcript.push(AppTranscriptMessage {
        timestamp_ms: None,
        images: Vec::new(),
        message_id: None,
        phase: None,
        role: "system".to_owned(),
        text: String::new(),
        tool: Some(AppTranscriptTool {
            terminal: None,
            effective_args: None,
            call_id: call.id.clone(),
            name: call.name.clone(),
            args: call.args.clone(),
            status: "running".to_owned(),
            result: None,
            metadata: Value::Null,
        }),
        subagent: None,
        streaming: false,
    });
}

fn finalize_interrupted_tools(transcript: &mut [AppTranscriptMessage]) {
    // Durable history/journal no longer has a live producer. A call without a
    // terminal result is interrupted, not an eternally running UI activity.
    for message in transcript {
        if let Some(tool) = message
            .tool
            .as_mut()
            .filter(|tool| tool.status == "running")
        {
            tool.status = "interrupted".to_owned();
        }
    }
}

fn append_hosted_tool_activity(transcript: &mut TranscriptRows, activity: &HostedToolActivity) {
    let status = match activity.status() {
        HostedToolStatus::Completed => "done",
        HostedToolStatus::Failed => "failed",
        HostedToolStatus::InProgress | HostedToolStatus::Searching => "running",
        HostedToolStatus::Unknown(_) => activity.status().as_str(),
        _ => "unknown",
    };
    let args = match activity {
        HostedToolActivity::WebSearch { action, .. } => {
            serde_json::to_value(action).unwrap_or(Value::Null)
        }
        HostedToolActivity::FileSearch {
            queries, results, ..
        } => serde_json::json!({
            "queries": queries,
            "result_count": results.len(),
        }),
        _ => Value::Null,
    };
    let result = match activity {
        HostedToolActivity::WebSearch { action, .. } => match action {
            crate::domain::WebSearchAction::Search { queries, sources } => Some(format!(
                "{} search quer{}; {} source{}",
                queries.len(),
                if queries.len() == 1 { "y" } else { "ies" },
                sources.len(),
                if sources.len() == 1 { "" } else { "s" }
            )),
            crate::domain::WebSearchAction::OpenPage { url } => Some(format!("opened {url}")),
            crate::domain::WebSearchAction::FindInPage { url, pattern } => {
                Some(format!("searched {url} for {pattern}"))
            }
            crate::domain::WebSearchAction::Unknown { name, .. } => {
                Some(format!("provider action: {name}"))
            }
            _ => None,
        },
        HostedToolActivity::FileSearch {
            queries, results, ..
        } => Some(format!(
            "{} quer{}; {} result{}",
            queries.len(),
            if queries.len() == 1 { "y" } else { "ies" },
            results.len(),
            if results.len() == 1 { "" } else { "s" }
        )),
        _ => None,
    };
    transcript.push(AppTranscriptMessage {
        timestamp_ms: None,
        images: Vec::new(),
        message_id: None,
        phase: None,
        role: "system".to_owned(),
        text: String::new(),
        tool: Some(AppTranscriptTool {
            terminal: None,
            effective_args: None,
            call_id: activity.id().to_owned(),
            name: activity.kind().as_str().to_owned(),
            args,
            status: status.to_owned(),
            result,
            metadata: serde_json::json!({
                "provider_hosted": true,
                "activity": activity,
                "citations": [],
            }),
        }),
        subagent: None,
        streaming: false,
    });
}

fn append_citation_metadata(transcript: &mut [AppTranscriptMessage], citation: &Citation) {
    let tool_name = match citation {
        Citation::Url { .. } => "web_search",
        Citation::File { .. } => "file_search",
        _ => return,
    };
    let Some(tool) = transcript.iter_mut().rev().find_map(|message| {
        message.tool.as_mut().filter(|tool| {
            tool.name == tool_name
                && tool
                    .metadata
                    .get("provider_hosted")
                    .and_then(Value::as_bool)
                    == Some(true)
        })
    }) else {
        return;
    };
    let Some(citations) = tool
        .metadata
        .get_mut("citations")
        .and_then(Value::as_array_mut)
    else {
        return;
    };
    if let Ok(citation) = serde_json::to_value(citation) {
        citations.push(citation);
    }
}

fn flush_transcript_text(
    transcript: &mut TranscriptRows,
    role: &str,
    message: &CanonicalMessage,
    text_parts: &mut Vec<&str>,
) {
    if text_parts.is_empty() {
        return;
    }
    transcript.push(AppTranscriptMessage {
        timestamp_ms: None,
        images: Vec::new(),
        message_id: Some(message.id),
        phase: message.phase,
        role: role.to_owned(),
        text: text_parts.join("\n"),
        tool: None,
        subagent: None,
        streaming: false,
    });
    text_parts.clear();
}

fn append_transcript_tool_result(transcript: &mut TranscriptRows, result: &ToolResult) {
    let status = if result.ok { "done" } else { "failed" }.to_owned();
    let result_text = result.text_or_status();
    if let Some(tool) = transcript.tool_mut(&result.call_id) {
        tool.terminal = result
            .metadata
            .get("tool_terminal")
            .and_then(|value| serde_json::from_value(value.clone()).ok());
        tool.status = status;
        tool.result = Some(result_text);
        tool.metadata = result.metadata.clone();
        return;
    }

    transcript.push(AppTranscriptMessage {
        timestamp_ms: None,
        images: Vec::new(),
        message_id: None,
        phase: None,
        role: "system".to_owned(),
        text: String::new(),
        tool: Some(AppTranscriptTool {
            terminal: result
                .metadata
                .get("tool_terminal")
                .and_then(|value| serde_json::from_value(value.clone()).ok()),
            effective_args: None,
            call_id: result.call_id.clone(),
            name: "tool".to_owned(),
            args: Value::Null,
            status,
            result: Some(result_text),
            metadata: result.metadata.clone(),
        }),
        subagent: None,
        streaming: false,
    });
}

fn transcript_role(role: &MessageRole) -> &'static str {
    match role {
        MessageRole::System | MessageRole::Developer => "system",
        MessageRole::User => "user",
        MessageRole::Assistant => "assistant",
        MessageRole::Tool => "system",
        _ => "system",
    }
}
