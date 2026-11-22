// Included as a test-only child of the exact Files Git snapshot module.
use super::*;
use proteus_extension::json;
use std::alloc::{GlobalAlloc, Layout, System};
use std::cell::Cell;
use std::mem::size_of;

thread_local! {
    static LIVE: Cell<(isize, isize)> = const { Cell::new((0, 0)) };
}

fn adjust(blocks: isize, bytes: isize) {
    let _ = LIVE.try_with(|meter| {
        let (old_blocks, old_bytes) = meter.get();
        meter.set((old_blocks + blocks, old_bytes + bytes));
    });
}

struct Meter;

unsafe impl GlobalAlloc for Meter {
    unsafe fn alloc(&self, layout: Layout) -> *mut u8 {
        let ptr = unsafe { System.alloc(layout) };
        if !ptr.is_null() {
            adjust(1, layout.size() as isize);
        }
        ptr
    }

    unsafe fn alloc_zeroed(&self, layout: Layout) -> *mut u8 {
        let ptr = unsafe { System.alloc_zeroed(layout) };
        if !ptr.is_null() {
            adjust(1, layout.size() as isize);
        }
        ptr
    }

    unsafe fn dealloc(&self, ptr: *mut u8, layout: Layout) {
        unsafe { System.dealloc(ptr, layout) };
        adjust(-1, -(layout.size() as isize));
    }

    unsafe fn realloc(&self, ptr: *mut u8, old: Layout, size: usize) -> *mut u8 {
        let ptr = unsafe { System.realloc(ptr, old, size) };
        if !ptr.is_null() {
            adjust(0, size as isize - old.size() as isize);
        }
        ptr
    }
}

#[global_allocator]
static GLOBAL: Meter = Meter;

fn sample() -> (isize, isize) {
    LIVE.with(Cell::get)
}

fn difference(
    (blocks, bytes): (isize, isize),
    (base_blocks, base_bytes): (isize, isize),
) -> (isize, isize) {
    (blocks - base_blocks, bytes - base_bytes)
}

const RAW: &[&str] = &["modified", "renamed", "deleted", "added", "untracked", "conflict"];

fn fixture(count: usize, mixed: bool) -> Value {
    let mut entries: Vec<_> = (0..count)
        .map(|i| {
            let branch = format!("b{:02}", i % 8);
            let file = format!("fixture_{i:04}.rs");
            json!({"path":format!("dir/{branch}/{file}"),"status":RAW[i % RAW.len()]})
        })
        .collect();
    if mixed {
        entries.extend([
            json!({"path":"dir/b00/fixture_0000.rs","status":"unknown"}),
            json!({"path":"dir/b01/fixture_0001.rs","status":true}),
            json!({"path":"dir/b02/fixture_0002.rs","status":""}),
            json!({"path":"dir/extra.rs"}),
            json!({"path":"../discard","status":"conflict"}),
        ]);
    }
    json!({"repository":true,"entries":entries})
}

fn report(tag: &str, count: usize, mixed: bool) {
    // Charge only the retained snapshot: the constructed JSON and all
    // temporary parse data are dropped before sampling.
    let base = sample();
    let mut snapshot = Git::parse(&fixture(count, mixed));
    assert_eq!(snapshot.files.len(), count + usize::from(mixed));
    let file_capacity = snapshot.files.capacity();
    let folder_count = snapshot.folders.len();
    let folder_capacity = snapshot.folders.capacity();
    let (labels, string_bytes, slot_size) = label_stats(&snapshot);
    std::hint::black_box(&snapshot);
    let (blocks, bytes) = difference(sample(), base);
    snapshot = Git::parse(&json!({"repository":false,"entries":[]}));
    assert!(snapshot.files.is_empty() && snapshot.folders.is_empty());
    std::hint::black_box(&snapshot);
    assert_eq!(sample(), base);
    drop(snapshot);
    assert_eq!(sample(), base);
    println!(
        "\nbacking {tag} {count} {} {file_capacity} {folder_count} {folder_capacity} {labels} {string_bytes} {slot_size} {blocks} {bytes}",
        count + usize::from(mixed)
    );
}

#[test]
fn measure_resident_git_snapshot_backing() {
    report("empty", 0, false);
    report("single", 1, false);
    report("ordinary-128", 128, false);
    report("cap-1000", 1000, false);
    report("mixed", 128, true);
}
