#[cfg(test)]
mod m550_invalidation_alloc {
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
    fn policy_and_reference_invalidation_keep_only_valid_previous_nodes() {
        let mermaid = ["mermaid".to_owned()];
        let mut doc = Document::default();
        let body = "я🦀 body & <\0 ".repeat(76_000);
        let source = format!("```mermaid\r\n{body}\r\n```\r\n\r\nХвост");
        {
            let first = doc.render(&source, &mermaid).unwrap();
            assert_eq!(first["children"][0]["type"], "content");
        }
        let (rerendered, stats) = measured(|| doc.render(&source, &[]).unwrap());
        assert_eq!(rerendered["children"][0]["type"], "code");
        assert_eq!(rerendered["children"][0]["text"], format!("{body}\r\n"));
        assert_eq!(
            rerendered.to_string(),
            Document::default()
                .render(&source, &[])
                .unwrap()
                .to_string()
        );
        println!("policy {} {stats:?}", body.len());

        let prefix = "[Ссылка][late]\n\n```mermaid\nА-->Б\n```\n";
        let tail = format!(
            "\n\nПозже [ссылка][late] {}\n\n",
            "Long line Я🦀 ".repeat(46_000)
        );
        let src = format!("{prefix}{tail}");
        let addition = format!("{src}[late]: https://example.invalid/цель");
        let mut refs = Document::default();
        {
            let first = refs.render(&src, &mermaid).unwrap();
            assert!(!first.to_string().contains("https://example.invalid"));
        }
        let closed_prefix = refs.prefix.bytes;
        let (updated, stats) = measured(|| refs.render(&addition, &mermaid).unwrap());
        assert!(closed_prefix > 0 && closed_prefix < addition.len());
        assert_eq!(refs.parsed_bytes, addition.len() - closed_prefix);
        assert!(updated.to_string().contains("https://example.invalid"));
        assert_eq!(
            updated.to_string(),
            Document::default()
                .render(&addition, &mermaid)
                .unwrap()
                .to_string()
        );
        println!("definitions {} {stats:?}", tail.len());

        // With unchanged scope, an edit to a fence invalidates the prefix hash
        // but still permits ordinary exact-source reuse of adjacent prose.
        let mut same = Document::default();
        let stable = "Одно и то же";
        let base = format!("{stable}\n\n```mermaid\n A-->B\n```\n\nПоследний абзац");
        same.render(&base, &mermaid).unwrap();
        let ptr = same.segments[0].node["html"].as_str().unwrap().as_ptr();
        let edit = base.replace("A-->B", "A-->C");
        let old_prefix = same.prefix.bytes;
        let (updated, stats) = measured(|| same.render(&edit, &mermaid).unwrap());
        assert!(old_prefix > 0);
        assert_eq!(same.parsed_bytes, edit.len());
        assert_eq!(
            same.segments[0].node["html"].as_str().unwrap().as_ptr(),
            ptr
        );
        assert_eq!(updated["children"][1]["source"], " A-->C\n");
        println!("reuse {} {stats:?}", edit.len());
    }
}
