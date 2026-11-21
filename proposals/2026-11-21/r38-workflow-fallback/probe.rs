// Complete production files from the pinned base and candidate, written by reproduce.py.
#[path = "versions/after.rs"]
mod after;
#[path = "versions/before.rs"]
mod before;

use proteus_contracts::{
    domain::{ToolResult, new_call_id},
    model_standard::{CanonicalMessage, ContentPart, MessageRole},
};
use serde_json::json;
use std::{
    alloc::{GlobalAlloc, Layout, System},
    cell::Cell,
    hint::black_box,
    time::Instant,
};

thread_local! {static ALLOCS: Cell<Option<(usize,usize)>> = const { Cell::new(None) };}
struct Counter;
#[global_allocator]
static ALLOCATOR: Counter = Counter;
fn record(size: usize) {
    ALLOCS.with(|c| {
        if let Some((calls, bytes)) = c.get() {
            c.set(Some((calls + 1, bytes + size)))
        }
    })
}
unsafe impl GlobalAlloc for Counter {
    unsafe fn alloc(&self, l: Layout) -> *mut u8 {
        record(l.size());
        unsafe { System.alloc(l) }
    }
    unsafe fn alloc_zeroed(&self, l: Layout) -> *mut u8 {
        record(l.size());
        unsafe { System.alloc_zeroed(l) }
    }
    unsafe fn realloc(&self, p: *mut u8, l: Layout, size: usize) -> *mut u8 {
        record(size);
        unsafe { System.realloc(p, l, size) }
    }
    unsafe fn dealloc(&self, p: *mut u8, l: Layout) {
        unsafe { System.dealloc(p, l) }
    }
}
fn tool(output: String, error: Option<String>) -> CanonicalMessage {
    let result = ToolResult::new(new_call_id(), false, output, vec![], error, json!({}));
    CanonicalMessage::new(MessageRole::Tool, vec![ContentPart::ToolResult { result }])
}

#[test]
fn differential() {
    let mut fields = vec![
        "".to_owned(),
        " \t\u{2003}\n".into(),
        "🦀e\u{301}\n\0".into(),
    ];
    for unit in ["x", "文", "🦀"] {
        for n in [
            1, 2, 127, 998, 999, 1000, 1001, 1997, 1998, 1999, 2000, 2001, 2002, 4096,
        ] {
            fields.push(format!("\u{2003}{}\n", unit.repeat(n)));
        }
    }
    let empty = CanonicalMessage::new(MessageRole::Assistant, vec![]);
    let existing = CanonicalMessage::text(MessageRole::Assistant, "real answer");
    let literal = CanonicalMessage::text(MessageRole::Assistant, "<empty model response>");
    let mut cases = 0;
    for output in &fields {
        for error in std::iter::once(None).chain(fields.iter().map(Some)) {
            let messages = [
                tool("older result".into(), Some("older error".into())),
                tool(output.clone(), error.cloned()),
                CanonicalMessage::text(MessageRole::User, "ignored"),
            ];
            for message in [&empty, &existing, &literal] {
                assert_eq!(
                    before::output_text(message, &messages),
                    after::output_text(message, &messages)
                );
                cases += 1;
            }
        }
    }
    for message in [&empty, &existing, &literal] {
        assert_eq!(
            before::output_text(message, &[]),
            after::output_text(message, &[])
        );
        cases += 1;
    }
    println!("differential: {cases} identical complete output strings");
}

type Render = fn(&CanonicalMessage, &[CanonicalMessage]) -> String;
fn measure(
    f: Render,
    msg: &CanonicalMessage,
    history: &[CanonicalMessage],
) -> (u128, usize, usize) {
    ALLOCS.set(Some((0, 0)));
    let start = Instant::now();
    let result = black_box(f(black_box(msg), black_box(history)));
    let ns = start.elapsed().as_nanos();
    let (calls, bytes) = ALLOCS.replace(None).unwrap();
    drop(result);
    (ns, calls, bytes)
}

#[test]
fn cost() {
    println!("case,old_ns,new_ns,old_calls,new_calls,old_requested_bytes,new_requested_bytes");
    let empty = CanonicalMessage::new(MessageRole::Assistant, vec![]);
    let normal = CanonicalMessage::text(MessageRole::Assistant, "normal answer without fallback");
    for (name, msg, output, err) in [
        ("normal", &normal, "x".repeat(2 << 20), None),
        ("blank", &empty, "  ".into(), Some("\u{2003}".into())),
        (
            "small",
            &empty,
            "small output".into(),
            Some(" tool error ".into()),
        ),
        ("2KiB", &empty, "x".repeat(2048), None),
        (
            "128KiB-error",
            &empty,
            "message".into(),
            Some("🦀".repeat(32 << 10)),
        ),
        ("2MiB", &empty, "x".repeat(2 << 20), None),
        (
            "1MiB+1MiB",
            &empty,
            "y".repeat(1 << 20),
            Some("z".repeat(1 << 20)),
        ),
    ] {
        let history = [tool(output, err)];
        assert_eq!(
            before::output_text(msg, &history),
            after::output_text(msg, &history)
        );
        let mut old = vec![];
        let mut new = vec![];
        for i in 0..105 {
            let (a, b) = if i % 2 == 0 {
                (
                    measure(before::output_text, msg, &history),
                    measure(after::output_text, msg, &history),
                )
            } else {
                let b = measure(after::output_text, msg, &history);
                (measure(before::output_text, msg, &history), b)
            };
            if i >= 4 {
                old.push(a);
                new.push(b)
            }
        }
        old.sort_unstable();
        new.sort_unstable();
        let (a, b) = (old[50], new[50]);
        println!("{name},{},{},{},{},{},{}", a.0, b.0, a.1, b.1, a.2, b.2);
        if name == "2MiB" || name == "1MiB+1MiB" {
            assert!(a.2 >= 2 << 20);
            assert!(b.2 < 32 << 10);
        }
    }
}
