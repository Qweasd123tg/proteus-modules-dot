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
    assert!(mode == "counts" || mode == "wire");
    for (shape, count, used, maximum) in [
        ("unused", 8, 0, json!(200_000)),
        ("fallback", 0, 34_000, Value::Null),
        ("known", 8, 34_000, json!(200_000)),
        ("mixed", 16, 65_000, json!(200_000)),
        ("other", 48, 120_000, Value::Null),
    ] {
        let known = [
            "instructions",
            "messages",
            "context",
            "tool_calls",
            "tool_results",
            "tool_schemas",
            "files",
            "patches",
        ];
        let mut categories: Vec<_> = (0..count)
            .map(|i| {
                let name = known
                    .get(i)
                    .map(|v| (*v).to_owned())
                    .unwrap_or_else(|| format!("segment_{i}_имя"));
                json!({"name":name,"tokens": if i%5==3 {1}else{250*(i+1)}})
            })
            .collect();
        categories.extend([
            json!({"name":"provider_cache_read","tokens":4321}),
            json!({"name":"negative","tokens":-500}),
            json!({"name":"invalid","tokens":"900"}),
        ]);
        let source = json!({"history":{"estimated_tokens":used},"diagnostics":["fixture"],"latest_usage":{
            "source":"provider","estimated_input_tokens":used,"max_input_tokens":maximum,
            "compaction_trigger_tokens":180_000,"categories":categories}});
        let (cells, c, b) = measure(|| window::cells(&source));
        let serialized = serde_json::to_string(&cells).unwrap();
        if mode == "counts" {
            println!("{shape} cells {c} {b} {}", serialized.len());
        } else {
            println!("{serialized}");
        }
        let (view, c, b) = measure(|| view::render(&source));
        let serialized = serde_json::to_string(&view).unwrap();
        if mode == "counts" {
            println!("{shape} popup-body {c} {b} {}", serialized.len());
        } else {
            println!("{serialized}");
        }
    }
}
