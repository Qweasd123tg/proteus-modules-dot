// Scratch-only entry point for paired provider-wire/allocator checks.
#[cfg(r60_probe)]
mod r60_probe {
    use crate::{
        domain::{ModelRef, ToolCall, ToolCallSurface, ToolResult},
        model_standard::{CanonicalMessage, CanonicalModelRequest, ContentPart, MessageRole},
    };
    use serde_json::json;
    use std::{
        alloc::{GlobalAlloc, Layout, System},
        sync::atomic::{AtomicBool, AtomicUsize, Ordering::Relaxed},
    };

    struct Meter;
    static ACTIVE: AtomicBool = AtomicBool::new(false);
    static REQUESTED: AtomicUsize = AtomicUsize::new(0);
    static CALLS: AtomicUsize = AtomicUsize::new(0);
    static LIVE: AtomicUsize = AtomicUsize::new(0);
    static PEAK: AtomicUsize = AtomicUsize::new(0);

    fn record(ptr: *mut u8, size: usize, old: usize) -> *mut u8 {
        if !ptr.is_null() {
            let now = if size >= old {
                LIVE.fetch_add(size - old, Relaxed) + (size - old)
            } else {
                LIVE.fetch_sub(old - size, Relaxed) - (old - size)
            };
            if ACTIVE.load(Relaxed) {
                CALLS.fetch_add(1, Relaxed);
                REQUESTED.fetch_add(size, Relaxed);
                PEAK.fetch_max(now, Relaxed);
            }
        }
        ptr
    }

    unsafe impl GlobalAlloc for Meter {
        unsafe fn alloc(&self, layout: Layout) -> *mut u8 {
            record(unsafe { System.alloc(layout) }, layout.size(), 0)
        }
        unsafe fn alloc_zeroed(&self, layout: Layout) -> *mut u8 {
            record(unsafe { System.alloc_zeroed(layout) }, layout.size(), 0)
        }
        unsafe fn realloc(&self, ptr: *mut u8, layout: Layout, size: usize) -> *mut u8 {
            record(
                unsafe { System.realloc(ptr, layout, size) },
                size,
                layout.size(),
            )
        }
        unsafe fn dealloc(&self, ptr: *mut u8, layout: Layout) {
            LIVE.fetch_sub(layout.size(), Relaxed);
            unsafe { System.dealloc(ptr, layout) }
        }
    }

    #[global_allocator]
    static GLOBAL: Meter = Meter;

    #[cfg(test)]
    #[test]
    #[ignore = "differential probe requires fixture environment"]
    fn allocation_case() {
        run()
    }

    fn raw_call(raw: String) -> ToolCall {
        ToolCall::new(
            "raw",
            "fixture_format",
            json!({"ignored":"raw takes priority"}),
        )
        .with_raw_arguments(raw)
    }

    fn decoded_call(text: String) -> ToolCall {
        ToolCall::new("json", "fixture_format", json!({"z":[1,false],"a":text}))
    }

    fn freeform_call(input: serde_json::Value) -> ToolCall {
        ToolCall::new("note", "fixture_note", json!({"input":input}))
            .with_surface(ToolCallSurface::Freeform)
    }

    pub(crate) fn run() {
        let fixture = std::env::var("R60_CASE").unwrap();
        let large = "aб🦀".repeat(20_000);
        let raw = " \n{ \"z\": \"привет\", \"a\": 1 }\t".to_owned();
        let plain = " keep this \nстрока 🦀 ".to_owned();
        let calls = match fixture.as_str() {
            "no-calls" => vec![],
            "raw-small" => vec![raw_call(raw)],
            "raw-large" => vec![raw_call(format!(" \n{{\"input\":\"{large}\"}}\t"))],
            "raw-malformed" => vec![raw_call("{not JSON 🦀\n".into())],
            "decoded-small" => vec![decoded_call(plain)],
            "decoded-large" => vec![decoded_call(large)],
            "freeform-small" => vec![freeform_call(plain.into())],
            "freeform-large" => vec![freeform_call(large.into())],
            "freeform-invalid" => vec![freeform_call(23.into())],
            "mixed-results" => vec![
                raw_call(raw),
                decoded_call(plain.clone()),
                freeform_call(plain.into()),
            ],
            _ => panic!("unknown fixture: {fixture}"),
        };
        let mut messages = vec![CanonicalMessage::text(MessageRole::User, "format a note")];
        for call in calls {
            let result =
                (fixture == "mixed-results").then(|| ToolResult::ok(call.id.clone(), "formatted"));
            messages.push(CanonicalMessage::new(
                MessageRole::Assistant,
                vec![ContentPart::ToolCall { call }],
            ));
            if let Some(result) = result {
                messages.push(CanonicalMessage::new(
                    MessageRole::Tool,
                    vec![ContentPart::ToolResult { result }],
                ));
            }
        }
        let request = CanonicalModelRequest::new(ModelRef::new("openai", "fixture"), messages);
        let run = || match crate::adapters::openai::r60_render(&request) {
            Ok(body) => body.to_string(),
            Err(error) => format!("ERROR: {error}"),
        };
        drop(run());
        let start = LIVE.load(Relaxed);
        PEAK.store(start, Relaxed);
        ACTIVE.store(true, Relaxed);
        let wire = run();
        ACTIVE.store(false, Relaxed);
        let peak = PEAK.load(Relaxed) - start;
        std::fs::write(std::env::var_os("R60_WIRE").unwrap(), wire).unwrap();
        println!(
            "R60 {} {} {}",
            REQUESTED.load(Relaxed),
            CALLS.load(Relaxed),
            peak
        );
    }
}

#[cfg(all(r60_probe, not(test)))]
fn main() {
    r60_probe::run()
}
