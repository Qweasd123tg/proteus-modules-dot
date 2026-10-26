//! Process-wide requested allocation counters, not an RSS or clone-only profiler.
//! Counters include Tokio and other allocations within each measured call interval.
use std::alloc::{GlobalAlloc, Layout, System};
use std::sync::atomic::{AtomicU64, Ordering};

use serde::Serialize;

pub struct CountingAllocator;
static ALLOCATIONS: AtomicU64 = AtomicU64::new(0);
static ALLOCATED: AtomicU64 = AtomicU64::new(0);
static DEALLOCATIONS: AtomicU64 = AtomicU64::new(0);
static DEALLOCATED: AtomicU64 = AtomicU64::new(0);

unsafe impl GlobalAlloc for CountingAllocator {
    unsafe fn alloc(&self, layout: Layout) -> *mut u8 {
        // SAFETY: forward the identical layout to the system allocator.
        let pointer = unsafe { System.alloc(layout) };
        if !pointer.is_null() {
            ALLOCATIONS.fetch_add(1, Ordering::Relaxed);
            ALLOCATED.fetch_add(layout.size() as u64, Ordering::Relaxed);
        }
        pointer
    }
    unsafe fn alloc_zeroed(&self, layout: Layout) -> *mut u8 {
        // SAFETY: forward the identical layout to the system allocator.
        let pointer = unsafe { System.alloc_zeroed(layout) };
        if !pointer.is_null() {
            ALLOCATIONS.fetch_add(1, Ordering::Relaxed);
            ALLOCATED.fetch_add(layout.size() as u64, Ordering::Relaxed);
        }
        pointer
    }
    unsafe fn dealloc(&self, pointer: *mut u8, layout: Layout) {
        DEALLOCATIONS.fetch_add(1, Ordering::Relaxed);
        DEALLOCATED.fetch_add(layout.size() as u64, Ordering::Relaxed);
        // SAFETY: GlobalAlloc's caller guarantees the pointer/layout pair.
        unsafe { System.dealloc(pointer, layout) };
    }
    unsafe fn realloc(&self, pointer: *mut u8, layout: Layout, new_size: usize) -> *mut u8 {
        // SAFETY: forward caller-provided pointer/layout/new size unchanged.
        let next = unsafe { System.realloc(pointer, layout, new_size) };
        if !next.is_null() {
            ALLOCATIONS.fetch_add(1, Ordering::Relaxed);
            ALLOCATED.fetch_add(new_size as u64, Ordering::Relaxed);
            DEALLOCATIONS.fetch_add(1, Ordering::Relaxed);
            DEALLOCATED.fetch_add(layout.size() as u64, Ordering::Relaxed);
        }
        next
    }
}

#[derive(Clone, Copy, Serialize)]
pub struct Counts {
    pub allocation_calls: u64,
    pub requested_bytes: u64,
    pub deallocation_calls: u64,
    pub released_bytes: u64,
}
impl Counts {
    pub fn read() -> Self {
        Self {
            allocation_calls: ALLOCATIONS.load(Ordering::Relaxed),
            requested_bytes: ALLOCATED.load(Ordering::Relaxed),
            deallocation_calls: DEALLOCATIONS.load(Ordering::Relaxed),
            released_bytes: DEALLOCATED.load(Ordering::Relaxed),
        }
    }
    pub fn since(self, before: Self) -> Self {
        Self {
            allocation_calls: self.allocation_calls - before.allocation_calls,
            requested_bytes: self.requested_bytes - before.requested_bytes,
            deallocation_calls: self.deallocation_calls - before.deallocation_calls,
            released_bytes: self.released_bytes - before.released_bytes,
        }
    }
}
