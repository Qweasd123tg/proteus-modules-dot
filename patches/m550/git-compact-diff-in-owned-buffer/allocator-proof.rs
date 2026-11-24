
mod m550_git_alloc {
    use std::{
        alloc::{GlobalAlloc, Layout, System},
        cell::Cell,
    };

    #[derive(Clone, Copy, Default)]
    struct Stats {
        allocs: usize,
        newly_allocated: usize,
        reallocs: usize,
        reallocated: usize,
        live: isize,
        peak: isize,
    }

    thread_local! {
        static METER: Cell<Option<Stats>> = const { Cell::new(None) };
    }

    fn change(allocation: Option<usize>, reallocation: Option<usize>, delta: isize) {
        let _ = METER.try_with(|cell| {
            if let Some(mut m) = cell.get() {
                if let Some(size) = allocation {
                    m.allocs += 1;
                    m.newly_allocated += size;
                }
                if let Some(size) = reallocation {
                    m.reallocs += 1;
                    m.reallocated += size;
                }
                m.live += delta;
                m.peak = m.peak.max(m.live);
                cell.set(Some(m));
            }
        });
    }

    struct Meter;

    unsafe impl GlobalAlloc for Meter {
        unsafe fn alloc(&self, layout: Layout) -> *mut u8 {
            let result = unsafe { System.alloc(layout) };
            if !result.is_null() {
                change(Some(layout.size()), None, layout.size() as isize);
            }
            result
        }

        unsafe fn alloc_zeroed(&self, layout: Layout) -> *mut u8 {
            let result = unsafe { System.alloc_zeroed(layout) };
            if !result.is_null() {
                change(Some(layout.size()), None, layout.size() as isize);
            }
            result
        }

        unsafe fn realloc(&self, ptr: *mut u8, layout: Layout, size: usize) -> *mut u8 {
            let result = unsafe { System.realloc(ptr, layout, size) };
            if !result.is_null() {
                change(None, Some(size), size as isize - layout.size() as isize);
            }
            result
        }

        unsafe fn dealloc(&self, ptr: *mut u8, layout: Layout) {
            change(None, None, -(layout.size() as isize));
            unsafe { System.dealloc(ptr, layout) }
        }
    }

    #[global_allocator]
    static ALLOCATOR: Meter = Meter;

    pub(super) struct Sample {
        len: usize,
        capacity: usize,
    }

    pub(super) fn start(patch: &String) -> Sample {
        METER.with(|m| assert!(m.replace(Some(Stats::default())).is_none()));
        Sample {
            len: patch.len(),
            capacity: patch.capacity(),
        }
    }

    impl Drop for Sample {
        fn drop(&mut self) {
            let stats = METER.with(|m| m.replace(None).unwrap());
            eprintln!(
                "alloc {} {} {} {} {} {} {} {}",
                self.len, self.capacity, stats.allocs, stats.newly_allocated, stats.reallocs,
                stats.reallocated, stats.live, stats.peak
            );
        }
    }
}
