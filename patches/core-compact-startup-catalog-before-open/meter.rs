// Compare allocator request sizes over an identical interval, not System/RSS bytes.
use std::{
    alloc::{GlobalAlloc, Layout, System},
    cell::Cell,
};
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub struct Stats {
    pub live: usize,
    pub peak: usize,
    pub peak_with_moved_realloc_overlap: usize,
    pub allocs: usize,
    pub reallocs: usize,
    pub moved: usize,
    pub checkpoint: [usize; 6],
    pub phase_peak: [usize; 6],
    pub phase: usize,
    pub input_vec_bytes: usize,
    pub sorted_vec_bytes: usize,
    pub sort_len: usize,
    pub sort_called: bool,
}
thread_local! {static ACTIVE:Cell<Option<Stats>>=const{Cell::new(None)};}
fn change(f: impl FnOnce(&mut Stats)) {
    let _ = ACTIVE.try_with(|c| {
        if let Some(mut s) = c.get() {
            f(&mut s);
            c.set(Some(s))
        }
    });
}
fn note(old: usize, new: usize, a: bool, r: bool, moved: bool) {
    change(|s| {
        if moved {
            s.peak_with_moved_realloc_overlap = s.peak_with_moved_realloc_overlap.max(s.live + new);
            s.moved += 1;
        }
        s.live = s.live.checked_sub(old).unwrap() + new;
        s.peak = s.peak.max(s.live);
        s.peak_with_moved_realloc_overlap = s.peak_with_moved_realloc_overlap.max(s.live);
        s.phase_peak[s.phase] = s.phase_peak[s.phase].max(s.live);
        s.allocs += usize::from(a);
        s.reallocs += usize::from(r);
    });
}
struct Meter;
#[global_allocator]
static METER: Meter = Meter;
unsafe impl GlobalAlloc for Meter {
    unsafe fn alloc(&self, l: Layout) -> *mut u8 {
        let p = unsafe { System.alloc(l) };
        if !p.is_null() {
            note(0, l.size(), true, false, false)
        }
        p
    }
    unsafe fn alloc_zeroed(&self, l: Layout) -> *mut u8 {
        let p = unsafe { System.alloc_zeroed(l) };
        if !p.is_null() {
            note(0, l.size(), true, false, false)
        }
        p
    }
    unsafe fn realloc(&self, p: *mut u8, l: Layout, n: usize) -> *mut u8 {
        let q = unsafe { System.realloc(p, l, n) };
        if !q.is_null() {
            note(l.size(), n, false, true, p != q)
        }
        q
    }
    unsafe fn dealloc(&self, p: *mut u8, l: Layout) {
        note(l.size(), 0, false, false, false);
        unsafe { System.dealloc(p, l) }
    }
}
// 0 before reply construction; 1 decoded response; 2 before sort; 3 after sort;
// 4 first attempted open; 5 first validation. Later attempts must not reset peaks.
pub fn checkpoint(n: usize) {
    change(|s| {
        if n > s.phase {
            s.phase = n;
            s.checkpoint[n] = s.live;
            s.phase_peak[n] = s.live;
        }
    });
}
pub fn input_capacity(n: usize) {
    change(|s| s.input_vec_bytes = n)
}
pub fn sorted_capacity(n: usize) {
    change(|s| s.sorted_vec_bytes = n)
}
pub fn sort_entry(n: usize) {
    change(|s| s.sort_len = n)
}
pub fn did_sort() {
    change(|s| s.sort_called = true)
}
pub fn scope<R>(f: impl FnOnce() -> R) -> (R, Stats) {
    assert!(ACTIVE.replace(Some(Stats::default())).is_none());
    let r = f();
    let x = ACTIVE.replace(None).unwrap();
    assert_eq!(x.live, 0, "no allocation may escape scoped comparison");
    (r, x)
}
