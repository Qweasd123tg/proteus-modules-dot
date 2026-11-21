// Compiled as an example in the exact locked proteus-tabs crate, without GPUI.
use proteus_tabs::{PaneId, TabLayout};
use serde_json::{Value, json};
use std::alloc::{GlobalAlloc, Layout, System};
use std::hint::black_box;
use std::sync::atomic::{AtomicUsize, Ordering::Relaxed};

struct Counting;
static CALLS: AtomicUsize = AtomicUsize::new(0);
static BYTES: AtomicUsize = AtomicUsize::new(0);

unsafe impl GlobalAlloc for Counting {
    unsafe fn alloc(&self, l: Layout) -> *mut u8 {
        CALLS.fetch_add(1, Relaxed);
        BYTES.fetch_add(l.size(), Relaxed);
        unsafe { System.alloc(l) }
    }
    unsafe fn alloc_zeroed(&self, l: Layout) -> *mut u8 {
        CALLS.fetch_add(1, Relaxed);
        BYTES.fetch_add(l.size(), Relaxed);
        unsafe { System.alloc_zeroed(l) }
    }
    unsafe fn realloc(&self, p: *mut u8, l: Layout, size: usize) -> *mut u8 {
        CALLS.fetch_add(1, Relaxed);
        BYTES.fetch_add(size, Relaxed);
        unsafe { System.realloc(p, l, size) }
    }
    unsafe fn dealloc(&self, p: *mut u8, l: Layout) {
        unsafe { System.dealloc(p, l) }
    }
}
#[global_allocator]
static ALLOC: Counting = Counting;

fn node(first: u32, count: u32, row: bool) -> Value {
    if count == 1 {
        let pinned = format!("file:pinned-{first}");
        let unpinned = format!("file:open-{first}");
        return json!({"pane": {"id":first,"tabs":[pinned,unpinned],"active":unpinned,"pinned":1}});
    }
    let children = [first, first + count / 2]
        .map(|id| json!({"node": node(id, count/2, !row), "size":{"weight":1.0}}));
    json!({"split":{"axis": if row {"row"} else {"column"}, "children": children}})
}

fn main() {
    let arm = std::env::args().nth(1).unwrap();
    assert!(arm == "stock" || arm == "candidate");
    for count in [1, 4, 32] {
        let layout: TabLayout = serde_json::from_value(json!({
            "focused":0, "next_id":count, "root":node(0,count,true)
        }))
        .unwrap();
        layout.validate().unwrap();
        let ids: Vec<_> = (0..=count)
            .map(|id| {
                (
                    PaneId(id),
                    format!("file:pinned-{id}"),
                    format!("file:open-{id}"),
                )
            })
            .collect();

        let before = (CALLS.load(Relaxed), BYTES.load(Relaxed));
        for (id, pinned, open) in black_box(&ids) {
            let layout = black_box(&layout);
            let target = (id.0 < count).then_some(*id);
            assert_eq!(black_box(layout.pane(*id)).map(|p| p.id), target);
            assert_eq!(black_box(layout.active(*id)), target.map(|_| open.as_str()));
            assert_eq!(black_box(layout.pane_of(open)), target);
            assert_eq!(black_box(layout.contains(open)), target.is_some());
            assert_eq!(black_box(layout.is_pinned(pinned)), target.is_some());
            assert!(!black_box(layout.is_pinned(open)));
        }
        let calls = CALLS.load(Relaxed) - before.0;
        let bytes = BYTES.load(Relaxed) - before.1;
        println!(
            "{arm}: panes={count} lookups={} alloc_or_realloc={calls} requested_bytes={bytes}",
            ids.len() * 6
        );
        if arm == "stock" {
            assert!(calls >= ids.len() * 6 && bytes > 0);
        } else {
            assert_eq!((calls, bytes), (0, 0));
        }
    }
}
