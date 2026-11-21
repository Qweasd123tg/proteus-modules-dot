// Scratch-only fixtures used to render actual context chunks.
use super::*;
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

fn fixture(case: &str) -> Vec<SkillDocument> {
    use std::os::unix::ffi::OsStringExt;
    let count = match case {
        "empty" => 0,
        "plain" | "nonutf8-location" => 1,
        "mixed" => 4,
        "catalog" => 64,
        "escape-heavy" => 16,
        _ => panic!("unknown fixture: {case}"),
    };
    (0..count)
        .map(|i| {
            let name = format!("review-{i:02}");
            let path = if case == "nonutf8-location" {
                std::ffi::OsString::from_vec(b"fixture/bad-\xff & notes/SKILL.md".to_vec()).into()
            } else if case == "plain" {
                format!("fixture/{name}/SKILL.md").into()
            } else {
                format!("fixture/{name} & notes/SKILL.md").into()
            };
            let description = match case {
                "plain" | "nonutf8-location" => "Check formatting and tests".to_owned(),
                "mixed" => "\tCheck  <diff>\n&  \"тесты\"\u{2003}'🦀' &amp;\r\n".to_owned(),
                "catalog" => "Inspect project notes  & test\nformats 🦀\u{00a0}".repeat(7),
                "escape-heavy" => "& < > \" ' 🦀\t".repeat(60),
                _ => panic!("unknown fixture"),
            };
            SkillDocument {
                id: name.clone(),
                enabled: true,
                name,
                description,
                body: String::new(),
                path,
                source: discovery::SkillSource::Project,
            }
        })
        .collect()
}

#[test]
#[ignore = "differential probe requires fixture environment"]
fn allocation_case() {
    let case = std::env::var("R63_CASE").unwrap();
    let docs = fixture(&case);
    let run = || serde_json::to_string(&vec![available_skills_chunk(&docs)]).unwrap();
    drop(run());
    let start = LIVE.load(Relaxed);
    PEAK.store(start, Relaxed);
    ACTIVE.store(true, Relaxed);
    let result = run();
    ACTIVE.store(false, Relaxed);
    let peak = PEAK.load(Relaxed) - start;
    std::fs::write(std::env::var_os("R63_WIRE").unwrap(), result).unwrap();
    println!(
        "R63 {} {} {}",
        REQUESTED.load(Relaxed),
        CALLS.load(Relaxed),
        peak
    );
}
