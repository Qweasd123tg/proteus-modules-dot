use super::*;
use domain::ToolCall;
use model_standard::{CanonicalMessage, ContentPart, MessageRole};
use transcript::{Change, Transcript};

fn projected() -> Vec<proteus_contracts::app_protocol::AppTranscriptMessage> {
    let message = CanonicalMessage::new(MessageRole::Assistant, vec![
        ContentPart::Text { text: "Before tool".into() },
        ContentPart::ToolCall { call: ToolCall::new("call-1", "read_file", serde_json::json!({"path":"README.md"})) },
        ContentPart::Text { text: "After tool".into() },
    ]);
    core_projection::transcript_messages(&[message])
}

#[test]
fn round8_core_legal_interleaved_canonical_message_creates_repeated_row_identity() {
    let rows = projected();
    assert_eq!(rows.len(), 3);
    assert_eq!(rows[0].text, "Before tool");
    assert_eq!(rows[2].text, "After tool");
    assert!(rows[0].message_id.is_some());
    assert_eq!(rows[0].message_id, rows[2].message_id);
}

#[test]
fn round8_identical_authoritative_snapshot_reassigns_assistant_keys_forever() {
    let rows = projected();
    let mut client = Transcript::default();
    client.reset(rows.clone());
    let first_keys: Vec<_> = client.entries().iter().map(|entry| entry.key).collect();
    for n in 0..10 {
        let old_keys: Vec<_> = client.entries().iter().map(|entry| entry.key).collect();
        let change = client.reset(rows.clone());
        let new_keys: Vec<_> = client.entries().iter().map(|entry| entry.key).collect();
        assert_ne!(change, Change::None, "must reproduce spurious invalidation");
        assert_ne!(old_keys[0], new_keys[0]);
        assert_ne!(old_keys[2], new_keys[2]);
        assert_eq!(old_keys[2], new_keys[0], "identity of after-text gets assigned to before-text");
        assert_eq!(old_keys[1], new_keys[1], "tool identity remains stable");
        eprintln!("round {n}: {old_keys:?} -> {new_keys:?}; {change:?}");
    }
    assert_ne!(first_keys[0], client.entries()[0].key);
}

#[test]
fn round8_control_distinct_canonical_message_ids_preserve_identical_snapshot() {
    let messages = [
        CanonicalMessage::text(MessageRole::Assistant, "Before tool"),
        CanonicalMessage::new(MessageRole::Assistant, vec![ContentPart::ToolCall { call: ToolCall::new("call-1", "read_file", serde_json::json!({})) }]),
        CanonicalMessage::text(MessageRole::Assistant, "After tool"),
    ];
    let rows = core_projection::transcript_messages(&messages);
    let mut client = Transcript::default();
    client.reset(rows.clone());
    assert_eq!(client.reset(rows), Change::None);
}

#[test]
fn round8_history_page_reuses_one_live_key_for_both_split_assistant_rows() {
    let rows = projected();
    let mut live = Transcript::default();
    live.reset(rows.clone());
    let mut archive = Transcript::default();
    archive.append_page(rows, &live);
    let keys: Vec<_> = archive.entries().iter().map(|entry| entry.key).collect();
    assert_eq!(keys[0], keys[2], "reproduces duplicate UI row key for distinct text blocks");
    assert_ne!(archive.entries()[0].text, archive.entries()[2].text);
    eprintln!("archived row keys: {keys:?}");
}
