use super::*;
use crate::agents::codex::{Item, ItemKind};
use crate::ledger;
use proteus_contracts::app_protocol::AppTranscriptTool;
use serde_json::{Value, json};
use uuid::Uuid;

const REV: &str = "synthetic-history-revision";
const END: usize = 1000;
const LIVE: usize = 950;

fn payload() -> Value {
    json!({"commands":[{"source":["a","b"],"flags":[true,false,null]}, {"cwd":"synthetic"}],"meta":{"budget":12}})
}

fn rows(range: Range<usize>, nested: bool, oversized: Option<usize>) -> Vec<AppTranscriptMessage> {
    range
        .map(|i| AppTranscriptMessage {
            timestamp_ms: Some(i as i64),
            message_id: Some(Uuid::from_u128(i as u128 + 1)),
            phase: None,
            role: if nested { "system" } else { "user" }.into(),
            text: if oversized == Some(i) {
                "x".repeat(CACHE_BYTES + 9)
            } else {
                format!("row {i}:A")
            },
            images: vec![],
            subagent: None,
            streaming: false,
            tool: nested.then(|| AppTranscriptTool {
                call_id: format!("tool-{i}"),
                name: "synthetic_tool".into(),
                args: payload(),
                effective_args: Some(payload()),
                status: "done".into(),
                result: Some("fixture:A".into()),
                metadata: json!({"tags":["x","y"],"attrs":{"enabled":true}}),
                terminal: None,
            }),
        })
        .collect()
}

fn cursor(before: usize) -> AppTranscriptCursor {
    AppTranscriptCursor {
        revision: REV.into(),
        before,
        base: None,
    }
}
fn page(range: Range<usize>, nested: bool, oversized: Option<usize>) -> AppTranscriptPage {
    AppTranscriptPage {
        revision: REV.into(),
        start: range.start,
        total: END,
        messages: rows(range, nested, oversized),
        base: None,
    }
}

fn ids(t: &Transcript) -> Vec<(u64, Option<u128>, usize, Option<u8>)> {
    t.entries()
        .iter()
        .map(|row| {
            (
                row.key,
                row.message_id.map(|id| id.as_u128()),
                row.text.len(),
                row.tool
                    .as_ref()
                    .and_then(|tool| tool.result.as_ref())
                    .and_then(|s| s.as_bytes().last())
                    .copied(),
            )
        })
        .collect()
}

fn fixture(nested: bool, warm: usize, oversized: Option<usize>) -> (History, Transcript) {
    let mut h = History::default();
    let mut t = Transcript::default();
    h.apply(
        &mut t,
        rows(LIVE..END, nested, oversized),
        Some(cursor(LIVE)),
    );
    for _ in 0..warm {
        let q = h.request(Direction::Older, &t).unwrap();
        h.accept_page(
            &t,
            Direction::Older,
            &q,
            page(q.before - PAGE_ROWS..q.before, nested, oversized),
            0..12,
        )
        .unwrap();
    }
    (h, t)
}

fn action(
    label: &str,
    nested: bool,
    warm: usize,
    dir: Direction,
    visible: Range<usize>,
    oversized: Option<usize>,
    context: bool,
) {
    let (mut h, t) = fixture(nested, warm, oversized);
    let prior = h.range(&t).unwrap();
    let anchor = h.displayed(&t).entries()[visible.start].key;
    let previous_anchor = prior.start + visible.start;
    if context {
        h.context_seek = Some(ContextSeek::new(ScrollTarget {
            row: prior.start + visible.start,
            fraction: 0.5,
        }));
    }
    let q = h.request(dir, &t).unwrap();
    let incoming = page(q.before - PAGE_ROWS..q.before, nested, oversized);
    ledger::begin(h.displayed(&t).entries());
    let changes = h.accept_page(&t, dir, &q, incoming, visible).unwrap();
    ledger::end(label);
    let range = h.range(&t).unwrap();
    let after = h.displayed(&t).entries();
    let anchor_offset = after
        .iter()
        .position(|row| row.key == anchor)
        .expect("visible logical anchor survives");
    assert_eq!(range.start + anchor_offset, previous_anchor);
    let budget = after
        .iter()
        .map(|entry| entry.retained_bytes())
        .sum::<usize>();
    println!(
        "parity\t{label}\t{prior:?}\t{range:?}\t{changes:?}\tanchor={anchor}:{anchor_offset}\tbudget={budget}\t{:?}",
        ids(h.displayed(&t))
    );
    if label == "core-older-nested" || label == "core-newer-nested" {
        assert_eq!(prior.rows, 200);
        assert_eq!(after.len(), 200);
        assert!(budget <= CACHE_BYTES);
    }
    if label == "core-byte-only" {
        assert!(budget <= CACHE_BYTES);
        assert_eq!(after.len(), 99);
    }
    if label == "core-large-visible" {
        assert!(after.iter().any(|row| row.text.len() > CACHE_BYTES));
        assert!(budget > CACHE_BYTES);
    }
}

fn snapshots() {
    for changed in [false, true] {
        let (mut h, mut t) = fixture(true, 4, None);
        let mut next = rows(LIVE..END, true, None);
        if changed {
            next.last_mut().unwrap().tool.as_mut().unwrap().result = Some("fixture:B".into());
        }
        let label = if changed {
            "core-snapshot-changed-live"
        } else {
            "core-snapshot-unchanged"
        };
        ledger::begin(h.displayed(&t).entries());
        let edits = h.apply(&mut t, next, Some(cursor(LIVE)));
        ledger::end(label);
        println!(
            "parity\t{label}\t{edits:?}\t{:?}\t{:?}",
            ids(&t),
            ids(h.displayed(&t))
        );
    }
}

fn item(i: usize, version: &str) -> Item {
    Item {
        id: format!("item-{i}"),
        turn_id: "synthetic-turn".into(),
        status: "running".into(),
        timestamp_ms: Some(i as i64),
        kind: ItemKind::Tool {
            name: "synthetic_tool".into(),
            input: json!({"payload":payload(),"version":version}),
            output: format!("fixture:{version}"),
        },
    }
}
fn codex() {
    for (label, which) in [
        ("codex-delta-with-headroom", 0),
        ("codex-replace", 1),
        ("codex-insert", 2),
    ] {
        let mut t = Transcript::default();
        for i in 0..200 {
            t.external_upsert(item(i, "A"));
        }
        let (_, mut left) = t.external_trim_budget(CACHE_ROWS, CACHE_BYTES);
        ledger::begin(t.entries());
        let change = match which {
            0 => t.external_delta("synthetic-turn", "item-199", "B", false, true),
            1 => t.external_upsert(item(199, "B")),
            _ => t.external_upsert(item(200, "B")),
        };
        let trim = t.external_trim_after_change(
            CACHE_ROWS,
            CACHE_BYTES,
            &mut left,
            (which == 0).then_some(1),
        );
        ledger::end(label);
        println!(
            "parity\t{label}\t{change:?}\t{trim:?}\tleft={left}\t{:?}",
            ids(&t)
        );
    }
}

fn trim_matrix() {
    let mut count = 0;
    for n in [0usize, 1, 49, 50, 51, 199, 200, 201, 249, 250, 251] {
        for big in [None, Some(0), n.checked_sub(1)] {
            let mut seed = Transcript::default();
            seed.reset(rows(0..n, false, big));
            for dir in [Direction::Older, Direction::Newer] {
                for visible in [
                    0..0,
                    0..1,
                    n / 2..(n / 2 + 10).min(n),
                    n.saturating_sub(11)..n,
                    n..n,
                    n..n.saturating_add(1),
                ] {
                    let mut w = HistoryWindow {
                        start: 40,
                        transcript: seed.clone(),
                    };
                    let changed = w.trim(dir, visible.clone());
                    println!(
                        "parity\tmatrix\t{n}:{big:?}:{dir:?}:{visible:?}\t{changed:?}\t{}\t{:?}",
                        w.start,
                        ids(&w.transcript)
                    );
                    count += 1;
                }
            }
        }
    }
    println!("parity\tmatrix-cases\t{count}");
}

pub(crate) fn run() {
    action(
        "core-older-text",
        false,
        3,
        Direction::Older,
        15..25,
        None,
        false,
    );
    action(
        "core-older-nested",
        true,
        3,
        Direction::Older,
        15..25,
        None,
        false,
    );
    action(
        "core-newer-nested",
        true,
        5,
        Direction::Newer,
        100..120,
        None,
        false,
    );
    action(
        "core-protected-edge",
        true,
        3,
        Direction::Older,
        180..199,
        None,
        false,
    );
    action(
        "core-context-older",
        true,
        3,
        Direction::Older,
        15..25,
        None,
        true,
    );
    action(
        "core-byte-only",
        false,
        0,
        Direction::Older,
        15..25,
        Some(999),
        false,
    );
    action(
        "core-large-visible",
        false,
        0,
        Direction::Older,
        45..50,
        Some(999),
        false,
    );
    snapshots();
    codex();
    trim_matrix();
}
