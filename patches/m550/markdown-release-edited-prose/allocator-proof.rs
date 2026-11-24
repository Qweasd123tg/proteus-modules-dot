#[cfg(test)]
mod m550_replaced_prose_alloc {
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

    fn measured(f: impl FnOnce() -> Value) -> (Value, Requests) {
        METER.with(|m| assert!(m.replace(Some(Requests::default())).is_none()));
        let node = black_box(f());
        let stats = METER.with(|m| m.replace(None).unwrap());
        (node, stats)
    }

    #[test]
    fn parse_replacement_keeps_live_neighbor_and_drops_obsolete_source() {
        fn assert_unique(doc: &Document) {
            let ids: std::collections::HashSet<_> = doc
                .segments
                .iter()
                .map(|segment| segment.id.as_str())
                .collect();
            assert_eq!(ids.len(), doc.segments.len());
        }

        let prose = "Plain Ж 🦀 line with UTF-8 ".repeat(41_000);
        let languages = ["mermaid".into()];
        let edited = format!("{prose} новинка");
        let mut doc = Document::default();
        {
            let first = doc.render(&prose, &languages).unwrap();
            assert_eq!(first["children"].as_array().unwrap().len(), 1);
        }
        let (new, stats) = measured(|| doc.render(&edited, &languages).unwrap());
        assert_eq!(doc.parsed_bytes, edited.len());
        assert_eq!(
            new,
            Document::default().render(&edited, &languages).unwrap()
        );
        assert!(
            new["children"][0]["html"]
                .as_str()
                .unwrap()
                .contains("новинка")
        );
        assert_unique(&doc);
        println!("plain_edit {} {stats:?}", prose.len());

        let prefix = "Перед блоком\r\n\r\n```mermaid\r\nflowchart LR\r\nA-->B\r\n```\r\n\r\n";
        let full = format!("{prefix}{prose}");
        let full_next = format!("{prefix}{edited}");
        let mut retained = Document::default();
        {
            let first = retained.render(&full, &languages).unwrap();
            assert_eq!(first["children"][1]["type"], "content");
        }
        let boundary = retained.prefix.bytes;
        let code = retained.segments[1].node["source"]
            .as_str()
            .unwrap()
            .as_ptr();
        let header = retained.segments[0].node["html"].as_str().unwrap().as_ptr();
        let (new, stats) = measured(|| retained.render(&full_next, &languages).unwrap());
        assert!(boundary > 0);
        assert_eq!(retained.parsed_bytes, full_next.len() - boundary);
        assert_eq!(
            retained.segments[1].node["source"]
                .as_str()
                .unwrap()
                .as_ptr(),
            code
        );
        assert_eq!(
            retained.segments[0].node["html"].as_str().unwrap().as_ptr(),
            header
        );
        assert_eq!(
            new,
            Document::default().render(&full_next, &languages).unwrap()
        );
        assert_unique(&retained);
        println!("fenced_edit {} {stats:?}", prose.len());

        retained.parsed_bytes = usize::MAX;
        let (identical, stats) = measured(|| retained.render(&full_next, &languages).unwrap());
        assert_eq!(identical, new);
        assert_eq!(
            retained.segments[0].node["html"].as_str().unwrap().as_ptr(),
            header
        );
        assert_eq!(
            retained.segments[1].node["source"]
                .as_str()
                .unwrap()
                .as_ptr(),
            code
        );
        assert_eq!(retained.parsed_bytes, full_next.len() - boundary);
        println!("fenced_unchanged {} {stats:?}", prose.len());

        // Edit the first fence payload in place. The old prefix is invalid,
        // but unchanged prose still has the same id/source and moves intact.
        let last = full_next.replace("A-->B", "A-->C");
        let (test, stats) = measured(|| retained.render(&last, &languages).unwrap());
        assert_eq!(test["children"][1]["source"], "flowchart LR\r\nA-->C\r\n");
        assert_eq!(
            retained.segments[0].node["html"].as_str().unwrap().as_ptr(),
            header
        );
        assert_eq!(retained.parsed_bytes, last.len());
        assert_unique(&retained);
        println!("prose_reuse {} {stats:?}", prose.len());
    }
}
