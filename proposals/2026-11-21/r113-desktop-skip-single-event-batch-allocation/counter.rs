use std::alloc::{GlobalAlloc, Layout, System};
use std::cell::Cell;
struct Meter;
thread_local! { static TALLY: Cell<Option<(usize,usize)>> = const { Cell::new(None) }; }
fn charge(n: usize) {
    TALLY.with(|c| {
        if let Some((calls, bytes)) = c.get() {
            c.set(Some((calls + 1, bytes + n)));
        }
    });
}
// Test-only pass-through allocator. Only the synchronous measured closure's thread is counted.
unsafe impl GlobalAlloc for Meter {
    unsafe fn alloc(&self, l: Layout) -> *mut u8 {
        charge(l.size());
        unsafe { System.alloc(l) }
    }
    unsafe fn alloc_zeroed(&self, l: Layout) -> *mut u8 {
        charge(l.size());
        unsafe { System.alloc_zeroed(l) }
    }
    unsafe fn dealloc(&self, p: *mut u8, l: Layout) {
        unsafe { System.dealloc(p, l) }
    }
    unsafe fn realloc(&self, p: *mut u8, l: Layout, n: usize) -> *mut u8 {
        charge(n);
        unsafe { System.realloc(p, l, n) }
    }
}
#[global_allocator]
static METER: Meter = Meter;
fn measurement<T>(f: impl FnOnce() -> T) -> (T, usize, usize) {
    TALLY.with(|c| {
        assert!(c.replace(Some((0, 0))).is_none());
        let result = std::hint::black_box(f());
        let (calls, bytes) = c.replace(None).unwrap();
        (result, calls, bytes)
    })
}
