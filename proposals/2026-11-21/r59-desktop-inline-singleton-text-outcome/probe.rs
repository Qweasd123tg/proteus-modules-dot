#![allow(dead_code, unused_imports)]

mod agents {
    pub mod codex;
}
mod transcript;

use proteus_contracts::app_protocol::{AppServerEvent, AppTranscriptMessage};
use proteus_contracts::domain::{Event, EventContext, EventEnvelope};
use std::hint::black_box;
use std::io::{self, BufWriter, Write};
use transcript::{TextRun, TextRunOutcome, Transcript};
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

fn event(thread: u128, offset: usize, text: &str, seq: u64) -> Box<AppServerEvent> {
    let mut envelope = EventEnvelope::new(
        EventContext::new(
            Uuid::from_u128(1),
            Uuid::from_u128(thread),
            Some(Uuid::from_u128(3)),
        ),
        seq,
        Event::AssistantTextDelta {
            offset,
            message_id: Uuid::from_u128(10),
            phase: None,
            text: text.into(),
        },
    );
    envelope.timestamp_ms = seq as i64 * 3;
    Box::new(AppServerEvent::Runtime {
        envelope: Box::new(envelope),
    })
}

fn fixture(base: Option<&str>) -> Transcript {
    let row = |id, text: &str| AppTranscriptMessage {
        timestamp_ms: Some(17 + id as i64),
        message_id: Some(Uuid::from_u128(id)),
        phase: None,
        role: "assistant".into(),
        text: text.to_owned(),
        images: Vec::new(),
        tool: None,
        subagent: None,
        streaming: true,
    };
    let mut transcript = Transcript::default();
    let mut input = vec![row(9, "earlier")];
    if let Some(base) = base {
        input.push(row(10, base));
    }
    transcript.reset(input);
    transcript.set_root_thread(Some(Uuid::from_u128(2)));
    transcript
}

fn run(thread: u128, operations: &[(usize, &str)], keep: usize) -> TextRun {
    let (offset, text) = operations[0];
    let mut run = TextRun::new(event(thread, offset, text, 100)).expect("assistant update");
    for (i, (offset, text)) in operations.iter().enumerate().skip(1) {
        run.push(event(thread, *offset, text, 100 + i as u64));
    }
    let mut i = 0;
    run.retain(|_| {
        let allowed = keep & (1 << i) != 0;
        i += 1;
        allowed
    });
    run
}

fn parity() -> io::Result<()> {
    let mut out = BufWriter::new(io::stdout().lock());
    let mut cases = 0usize;
    let ops = [
        (0, ""),
        (1, ""),
        (5, ""),
        (0, "a"),
        (1, "a"),
        (1, "🦀"),
        (2, "ч"),
        (4, "é"),
        (usize::MAX, "ÿ"),
    ];
    for base in [None, Some(""), Some("é"), Some("é🦀")] {
        for thread in [2, 8] {
            for &a in &ops {
                for &b in &ops {
                    for &c in &ops {
                        for keep in 0..8 {
                            let mut transcript = fixture(base);
                            let run = run(thread, &[a, b, c], keep);
                            let mut outcome = transcript.apply_text_run(&run);
                            let events: Vec<_> = outcome.event_changes().collect();
                            let layout: Vec<_> = outcome.layout_changes().collect();
                            let shown = outcome.shown();
                            assert!(!outcome.feedback_changed);
                            outcome.feedback_changed = true;
                            assert!(outcome.shown());
                            write!(out, "{events:?}|{layout:?}|{shown}|")?;
                            for entry in transcript.entries() {
                                write!(
                                    out,
                                    "{:?},{:?},{:?},{:?},{:?},{:?};",
                                    entry.key,
                                    entry.role,
                                    entry.message_id,
                                    entry.time,
                                    entry.streaming,
                                    entry.text
                                )?;
                            }
                            writeln!(out)?;
                            cases += 1;
                        }
                    }
                }
            }
        }
    }
    writeln!(out, "parity cases\t{cases}")?;
    out.flush()
}

fn measure(name: &str, base: Option<&str>, thread: u128, ops: &[(usize, &str)], keep: usize) {
    let mut transcript = fixture(base);
    let run = run(thread, ops, keep);
    let before = counter::read();
    let outcome = black_box(transcript.apply_text_run(black_box(&run)));
    let after = counter::read();
    println!(
        "alloc\t{name}\t{}\t{}",
        after.0 - before.0,
        after.1 - before.1
    );
    let event_changes: Vec<_> = outcome.event_changes().collect();
    let layout_changes: Vec<_> = outcome.layout_changes().collect();
    println!(
        "outcome\t{name}\t{event_changes:?}\t{layout_changes:?}\t{}",
        outcome.shown()
    );
}

fn allocations() {
    println!("inline-size\t{}", std::mem::size_of::<TextRunOutcome>());
    let four = [(0, "é"), (2, "🦀"), (5, ""), (7, "x")];
    measure("singleton-new", None, 2, &[(0, "é")], 1);
    measure("singleton-update", Some("é"), 2, &[(2, "🦀")], 1);
    measure("singleton-empty", None, 2, &[(0, "")], 1);
    measure("singleton-foreign", None, 8, &[(0, "é")], 1);
    measure("filtered-to-one", None, 2, &four, 2);
    measure("filtered-to-empty", None, 2, &four, 0);
    measure("four-accepted", Some("prefix"), 2, &four, 15);
    measure("four-foreign", Some("prefix"), 8, &four, 15);
}

fn main() -> io::Result<()> {
    match std::env::args().nth(1).as_deref() {
        Some("parity") => parity(),
        Some("alloc") => {
            allocations();
            Ok(())
        }
        _ => panic!("expected parity or alloc"),
    }
}
