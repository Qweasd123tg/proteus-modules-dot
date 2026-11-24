#[cfg(test)]
mod m550_closer_alloc {
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
    fn plain_widget_utf8_tail_cost_and_tight_owner() {
        let plain = "🦀 Привет\r\n\u{2028}\0 ".repeat(45_000);
        let suffix = '&';
        let late_markup = format!("{plain}{suffix}");
        let url = "https://example.invalid/я?left=a&right=z";
        let green = format!("{url}\n{plain}");
        for (name, source, escaped) in [
            ("ordinary", plain.as_str(), plain.clone()),
            ("late_markup", late_markup.as_str(), format!("{plain}&amp;")),
            (
                "linked_prefix",
                green.as_str(),
                format!(
                    "<a href=\"https://example.invalid/я?left=a&amp;right=z\">https://example.invalid/я?left=a&amp;right=z</a>\n{plain}"
                ),
            ),
            ("empty", "", String::new()),
        ] {
            let (widget, cost) = measured(|| render("plain-view", source).unwrap());
            assert_eq!(widget["type"], "rich_text");
            assert_eq!(widget["id"], "plain-view");
            let Value::String(ref html) = widget["html"] else {
                panic!()
            };
            assert_eq!(
                html,
                &format!("<div style=\"white-space: pre-wrap\">{escaped}</div>")
            );
            assert_eq!(html.capacity(), html.len());
            println!("{name} {} {cost:?}", html.len());
        }
    }
}
