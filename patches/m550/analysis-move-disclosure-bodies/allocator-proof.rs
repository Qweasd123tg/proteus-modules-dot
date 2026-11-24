#[cfg(test)]
mod m550_model_step_alloc {
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
    fn actual_model_step_preserves_assembled_disclosures() {
        let instructions = "Инструкция 🦀 & \"quoted\"\t\r\n".repeat(32_000);
        let question = "Запрос 🧪 \u{2028}\0\r\n".repeat(38_000);
        let answer = "Ответ 🦀 \r\n \"literal\"".repeat(36_000);
        let message =
            |role, text| json!({"role": role, "parts":[{"payload":{"Text":{"text":text}}}]});
        let step = json!({"sequence":9, "started_at_ms":1,"finished_at_ms":123,
            "data":{"kind":"model", "exchange_id":"x", "request":{
                "model":{"model":"fixture"},
                "instructions":[{"kind":"developer","priority":11,"text":instructions}],
                "messages":[message("User",&question)], "tools":[{"name":"one"},{"name":null}]},
                "response":{"messages":[message("Assistant",&answer)],"finish_reason":"Stop"}}});
        METER.with(|m| assert!(m.replace(Some(Requests::default())).is_none()));
        let root = black_box(details::step_card(black_box(&step), &Open));
        let stats = METER.with(|m| m.replace(None).unwrap());
        let exact_instructions = format!("[developer · приоритет 11]\n{instructions}");
        for (key, body) in [
            ("9:instructions", exact_instructions.as_str()),
            ("9:message-0", question.trim()),
            ("9:tools", "one\nNone"),
            ("9:answer", answer.as_str()),
        ] {
            let entry = root
                .list("children")
                .iter()
                .find(|ch| ch.str("id") == key)
                .unwrap();
            let Value::String(text) = &entry["children"][0]["text"] else {
                panic!()
            };
            assert_eq!(text.as_str(), body);
            assert_eq!(text.capacity(), text.len());
            assert_eq!(entry["open"], Open.is(key));
            assert_eq!(entry["children"][0]["wrap"], true);
        }
        let raw = root
            .list("children")
            .iter()
            .find(|ch| ch.str("id") == "9:raw")
            .unwrap();
        assert_eq!(raw["children"][0]["language"], "json");
        assert_eq!(
            raw["children"][0]["text"],
            serde_json::to_string_pretty(&step).unwrap()
        );
        println!(
            "step {} {stats:?}",
            exact_instructions.len() + question.trim().len() + "one\nNone".len() + answer.len()
        );
    }
}
