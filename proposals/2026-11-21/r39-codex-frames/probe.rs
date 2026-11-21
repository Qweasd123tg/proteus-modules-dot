// Included as a test-only child of the real transport's private framing module.
// The verifier supplies the tiny stock/candidate adapter called drive().
use super::*;
use std::{
    alloc::{GlobalAlloc, Layout, System},
    cell::Cell,
    hint::black_box,
};

struct Meter;
thread_local! {
    static METER: Cell<Option<(usize, usize)>> = const { Cell::new(None) };
}
fn record(size: usize) {
    METER.with(|meter| {
        if let Some((calls, bytes)) = meter.get() {
            meter.set(Some((calls + 1, bytes + size)));
        }
    });
}
#[global_allocator]
static ALLOC: Meter = Meter;
unsafe impl GlobalAlloc for Meter {
    unsafe fn alloc(&self, layout: Layout) -> *mut u8 {
        record(layout.size());
        unsafe { System.alloc(layout) }
    }
    unsafe fn realloc(&self, p: *mut u8, layout: Layout, size: usize) -> *mut u8 {
        record(size);
        unsafe { System.realloc(p, layout, size) }
    }
    unsafe fn alloc_zeroed(&self, layout: Layout) -> *mut u8 {
        record(layout.size());
        unsafe { System.alloc_zeroed(layout) }
    }
    unsafe fn dealloc(&self, p: *mut u8, layout: Layout) {
        unsafe { System.dealloc(p, layout) }
    }
}

#[test]
fn framing_allocations() {
    const FRAMES: usize = 16_384;
    for (name, capacity, wire_size) in [
        ("aligned", 8192, 128),
        ("unaligned", 8192, 117),
        ("fragmented", 32, 117),
    ] {
        let mut line = r#"{"method":"item/textDelta","params":{"text":"Привет"}}"#
            .as_bytes()
            .to_vec();
        line.resize(wire_size - 1, b' '); // legal trailing JSON whitespace
        line.push(b'\n');
        let corpus = line.repeat(FRAMES);
        for decode in [false, true] {
            let mut reader = BufReader::with_capacity(capacity, corpus.as_slice());
            let mut seen = 0;
            METER.with(|meter| meter.set(Some((0, 0))));
            drive(&mut reader, 1024, |frame| {
                assert_eq!(black_box(frame), &line[..wire_size - 1]);
                if decode {
                    let value: Value = serde_json::from_slice(frame).unwrap();
                    assert_eq!(black_box(&value)["params"]["text"], "Привет");
                }
                seen += 1;
                Ok(())
            })
            .unwrap();
            let (calls, bytes) = METER.with(|meter| meter.take().unwrap());
            assert_eq!(seen, FRAMES);
            println!(
                "case={name} capacity={capacity} wire_bytes={wire_size} frames={seen} decode={decode} allocation_requests={calls} requested_bytes={bytes}"
            );
        }
    }
}
