//! Pure validation of a pinned full-read ToolResult convention.
//! No host callbacks, filesystem access, assertion semantics or provenance proof.
use std::path::Path;

use anyhow::{Result, ensure};
use proteus_module_sdk::contracts::domain::ToolResult;
use serde::Deserialize;

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct ReadMetadata {
    tool: String,
    path: String,
    total_lines: u64,
    returned_lines: u64,
    truncated: bool,
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

// Present-null is not the same as absent; reject ambiguous optional metadata.
fn present<'de, D, T>(deserializer: D) -> std::result::Result<Option<T>, D::Error>
where
    D: serde::Deserializer<'de>,
    T: Deserialize<'de>,
{
    T::deserialize(deserializer).map(Some)
}

/// Validate returned host bytes. A matching envelope is not source authentication.
/// The caller separately bounds raw callback JSON, grants, paths and cancellation.
pub fn checked_read<'a>(
    result: &'a ToolResult,
    expected_call_id: &str,
    expected_path: &Path,
    max_output_bytes: usize,
) -> Result<&'a str> {
    ensure!(
        result.call_id == expected_call_id,
        "reader result call_id mismatch"
    );
    ensure!(
        result.ok && result.error.is_none(),
        "reader did not succeed"
    );
    ensure!(
        result.content.is_empty(),
        "reader returned ambiguous structured content"
    );
    ensure!(
        result.output.len() <= max_output_bytes,
        "reader output byte bound exceeded"
    );
    let metadata: ReadMetadata = serde_json::from_value(result.metadata.clone())
        .map_err(|_| anyhow::anyhow!("invalid or unsupported full-read metadata"))?;
    ensure!(metadata.tool == "read_file", "unexpected reader identity");
    ensure!(
        Some(metadata.path.as_str()) == expected_path.to_str(),
        "reader path differs from configured cwd/path"
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

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    fn result(text: &str) -> ToolResult {
        let r=ToolResult::ok("read-1".into(), text).with_metadata(json!({
            "tool":"read_file","path":"/workspace/source.txt",
            "total_lines":text.lines().count(),"returned_lines":text.lines().count(),"truncated":false
        }));
        // Every negative starts with this independently passing full envelope.
        assert_eq!(
            checked_read(&r, "read-1", Path::new("/workspace/source.txt"), usize::MAX).unwrap(),
            text
        );
        r
    }
    fn fails(r: &ToolResult, call: &str, path: &str, cap: usize, expected: &str) {
        assert_eq!(
            checked_read(r, call, Path::new(path), cap)
                .unwrap_err()
                .to_string(),
            expected
        );
    }

    #[test]
    fn preserves_exact_bytes_and_explicit_limit() {
        let r = result("a\r\nПривет\n");
        assert_eq!(
            checked_read(
                &r,
                "read-1",
                Path::new("/workspace/source.txt"),
                r.output.len()
            )
            .unwrap(),
            r.output
        );
        fails(
            &r,
            "read-1",
            "/workspace/source.txt",
            r.output.len() - 1,
            "reader output byte bound exceeded",
        );
    }

    #[test]
    fn absent_optional_flags_are_allowed_but_present_null_is_not() {
        for field in [
            "duration_ms",
            "output_truncated",
            "error_truncated",
            "canceled",
            "timed_out",
        ] {
            let mut r = result("x");
            r.metadata[field] = serde_json::Value::Null;
            fails(
                &r,
                "read-1",
                "/workspace/source.txt",
                10,
                "invalid or unsupported full-read metadata",
            );
        }
    }

    #[test]
    fn typed_false_flags_and_duration_are_allowed() {
        let mut r = result("x");
        r.metadata["duration_ms"] = json!(0);
        for field in [
            "output_truncated",
            "error_truncated",
            "canceled",
            "timed_out",
        ] {
            r.metadata[field] = json!(false);
        }
        assert_eq!(
            checked_read(&r, "read-1", Path::new("/workspace/source.txt"), 10).unwrap(),
            "x"
        );
    }

    #[test]
    fn rejects_unknown_reader_metadata() {
        for field in [
            "redacted",
            "start_line",
            "limit",
            "line_numbers",
            "provenance_verified",
        ] {
            let mut r = result("x");
            r.metadata[field] = json!(false);
            fails(
                &r,
                "read-1",
                "/workspace/source.txt",
                10,
                "invalid or unsupported full-read metadata",
            );
        }
    }

    #[test]
    fn checks_correlation_path_and_completeness_independently() {
        let base = result("x");
        fails(
            &base,
            "wrong",
            "/workspace/source.txt",
            10,
            "reader result call_id mismatch",
        );
        fails(
            &base,
            "read-1",
            "/workspace/other.txt",
            10,
            "reader path differs from configured cwd/path",
        );
        for (key, value, expected) in [
            ("tool", json!("other"), "unexpected reader identity"),
            ("total_lines", json!(2), "reader full-line counts mismatch"),
            (
                "returned_lines",
                json!(0),
                "reader full-line counts mismatch",
            ),
            ("truncated", json!(true), "reader returned partial content"),
            (
                "output_truncated",
                json!(true),
                "reader was truncated, canceled, or timed out",
            ),
            (
                "error_truncated",
                json!(true),
                "reader was truncated, canceled, or timed out",
            ),
            (
                "canceled",
                json!(true),
                "reader was truncated, canceled, or timed out",
            ),
            (
                "timed_out",
                json!(true),
                "reader was truncated, canceled, or timed out",
            ),
            (
                "duration_ms",
                json!(-1),
                "invalid or unsupported full-read metadata",
            ),
        ] {
            let mut r = base.clone();
            r.metadata[key] = value;
            fails(&r, "read-1", "/workspace/source.txt", 10, expected);
        }
    }
}
