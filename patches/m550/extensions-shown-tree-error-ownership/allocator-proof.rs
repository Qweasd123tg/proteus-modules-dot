#[cfg(test)]
mod m550_failed_alloc {
    use super::*;
    use std::{
        alloc::{GlobalAlloc, Layout, System},
        cell::Cell,
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

    fn measured(f: impl FnOnce()) -> Requests {
        METER.with(|m| assert_eq!(m.replace(Some(Requests::default())), None));
        f();
        METER.with(|m| m.replace(None)).unwrap()
    }

    #[test]
    fn first_repeat_null_and_content_errors_use_exact_ownership() {
        let mut host = Host::default();
        let view = "fixture 🦀";
        host.sequences.insert(view.to_owned(), 9);
        host.session = Some("/synthetic/one".into());

        // First failure has no prior child; an actual shown null does.
        host.failed(view, "first");
        assert_eq!(
            host.sent.borrow().last().unwrap()["root"]["children"]
                .as_array()
                .unwrap()
                .len(),
            1
        );
        host.show(view, Value::Null);
        host.failed(view, "shown null");
        let sent = host.sent.borrow();
        let children = sent.last().unwrap()["root"]["children"].as_array().unwrap();
        assert_eq!(children.len(), 2);
        assert_eq!(children[1], Value::Null);
        assert!(host.is_shown(view));
        drop(sent);

        let content = "Привет 🦀\0\r\n \"abc\" ".repeat(45_000);
        let bytes = content.len();
        host.show(view, ui::text(content));
        let source = host.shown[view]["text"].as_str().unwrap().as_ptr();
        host.sent.borrow_mut().clear();
        for (repeat, error) in ["Код: \"test\"\n", "Вторая ошибка 🦀"]
            .into_iter()
            .enumerate()
        {
            let cost = measured(|| host.failed(view, error));
            assert_eq!(host.shown[view]["text"].as_str().unwrap().as_ptr(), source);
            let sent = host.sent.borrow();
            let envelope = sent.last().unwrap();
            let children = envelope["root"]["children"].as_array().unwrap();
            assert_eq!(children.len(), 2);
            assert_eq!(children[0]["children"][0]["text"], error);
            assert_eq!(children[1], host.shown[view]);
            assert!(envelope.get("source_revision").is_none());
            assert_eq!(envelope["sequence"], 9);
            assert_eq!(envelope["session_dir"], "/synthetic/one");
            println!("fallback{repeat} {bytes} {cost:?}");
            drop(sent);
            host.sent.borrow_mut().clear();
        }

        host.views.insert(view.to_owned(), (Surface::Content, None));
        host.content.insert(
            view.to_owned(),
            Content {
                language: "fixture".into(),
                source: "body".into(),
                context: Value::Null,
                source_revision: Some(47),
            },
        );
        let cost = measured(|| host.failed(view, "Ошибка содержимого"));
        let sent = host.sent.borrow();
        let frame = sent.last().unwrap();
        assert_eq!(frame["type"], "content_error");
        assert_eq!(frame["source_revision"], 47);
        assert!(frame.get("root").is_none());
        assert_eq!(host.shown[view]["text"].as_str().unwrap().as_ptr(), source);
        println!("content {bytes} {cost:?}");
    }
}
