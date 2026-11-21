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
static FINISH_LOOKUPS: AtomicUsize = AtomicUsize::new(0);
static MODEL_LOOKUPS: AtomicUsize = AtomicUsize::new(0);

fn measured_at<'a>(request: &'a Value, key: &str) -> &'a Value {
    match key {
        "finished_at_ms" => FINISH_LOOKUPS.fetch_add(1, Relaxed),
        "model" => MODEL_LOOKUPS.fetch_add(1, Relaxed),
        _ => unreachable!(),
    };
    request.at(key)
}

fn main() {
    let mode = std::env::args().nth(1).unwrap();
    assert!(mode == "counts" || mode == "outputs");
    let selected = Model {
        provider: "fixture".into(),
        name: "alpha".into(),
    };
    for (case, count, filter, mixed) in [
        ("small-selected", 32, true, true),
        ("mixed-selected", 2048, true, true),
        ("mixed-unfiltered", 2048, false, true),
        ("complete-selected", 8192, true, false),
    ] {
        let requests: Vec<_> = (0..count)
            .map(|i| {
                let mut request = json!({
                    "origin":"direct", "status":"completed", "started_at_ms":1000,
                    "finished_at_ms":3000 + ((i * 29) % 137), "model":{"provider":"fixture","model":"alpha"},
                    "usage":{"output_tokens":i + 10}
                });
                if mixed {
                    match i % 8 {
                        0 => request["origin"] = json!("compaction"),
                        1 => request["status"] = json!("unfinished"),
                        2 => request["finished_at_ms"] = Value::Null,
                        3 => request["model"]["provider"] = json!("different"),
                        4 => request["model"]["model"] = json!("β"),
                        _ => {}
                    }
                }
                request
            })
            .collect();
        let snapshot = json!({"requests": requests});
        FINISH_LOOKUPS.store(0, Relaxed);
        MODEL_LOOKUPS.store(0, Relaxed);
        let (result, calls, bytes) = measure(|| sample::latest(&snapshot, filter.then_some(&selected)));
        let finish = FINISH_LOOKUPS.load(Relaxed);
        let model = MODEL_LOOKUPS.load(Relaxed);
        let result = result.unwrap().unwrap();
        if mode == "counts" {
            println!("{case} {count} {filter} {finish} {model} {calls} {bytes}");
        } else {
            println!("{}", json!([case, result.model.provider, result.model.name, result.elapsed_ms, result.output, result.rate()]));
        }
    }
}
