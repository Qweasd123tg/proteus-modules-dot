use super::*;
use crate::{
    core::{HistoryMutated, JOURNAL_SCHEMA_VERSION},
    domain::{SessionId, ToolCall},
    model_standard::{CanonicalMessage, MessageRole},
    r46_alloc::measure,
};
use uuid::Uuid;

fn message(i: usize, kind: &str) -> CanonicalMessage {
    let text = |s: &str| ContentPart::Text { text: s.to_owned() };
    let call = |suffix: &str| ContentPart::ToolCall {
        call: ToolCall::new(
            format!("{i}-{suffix}"),
            "read",
            serde_json::json!({ "path": "example" }),
        ),
    };
    let parts = match kind {
        "single" => vec![text("a short response α")],
        "multiple" => vec![text(" α α "), text("🌊"), text("三"), text("尾")],
        "mixed" => vec![
            text(" first "),
            call("1"),
            text("\u{2002}"),
            text("two"),
            text("三"),
            call("2"),
            text("🌊 trailing "),
            text("終"),
        ],
        "reasoning" => vec![ContentPart::ReasoningSummary {
            text: "summary".into(),
        }],
        _ => unreachable!(),
    };
    let mut item = CanonicalMessage::new(MessageRole::Assistant, parts);
    item.id = Uuid::from_u128(10_000 + i as u128);
    for (j, part) in item.parts.iter_mut().enumerate() {
        part.part_id = Uuid::from_u128(99_999 + 16 * i as u128 + j as u128);
    }
    item
}

#[test]
fn transcript_projection_allocation_diff_fixture() {
    let session: SessionId = Uuid::from_u128(1);
    let mut results = Vec::new();
    for (count, kind) in [
        (0, "single"),
        (1, "single"),
        (128, "single"),
        (1024, "single"),
        (128, "multiple"),
        (128, "mixed"),
        (128, "reasoning"),
    ] {
        let records: Vec<_> = (0..count)
            .map(|i| JournalRecord {
                schema_version: JOURNAL_SCHEMA_VERSION,
                record_id: Uuid::from_u128(100 + i as u128),
                session_seq: i as u64 + 1,
                timestamp_ms: 100 + i as i64,
                session_id: session,
                execution_id: None,
                thread_id: None,
                turn_id: None,
                entry: JournalEntry::HistoryMutated(HistoryMutated {
                    previous_revision: i as u64,
                    new_revision: i as u64 + 1,
                    mutation: HistoryMutationKind::Append,
                    messages: vec![message(i, kind)],
                    compaction: None,
                    tool_results: vec![],
                }),
            })
            .collect();
        let projection = crate::core::JournalProjection::build(session, records).unwrap();
        let (rows, stats) = measure(|| from_records(&projection.records, None).unwrap());
        assert_eq!(rows.len(), if kind == "mixed" { count * 5 } else { count });
        println!(
            "measure kind={kind} messages={count} rows={} calls={} bytes={}",
            rows.len(),
            stats.calls,
            stats.bytes
        );
        results.push(rows);
    }
    std::fs::write(
        std::env::var_os("PROTEUS_TRANSCRIPT_PROBE_OUTPUT").unwrap(),
        serde_json::to_vec(&results).unwrap(),
    )
    .unwrap();
}
