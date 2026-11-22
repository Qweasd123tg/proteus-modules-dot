// Included as a test-only child of the exact Files tree module.
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

fn listing(folder: &str, rows: usize, aliases: usize) -> Listing {
    // Both a normal name and a distinct alias are exactly 28 UTF-8 bytes.
    let entries: Vec<_> = (0..rows)
        .map(|i| {
            let basename = format!("f{i:024}.rs");
            let path = format!("{folder}/{basename}");
            let name = if i < aliases {
                format!("a{i:024}.rs")
            } else {
                basename
            };
            assert_eq!(name.len(), 28);
            json!({"name":name,"path":path,"kind":"file"})
        })
        .collect();
    Listing::parse(&json!({"entries":entries}))
}

fn scope(tag: &str, folders: usize, rows: usize, aliases: usize) {
    let baseline = sample();
    let mut project = Project::default();
    for i in 0..folders {
        let folder = format!("fixture-{i:02}");
        project
            .listing(&folder, &mut |path| Ok(listing(path, rows, aliases)))
            .unwrap();
    }
    assert_eq!(project.listings.len(), folders);
    // No JSON, Lines, Value widget tree, wire bytes, or folder temporaries are live.
    let mut name_blocks = 0;
    let mut name_bytes = 0;
    let mut path_bytes = 0;
    let mut vec_bytes = 0;
    for cached in project.listings.values() {
        let cached = cached.as_ref().unwrap();
        assert_eq!(cached.entries.len(), rows);
        vec_bytes += cached.entries.capacity() * size_of::<Entry>();
        for entry in &cached.entries {
            let (label, owned) = entry_name_stats(entry);
            assert_eq!(label.len(), 28);
            let path_label = entry.path.rsplit_once('/').unwrap().1;
            if label.as_bytes()[0] == b'f' {
                assert_eq!(label, path_label);
            } else {
                assert_ne!(label, path_label);
            }
            assert!(entry.path.is_ascii());
            name_blocks += usize::from(owned != 0);
            name_bytes += owned;
            path_bytes += entry.path.capacity();
        }
    }
    std::hint::black_box(&project);
    let (blocks, bytes) = difference(sample(), baseline);
    project.invalidate(true);
    assert!(project.listings.is_empty());
    let (warm_blocks, warm_bytes) = difference(sample(), baseline);
    drop(project);
    assert_eq!(sample(), baseline);
    println!(
        "\nbacking {tag} {folders} {rows} {aliases} {} {name_blocks} {name_bytes} {path_bytes} {vec_bytes} {blocks} {bytes} {warm_blocks} {warm_bytes}",
        size_of::<Entry>()
    );
}

#[test]
fn measure_project_listing_backing() {
    scope("empty", 1, 0, 0);
    scope("ordinary-1", 1, 1000, 0);
    scope("ordinary-8", 8, 1000, 0);
    scope("ordinary-64", 64, 1000, 0);
    scope("mixed-1pct", 1, 1000, 10);
    scope("all-alias", 1, 1000, 1000);
}
