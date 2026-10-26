//! Deliberately pins the full-read result convention, not arbitrary reader text.
use std::path::Path;

use anyhow::{Result, ensure};
use proteus_module_sdk::contracts::domain::ToolResult;
use serde::Deserialize;

use crate::config::MAX_FILE_BYTES;

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct ReadMetadata {
    tool: String,
    path: String,
    total_lines: u64,
    returned_lines: u64,
    truncated: bool,
    // Core adds duration_ms to successful results; the other flags are negative evidence.
    #[serde(default, deserialize_with = "present")]
    duration_ms: Option<u64>,
    #[serde(default, deserialize_with = "present")]
    output_truncated: Option<bool>,
    #[serde(default, deserialize_with = "present")]
    error_truncated: Option<bool>,
    #[serde(default, deserialize_with = "present")]
    canceled: Option<bool>,
    #[serde(default, deserialize_with = "present")]
    timed_out: Option<bool>,
}

fn present<'de, D, T>(deserializer: D) -> Result<Option<T>, D::Error>
where
    D: serde::Deserializer<'de>,
    T: Deserialize<'de>,
{
    T::deserialize(deserializer).map(Some)
}

pub fn checked_read<'a>(
    result: &'a ToolResult,
    call_id: &str,
    expected_path: &Path,
) -> Result<&'a str> {
    ensure!(result.call_id == call_id, "reader result call_id mismatch");
    ensure!(
        result.ok && result.error.is_none(),
        "reader did not succeed"
    );
    ensure!(
        result.content.is_empty(),
        "reader returned ambiguous structured content"
    );
    ensure!(
        result.output.len() <= MAX_FILE_BYTES,
        "document exceeds {MAX_FILE_BYTES} bytes"
    );
    let metadata: ReadMetadata = serde_json::from_value(result.metadata.clone())
        .map_err(|_| anyhow::anyhow!("invalid or unsupported full-read metadata"))?;
    ensure!(metadata.tool == "read_file", "unexpected reader identity");
    ensure!(
        Some(metadata.path.as_str()) == expected_path.to_str(),
        "reader resolved path differs from configured cwd/path (aliases are unsupported)"
    );
    ensure!(!metadata.truncated, "reader returned partial content");
    for flag in [
        metadata.output_truncated,
        metadata.error_truncated,
        metadata.canceled,
        metadata.timed_out,
    ] {
        ensure!(
            !flag.unwrap_or(false),
            "reader was truncated, canceled, or timed out"
        );
    }
    let _ = metadata.duration_ms;
    let lines = result.output.lines().count() as u64;
    ensure!(
        metadata.total_lines == lines && metadata.returned_lines == lines,
        "reader full-line counts mismatch"
    );
    Ok(&result.output)
}
