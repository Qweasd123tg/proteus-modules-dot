#[cfg(test)]
mod m550_reference_alloc {
    use super::*;
    use std::{
        alloc::{GlobalAlloc, Layout, System},
        cell::Cell,
        hint::black_box,
    };

    #[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
    struct Requests {
        alloc: usize,
        realloc: usize,
        bytes: usize,
    }

    thread_local! {
        static METER: Cell<Option<Requests>> = const { Cell::new(None) };
    }

    fn count(size: usize, realloc: bool) {
        let _ = METER.try_with(|meter| {
            if let Some(mut r) = meter.get() {
                if realloc {
                    r.realloc += 1;
                } else {
                    r.alloc += 1;
                }
                r.bytes += size;
                meter.set(Some(r));
            }
        });
    }

    struct Meter;
    unsafe impl GlobalAlloc for Meter {
        unsafe fn alloc(&self, layout: Layout) -> *mut u8 {
            count(layout.size(), false);
            unsafe { System.alloc(layout) }
        }

        unsafe fn alloc_zeroed(&self, layout: Layout) -> *mut u8 {
            count(layout.size(), false);
            unsafe { System.alloc_zeroed(layout) }
        }

        unsafe fn realloc(&self, ptr: *mut u8, layout: Layout, size: usize) -> *mut u8 {
            count(size, true);
            unsafe { System.realloc(ptr, layout, size) }
        }

        unsafe fn dealloc(&self, ptr: *mut u8, layout: Layout) {
            unsafe { System.dealloc(ptr, layout) }
        }
    }

    #[global_allocator]
    static ALLOCATOR: Meter = Meter;

    fn measured(f: impl FnOnce() -> Value) -> (Value, Requests) {
        METER.with(|m| assert_eq!(m.replace(Some(Requests::default())), None));
        let v = black_box(f());
        (v, METER.with(|m| m.replace(None)).unwrap())
    }

    #[test]
    fn actual_parser_cold_warm_reference_table_and_release() {
        let languages = vec!["mermaid".to_owned()];
        let mut doc = Document::default();
        let mut prefix = String::new();
        for n in 0..600 {
            prefix.push_str(&format!(
                "[fixture-{n}]: https://test.invalid/path{n} \"{}\"",
                "🦀яяя Quoted / &amp; λ\t hi ".repeat(18)
            ));
            prefix.push('\n');
        }
        prefix.push_str("\n```mermaid\n A-->B\n```\n\n");
        let cold = format!("{prefix}plain first");
        let warm = format!("{prefix}plain tail");
        let changed =
            format!("{prefix}plain and [reference][tail]\n\n[tail]: https://test.invalid/delayed");
        let removed = "Other content [reference][tail]";
        let (first, cold_cost) = measured(|| doc.render(&cold, &languages).unwrap());
        assert!(doc.definitions.len() == 600);
        let referenced_bytes: usize = doc.definitions.iter().map(String::len).sum();
        assert!(referenced_bytes > 300_000);
        let identity_before: Vec<_> = doc.definitions.iter().map(|s| s.as_ptr()).collect();
        let (second, warm_cost) = measured(|| doc.render(&warm, &languages).unwrap());
        assert!(doc.parsed_bytes < 40);
        let identity_unchanged: Vec<_> = doc.definitions.iter().map(|s| s.as_ptr()).collect();
        let (third, changed_cost) = measured(|| doc.render(&changed, &languages).unwrap());
        assert_eq!(doc.definitions.len(), 601);
        let identity_changed: Vec<_> = doc.definitions[..600].iter().map(|s| s.as_ptr()).collect();
        assert!(third.to_string().contains("https://test.invalid/delayed"));
        assert!(second.to_string().contains("plain tail"));
        assert!(first.to_string().contains("plain first"));
        let remaining = doc.render(removed, &languages).unwrap();
        assert!(!remaining.to_string().contains("https://test.invalid"));
        assert!(doc.definitions.is_empty() && doc.definitions.capacity() == 0);
        let reused_unchanged = identity_before == identity_unchanged;
        let reused_changed = identity_unchanged == identity_changed;
        let expected = std::env::var("EXPECT_REFERENCE_MOVE").unwrap() == "yes";
        assert_eq!((reused_unchanged, reused_changed), (expected, expected));
        println!("cold {cold_cost:?}");
        println!("warm {warm_cost:?}");
        println!("changed {changed_cost:?}");
        println!(
            "reference bytes {referenced_bytes}; preserve same/changed buffers {reused_unchanged}/{reused_changed}"
        );
    }
}
