use std::alloc::{GlobalAlloc, Layout, System};
use std::cell::Cell;

struct Meter;
// Layout-level requested sizes; unrelated threads, libc and GPU aren't counted.
thread_local! {
    static TALLY: Cell<Option<(usize, usize, isize)>> = const { Cell::new(None) };
}
fn note(calls: usize, bytes: usize, released: usize) {
    let _ = TALLY.try_with(|c| {
        if let Some((n, b, live)) = c.get() {
            c.set(Some((
                n + calls,
                b + bytes,
                live + bytes as isize - released as isize,
            )));
        }
    });
}
// Test-only pass-through allocator.
unsafe impl GlobalAlloc for Meter {
    unsafe fn alloc(&self, l: Layout) -> *mut u8 {
        let p = unsafe { System.alloc(l) };
        if !p.is_null() {
            note(1, l.size(), 0);
        }
        p
    }
    unsafe fn alloc_zeroed(&self, l: Layout) -> *mut u8 {
        let p = unsafe { System.alloc_zeroed(l) };
        if !p.is_null() {
            note(1, l.size(), 0);
        }
        p
    }
    unsafe fn dealloc(&self, p: *mut u8, l: Layout) {
        note(0, 0, l.size());
        unsafe { System.dealloc(p, l) };
    }
    unsafe fn realloc(&self, p: *mut u8, l: Layout, n: usize) -> *mut u8 {
        let next = unsafe { System.realloc(p, l, n) };
        if !next.is_null() {
            note(1, n, l.size());
        }
        next
    }
}
#[global_allocator]
static METER: Meter = Meter;
pub fn measure<T>(f: impl FnOnce() -> T) -> (T, [isize; 3]) {
    TALLY.with(|c| {
        assert!(c.replace(Some((0, 0, 0))).is_none());
        let result = std::hint::black_box(f());
        let (calls, bytes, live) = c.replace(None).unwrap();
        (result, [calls as isize, bytes as isize, live])
    })
}
