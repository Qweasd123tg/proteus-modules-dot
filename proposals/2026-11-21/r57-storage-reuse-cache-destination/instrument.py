#!/usr/bin/env python3
"""Only in disposable checkouts: count allocations within WriteCache execution."""
import argparse
from pathlib import Path

p = argparse.ArgumentParser(description=__doc__)
p.add_argument("checkout", type=Path)
root = p.parse_args().checkout
part = root/"components/session-storage-module/src/main.rs"
s = part.read_text()
old = "        self.0.execute(request)"
assert s.count(old) == 1 and "mod write_cache_alloc_probe" not in s
s = s.replace(old, "        write_cache_alloc_probe::execute(&self.0, request)")
part.write_text(s + '''
mod write_cache_alloc_probe {
    use super::*;
    use std::{alloc::{GlobalAlloc, Layout, System}, cell::Cell};

    struct Counter;
    #[global_allocator]
    static ALLOCATOR: Counter = Counter;
    thread_local! {
        static ACTIVE: Cell<Option<(u64, u64)>> = const { Cell::new(None) };
    }

    fn count(bytes: usize) {
        ACTIVE.with(|active| {
            if let Some((calls, requested)) = active.get() {
                active.set(Some((calls.wrapping_add(1), requested.wrapping_add(bytes as u64))));
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
        if !matches!(&request, SessionStorageRequest::WriteCache { .. }) {
            return storage.execute(request);
        }
        ACTIVE.set(Some((0, 0)));
        let response = storage.execute(request);
        let (calls, bytes) = ACTIVE.replace(None).unwrap();
        eprintln!("R57 {calls} {bytes}");
        response
    }
}
''')

p = root/"components/session-storage-module/src/main.rs"
text = p.read_text()
old = "fn main() {"
assert text.count(old)==1
p.write_text(text.replace(old,old+'\n    session_storage::r57_prepare_stock_mode();'))
p = root/"storage/session-storage/src/lib.rs"
s = p.read_text()
p.write_text(s+'''
// Instrumentation only; not in the candidate patch.
use std::sync::atomic::{AtomicBool, Ordering};
static R57_STOCK_PATH: AtomicBool = AtomicBool::new(false);
pub fn r57_prepare_stock_mode() {
    R57_STOCK_PATH.store(std::env::var_os("R57_STOCK_PATH").is_some(), Ordering::Relaxed);
}
''')
p = root/"storage/session-storage/src/service/cache.rs"
s = p.read_text()
old = '    evict(&dir, &destination)?;'
assert s.count(old)==1
p.write_text(s.replace(old,'''
        if crate::R57_STOCK_PATH.load(std::sync::atomic::Ordering::Relaxed) {
            drop(destination);
            evict(&dir, &path(&dir, &key))?;
        } else {
            evict(&dir, &destination)?;
        }'''.strip('\n')))
