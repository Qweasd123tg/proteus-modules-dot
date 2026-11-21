#!/usr/bin/env python3
"""Only in disposable checkouts. OpenDisplaySnapshot worker allocator accounting."""
from pathlib import Path
import sys

root=Path(sys.argv[1])
p=root/'components/session-storage-module/src/main.rs'
s=p.read_text()
old='        self.0.execute(request)'
assert s.count(old)==1
s=s.replace(old,'        allocator_probe::execute(&self.0, request)')
assert s.count('fn main() {')==1
s=s.replace('fn main() {','fn main() {\n    session_storage::r60_prepare_stock_mode();')
p.write_text(s+'''
mod allocator_probe {
    use super::*;
    use std::{alloc::{GlobalAlloc, Layout, System}, cell::Cell};

    struct Counter;
    #[global_allocator]
    static ALLOCATOR: Counter = Counter;
    thread_local! { static ACTIVE: Cell<Option<(u64,u64)>> = const { Cell::new(None) }; }

    fn count(bytes: usize) {
        ACTIVE.with(|active| {
            if let Some((calls, requested)) = active.get() {
                active.set(Some((calls + 1, requested + bytes as u64)));
            }
        });
    }
    unsafe impl GlobalAlloc for Counter {
        unsafe fn alloc(&self, layout: Layout) -> *mut u8 {
            count(layout.size());
            unsafe { System.alloc(layout) }
        }
        unsafe fn alloc_zeroed(&self, layout: Layout) -> *mut u8 {
            count(layout.size());
            unsafe { System.alloc_zeroed(layout) }
        }
        unsafe fn realloc(&self, ptr: *mut u8, layout: Layout, size: usize) -> *mut u8 {
            count(size);
            unsafe { System.realloc(ptr, layout, size) }
        }
        unsafe fn dealloc(&self, ptr: *mut u8, layout: Layout) {
            unsafe { System.dealloc(ptr, layout) }
        }
    }
    pub fn execute(storage: &StorageService, request: SessionStorageRequest)
        -> Result<SessionStorageResponse>
    {
        if !matches!(&request, SessionStorageRequest::OpenDisplaySnapshot { .. }) {
            return storage.execute(request);
        }
        ACTIVE.set(Some((0, 0)));
        let response = storage.execute(request);
        let (calls, requested) = ACTIVE.replace(None).unwrap();
        eprintln!("R60 {calls} {requested}");
        response
    }
}
''')
r=root/'storage/session-storage/src'
p=r/'lib.rs'
s=p.read_text()
p.write_text(s+'''
// Local measurement only; actual candidate always takes the scratch path.
use std::sync::atomic::{AtomicBool, Ordering};
static R60_STOCK_PATH: AtomicBool = AtomicBool::new(false);
pub fn r60_prepare_stock_mode() {
    R60_STOCK_PATH.store(std::env::var_os("R60_STOCK_PATH").is_some(), Ordering::Relaxed);
}
''')
p=r/'service/display.rs'
s=p.read_text()
old='        while let Some(record) = source.next_with_scratch(&mut line)? {'
assert s.count(old)==1
p.write_text(s.replace(old,'''        while let Some(record) = if crate::R60_STOCK_PATH.load(std::sync::atomic::Ordering::Relaxed) {
            source.next()
        } else {
            source.next_with_scratch(&mut line)
        }? {'''))
