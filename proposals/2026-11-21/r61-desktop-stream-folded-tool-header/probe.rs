#![allow(dead_code, unused_imports)]

mod agents {
    pub mod codex;
}
mod transcript;
mod ui;

use proteus_contracts::app_protocol::{AppTranscriptMessage, AppTranscriptTool};
use serde_json::Value;
use std::hint::black_box;
use std::ops::Range;
use transcript::{Entry, Transcript, tool_chain};
use ui::chat::tool_chain::{candidate, stock};

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

fn tool(i: usize, name: &str, status: &str) -> AppTranscriptTool {
    AppTranscriptTool {
        terminal: None,
        call_id: format!("synthetic-{i}"),
        name: name.into(),
        status: status.into(),
        args: Value::Null,
        effective_args: None,
        result: None,
        metadata: Value::Null,
    }
}

fn corpus(ops: &[Option<(&str, &str)>]) -> Transcript {
    let rows = ops
        .iter()
        .enumerate()
        .map(|(i, op)| AppTranscriptMessage {
            timestamp_ms: Some(i as i64),
            message_id: Some(uuid::Uuid::from_u128(i as u128 + 1)),
            phase: None,
            role: if op.is_some() { "system" } else { "assistant" }.into(),
            text: "synthetic transcript".into(),
            images: vec![],
            tool: op.map(|(n, s)| tool(i, n, s)),
            subagent: None,
            streaming: false,
        })
        .collect();
    let mut transcript = Transcript::default();
    transcript.reset(rows);
    transcript
}

fn parity() {
    let statuses = [
        "done",
        "running",
        "approved",
        "waiting_approval",
        "failed",
        "denied",
        "unknown",
        "interrupted",
        "completed",
        "",
    ];
    let names = ["read_file", "apply_patch", "Проверка 🐚", ""];
    let mut cases = 0;
    for x in statuses {
        for y in statuses {
            for z in statuses {
                for n in names {
                    for m in names {
                        for p in names {
                            let model =
                                corpus(&[None, Some((n, x)), Some((m, y)), Some((p, z)), None]);
                            let rows = model.entries();
                            let run = tool_chain(rows, 2).unwrap();
                            assert_eq!(run, 1..4);
                            assert_eq!(stock::summarize(rows, run.clone()), candidate(rows, run));
                            cases += 1;
                        }
                    }
                }
            }
        }
    }
    let model = corpus(&[
        None,
        Some(("shell", "done")),
        None,
        Some(("search", "approved")),
        Some(("shell", "failed")),
        None,
    ]);
    for start in 0..=model.entries().len() {
        for end in start..=model.entries().len() {
            let rows = model.entries();
            assert_eq!(
                stock::summarize(rows, start..end),
                candidate(rows, start..end)
            );
            cases += 1;
        }
    }
    assert_eq!(cases, 64028);
    println!("PASS {cases} exact header count/status/ordered-label comparisons");
}

type Summary<'a> = (usize, &'static str, Vec<(&'a str, usize)>);
type Project = for<'a> fn(&'a [Entry], Range<usize>) -> Summary<'a>;

fn measure(project: Project, name: &str, data: &[Option<(&str, &str)>], folded: bool) {
    let transcript = corpus(data);
    let rows = transcript.entries();
    let run = if folded {
        let run = tool_chain(rows, 0).unwrap();
        assert_eq!(run, 0..data.len());
        run
    } else {
        0..rows.len()
    };
    let before = counter::read();
    let result = black_box(project(black_box(rows), black_box(run)));
    let after = counter::read();
    black_box(&result);
    println!(
        "alloc\t{name}\t{}\t{}",
        after.0 - before.0,
        after.1 - before.1
    );
}

fn allocations(arm: &str) {
    let project: Project = match arm {
        "stock" => stock::summarize,
        "candidate" => candidate,
        _ => panic!("expected stock or candidate"),
    };
    measure(project, "empty-control", &[], false);
    measure(
        project,
        "three-ordinary",
        &[Some(("read_file", "done")); 3],
        true,
    );
    measure(
        project,
        "eight-different",
        &[
            Some(("read_file", "done")),
            Some(("list", "done")),
            Some(("search", "denied")),
            Some(("replace", "done")),
            Some(("shell", "done")),
            Some(("web", "done")),
            Some(("patch", "done")),
            Some(("check", "waiting_approval")),
        ],
        true,
    );
    let statuses = [
        "done",
        "done",
        "waiting_approval",
        "denied",
        "unknown",
        "approved",
    ];
    let names = ["read_file", "apply_patch", "shell"];
    let long: Vec<_> = (0..48)
        .map(|i| Some((names[i % names.len()], statuses[i % statuses.len()])))
        .collect();
    measure(project, "forty-eight", &long, true);
}

fn main() {
    let arm = std::env::args().nth(1).unwrap();
    if arm == "parity" {
        parity();
    } else {
        allocations(&arm);
    }
}
