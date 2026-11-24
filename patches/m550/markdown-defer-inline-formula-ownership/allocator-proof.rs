mod m550_inline_alloc {
    use std::{
        alloc::{GlobalAlloc, Layout, System},
        cell::Cell,
    };

    #[derive(Clone, Copy, Debug, Default)]
    struct Requests {
        allocs: usize,
        bytes: usize,
        live: isize,
        peak: isize,
        expansion: Option<(isize, isize)>,
    }

    thread_local! {
        static METER: Cell<Option<Requests>> = const { Cell::new(None) };
    }

    fn change(request: Option<usize>, delta: isize) {
        let _ = METER.try_with(|cell| {
            if let Some(mut r) = cell.get() {
                if let Some(bytes) = request {
                    r.allocs += 1;
                    r.bytes += bytes;
                }
                r.live += delta;
                r.peak = r.peak.max(r.live);
                if let Some((_, peak)) = &mut r.expansion {
                    *peak = (*peak).max(r.live);
                }
                cell.set(Some(r));
            }
        });
    }

    struct Meter;

    unsafe impl GlobalAlloc for Meter {
        unsafe fn alloc(&self, layout: Layout) -> *mut u8 {
            let result = unsafe { System.alloc(layout) };
            if !result.is_null() {
                change(Some(layout.size()), layout.size() as isize);
            }
            result
        }

        unsafe fn alloc_zeroed(&self, layout: Layout) -> *mut u8 {
            let result = unsafe { System.alloc_zeroed(layout) };
            if !result.is_null() {
                change(Some(layout.size()), layout.size() as isize);
            }
            result
        }

        unsafe fn realloc(&self, ptr: *mut u8, layout: Layout, size: usize) -> *mut u8 {
            let result = unsafe { System.realloc(ptr, layout, size) };
            if !result.is_null() {
                change(Some(size), size as isize - layout.size() as isize);
            }
            result
        }

        unsafe fn dealloc(&self, ptr: *mut u8, layout: Layout) {
            change(None, -(layout.size() as isize));
            unsafe { System.dealloc(ptr, layout) }
        }
    }

    #[global_allocator]
    static ALLOCATOR: Meter = Meter;


    pub(super) struct RenderMeter;

    pub(super) fn start() -> RenderMeter {
        METER.with(|m| assert!(m.replace(Some(Requests::default())).is_none()));
        RenderMeter
    }



    pub(super) fn expand() {
        METER.with(|m| {
            let mut stats = m.get().expect("inside native render");
            assert!(stats.expansion.is_none());
            stats.expansion = Some((stats.live, stats.live));
            m.set(Some(stats));
        });
    }

    impl Drop for RenderMeter {
        fn drop(&mut self) {
            let stats = METER.with(|m| m.replace(None).expect("exactly one active render"));
            let (enter, peak) = stats.expansion.unwrap_or((-1,-1));
            eprintln!("alloc {} {} {} {} {} {}", stats.allocs, stats.bytes, stats.live,
                      stats.peak, enter, peak);
        }
    }
}
