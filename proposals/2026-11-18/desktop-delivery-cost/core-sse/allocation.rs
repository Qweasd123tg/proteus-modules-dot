//! Test-only allocator around production frame encoding. Prepare FRAME_FN_FILE
//! from the exact pinned source; see reproduce.sh. This program does no I/O in
//! the measurement window and reports requested bytes, not RSS or allocator overhead.
mod codec {
    use bytes::Bytes;
    use proteus_contracts::app_protocol::StdioOutput;
    include!(env!("FRAME_FN_FILE"));
}
use proteus_contracts::app_protocol::{
    AppServerEvent, AppSessionSnapshot, AppTranscriptMessage, StdioOutput,
};
use std::alloc::{GlobalAlloc, Layout, System};
use std::sync::atomic::{AtomicBool, AtomicIsize, AtomicUsize, Ordering::Relaxed};
struct Traffic;
#[global_allocator]
static ALLOCATOR: Traffic = Traffic;
static ACTIVE: AtomicBool = AtomicBool::new(false);
static BYTES: AtomicUsize = AtomicUsize::new(0);
static COUNT: AtomicUsize = AtomicUsize::new(0);
static NET: AtomicIsize = AtomicIsize::new(0);
static HIGH: AtomicIsize = AtomicIsize::new(0);
fn net(delta: isize) {
    let now = NET.fetch_add(delta, Relaxed) + delta;
    HIGH.fetch_max(now, Relaxed);
}
fn account(size: usize, old_size: usize) {
    if ACTIVE.load(Relaxed) {
        BYTES.fetch_add(size, Relaxed);
        COUNT.fetch_add(1, Relaxed);
        net(size as isize - old_size as isize);
    }
}
// Each operation is forwarded to System with the original layout. Count
// cumulative requests and peak live requested bytes above entry, net of frees.
// Reallocation contributes its new size to traffic and its difference to live bytes.
// Neither measure includes allocator overhead, RSS, or internal realloc copying.
unsafe impl GlobalAlloc for Traffic {
    unsafe fn alloc(&self, layout: Layout) -> *mut u8 {
        account(layout.size(), 0);
        unsafe { System.alloc(layout) }
    }
    unsafe fn alloc_zeroed(&self, layout: Layout) -> *mut u8 {
        account(layout.size(), 0);
        unsafe { System.alloc_zeroed(layout) }
    }
    unsafe fn dealloc(&self, ptr: *mut u8, layout: Layout) {
        if ACTIVE.load(Relaxed) {
            net(-(layout.size() as isize));
        }
        unsafe { System.dealloc(ptr, layout) }
    }
    unsafe fn realloc(&self, ptr: *mut u8, layout: Layout, size: usize) -> *mut u8 {
        account(size, layout.size());
        unsafe { System.realloc(ptr, layout, size) }
    }
}

fn rows(n: usize, chars: usize) -> Vec<AppTranscriptMessage> {
    (0..n)
        .map(|i| AppTranscriptMessage {
            message_id: Some(uuid::Uuid::from_u128(i as u128 + 7)),
            timestamp_ms: Some(i as i64),
            phase: None,
            role: if i % 2 == 0 { "user" } else { "assistant" }.into(),
            text: format!("{i} \"первая строка\"\n終\\ {}", "x".repeat(chars)),
            images: vec![],
            tool: None,
            subagent: None,
            streaming: false,
        })
        .collect()
}
fn event(n: usize, len: usize) -> StdioOutput {
    StdioOutput::Event {
        event: Box::new(AppServerEvent::SessionSnapshot {
            snapshot: Box::new(AppSessionSnapshot {
                session_id: uuid::Uuid::from_u128(42),
                stream_id: "stream".into(),
                seq: 43,
                root_thread_id: None,
                transcript: rows(n, len),
                history: None,
                execution: Default::default(),
            }),
        }),
    }
}

fn four() {
    for (name, n, sz) in [
        ("empty", 0, 0),
        ("short", 1, 80),
        ("typical", 50, 1024),
        ("large", 50, 65536),
    ] {
        let output = event(n, sz);
        COUNT.store(0, Relaxed);
        NET.store(0, Relaxed);
        HIGH.store(0, Relaxed);
        BYTES.store(0, Relaxed);
        ACTIVE.store(true, Relaxed);
        let frame = std::hint::black_box(codec::encode_sse_output(&output));
        ACTIVE.store(false, Relaxed);
        println!(
            "HEAP shape={name} bytes={} calls={} traffic={} peak={} live={}",
            frame.len(),
            COUNT.load(Relaxed),
            BYTES.load(Relaxed),
            HIGH.load(Relaxed),
            NET.load(Relaxed)
        );
        drop(frame);
    }
}
fn sweep() {
    for n in [1, 2, 50] {
        let mut sizes: Vec<usize> = (0..=4096).collect();
        for power in 13..=20 {
            for d in [0, 1, 2, 4, 8, 16, 32, 64, 128, 256, 512] {
                sizes.push((1 << power) - d);
                sizes.push((1 << power) + d);
            }
        }
        sizes.sort();
        sizes.dedup();
        for sz in sizes {
            let output = event(n, sz);
            COUNT.store(0, Relaxed);
            NET.store(0, Relaxed);
            HIGH.store(0, Relaxed);
            BYTES.store(0, Relaxed);
            ACTIVE.store(true, Relaxed);
            let frame = std::hint::black_box(codec::encode_sse_output(&output));
            ACTIVE.store(false, Relaxed);
            println!(
                "{},{},{},{},{},{},{}",
                n,
                sz,
                frame.len(),
                COUNT.load(Relaxed),
                BYTES.load(Relaxed),
                HIGH.load(Relaxed),
                NET.load(Relaxed)
            );
            drop(frame);
        }
    }
}

fn main() {
    if std::env::args().nth(1).as_deref() == Some("sweep") {
        sweep()
    } else {
        four()
    }
}
