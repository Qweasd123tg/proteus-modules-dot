#![allow(dead_code, unused_imports)]

mod agents {
    pub mod codex;
}
mod transcript;
mod ui;

use proteus_contracts::app_protocol::{
    AppSubagentSession, AppTranscriptMessage, AppTranscriptSubagent, AppTranscriptTool,
};
use proteus_contracts::contracts::ToolTerminalRef;
use serde_json::{Value, json};
use std::hint::black_box;
use std::ops::Range;
use transcript::{Entry, Transcript};
use ui::chat::{HistoryRange, baseline, candidate};
use uuid::Uuid;

mod counter {
    use std::alloc::{GlobalAlloc, Layout, System};
    use std::sync::atomic::{AtomicUsize, Ordering::Relaxed};
    struct Counter;
    static CALLS: AtomicUsize = AtomicUsize::new(0);
    static BYTES: AtomicUsize = AtomicUsize::new(0);
    #[global_allocator]
    static A: Counter = Counter;
    unsafe impl GlobalAlloc for Counter {
        unsafe fn alloc(&self, layout: Layout) -> *mut u8 {
            CALLS.fetch_add(1, Relaxed);
            BYTES.fetch_add(layout.size(), Relaxed);
            unsafe { System.alloc(layout) }
        }
        unsafe fn dealloc(&self, p: *mut u8, layout: Layout) {
            unsafe { System.dealloc(p, layout) }
        }
        unsafe fn realloc(&self, p: *mut u8, layout: Layout, new: usize) -> *mut u8 {
            CALLS.fetch_add(1, Relaxed);
            BYTES.fetch_add(new, Relaxed);
            unsafe { System.realloc(p, layout, new) }
        }
    }
    pub fn read() -> (usize, usize) {
        (CALLS.load(Relaxed), BYTES.load(Relaxed))
    }
}

fn tool(i: usize, group: &str) -> Option<AppTranscriptTool> {
    if group == "text" || group.starts_with("overlay") {
        return None;
    }
    Some(AppTranscriptTool {
        terminal: (group == "terminal").then(|| ToolTerminalRef {
            id: Uuid::from_u128(42),
            title: "synthetic terminal".into(),
            tty: true,
        }),
        call_id: format!("synthetic-{i}"),
        name: "read_file".into(),
        status: "done".into(),
        args: Value::Null,
        effective_args: None,
        result: None,
        metadata: match group {
            "bound-task" => {
                json!({"tool":"task", "child_thread_id":"child", "subagent_session":session(7)})
            }
            "disagrees" => {
                json!({"tool":"spawn_agent", "child_thread_id":"child", "subagent_session":session(8)})
            }
            "unbound-task" => json!({"tool":"followup_task", "child_thread_id":"child"}),
            _ => Value::Null,
        },
    })
}

fn session(id: u128) -> AppSubagentSession {
    AppSubagentSession {
        session_id: Uuid::from_u128(id),
        session_dir: format!("/synthetic/session/{id}").into(),
    }
}

fn corpus(n: usize, style: usize) -> Transcript {
    let rows = (0..n)
        .map(|i| {
            let tail = n - 1 - i;
            let group = match style {
                0 => "text",
                1 => "ordinary",
                2 => {
                    if i < 4 || tail < 5 {
                        "ordinary"
                    } else {
                        "text"
                    }
                }
                3..=6 => {
                    if tail < (style - 1) {
                        match style {
                            3 => "bound-task",
                            4 => "disagrees",
                            5 => "unbound-task",
                            _ => {
                                if tail == 0 {
                                    "terminal"
                                } else {
                                    "ordinary"
                                }
                            }
                        }
                    } else if i == 1 {
                        "overlay-bound"
                    } else if i == 2 && style == 6 {
                        "overlay-unbound"
                    } else if tail < 12 || i < 1 {
                        "ordinary"
                    } else {
                        "text"
                    }
                }
                _ => unreachable!(),
            };
            AppTranscriptMessage {
                timestamp_ms: Some(i as i64),
                message_id: Some(Uuid::from_u128(i as u128 + 1)),
                phase: None,
                role: if group == "text" {
                    "assistant"
                } else {
                    "system"
                }
                .into(),
                text: "synthetic transcript".into(),
                images: vec![],
                tool: tool(i, group),
                subagent: group.starts_with("overlay").then(|| AppTranscriptSubagent {
                    child_thread_id: "child".into(),
                    session: (group == "overlay-bound").then(|| session(7)),
                    role: "explorer".into(),
                    description: None,
                    status: "running".into(),
                    iterations: None,
                    tools: vec![],
                }),
                streaming: false,
            }
        })
        .collect();
    let mut transcript = Transcript::default();
    transcript.reset(rows);
    transcript
}

fn options(rows: usize) -> [Option<HistoryRange>; 5] {
    [
        None,
        Some(HistoryRange {
            start: 0,
            rows,
            total: rows,
        }),
        Some(HistoryRange {
            start: 17,
            rows,
            total: 17 + rows,
        }),
        Some(HistoryRange {
            start: 0,
            rows,
            total: rows + 10,
        }),
        Some(HistoryRange {
            start: 17,
            rows,
            total: 17 + rows + 10,
        }),
    ]
}

fn parity() {
    let mut compared = 0;
    let mut contexts = 0;
    for n in [0, 1, 2, 3, 8, 20, 50, 100] {
        for style in 0..=6 {
            let t = corpus(n, style);
            let entries = t.entries();
            for range in options(n) {
                for compact in [false, true] {
                    let old = baseline(entries, compact, range);
                    let new = candidate(entries, compact, range);
                    contexts += 1;
                    for ix in 0..=n + 2 {
                        assert_eq!(
                            !old.iter().any(|r| r.contains(&ix)),
                            new(ix),
                            "rows={n} style={style} range={range:?} compact={compact} ix={ix}"
                        );
                        compared += 1;
                    }
                }
            }
        }
    }
    assert_eq!(contexts, 560);
    let t = corpus(50, 3);
    let row = candidate(t.entries(), true, options(50)[4]);
    // The footer belongs to the last visible tool group (up to 47).
    // The last raw row 49 is incomplete, but the hidden interior 48 is not
    // covered by either range. Preserve, rather than widen, that gap.
    assert!(!row(47));
    assert!(row(48));
    assert!(!row(49));
    assert!(row(30));
    let old = baseline(&[], false, None);
    let new = candidate(&[], false, None);
    println!(
        "inline context bytes {} -> {}",
        std::mem::size_of_val(&old),
        std::mem::size_of_val(&new)
    );
    println!("PASS {contexts} exact row contexts and {compared} measure eligibility decisions");
}

fn measure<O>(arm: &str, name: &str, build: impl FnOnce() -> O, count: impl FnOnce(&O) -> usize) {
    let before = counter::read();
    let context = black_box(build());
    black_box(count(&context));
    let after = counter::read();
    black_box(&context);
    println!(
        "alloc\t{arm}\t{name}\t{}\t{}",
        after.0 - before.0,
        after.1 - before.1
    );
}

fn counts(arm: &str) {
    for (case, n, style, compact, mode) in [
        ("no-range", 0, 0, false, 0),
        ("unclipped-full", 50, 0, false, 1),
        ("paged-live-tail", 50, 1, true, 2),
        ("paged-first-page", 50, 2, true, 3),
        ("paged-middle-grouped", 50, 2, true, 4),
        ("paged-hidden-footer", 50, 3, true, 4),
    ] {
        let t = corpus(n, style);
        let entries = black_box(t.entries());
        let range = options(n)[mode];
        match arm {
            "stock" => measure(
                arm,
                case,
                || baseline(entries, compact, range),
                |v| {
                    (0..n)
                        .filter(|ix| !v.iter().any(|r| r.contains(ix)))
                        .count()
                },
            ),
            "candidate" => measure(
                arm,
                case,
                || candidate(entries, compact, range),
                |eligible| (0..n).filter(|ix| eligible(*ix)).count(),
            ),
            _ => panic!("data arm"),
        }
    }
}

fn main() {
    let arm = std::env::args().nth(1).unwrap();
    if arm == "parity" {
        parity();
    } else {
        counts(&arm);
    }
}
