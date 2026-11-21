//! Model-free fixtures using real, unmodified Desktop transcript operations.
use super::agents::codex::{Item, ItemKind};
use super::transcript::Transcript;
use proteus_contracts::app_protocol::AppTranscriptMessage;

const ROWS: usize = 200;
const BYTES: usize = 8 * 1024 * 1024;

fn item(i: usize) -> Item {
    Item {
        id: format!("item-{i}"),
        turn_id: "synthetic-turn".into(),
        kind: ItemKind::Assistant {
            text: "synthetic Codex item".into(),
        },
        status: "completed".into(),
        timestamp_ms: Some(i as i64),
    }
}

pub fn resumed_codex(while_paused: usize) -> (Transcript, Transcript) {
    let mut live = Transcript::default();
    let mut headroom = BYTES;
    for i in 0..ROWS {
        live.external_upsert(item(i));
        live.external_trim_after_change(ROWS, BYTES, &mut headroom, None);
    }
    let archive = live.clone();
    for i in ROWS..ROWS + while_paused {
        live.external_upsert(item(i));
        live.external_trim_after_change(ROWS, BYTES, &mut headroom, None);
    }
    (archive, live)
}

pub fn older_codex_page() -> (Transcript, Transcript) {
    let (old, mut newer) = resumed_codex(ROWS);
    newer.external_prepend((1000..1050).map(item).collect());
    (old, newer)
}

pub fn fresh_core_seek() -> (Transcript, Transcript) {
    let page = |count| {
        (0..count)
            .map(|i| AppTranscriptMessage {
                timestamp_ms: Some(i),
                message_id: None,
                phase: None,
                role: "assistant".into(),
                text: format!("synthetic history row {i}"),
                images: Vec::new(),
                tool: None,
                subagent: None,
                streaming: false,
            })
            .collect()
    };
    let mut live = Transcript::default();
    live.reset(page(ROWS as i64 * 2));
    live.remove(0..ROWS);
    // Stock History::accept_seek starts with a fresh reducer and resets on
    // the requested 50-row page, independent of the live window above.
    let mut sought = Transcript::default();
    sought.reset(page(50));
    (live, sought)
}
