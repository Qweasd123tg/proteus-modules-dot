#[cfg(test)]
mod m550_fence_ownership {
    use super::*;
    use std::{
        alloc::{GlobalAlloc, Layout, System},
        cell::Cell,
        hint::black_box,
    };

    #[derive(Clone, Copy, Debug, Default)]
    struct Requests {
        allocs: usize,
        bytes: usize,
        live: isize,
        peak: isize,
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

    #[test]
    fn closed_spans_share_exact_source_until_render_while_open_stays_owned() {
        let first = format!("{}\r\n", "Я🦀 \"&<>\0".repeat(60_000));
        let second = format!("{}\n", "🦀 Second body \t".repeat(48_000));
        let source = format!(
            "```MeRmAiD\r\n{first}```\r\n\n~~~RUST\n{second}~~~\n\n```text\r\nsmall open 🦀\r\n"
        );
        let languages = ["mermaid".to_owned()];
        METER.with(|m| assert!(m.replace(Some(Requests::default())).is_none()));
        let parsed = black_box(parse(black_box(&source), &languages));
        let stats = METER.with(|m| m.replace(None).unwrap());
        assert_eq!(parsed.blocks.len(), 3);
        assert!(parsed.blocks[0].claimed && parsed.blocks[0].closed);
        assert!(!parsed.blocks[1].claimed && parsed.blocks[1].closed);
        let expected = std::env::var("EXPECT_DIRECT_SOURCE").unwrap() == "yes";
        for (i, bytes) in [&first, &second].into_iter().enumerate() {
            let fence = &parsed.blocks[i];
            assert_eq!(fence.code, bytes.as_str());
            assert_eq!(fence.ordinal, i);
            let stage = source.find(bytes).unwrap();
            assert_eq!(fence.code.as_ptr() == source[stage..].as_ptr(), expected);
        }
        let open = &parsed.blocks[2];
        assert!(!open.closed && !open.claimed);
        assert_eq!(open.code, "small open 🦀");
        let start = source.find("small open").unwrap();
        assert_ne!(open.code.as_ptr(), source[start..].as_ptr());
        println!("parsed {} {stats:?}", first.len() + second.len());
    }
}
