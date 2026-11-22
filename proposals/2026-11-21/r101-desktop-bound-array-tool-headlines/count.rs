use std::alloc::{GlobalAlloc, Layout, System};
use std::cell::Cell;

#[derive(Clone, Copy, Debug, Default)]
pub struct Work {
    pub requests: usize,
    pub bytes: usize,
}

thread_local! {
    static WORK: Cell<Option<Work>> = const { Cell::new(None) };
}

pub fn start() {
    WORK.with(|count| assert!(count.replace(Some(Work::default())).is_none()));
}

pub fn stop() -> Work {
    WORK.with(|count| count.replace(None).expect("one scoped interval"))
}

fn note(size: usize) {
    let _ = WORK.try_with(|count| {
        if let Some(mut work) = count.get() {
            work.requests += 1;
            work.bytes += size;
            count.set(Some(work));
        }
    });
}

struct Counter;
unsafe impl GlobalAlloc for Counter {
    unsafe fn alloc(&self, layout: Layout) -> *mut u8 {
        note(layout.size());
        unsafe { System.alloc(layout) }
    }
    unsafe fn alloc_zeroed(&self, layout: Layout) -> *mut u8 {
        note(layout.size());
        unsafe { System.alloc_zeroed(layout) }
    }
    unsafe fn realloc(&self, ptr: *mut u8, layout: Layout, size: usize) -> *mut u8 {
        note(size);
        unsafe { System.realloc(ptr, layout, size) }
    }
    unsafe fn dealloc(&self, ptr: *mut u8, layout: Layout) {
        unsafe { System.dealloc(ptr, layout) }
    }
}
#[global_allocator]
static ALLOC: Counter = Counter;
