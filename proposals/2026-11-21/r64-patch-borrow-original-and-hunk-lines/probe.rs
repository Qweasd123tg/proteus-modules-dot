// Scratch-only text hunk and full patch fixture checks.
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

fn fixture(case: &str) -> (String, String) {
    let source_line = |i| format!("row-{i:04} readable project note {}", "аб".repeat(30));
    let (source, hunk) = match case {
        "small-lf" => (
            "header\nold\nkeep\n".into(),
            "@@\n-old\n+new 🦀\n keep\n".into(),
        ),
        "small-crlf" => (
            "header\r\nold\r\nkeep\r\n".into(),
            "@@\n-old\n+new 🦀\n keep\n".into(),
        ),
        "mixed-eol" => ("old\nkeep\r\n".into(), "@@\n-old\n+new 🦀\n".into()),
        "no-eol" => ("old".into(), "@@\n-old\n+new\n+second\n".into()),
        "empty-delete" => ("old\n".into(), "@@\n-old\n".into()),
        "many-lines" => {
            let lines = (0..6000).map(|i| source_line(i)).collect::<Vec<_>>();
            (
                lines.join("\n"),
                format!("@@\n-{}\n+replacement note\n", lines[2500]),
            )
        }
        "hunk-heavy" => {
            let mut patch = "@@\n".to_owned();
            let mut source = String::new();
            for i in 0..600 {
                let old = source_line(i);
                source.push_str(&old);
                source.push('\n');
                if i % 3 == 0 {
                    patch.push_str(&format!("-{old}\n+revised note {i}\n"));
                } else {
                    patch.push_str(&format!(" {old}\n"));
                }
            }
            (source, patch)
        }
        "mismatch" => ("old\nkeep\n".into(), "@@\n-missing\n+new\n".into()),
        "add-only-hunk" => ("old\nkeep\n".into(), "@@\n+new\n".into()),
        _ => panic!("unknown fixture"),
    };
    (
        source,
        format!("*** Begin Patch\n*** Update File: notes.txt\n{hunk}*** End Patch"),
    )
}

#[test]
#[ignore = "differential probe requires fixture environment"]
fn allocation_case() {
    let case = std::env::var("R64_CASE").unwrap();
    let (source, patch) = fixture(&case);
    let parsed = crate::parse_patch(&patch).unwrap();
    let [
        PatchOperation::Update {
            hunks,
            no_newline_at_eof,
            ..
        },
    ] = parsed.as_slice()
    else {
        panic!("expected single local notes update");
    };
    let run = || apply_hunks(&source, hunks, *no_newline_at_eof);
    drop(run());
    let start = LIVE.load(Relaxed);
    PEAK.store(start, Relaxed);
    ACTIVE.store(true, Relaxed);
    let result = run();
    ACTIVE.store(false, Relaxed);
    let peak = PEAK.load(Relaxed) - start;

    // Independently exercise the crate's complete local operation on a fixture.
    let dir = tempfile::tempdir().unwrap();
    let file = dir.path().join("notes.txt");
    std::fs::write(&file, &source).unwrap();
    let summary = crate::apply_patch(&patch, dir.path());
    let stored = std::fs::read_to_string(file).unwrap();
    match &result {
        Ok(updated) => {
            assert_eq!(&stored, updated);
            assert_eq!(summary.as_deref(), Ok("updated notes.txt"));
        }
        Err(error) => {
            assert_eq!(&stored, &source);
            assert_eq!(summary.as_ref().unwrap_err(), error);
        }
    }
    let wire = serde_json::to_vec(&(result, summary, stored)).unwrap();
    std::fs::write(std::env::var_os("R64_WIRE").unwrap(), wire).unwrap();
    println!(
        "R64 {} {} {}",
        REQUESTED.load(Relaxed),
        CALLS.load(Relaxed),
        peak
    );
}
