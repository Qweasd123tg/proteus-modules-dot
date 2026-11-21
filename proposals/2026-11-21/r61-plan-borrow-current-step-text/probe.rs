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
    use model::{Snapshot, Visibility};
    use proteus_extension::json;
    let mode = std::env::args().nth(1).unwrap();
    assert!(mode == "counts" || mode == "wire");
    for (shape, n) in [
        ("typed-small", 4),
        ("typed-24", 24),
        ("typed-96", 96),
        ("encoded", 24),
        ("retained-owned", 24),
    ] {
        let steps = (0..n)
            .map(|i| {
                json!({
                    "step":format!("Шаг {i}: проверить подготовленные файлы и сохранить результат"),
                    "status":match i {0 => "completed", 1 => "in_progress", _ => "pending"}
                })
            })
            .collect::<Vec<_>>();
        let args = json!({"plan":steps});
        let args = if shape == "encoded" {
            Value::String(args.to_string())
        } else {
            args
        };
        let entries = [
            json!({"role":"assistant","tool":{"name":"update_plan","status":"completed","effective_args":args}}),
        ];
        let load = || {
            if shape == "retained-owned" {
                Snapshot::from_tool_owned(entries[0].at("tool"))
            } else {
                model::latest(&entries, Visibility::Current, true).unwrap()
            }
        };
        let (output, calls, bytes) = measure(|| {
            let plan = load();
            assert_eq!(plan.steps.len(), n);
            (plan.summary(), plan.current().unwrap().to_owned())
        });
        if mode == "wire" {
            println!("{}", json!(output));
        } else {
            println!("{shape} {n} summary {calls} {bytes}");
        }
        let (output, calls, bytes) = measure(|| model::details(&load()));
        if mode == "wire" {
            println!("{output}");
        } else {
            println!("{shape} {n} popup-tree {calls} {bytes}");
        }
    }
}
