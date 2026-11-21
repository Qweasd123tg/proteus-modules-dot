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
    use proteus_extension::{ValueExt, json};
    let mode = std::env::args().nth(1).unwrap();
    assert!(mode == "wire" || mode == "counts");
    for n in [1, 20, 400, 2000] {
        let requests=(0..n).map(|i| {
            let model=match i%4 {
                0=>json!({"provider":"fixture/proxy","model":"地"}),
                1=>json!({"provider":"fixture","model":"proxy/地"}),
                2=>json!({"provider":"fixture","model":"other"}),
                _=>Value::Null,
            };
            json!({"exchange_id":format!("r{i}"),"turn_id":format!("t{}",i%3),"status":"completed",
                   "model":model,"usage":{"input_tokens":1200,"output_tokens":12},
                   "started_at_ms":i*1000,"finished_at_ms":i*1000+100})
        }).collect::<Vec<_>>();
        let snapshot = json!({"requests":requests,"latest_turn_id":"t2"});
        let requests = snapshot.list("requests");
        let (models, calls, bytes) = measure(|| view::model_options_probe(requests));
        if mode == "wire" {
            println!("{}", json!(models));
        } else {
            println!("{n} picker-labels {calls} {bytes}");
        }
        let (selected, calls, bytes) =
            measure(|| report::scoped(&snapshot, "all", Some("fixture/proxy/地")));
        assert_eq!(selected.len(), (n + 1) / 2);
        if mode == "wire" {
            println!(
                "{}",
                json!(
                    selected
                        .iter()
                        .map(|r| r.str("exchange_id"))
                        .collect::<Vec<_>>()
                )
            );
        } else {
            println!("{n} filter {calls} {bytes}");
        }
        for (surface, selected) in [
            ("full-unfiltered", None),
            ("full-filtered", Some("fixture/proxy/地".to_owned())),
        ] {
            let mut state = Usage {
                model: selected,
                ..Usage::default()
            };
            let (res, calls, bytes) = measure(|| view::render(&mut state, &snapshot));
            if mode == "wire" {
                println!("{}", json!(res.unwrap()));
            } else {
                println!("{n} {surface} {calls} {bytes}");
            }
        }
    }
}
