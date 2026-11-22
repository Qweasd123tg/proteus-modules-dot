// Test-only Plan projection counters; never part of the product patches.
use super::*;

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

thread_local! {
    static VISITS: Cell<(usize, usize, usize)> = const { Cell::new((0, 0, 0)) };
}

pub(super) fn input_row() {
    VISITS.with(|m| {
        let (raw, separate, inline) = m.get();
        m.set((raw + 1, separate, inline));
    });
}

pub(super) fn separate_row() {
    VISITS.with(|m| {
        let (raw, separate, inline) = m.get();
        m.set((raw, separate + 1, inline));
    });
}

pub(super) fn inline_complete() {
    VISITS.with(|m| {
        let (raw, separate, inline) = m.get();
        m.set((raw, separate, inline + 1));
    });
}

fn ordinary(n: usize) -> Vec<Value> {
    (0..n)
        .map(|i| {
            let status = ["pending", "completed", "in_progress", "completed", "pending"][i % 5];
            json!({"step":format!("Обычный шаг {i}: проверка 🧪"),"status":status})
        })
        .collect()
}

#[test]
fn measure_plan_projection() {
    println!(); // Put the first measurement on its own line after the libtest banner.
    let mixed = vec![
        json!({"step":"repeat","status":"completed"}),
        json!({"step":5,"status":"completed"}),
        json!({"status":"completed"}),
        json!({"step":"","status":"completed"}),
        json!({"step":"repeat","status":"pending"}),
        json!({"step":"early active","status":"in_progress"}),
        json!({"step":"later active","status":"in_progress"}),
        json!({"step":"bad status","status":[]}),
        json!({"step":"missing status"}),
        json!({"step":"unknown","status":"Completed"}),
        json!(false),
    ];
    for (case, rows, encoded, valid, completed) in [
        ("empty", vec![], false, 0, 0),
        ("short", ordinary(6), false, 6, 2),
        ("modest", ordinary(12), false, 12, 5),
        ("encoded", ordinary(12), true, 12, 5),
        ("cached", ordinary(12), false, 12, 5),
        ("mixed", mixed, false, 6, 2),
    ] {
        let input = rows.len();
        let args = json!({"plan": rows});
        let tool = if encoded {
            json!({"effective_args":args.to_string(),"args":{"ignored":true}})
        } else {
            json!({"args":args,"effective_args":null})
        };
        VISITS.set((0, 0, 0));
        let (snapshot, calls, bytes) = scope(|| {
            let input = std::hint::black_box(&tool);
            if case == "cached" { cached(input) } else { Snapshot::from_tool(input) }
        });
        assert_eq!((snapshot.steps.len(),snapshot.done),(valid,completed));
        let (raw, separate, inline) = VISITS.get();
        assert_eq!(raw,input);
        println!(
            "ops {case} {raw} {valid} {separate} {inline} {completed} {} {calls} {bytes}",
            snapshot.steps.capacity()
        );
        let projection = json!({"summary":snapshot.summary(),"current":snapshot.current(),"details":details(&snapshot)});
        println!("tree {case} {projection}");
    }
}
