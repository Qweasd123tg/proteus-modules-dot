#![allow(dead_code, unused_imports)]

mod candidate;
mod stock;
mod tool_row;

use proteus_contracts::app_protocol::{
    AppExecutionState, AppRun, AppRunStatus, AppSessionSnapshot, AppTranscriptMessage,
    AppTranscriptTool,
};
use serde_json::Value;
use std::hint::black_box;
use uuid::Uuid;

#[derive(Debug, PartialEq, Eq)]
struct ReceiptState {
    sends: Vec<(String, bool, bool, Option<Uuid>)>,
    latest: Option<(String, usize)>,
    run: Option<String>,
    phase: u8,
}

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

fn message(id: Option<u128>, tool: Option<&str>) -> AppTranscriptMessage {
    AppTranscriptMessage {
        timestamp_ms: Some(44),
        message_id: id.map(Uuid::from_u128),
        phase: None,
        role: if tool.is_some() { "system" } else { "user" }.into(),
        text: "same text".into(),
        images: Vec::new(),
        tool: tool.map(|status| AppTranscriptTool {
            call_id: "synthetic-call".into(),
            name: "read_file".into(),
            args: Value::Null,
            effective_args: None,
            status: status.into(),
            result: None,
            metadata: Value::Null,
            terminal: None,
        }),
        subagent: None,
        streaming: false,
    }
}

fn run(id: &str, status: AppRunStatus) -> AppRun {
    AppRun {
        run_id: id.into(),
        options: Default::default(),
        status,
        error: None,
    }
}
fn snapshot(
    transcript: Vec<AppTranscriptMessage>,
    execution: AppExecutionState,
) -> AppSessionSnapshot {
    AppSessionSnapshot {
        session_id: Uuid::from_u128(42),
        stream_id: "synthetic".into(),
        seq: 23,
        root_thread_id: Some(Uuid::from_u128(4)),
        execution,
        transcript,
        history: None,
    }
}

macro_rules! init {
    ($which:ident, $pending:expr) => {{
        let mut state = $which::Feedback::default();
        for (name, disposition) in $pending {
            state.begin(name.into(), "same text".into(), &[], &[]);
            match disposition {
                0 => {}
                1 => {
                    state.complete(name, true, None);
                }
                2..=5 => {
                    state.complete(name, true, Some(Uuid::from_u128(disposition as u128 - 1)));
                }
                _ => unreachable!(),
            }
        }
        state
    }};
}

fn parity() {
    let mut n = 0;
    let choices = [
        (None, None),
        (Some(1), None),
        (Some(2), None),
        (Some(3), Some("running")),
        (Some(3), Some("approved")),
        (None, Some("done")),
    ];
    let names = ["one", "two", "three", "other"];
    let runs = [
        (None, None),
        (Some(run("one", AppRunStatus::Running)), None),
        (
            Some(run("other", AppRunStatus::Running)),
            Some(run("two", AppRunStatus::Timeout)),
        ),
        (None, Some(run("three", AppRunStatus::Success))),
        (
            Some(run("one", AppRunStatus::Canceled)),
            Some(run("other", AppRunStatus::Error)),
        ),
    ];
    for (active, last) in runs {
        for a in choices {
            for b in choices {
                for c in [None, Some(choices[1]), Some(choices[4])] {
                    let rows = [Some(a), Some(b), c]
                        .into_iter()
                        .flatten()
                        .map(|(id, status)| message(id, status))
                        .collect();
                    let snap = snapshot(
                        rows,
                        AppExecutionState {
                            active: active.clone(),
                            last: last.clone(),
                        },
                    );
                    for x in 0..=5 {
                        for y in 0..=5 {
                            for z in 0..=5 {
                                let pending = [(names[0], x), (names[1], y), (names[2], z)];
                                let mut old = init!(stock, pending);
                                let mut new = init!(candidate, pending);
                                stock::project_snapshot(&mut old, &snap);
                                candidate::project_snapshot(&mut new, &snap);
                                assert_eq!(old.inspect(), new.inspect());
                                // Feedback remains the same when the authoritative
                                // page is replayed, and when a late HTTP failure arrives.
                                stock::project_snapshot(&mut old, &snap);
                                candidate::project_snapshot(&mut new, &snap);
                                assert_eq!(
                                    old.complete("two", false, None),
                                    new.complete("two", false, None)
                                );
                                assert_eq!(old.inspect(), new.inspect());
                                n += 2;
                            }
                        }
                    }
                }
            }
        }
    }
    assert_eq!(n, 233_280);
    println!("PASS {n} exact snapshot/replay receipt decisions with late failure controls");
}

fn measure<P>(arm: &str, label: &str, call: impl FnOnce() -> P) {
    let before = counter::read();
    let result = black_box(call());
    let after = counter::read();
    black_box(&result);
    println!(
        "alloc\t{arm}\t{label}\t{}\t{}",
        after.0 - before.0,
        after.1 - before.1
    );
}

fn allocations(arm: &str) {
    for (name, len, pending, active) in [
        ("empty", 0, &[][..], None),
        ("ordinary-first-page", 50, &[][..], None),
        ("synthetic-tail-200", 200, &[][..], None),
        ("pending-unknown-id", 50, &[("one", 0)][..], None),
        ("run-matched-receipt", 50, &[("one", 2)][..], Some("one")),
        ("known-echo", 50, &[("one", 3)][..], None),
        ("known-mismatch", 50, &[("one", 5)][..], None),
        (
            "several-pending-known",
            200,
            &[("one", 2), ("other", 4), ("third", 5)][..],
            None,
        ),
    ] {
        let rows = (0..len)
            .map(|ix| message(Some(if ix + 1 == len { 2 } else { 213 + ix as u128 }), None))
            .collect();
        let snap = snapshot(
            rows,
            AppExecutionState {
                active: active.map(|id| run(id, AppRunStatus::Running)),
                last: None,
            },
        );
        match arm {
            "stock" => {
                let mut state = init!(stock, pending.iter().copied());
                measure(arm, name, || {
                    stock::project_snapshot(&mut state, black_box(&snap));
                    black_box(&state);
                });
            }
            "candidate" => {
                let mut state = init!(candidate, pending.iter().copied());
                measure(arm, name, || {
                    candidate::project_snapshot(&mut state, black_box(&snap));
                    black_box(&state);
                });
            }
            _ => panic!("data arm"),
        }
    }
}

fn main() {
    let arm = std::env::args().nth(1).unwrap();
    if arm == "parity" {
        parity();
    } else {
        allocations(&arm);
    }
}
