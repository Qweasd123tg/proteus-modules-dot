// Build as a temporary SDK example, never in the shipped binaries.
use proteus_extension::{Value, json, ui};
use std::alloc::{GlobalAlloc, Layout, System};
use std::cell::Cell;

thread_local! {
    static ACTIVE: Cell<bool> = const { Cell::new(false) };
    static COUNTS: Cell<(usize, usize)> = const { Cell::new((0, 0)) };
}

struct Meter;

#[global_allocator]
static METER: Meter = Meter;

fn record(bytes: usize) {
    if ACTIVE.try_with(Cell::get).unwrap_or(false) {
        COUNTS.with(|c| {
            let (calls, old_bytes) = c.get();
            c.set((calls + 1, old_bytes + bytes));
        });
    }
}

unsafe impl GlobalAlloc for Meter {
    unsafe fn alloc(&self, layout: Layout) -> *mut u8 {
        let ptr = unsafe { System.alloc(layout) };
        if !ptr.is_null() {
            record(layout.size());
        }
        ptr
    }

    unsafe fn dealloc(&self, ptr: *mut u8, layout: Layout) {
        unsafe { System.dealloc(ptr, layout) };
    }

    unsafe fn realloc(&self, ptr: *mut u8, previous: Layout, bytes: usize) -> *mut u8 {
        let ptr = unsafe { System.realloc(ptr, previous, bytes) };
        if !ptr.is_null() {
            record(bytes);
        }
        ptr
    }
}

fn measure<T>(f: impl FnOnce() -> T) -> (T, usize, usize) {
    COUNTS.with(|c| c.set((0, 0)));
    ACTIVE.with(|a| a.set(true));
    let out = std::hint::black_box(f());
    ACTIVE.with(|a| a.set(false));
    let (calls, bytes) = COUNTS.with(Cell::get);
    (out, calls, bytes)
}

fn prepared(payload_bytes: usize, spare: Option<usize>) -> Vec<Value> {
    let mut children = Vec::with_capacity(spare.unwrap_or(1));
    children.push(json!({"type":"content","id":"fixture","language":"text/plain",
                         "source":"a".repeat(payload_bytes), "extra":{"z":[null,"α"],"a":true}}));
    children
}

fn main() {
    let mode = std::env::args().nth(1).unwrap();
    assert!(mode == "counts" || mode == "wire");
    for (case, bytes, reserve) in [
        ("row-small", 64, None),
        ("stack-large", 65536, None),
        ("nested-large", 65536, None),
        ("card-present-empty-title", 1024, None),
        ("split-widths", 1024, None),
        ("row-spare-capacity", 1024, Some(64)),
        ("fill-control", 65536, Some(64)),
        ("empty-control", 0, None),
    ] {
        let children = if case == "empty-control" {
            Vec::new()
        } else {
            prepared(bytes, reserve)
        };
        let widths = vec![
            None, Some(320.0), Some(-0.0), Some(f64::NAN), Some(f64::INFINITY), Some(f64::NEG_INFINITY),
        ];
        let (output, calls, requested) = measure(|| match case {
            "nested-large" => ui::split(
                vec![ui::card(None, vec![ui::stack(vec![ui::row(children)])])],
                widths,
            ),
            "row-small" | "row-spare-capacity" => ui::row(children),
            "stack-large" | "empty-control" => ui::stack(children),
            "card-present-empty-title" => ui::card(Some(""), children),
            "split-widths" => ui::split(children, widths),
            "fill-control" => ui::fill(children),
            _ => unreachable!(),
        });
        if mode == "counts" {
            let cap = output["children"].as_array().unwrap().capacity();
            println!("{case} {bytes} {calls} {requested} {cap}");
        } else {
            println!("{}", json!([case, output]));
        }
    }
}
