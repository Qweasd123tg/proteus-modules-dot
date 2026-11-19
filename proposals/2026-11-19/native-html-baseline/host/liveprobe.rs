//! Counts logical live requested Rust heap bytes; no timing or resident-memory claims.
use gpui::{AppContext as _, TestAppContext, TestDispatcher};
use gpui_base::text::{TextViewState, r5_counts};
use serde_json::{Value, json};
use std::alloc::{GlobalAlloc, Layout, System};
use std::collections::BTreeMap;
use std::sync::atomic::{AtomicBool, AtomicUsize, Ordering::SeqCst};

struct Meter;
#[global_allocator] static ALLOC: Meter = Meter;
static LIVE: AtomicUsize = AtomicUsize::new(0);
static PEAK: AtomicUsize = AtomicUsize::new(0);
static ACTIVE: AtomicBool = AtomicBool::new(false);

fn grow(size: usize) {
    let now = LIVE.fetch_add(size, SeqCst) + size;
    if ACTIVE.load(SeqCst) { PEAK.fetch_max(now, SeqCst); }
}

unsafe impl GlobalAlloc for Meter {
    unsafe fn alloc(&self, layout: Layout) -> *mut u8 {
        let p = unsafe { System.alloc(layout) };
        if !p.is_null() { grow(layout.size()); } p
    }
    unsafe fn alloc_zeroed(&self, layout: Layout) -> *mut u8 {
        let p = unsafe { System.alloc_zeroed(layout) };
        if !p.is_null() { grow(layout.size()); } p
    }
    unsafe fn dealloc(&self, p: *mut u8, layout: Layout) {
        LIVE.fetch_sub(layout.size(), SeqCst);
        unsafe { System.dealloc(p, layout) };
    }
    unsafe fn realloc(&self, p: *mut u8, old: Layout, n: usize) -> *mut u8 {
        let updated = unsafe { System.realloc(p, old, n) };
        if !updated.is_null() {
            if n >= old.size() { grow(n - old.size()); }
            else { LIVE.fetch_sub(old.size() - n, SeqCst); }
        }
        updated
    }
}
fn now() -> usize { LIVE.load(SeqCst) }

fn main() {
    let a: Vec<_> = std::env::args().collect();
    let input: BTreeMap<String,String> = std::fs::read_to_string(&a[1]).unwrap().lines().map(|l| {
        let x: Value = serde_json::from_str(l).unwrap();
        (x["name"].as_str().unwrap().to_owned(),x["html"].as_str().unwrap().to_owned())
    }).collect();
    let names: &[&str] = match a[2].as_str() {
        "typical32" => &["plain-ack","plain-link","plain-escape","md-selection","md-table"],
        "edge32" => &["md-table-4096","md-links-4096"],
        "control32" => &["plain-4097"],
        _ => panic!("unknown case"),
    };
    let inputs: Vec<_> = (0..32).map(|i| input[names[i%names.len()]].as_str()).collect();
    let mut cx = TestAppContext::build(TestDispatcher::new(41),Some("live_state_qual"));
    for run in 0..2 {
        let mut held = Vec::with_capacity(32);
        let before_count = r5_counts();
        let baseline = now();
        PEAK.store(baseline,SeqCst);
        ACTIVE.store(true,SeqCst);
        for text in &inputs { held.push(cx.new(|cx| new_html(text,cx))); }
        let sync = now();
        let sync_counts = r5_counts();
        cx.run_until_parked();
        let idle = now();
        let peak = PEAK.load(SeqCst);
        ACTIVE.store(false,SeqCst);
        let final_counts = r5_counts();
        assert!(held.iter().all(|s| s.read_with(&cx,|state,_| state.is_ready())));
        drop(held);
        cx.update(|_| {});
        cx.run_until_parked();
        let dropped = now();
        if run == 1 {
            let d = |v:usize| v as i64-baseline as i64;
            println!("{}",json!({"baseline":baseline, "sync_delta":d(sync),"held_idle_delta":d(idle),
                "peak_delta":d(peak),"after_drop_delta":d(dropped),
                "fg":sync_counts[0]-before_count[0], "bg":final_counts[0]-sync_counts[0]}));
        }
    }
}


// The scoped arm executes the *actual constructor expression* from RichText::new,
// copied and checked while preparing the pinned tree. This benchmark has no Window.
fn new_html(html: &str, cx: &mut gpui::Context<TextViewState>) -> TextViewState {
    #[cfg(feature="scoped")]
    { include!(concat!(env!("CARGO_MANIFEST_DIR"), "/factory.in")) }
    #[cfg(not(feature="scoped"))]
    { TextViewState::html(html, cx) }
}
