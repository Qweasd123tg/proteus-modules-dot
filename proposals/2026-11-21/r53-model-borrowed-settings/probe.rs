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
        if !p.is_null() { record(layout.size()); }
        p
    }
    unsafe fn dealloc(&self, p: *mut u8, layout: Layout) {
        unsafe { System.dealloc(p, layout) }
    }
    unsafe fn realloc(&self, p: *mut u8, layout: Layout, size: usize) -> *mut u8 {
        let p = unsafe { System.realloc(p, layout, size) };
        if !p.is_null() { record(size); }
        p
    }
}
fn measure<T>(f: impl FnOnce() -> T) -> (T,usize,usize) {
    CALLS.store(0, Relaxed);
    BYTES.store(0, Relaxed);
    let output = std::hint::black_box(f());
    (output, CALLS.load(Relaxed), BYTES.load(Relaxed))
}
fn main() {
    let mode = std::env::args().nth(1).unwrap();
    assert!(mode == "wire" || mode == "counts");
    for (workload, efforts_count, extra_count, option_count) in [
        ("base", 2, 0, 0),
        ("one-extra", 2, 1, 3),
        ("four-extras", 4, 4, 8),
        ("ten-extras", 4, 10, 12),
    ] {
        let mut reasoning = vec![json!({"name":"По профилю","value":"_default"})];
        reasoning.extend((0..efforts_count).map(|i|json!({"name":format!("Усилие {i}"),"value":format!("effort:v{i}")})));
        let mut settings=vec![
            json!({"id":"model","name":"Модель","control":{"type":"select","value":"one","options":[{"name":"First","value":"one"},{"name":"Second","value":"two"}]}}),
            json!({"id":"reasoning_effort","name":"Усилие","control":{"type":"select","value":"_default","options":reasoning}}),
        ];
        settings.extend((0..extra_count).map(|i| {
            let options=(0..option_count).map(|j|json!({"name":format!("Вариант {j}"),"value":format!("choice-{j}")})).collect::<Vec<_>>();
            json!({"id":format!("provider/setting-{i}"),"name":format!("Настройка {i}"),"control":{"type":"select","value":"choice-0","options":options}})
        }));
        let mut host=Host::default();
        host.state=Some(json!({"config":{"profile":"Test","model":{"name":"one"},"model_options":[{"provider":"A","name":"one","default_reasoning_effort":"v1"},{"provider":"B","name":"two"}],"session_settings":settings}}));
        let (efforts,c,b)=measure(||settings::efforts(&host));
        assert_eq!(efforts.len(),efforts_count);
        if mode=="counts" { println!("{workload} efforts {c} {b} {}",efforts.len()); }
        let (extras,c,b)=measure(||settings::extra(&host));
        assert_eq!(extras.len(),extra_count);
        if mode=="counts" { println!("{workload} extras {c} {b} {}",extras.len()); }
        let (face,c,b)=measure(||label(&host));
        if mode=="counts" { println!("{workload} badge-label {c} {b} {}",face.len()); }
        else { println!("{}",json!(face)); }
        for (surface,models_open) in [("summary",false),("models",true)] {
            let (output,c,b)=measure(||popup::render(&host,models_open));
            let bytes=output.to_string();
            if mode=="counts" { println!("{workload} {surface} {c} {b} {}",bytes.len()); }
            else { println!("{bytes}"); }
        }
    }
}
