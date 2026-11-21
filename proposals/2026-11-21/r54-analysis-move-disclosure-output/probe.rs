// Inserted only in a separate temporary release measurement build.
use std::alloc::{GlobalAlloc, Layout, System};
use std::sync::atomic::{AtomicUsize, Ordering::Relaxed};
struct Meter;
#[global_allocator]
static METER: Meter = Meter;
static CALLS: AtomicUsize = AtomicUsize::new(0);
static BYTES: AtomicUsize = AtomicUsize::new(0);
fn record(size: usize) {
    CALLS.fetch_add(1, Relaxed);
    BYTES.fetch_add(size, Relaxed);
}
unsafe impl GlobalAlloc for Meter {
    unsafe fn alloc(&self, layout: Layout) -> *mut u8 {
        let p = unsafe { System.alloc(layout) };
        if !p.is_null() {
            record(layout.size());
        }
        p
    }
    unsafe fn dealloc(&self, p: *mut u8, layout: Layout) {
        unsafe { System.dealloc(p, layout) }
    }
    unsafe fn realloc(&self, p: *mut u8, layout: Layout, size: usize) -> *mut u8 {
        let p = unsafe { System.realloc(p, layout, size) };
        if !p.is_null() {
            record(size);
        }
        p
    }
}
fn measure<T>(f: impl FnOnce() -> T) -> (T, usize, usize) {
    CALLS.store(0, Relaxed);
    BYTES.store(0, Relaxed);
    let output = std::hint::black_box(f());
    (output, CALLS.load(Relaxed), BYTES.load(Relaxed))
}
fn main() {
    let mode = std::env::args().nth(1).unwrap();
    assert!(mode == "wire" || mode == "counts");
    for (shape, repeat) in [
        ("short", 2),
        ("text-medium", 512),
        ("text-large", 8192),
        ("structured", 8192),
    ] {
        let body = "synthetic строка \"q\"\r\n".repeat(repeat);
        let sampled_bytes = body.len();
        let tool_output = if shape == "structured" {
            json!({"summary":"sample", "rows":[{"name":"пример","detail":body}]})
        } else {
            Value::String(body.clone())
        };
        let step = json!({"sequence":3, "started_at_ms":1000, "finished_at_ms":2000,
            "data":{"kind":"tool","call":{"id":"fixture","name":"preview","args":{}},"result":{"ok":true,"output":tool_output}}});
        let turn = json!({"turn_id":"one", "task":{"text":"Synthetic task"}, "steps":[step],
            "output":{"text":body},"module_epoch":1,"config_snapshot":{"fixture":true}});
        let data = json!({"session_id":"fixture", "revision":1,
            "turns":[{"turn_id":"one","number":1,"status":"success","prompt_preview":"Task"}],"selected":turn});
        let turn = data.at("selected");
        let step = &turn.list("steps")[0];
        let open = Open;
        for (case, (view, calls, bytes)) in [
            ("tool-card", measure(|| details::step_card(step, &open))),
            (
                "turn-card",
                measure(|| summary::turn_summary(turn, &json!(1), &json!("success"), &open)),
            ),
            (
                "analysis-page",
                measure(|| {
                    Analysis {
                        step: Some(3),
                        ..Analysis::default()
                    }
                    .page(&data, Value::Null)
                }),
            ),
        ] {
            let serialized = view.to_string();
            assert!(serialized.contains("synthetic"));
            if mode == "wire" {
                println!("{serialized}");
            } else {
                println!(
                    "{shape} {sampled_bytes} {case} {calls} {bytes} {}",
                    serialized.len()
                );
            }
        }
    }
}
