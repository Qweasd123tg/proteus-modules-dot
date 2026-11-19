// Optional app-level allocator, not linked into the timing binary.
use std::alloc::{GlobalAlloc, Layout, System};
use std::sync::atomic::{AtomicBool, AtomicU64, Ordering::Relaxed};
pub struct Meter;
#[global_allocator]
static ALLOCATOR: Meter = Meter;
static ON: AtomicBool = AtomicBool::new(false);
static CALLS: AtomicU64 = AtomicU64::new(0);
static BYTES: AtomicU64 = AtomicU64::new(0);
fn note(size: usize) {
    if ON.load(Relaxed) {
        CALLS.fetch_add(1, Relaxed);
        BYTES.fetch_add(size as u64, Relaxed);
    }
}
unsafe impl GlobalAlloc for Meter {
    unsafe fn alloc(&self, l: Layout) -> *mut u8 {
        note(l.size()); unsafe { System.alloc(l) }
    }
    unsafe fn alloc_zeroed(&self, l: Layout) -> *mut u8 {
        note(l.size()); unsafe { System.alloc_zeroed(l) }
    }
    unsafe fn dealloc(&self, p: *mut u8, l: Layout) {
        unsafe { System.dealloc(p, l) }
    }
    unsafe fn realloc(&self, p: *mut u8, l: Layout, n: usize) -> *mut u8 {
        note(n); unsafe { System.realloc(p, l, n) }
    }
}
pub fn start() { CALLS.store(0, Relaxed); BYTES.store(0, Relaxed); ON.store(true, Relaxed); }
pub fn stop() -> [u64; 2] { ON.store(false, Relaxed); [CALLS.load(Relaxed), BYTES.load(Relaxed)] }
