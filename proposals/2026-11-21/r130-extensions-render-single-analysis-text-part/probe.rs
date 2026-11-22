// Standalone test-only allocator meter for the actual Analysis message-body helper.
use proteus_extension::{Value, json};
use std::alloc::{GlobalAlloc, Layout, System};
use std::cell::Cell;

thread_local! {
    static METER: Cell<Option<(usize, usize)>> = const { Cell::new(None) };
}

fn record(size: usize) {
    let _ = METER.try_with(|meter| {
        if let Some((calls, bytes)) = meter.get() {
            meter.set(Some((calls + 1, bytes + size)));
        }
    });
}

struct Allocations;

unsafe impl GlobalAlloc for Allocations {
    unsafe fn alloc(&self, layout: Layout) -> *mut u8 {
        let ptr = unsafe { System.alloc(layout) };
        if !ptr.is_null() {
            record(layout.size());
        }
        ptr
    }

    unsafe fn alloc_zeroed(&self, layout: Layout) -> *mut u8 {
        let ptr = unsafe { System.alloc_zeroed(layout) };
        if !ptr.is_null() {
            record(layout.size());
        }
        ptr
    }

    unsafe fn dealloc(&self, ptr: *mut u8, layout: Layout) {
        unsafe { System.dealloc(ptr, layout) };
    }

    unsafe fn realloc(&self, ptr: *mut u8, old: Layout, size: usize) -> *mut u8 {
        let ptr = unsafe { System.realloc(ptr, old, size) };
        if !ptr.is_null() {
            record(size);
        }
        ptr
    }
}

#[global_allocator]
static GLOBAL: Allocations = Allocations;

fn scope<T>(op: impl FnOnce() -> T) -> (T, usize, usize) {
    assert!(METER.replace(Some((0, 0))).is_none());
    let out = std::hint::black_box(op());
    let (calls, bytes) = METER.take().unwrap();
    (out, calls, bytes)
}

fn message(parts: Vec<Value>) -> Value {
    let parts: Vec<_> = parts
        .into_iter()
        .map(|payload| json!({"payload": payload}))
        .collect();
    json!({"role": "User", "parts": parts, "metadata": {"z": true, "a": null}})
}

fn singleton(text: Value) -> Value {
    message(vec![json!({"Text": {"text": text}})])
}

fn ordinary(count: usize) -> Vec<Value> {
    let pattern = "Synthetic Analysis message body. Ж 🧪 e\u{0301}\r\n";
    (0..count)
        .map(|i| {
            let size = 2048 + i * 512;
            let body = pattern.repeat((size - 1) / pattern.len()) + &"x".repeat(1 + (size - 1) % pattern.len());
            assert_eq!(body.trim().len(), size);
            singleton(json!(format!("\u{2003}\t{body}\r\n\u{3000}")))
        })
        .collect()
}

#[test]
fn measure_analysis_message_text() {
    println!();
    let cases = [
        ("ordinary-one", ordinary(1)),
        ("ordinary-dozen", ordinary(12)),
        ("blank", vec![singleton(json!("\u{2003}\t\r\n")), singleton(json!(""))]),
        ("typed-malformed", vec![singleton(json!(41)), message(vec![json!({"Text": {}})]),
                                 message(vec![json!({"Text": ["not an object"]})])]),
        ("empty-or-reasoning", vec![message(vec![]), json!({"parts": true}),
                                    message(vec![json!({"Reasoning": {"text": "synthetic", "signature": null}})])]),
        ("unknown-payload", vec![json!({"parts": [false]}), message(vec![json!({"text": "wrong case"})]),
                                  message(vec![json!({"Text": {"text": "two tags"}, "Image": {}})])]),
        ("generated", vec![message(vec![json!({"ToolCall": {"call": {"name": "fixture", "args": {"b": [true, null], "a": 2}}}})]),
                            message(vec![json!({"ToolResult": {"result": {"call_id": "fixture", "output": "text \t"}}})]),
                            message(vec![json!({"FileRef": {"path": "fixture.txt", "content": "NOT READ 🧪"}})]),
                            message(vec![json!({"Image": {"image": "fixture"}})])]),
        ("multipart", vec![message(vec![json!({"ReasoningSummary": {"text": "filtered"}}),
                                         json!({"Text": {"text": "only visible"}})]),
                            message(vec![json!({"Text": {"text": " \t first 🧪 \n"}}),
                                         json!({"Text": {"text": "second \u{2003} "}}),
                                         json!({"FileRef": {"path": "synthetic"}})])]),
    ];
    for (case, messages) in cases {
        let mut output = Vec::with_capacity(messages.len());
        let (_, calls, bytes) = scope(|| {
            for value in &messages {
                output.push(crate::text::message_text(std::hint::black_box(value)));
            }
        });
        let length = output.iter().map(String::len).sum::<usize>();
        let capacity = output.iter().map(String::capacity).sum::<usize>();
        if case.starts_with("ordinary-") {
            assert!(output.iter().all(|body| (2048..=8192).contains(&body.len()) && body.capacity() == body.len()));
            assert_eq!(length, (0..messages.len()).map(|i| 2048 + i*512).sum::<usize>());
        }
        println!("ops {case} {} {length} {capacity} {calls} {bytes}", messages.len());
        println!("shape {case} {}", serde_json::to_string(&output).unwrap());
    }
}
