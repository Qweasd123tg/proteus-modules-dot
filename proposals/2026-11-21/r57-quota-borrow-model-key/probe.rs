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
    for (shape, model) in [
        ("null", Value::Null),
        (
            "model",
            json!({"provider":"fixture","name":"example-model","label":"Synthetic model"}),
        ),
        (
            "metadata",
            json!({"provider":"fixture","name":"example-model","label":"Synthetic model",
            "metadata":{"tier":"fixture","aliases":["one","two"],"description":"Synthetic provider metadata"}}),
        ),
    ] {
        for (mode, surface) in [("badge", Surface::Badge), ("popup", Surface::Popup)] {
            let mut host = Host::default();
            host.session = Some("/quota-fixture-session".into());
            host.state = Some(json!({"config":{"model":model}}));
            let mut quota = Quota {
                session: host.session.clone(),
                model: model.clone(),
                loaded: true,
                snapshot: json!({"plan":"Test","buckets":[
                    {"id":"shared","name":"Общий лимит","windows":[{"id":"rolling","used_percent":20,"duration_seconds":18000}]}
                ]}),
                deadline: Some(Instant::now() + Duration::from_secs(3600)),
                ..Quota::default()
            };
            quota.render(&mut host, mode, surface, None).unwrap();
            for _ in 0..3 {
                let (result, calls, bytes) =
                    measure(|| quota.render(&mut host, mode, surface, None));
                result.unwrap();
                assert!(quota.loaded && quota.error.is_none());
                eprintln!("{shape} {mode} {calls} {bytes}");
            }
        }
    }
}
