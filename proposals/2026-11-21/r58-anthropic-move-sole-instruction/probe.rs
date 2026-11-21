// Scratch-only public entry point for paired provider-wire/allocator checks.
#[cfg(r58_probe)]
mod r58_probe {
    use crate::{
        domain::{CacheHints, ModelRef},
        model_standard::{CanonicalMessage, CanonicalModelRequest, InstructionBlock, InstructionKind, MessageRole},
    };
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
            record(unsafe { System.realloc(ptr, layout, size) }, size, layout.size())
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

    pub(crate) fn run() {
        let fixture = std::env::var("R58_CASE").unwrap();
        let cache = std::env::var_os("R58_CACHE").is_some();
        let part = |text: String, p| InstructionBlock::new(InstructionKind::Developer, text, p);
        let (instructions, legacy) = match fixture.as_str() {
            "canonical-small" => (vec![part(" Be precise 🦀 ".into(), 7)], vec![]),
            "canonical-large" => (vec![part("aб🦀".repeat(20_000), 7)], vec![]),
            "legacy-large" => (vec![], vec!["aб🦀".repeat(20_000)]),
            "both-small" => (
                vec![part("low".into(), 1), part(" high ".into(), 7), part(" tied\n".into(), 7)],
                vec!["".into(), " legacy \t".into(), "".into()],
            ),
            "both-large" => (
                vec![part("setup".repeat(10_000), 7)],
                vec!["aб🦀".repeat(14_000)],
            ),
            "all-empty" => (vec![part(" \u{2003}\n".into(), 7)], vec!["".into()]),
            "pair-empty-legacy" => (vec![part(" \u{2003}\n".into(), 7)], vec!["".into(), "".into()]),
            _ => panic!("unknown fixture: {fixture}"),
        };
        let mut messages = legacy.into_iter().map(|s| CanonicalMessage::text(MessageRole::System, s)).collect::<Vec<_>>();
        messages.push(CanonicalMessage::text(MessageRole::User, "question"));
        let request = CanonicalModelRequest::new(ModelRef::new("anthropic", "fixture"), messages)
            .with_instructions(instructions)
            .with_cache(CacheHints::new(cache, false));
        let run = || crate::adapters::anthropic::r58_render(&request).unwrap().to_string();
        drop(run());
        let start = LIVE.load(Relaxed);
        PEAK.store(start, Relaxed);
        ACTIVE.store(true, Relaxed);
        let wire = run();
        ACTIVE.store(false, Relaxed);
        let peak = PEAK.load(Relaxed) - start;
        std::fs::write(std::env::var_os("R58_WIRE").unwrap(), wire).unwrap();
        println!("R58 {} {} {}", REQUESTED.load(Relaxed), CALLS.load(Relaxed), peak);
    }
}

#[cfg(all(r58_probe, not(test)))]
fn main() {
    r58_probe::run()
}
