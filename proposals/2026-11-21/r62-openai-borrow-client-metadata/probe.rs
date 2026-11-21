// Scratch-only request renderer fixtures for metadata merge and allocator checks.
#[cfg(r62_probe)]
mod r62_probe {
    use crate::{
        domain::ModelRef,
        model_standard::{CanonicalMessage, CanonicalModelRequest, MessageRole},
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

    fn group(prefix: &str, n: usize, value: &str) -> std::collections::BTreeMap<String, String> {
        (0..n)
            .map(|i| (format!("{prefix}_{i:02}"), value.into()))
            .collect()
    }

    pub(crate) fn run() {
        let case = std::env::var("R62_CASE").unwrap();
        let small_profile = || {
            std::collections::BTreeMap::from([
                ("session_id".into(), "configured".into()),
                ("z_provider".into(), "профиль".into()),
            ])
        };
        let small_request = || {
            std::collections::BTreeMap::from([
                ("session_id".into(), String::new()),
                ("a_request".into(), "запрос 🦀".into()),
            ])
        };
        let profile_value = "п🦀".repeat(40);
        let request_value = "р🦀".repeat(40);
        let (configured, requested) = match case.as_str() {
            "empty" => (group("", 0, ""), group("", 0, "")),
            "profile-small" => (small_profile(), group("", 0, "")),
            "request-small" => (group("", 0, ""), small_request()),
            "merged-small" => (small_profile(), small_request()),
            "profile-rich" => (group("profile", 12, &profile_value), group("", 0, "")),
            "request-rich" => (group("", 0, ""), group("req", 12, &request_value)),
            "merged-rich" => {
                let mut profile = group("profile", 6, &profile_value);
                profile.extend(group("shared", 2, &profile_value));
                let mut request = group("req", 6, &request_value);
                request.extend(group("shared", 2, &request_value));
                (profile, request)
            }
            "overlap-all" => (
                group("shared", 8, &profile_value),
                group("shared", 8, "new"),
            ),
            _ => panic!("unknown fixture: {case}"),
        };
        let render = crate::adapters::openai::r62_prepare_renderer(&json!({
            "client_metadata":configured,
        }))
        .unwrap();
        let request = CanonicalModelRequest::new(
            ModelRef::new("openai", "fixture"),
            vec![CanonicalMessage::text(MessageRole::User, "format a note")],
        )
        .with_client_metadata(requested);
        let run = || render(&request).unwrap().to_string();
        drop(run());
        let start = LIVE.load(Relaxed);
        PEAK.store(start, Relaxed);
        ACTIVE.store(true, Relaxed);
        let wire = run();
        ACTIVE.store(false, Relaxed);
        let peak = PEAK.load(Relaxed) - start;
        std::fs::write(std::env::var_os("R62_WIRE").unwrap(), wire).unwrap();
        println!(
            "R62 {} {} {}",
            REQUESTED.load(Relaxed),
            CALLS.load(Relaxed),
            peak
        );
    }
}

#[cfg(all(r62_probe, not(test)))]
fn main() {
    r62_probe::run()
}
