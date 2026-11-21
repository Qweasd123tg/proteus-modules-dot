// Scratch-only input fixtures for the real workflow history projection.
use super::*;
use std::{
    alloc::{GlobalAlloc, Layout, System},
    sync::atomic::{AtomicBool, AtomicUsize, Ordering::Relaxed},
};

struct Meter;
static ACTIVE: AtomicBool = AtomicBool::new(false);
static REQUESTED: AtomicUsize = AtomicUsize::new(0);
static CALLS: AtomicUsize = AtomicUsize::new(0);
static LIVE: AtomicUsize = AtomicUsize::new(0);
static PEAK: AtomicUsize = AtomicUsize::new(0);

fn record(ptr: *mut u8, size: usize, old: usize) -> *mut u8 {
    if !ptr.is_null() {
        let now = if size >= old {
            LIVE.fetch_add(size - old, Relaxed) + (size - old)
        } else {
            LIVE.fetch_sub(old - size, Relaxed) - (old - size)
        };
        if ACTIVE.load(Relaxed) {
            CALLS.fetch_add(1, Relaxed);
            REQUESTED.fetch_add(size, Relaxed);
            PEAK.fetch_max(now, Relaxed);
        }
    }
    ptr
}

unsafe impl GlobalAlloc for Meter {
    unsafe fn alloc(&self, layout: Layout) -> *mut u8 {
        record(unsafe { System.alloc(layout) }, layout.size(), 0)
    }
    unsafe fn alloc_zeroed(&self, layout: Layout) -> *mut u8 {
        record(unsafe { System.alloc_zeroed(layout) }, layout.size(), 0)
    }
    unsafe fn realloc(&self, ptr: *mut u8, layout: Layout, size: usize) -> *mut u8 {
        record(unsafe { System.realloc(ptr, layout, size) }, size, layout.size())
    }
    unsafe fn dealloc(&self, ptr: *mut u8, layout: Layout) {
        LIVE.fetch_sub(layout.size(), Relaxed);
        unsafe { System.dealloc(ptr, layout) }
    }
}

#[global_allocator]
static GLOBAL: Meter = Meter;

fn message(number: usize, role: MessageRole, payload: ContentPart) -> CanonicalMessage {
    let fixed = |n| format!("00000000-0000-7000-8000-{n:012x}").parse().unwrap();
    let mut message = CanonicalMessage::new(role, vec![payload]).with_id(fixed(number));
    message.parts[0].part_id = fixed(number + 0x1_0000);
    message
}

fn text(number: usize, role: MessageRole, text: &str) -> CanonicalMessage {
    message(number, role, ContentPart::Text { text: text.into() })
}

fn wire(turn: &TurnScaffold) -> String {
    match turn.history_update() {
        Ok(history) => serde_json::to_string(&history).unwrap(),
        Err(error) => serde_json::to_string(&error.message).unwrap(),
    }
}

#[test]
#[ignore = "differential probe requires fixture environment"]
fn allocation_case() {
    let case = std::env::var("R59_CASE").unwrap();
    let count = if case.ends_with("-large") { 96 } else { 2 };
    let mut persisted = (1..=count)
        .map(|n| {
            let result = ToolResult::ok(
                format!("old-call-{n}"),
                if count < 5 { "previous".into() } else { "Прошлый результат 🦀\n".repeat(600) },
            )
            .with_metadata(serde_json::json!({"z":[n,"nested"],"a":{"β":true}}));
            message(n, MessageRole::Tool, ContentPart::ToolResult { result })
        })
        .collect::<Vec<_>>();
    let current = text(1_000, MessageRole::User, "now");
    let mut anchor = current.id;
    persisted.push(current);
    if case != "normal-empty" {
        persisted.extend([
            text(1_001, MessageRole::Assistant, "first new 🦀\n"),
            text(1_002, MessageRole::Assistant, "second new"),
        ]);
    }
    let replacement = match case.as_str() {
        "replace-small" | "replace-large" => Some(count + 2),
        "bad-replacement" => Some(count + 10),
        "missing-anchor" => {
            anchor = text(6_000, MessageRole::User, "gone").id;
            None
        }
        _ => None,
    };
    let turn = TurnScaffold {
        model_messages: Vec::new(),
        persistent_messages: persisted,
        current_user_message_id: anchor,
        current_turn_messages_start: count + 1,
        context_chunks: 0,
        context_token_estimate: None,
        compactions: vec![HistoryCompactionReport::unchanged(count + 1, Some("fits".into()))],
        history_replacement_len: replacement,
        pending_preparation: None,
        result_bindings: Default::default(),
    };
    drop(wire(&turn));
    let start = LIVE.load(Relaxed);
    PEAK.store(start, Relaxed);
    ACTIVE.store(true, Relaxed);
    let result = wire(&turn);
    ACTIVE.store(false, Relaxed);
    let peak = PEAK.load(Relaxed) - start;
    std::fs::write(std::env::var_os("R59_WIRE").unwrap(), result).unwrap();
    println!("R59 {} {} {}", REQUESTED.load(Relaxed), CALLS.load(Relaxed), peak);
}
