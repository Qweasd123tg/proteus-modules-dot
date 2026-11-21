// Compile alongside a ui.rs copy from the stock or patched sdk/src/ui.rs.
// Print cumulative allocation requests and the additional peak live bytes
// during each constructor; the JSON output itself is written after the snapshot.
#![allow(dead_code)]
mod ui;

use serde_json::{Value, json};
use std::alloc::{GlobalAlloc, Layout, System};
use std::io::Write;
use std::sync::atomic::{AtomicUsize, Ordering::Relaxed};

struct Counting;
#[global_allocator]
static A: Counting = Counting;
static CALLS: AtomicUsize = AtomicUsize::new(0);
static REQUESTED: AtomicUsize = AtomicUsize::new(0);
static LIVE: AtomicUsize = AtomicUsize::new(0);
static PEAK: AtomicUsize = AtomicUsize::new(0);

fn record_new(size: usize, old: usize) {
    CALLS.fetch_add(1, Relaxed);
    REQUESTED.fetch_add(size, Relaxed);
    if size >= old {
        let extra = size - old;
        let live = LIVE.fetch_add(extra, Relaxed) + extra;
        PEAK.fetch_max(live, Relaxed);
    } else {
        LIVE.fetch_sub(old - size, Relaxed);
    }
}

unsafe impl GlobalAlloc for Counting {
    unsafe fn alloc(&self, layout: Layout) -> *mut u8 {
        let p = unsafe { System.alloc(layout) };
        if !p.is_null() {
            record_new(layout.size(), 0);
        }
        p
    }
    unsafe fn dealloc(&self, p: *mut u8, layout: Layout) {
        LIVE.fetch_sub(layout.size(), Relaxed);
        unsafe { System.dealloc(p, layout) };
    }
    unsafe fn realloc(&self, p: *mut u8, layout: Layout, size: usize) -> *mut u8 {
        let result = unsafe { System.realloc(p, layout, size) };
        if !result.is_null() {
            record_new(size, layout.size());
        }
        result
    }
}

fn main() {
    let mut out = std::io::stdout().lock();
    for n in [0, 1, 100, 1_000] {
        for kind in ["list", "lanes"] {
            // Deterministic synthetic nested rows, not live Git UI traces.
            let make_row = |i: usize| {
                let id = format!("commit-{i:04}");
                let label = format!("Правка №{i} 🦀");
                let menu = vec![json!({"label":"View Commit","action":"open_commit","value":id})];
                if kind == "list" {
                    json!({"id":id,"label":label,"chips":["v1"],"meta":["Alice","2 ч",id],"menu":menu})
                } else {
                    json!({"id":id,"label":label,"lane":0,"color":0,"cells":["",label],
                           "down":[{"from":0,"to":0,"color":0}],"menu":menu})
                }
            };
            let rows: Vec<Value> = (0..n).map(make_row).collect();
            let columns = vec![
                json!({"label":"Graph","kind":"graph","weight":2}),
                json!({"label":"Description","weight":1}),
            ];
            let calls = CALLS.load(Relaxed);
            let bytes = REQUESTED.load(Relaxed);
            let live = LIVE.load(Relaxed);
            PEAK.store(live, Relaxed);
            let result = if kind == "list" {
                ui::list("log", rows, "log")
            } else {
                ui::lanes("graph", columns, rows, "graph_log")
            };
            let counts = (
                CALLS.load(Relaxed) - calls,
                REQUESTED.load(Relaxed) - bytes,
                PEAK.load(Relaxed) - live,
            );
            eprintln!("{kind}\t{n}\t{}\t{}\t{}", counts.0, counts.1, counts.2);
            serde_json::to_writer(&mut out, &result).unwrap();
            writeln!(out).unwrap();
        }
    }
}
