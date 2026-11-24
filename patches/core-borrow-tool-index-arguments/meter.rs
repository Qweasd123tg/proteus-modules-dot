use std::{
    alloc::{GlobalAlloc, Layout, System},
    cell::Cell,
};
#[derive(Default, Clone, Copy, Debug)]
pub struct Stats {
    pub live: usize,
    pub peak: usize,
    pub req: usize,
    pub allocs: usize,
    pub reallocs: usize,
}
thread_local! { static ACTIVE:Cell<Option<Stats>>=const{Cell::new(None)}; }
fn note(old: usize, new: usize, alloc: bool, realloc: bool) {
    let _ = ACTIVE.try_with(|c| {
        if let Some(mut s) = c.get() {
            s.live = s.live.checked_sub(old).unwrap() + new;
            s.peak = s.peak.max(s.live);
            s.req += new;
            s.allocs += usize::from(alloc);
            s.reallocs += usize::from(realloc);
            c.set(Some(s));
        }
    });
}
struct Meter;
unsafe impl GlobalAlloc for Meter {
    unsafe fn alloc(&self, l: Layout) -> *mut u8 {
        let r = unsafe { System.alloc(l) };
        if !r.is_null() {
            note(0, l.size(), true, false);
        }
        r
    }
    unsafe fn alloc_zeroed(&self, l: Layout) -> *mut u8 {
        let r = unsafe { System.alloc_zeroed(l) };
        if !r.is_null() {
            note(0, l.size(), true, false);
        }
        r
    }
    unsafe fn realloc(&self, p: *mut u8, l: Layout, n: usize) -> *mut u8 {
        let r = unsafe { System.realloc(p, l, n) };
        if !r.is_null() {
            note(l.size(), n, false, true);
        }
        r
    }
    unsafe fn dealloc(&self, p: *mut u8, l: Layout) {
        note(l.size(), 0, false, false);
        unsafe { System.dealloc(p, l) }
    }
}
#[global_allocator]
static A: Meter = Meter;
pub fn scope<R>(f: impl FnOnce() -> R) -> (R, Stats) {
    assert!(ACTIVE.replace(Some(Stats::default())).is_none());
    let r = f();
    (r, ACTIVE.replace(None).unwrap())
}
