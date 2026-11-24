// Replay-only instrumentation for allocations >= 64 KiB on the native invocation thread.
// Logical Rust Layout bytes, not allocator overhead or process RSS.
use std::alloc::{GlobalAlloc, Layout, System};
use std::cell::Cell;
use crate::contracts::contracts::SessionStorageResponse;

const MIN: usize = 64 * 1024;
#[derive(Clone, Copy)]
struct Entry { ptr: usize, size: usize, generation: u64 }
const EMPTY: Entry = Entry { ptr: 0, size: 0, generation: 0 };

#[derive(Clone, Copy)]
struct Meter {
    track: bool, slots: [Entry; 32], next: u64,
    live: usize, peak: usize, requested: usize, events: usize, overflow: bool,
}
const INITIAL: Meter = Meter {
    track: false, slots: [EMPTY; 32], next: 0, live: 0, peak: 0,
    requested: 0, events: 0, overflow: false,
};
thread_local! { static STATE: Cell<Meter> = const { Cell::new(INITIAL) }; }
struct Allocator;
#[global_allocator]
static ALLOCATOR: Allocator = Allocator;

fn change(old: usize, new: usize, bytes: usize) {
    let _ = STATE.try_with(|cell| {
        let mut s = cell.get();
        if !s.track { return; }
        let idx = s.slots.iter().position(|e| e.ptr == old && old != 0);
        if let Some(index) = idx {
            s.live -= s.slots[index].size;
            s.slots[index] = EMPTY;
        }
        if new != 0 && bytes >= MIN {
            if let Some(entry) = s.slots.iter_mut().find(|e| e.ptr == 0) {
                s.next += 1;
                *entry = Entry { ptr: new, size: bytes, generation: s.next };
                s.live += bytes;
                s.peak = s.peak.max(s.live);
                s.requested += bytes;
                s.events += 1;
            } else { s.overflow = true; }
        }
        cell.set(s);
    });
}

unsafe impl GlobalAlloc for Allocator {
    unsafe fn alloc(&self, layout: Layout) -> *mut u8 {
        let out = unsafe { System.alloc(layout) };
        if layout.size() >= MIN && !out.is_null() { change(0, out as usize, layout.size()); }
        out
    }
    unsafe fn alloc_zeroed(&self, layout: Layout) -> *mut u8 {
        let out = unsafe { System.alloc_zeroed(layout) };
        if layout.size() >= MIN && !out.is_null() { change(0, out as usize, layout.size()); }
        out
    }
    unsafe fn realloc(&self, ptr: *mut u8, layout: Layout, size: usize) -> *mut u8 {
        let out = unsafe { System.realloc(ptr, layout, size) };
        if (layout.size() >= MIN || size >= MIN) && !out.is_null() {
            change(ptr as usize, out as usize, size);
        }
        out
    }
    unsafe fn dealloc(&self, ptr: *mut u8, layout: Layout) {
        if layout.size() >= MIN { change(ptr as usize, 0, 0); }
        unsafe { System.dealloc(ptr, layout) }
    }
}

pub(super) fn begin() {
    STATE.with(|s| s.set(Meter { track: true, ..INITIAL }));
}

pub(super) fn backend(response: &SessionStorageResponse) {
    if let SessionStorageResponse::BlobData { data_base64, .. } = response {
        line("backend", data_base64.as_ptr() as usize, data_base64.len(), data_base64.capacity());
        STATE.with(|cell| {
            let mut s = cell.get();
            if s.track {
                s.peak = s.live;
                s.requested = 0;
                s.events = 0;
                cell.set(s);
            }
        });
    }
}

pub(super) fn value(phase: &str, value: Option<&serde_json::Value>) {
    let string = value.and_then(|v| v.get("data_base64")).and_then(serde_json::Value::as_str);
    let (ptr, size) = string.map(|s| (s.as_ptr() as usize, s.len())).unwrap_or_default();
    line(phase, ptr, size, 0);
}

pub(super) fn line(phase: &str, ptr: usize, size: usize, capacity: usize) {
    STATE.with(|cell| {
        let s = cell.get();
        if !s.track { return; }
        let entry = s.slots.iter().find(|e| e.ptr == ptr && ptr != 0).copied().unwrap_or(EMPTY);
        // Suspend the meter to avoid charging the logging operation itself.
        cell.set(Meter { track: false, ..s });
        let thread = std::thread::current();
        eprintln!("R277M {} {} {} {} {} {} {} {} {} {} {}",
            thread.name().unwrap_or("-"), phase, size, capacity, entry.generation, entry.size,
            s.live, s.peak, s.requested, s.events, usize::from(s.overflow));
        cell.set(s);
    });
}
