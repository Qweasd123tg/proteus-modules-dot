// Temporary test-only probe: place in src/codec/allocation_probe.rs
// and add "#[cfg(test)] mod allocation_probe;" to src/codec.rs.
use super::*;
use ring::digest::{Context as HashContext, SHA256};
use std::alloc::{GlobalAlloc, Layout, System};
use std::cell::Cell;
use std::path::PathBuf;

struct Count;
#[global_allocator]
static ALLOC: Count = Count;
thread_local! {
    static TOTAL: Cell<Option<(u64, u64)>> = const { Cell::new(None) };
}
fn note(n: usize) {
    let _ = TOTAL.try_with(|slot| {
        if let Some((calls, bytes)) = slot.get() {
            slot.set(Some((calls + 1, bytes + n as u64)));
        }
    });
}
unsafe impl GlobalAlloc for Count {
    unsafe fn alloc(&self, layout: Layout) -> *mut u8 {
        note(layout.size());
        unsafe { System.alloc(layout) }
    }
    unsafe fn alloc_zeroed(&self, layout: Layout) -> *mut u8 {
        note(layout.size());
        unsafe { System.alloc_zeroed(layout) }
    }
    unsafe fn dealloc(&self, p: *mut u8, layout: Layout) {
        unsafe { System.dealloc(p, layout) }
    }
    unsafe fn realloc(&self, p: *mut u8, layout: Layout, n: usize) -> *mut u8 {
        note(n);
        unsafe { System.realloc(p, layout, n) }
    }
}

#[test]
fn measure_inline_decode_allocations() {
    let path = PathBuf::from(std::env::var_os("PROTEUS_CODEC_PROBE_JOURNAL").unwrap());
    let bytes = std::fs::read(&path).unwrap();
    let session_dir = path.parent().unwrap();
    let source_digest = sha256_hex(&bytes);
    assert_eq!(bytes.last(), Some(&b'\n'));
    let mut lines = bytes[..bytes.len() - 1].split(|&b| b == b'\n');
    let first: serde_json::Value = serde_json::from_slice(lines.next().unwrap()).unwrap();
    let id: SessionId = serde_json::from_value(first["session_id"].clone()).unwrap();
    for pass in 0..=3 {
        let (mut records, mut calls, mut requested) = (0, 0, 0);
        let mut canonical_hash = HashContext::new(&SHA256);
        for line in bytes[..bytes.len() - 1].split(|&b| b == b'\n') {
            TOTAL.set(Some((0, 0)));
            let result = decode(session_dir, id, line);
            let (new_calls, new_requested) = TOTAL.replace(None).unwrap();
            let (record, external) = result.unwrap();
            records += 1;
            calls += new_calls;
            requested += new_requested;
            assert_eq!(record.session_seq, records);
            assert!(!external);
            canonical_hash.update(&serde_json::to_vec(&record).unwrap());
            canonical_hash.update(b"\n");
        }
        let canonical_digest = crate::io::digest_hex(canonical_hash.finish());
        if pass > 0 {
            println!(
                "CODEC,{pass},{records},{calls},{requested},{source_digest},{canonical_digest}"
            );
        }
    }
}
