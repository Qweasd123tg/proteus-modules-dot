use super::*;
use crate::{ledger, transcript::Entry};
use serde_json::{Value, json};
use std::sync::Arc;
use uuid::Uuid;

const LIVE: usize = 950;
const REV: &str = "synthetic-forward-history";

fn rows(range: Range<usize>, changed: bool) -> Vec<AppTranscriptMessage> {
    range
        .map(|i| AppTranscriptMessage {
            timestamp_ms: Some(i as i64 + if changed { 1 } else { 0 }),
            message_id: Some(Uuid::from_u128(i as u128 + 1)),
            phase: None,
            role: if i % 2 == 0 { "assistant" } else { "user" }.into(),
            text: format!(
                "row {i}: {}{}",
                "строка 🦀".repeat(64),
                if changed && i >= LIVE && i % 5 == 0 {
                    "!"
                } else {
                    ""
                }
            ),
            images: vec![],
            tool: None,
            subagent: None,
            streaming: changed && i % 7 == 0,
        })
        .collect()
}

fn page(range: Range<usize>, live_count: usize, changed: bool) -> AppTranscriptPage {
    AppTranscriptPage {
        revision: REV.into(),
        start: range.start,
        total: LIVE + live_count,
        messages: rows(range, changed),
        base: None,
    }
}

fn cursor(before: usize) -> AppTranscriptCursor {
    AppTranscriptCursor {
        revision: REV.into(),
        before,
        base: None,
    }
}

fn trace(entry: &Entry) -> Value {
    json!({
        "key": entry.key,
        "id": entry.message_id,
        "role": format!("{:?}", entry.role),
        "text": &*entry.text,
        "images": entry.images,
        "tool": entry.tool,
        "subagent": entry.subagent,
        "streaming": entry.streaming,
        "time": entry.time
    })
}

fn fixture(
    name: &str,
    distance: usize,
    live_count: usize,
    changed: bool,
    length: usize,
    shared: usize,
) {
    let mut live = Transcript::default();
    let mut history = History::default();
    history.apply(
        &mut live,
        rows(LIVE..LIVE + live_count, false),
        Some(cursor(LIVE)),
    );
    let target = ScrollTarget {
        row: LIVE - distance,
        fraction: 0.0,
    };
    history.seek = Some(target);
    let seek = history.seek_cursor().unwrap();
    history
        .accept_seek(
            &live,
            &seek,
            page(seek.before - PAGE_ROWS..seek.before, live_count, false),
        )
        .unwrap();

    let newer = history.request(Direction::Newer, &live).unwrap();
    let before = seek.before;
    assert_eq!(newer.before - before, length);
    let next = page(before..newer.before, live_count, changed);
    let bytes: usize = next.messages.iter().map(|row| row.text.len()).sum();
    let matching_bytes: usize = (before..newer.before)
        .zip(&next.messages)
        .filter(|(ordinal, message)| {
            live.entries()
                .get(ordinal.saturating_sub(LIVE))
                .is_some_and(|old| *ordinal >= LIVE && old.text.as_ref() == message.text)
        })
        .map(|(_, message)| message.text.len())
        .sum();
    let (change, (conversions, copied_bytes)) =
        ledger::run(|| history.accept_page(&live, Direction::Newer, &newer, next, 17..25));
    assert_eq!(
        change,
        Some(vec![Change::Spliced {
            start: PAGE_ROWS,
            removed: 0,
            inserted: length
        }])
    ); // No eviction in any fixture, including with #393.
    let range = history.range(&live).unwrap();
    assert_eq!(range.rows, PAGE_ROWS + length);
    let after = history.displayed(&live).entries();
    let shared_keyspace = match std::env::var("HISTORY_PROBE_EXPECT_SHARED_KEYSPACE")
        .as_deref()
        .unwrap()
    {
        "1" => true,
        "0" => false,
        _ => panic!("expected 0 or 1"),
    };
    // The first accepted row is outside the live range. Stock assigns it
    // from an archive-local counter; #274 made that counter shared in M150.
    assert_eq!(
        after[PAGE_ROWS].key as usize,
        PAGE_ROWS + 1 + if shared_keyspace { live_count } else { 0 }
    );
    let seen_shared = after[PAGE_ROWS..]
        .iter()
        .zip(before..newer.before)
        .filter(|(row, i)| {
            *i >= LIVE && Arc::ptr_eq(&row.text, &live.entries()[i.saturating_sub(LIVE)].text)
        })
        .count();
    assert_eq!(seen_shared, shared);
    assert_eq!(range.start + 17, seek.before - PAGE_ROWS + 17);
    assert_eq!(range.start + range.rows, newer.before);
    println!(
        "TRACE {name} {change:?} {range:?} {}",
        serde_json::to_string(&after.iter().map(trace).collect::<Vec<_>>()).unwrap()
    );
    let latest = history.latest(&live);
    assert!(!history.archived());
    println!("TRACE {name} latest={latest:?}");
    // Only the composed tree shares the seek window and live row counter.
    live.push_user(None, "after", vec![]);
    let next_key = live.entries().last().unwrap().key;
    let archive_keys = if shared_keyspace {
        PAGE_ROWS + length
    } else {
        0
    };
    assert_eq!(next_key as usize, live_count + archive_keys + 1);
    println!("TRACE {name} next={next_key} shared={seen_shared}");
    println!("WORK {name} {length} {shared} {conversions} {bytes} {matching_bytes} {copied_bytes}");
}

pub fn run() {
    // Ordinary newer request after a 50-row seek: 35 rows cross onto a still-live tail.
    fixture("crossing", 40, 50, false, 50, 35);
    // These differing overlapping rows retain their new text and canonical dates.
    fixture("changed", 40, 50, true, 50, 28);
    fixture("nonoverlap", 100, 50, false, 50, 0);
    // Close seek matches the real stock regression test at row 920.
    fixture("near", 30, 50, false, 50, 45);
}
