#[cfg(test)]
mod m550_layout_alloc {
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
    fn actual_analysis_page_moves_owned_details_until_the_root() {
        fn contains_code(node: &Value, text: &str) -> bool {
            (node["type"] == "code" && node["text"].as_str() == Some(text))
                || node.list("children").iter().any(|c| contains_code(c, text))
        }
        let bytes = "Ж🦀 & <\r\n'quoted'\0 ".repeat(56_000);
        let detail = "Инструмент 🦀\u{2029} & \r\n".repeat(23_000);
        let data = json!({
            "session_id":"synthetic","revision":84,
            "turns":[{"turn_id":"turn","number":4,"status":"success","prompt_preview":"before"}],
            "selected":{
                "turn_id":"turn","task":{"text":"Task"},"output":{"text":bytes},"steps":[{
                    "sequence":7,"started_at_ms":100,"finished_at_ms":133,
                    "data":{"kind":"tool","call":{"id":"test-call","name":"fixture","args":{"a":true}},
                            "result":{"output":detail,"call_id":"test-call","ok":true,"content":[]}}
                }],"module_epoch":5
            }
        });
        let mut analysis = Analysis::default();
        let picker = proteus_extension::ui::text("picker");
        METER.with(|m| assert!(m.replace(Some(Requests::default())).is_none()));
        let root = black_box(analysis.page(black_box(&data), picker));
        let stats = METER.with(|m| m.replace(None).unwrap());
        assert!(contains_code(&root, &bytes));
        assert!(contains_code(&root, &detail));
        let split = &root["children"][0];
        assert_eq!(split["widths"], json!([260, 320, null]));
        assert_eq!(split["children"].as_array().unwrap().len(), 3);
        assert_eq!(analysis.step, Some(7));
        println!("page {} {stats:?}", bytes.len() + detail.len());

        let child = proteus_extension::ui::text(bytes);
        let ptr = child["text"].as_str().unwrap().as_ptr();
        let owned_card = nodes::card("Title", vec![child]);
        let exact = std::env::var("EXPECT_MOVED_WIDGETS").unwrap() == "yes";
        assert_eq!(
            owned_card["children"][0]["text"].as_str().unwrap().as_ptr() == ptr,
            exact
        );
        let root = nodes::column(vec![nodes::row(vec![owned_card])]);
        let expected = &root["children"][0]["children"][0]["children"][0]["text"];
        if exact {
            assert_eq!(expected.as_str().unwrap().as_ptr(), ptr);
        }
        let before = analysis.page(&Value::Null, proteus_extension::ui::text("picker"));
        assert_eq!(before["type"], "stack");
        assert_eq!(before["children"].as_array().unwrap().len(), 5);
    }
}
