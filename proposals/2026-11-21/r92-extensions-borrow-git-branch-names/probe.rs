// Test-only diagnostic included under the package's private model tests.
use crate::Git;
use proteus_extension::{Host, Value, json};
use std::alloc::{GlobalAlloc, Layout, System};
use std::cell::Cell;
use std::hint::black_box;

#[derive(Clone, Copy, Default)]
struct Counters {
    blocks: isize,
    live: isize,
    calls: usize,
    requested: usize,
}

thread_local! {
    static METER: Cell<Counters> = const { Cell::new(Counters { blocks:0, live:0, calls:0, requested:0 }) };
}

fn adjust(blocks: isize, bytes: isize, request: Option<usize>) {
    let _ = METER.try_with(|meter| {
        let mut state = meter.get();
        state.blocks += blocks;
        state.live += bytes;
        if let Some(requested) = request {
            state.calls += 1;
            state.requested += requested;
        }
        meter.set(state);
    });
}

struct Allocations;
unsafe impl GlobalAlloc for Allocations {
    unsafe fn alloc(&self, layout: Layout) -> *mut u8 {
        let ptr = unsafe { System.alloc(layout) };
        if !ptr.is_null() {
            adjust(1, layout.size() as isize, Some(layout.size()));
        }
        ptr
    }

    unsafe fn alloc_zeroed(&self, layout: Layout) -> *mut u8 {
        let ptr = unsafe { System.alloc_zeroed(layout) };
        if !ptr.is_null() {
            adjust(1, layout.size() as isize, Some(layout.size()));
        }
        ptr
    }

    unsafe fn dealloc(&self, ptr: *mut u8, layout: Layout) {
        unsafe { System.dealloc(ptr, layout) };
        adjust(-1, -(layout.size() as isize), None);
    }

    unsafe fn realloc(&self, ptr: *mut u8, old: Layout, size: usize) -> *mut u8 {
        let ptr = unsafe { System.realloc(ptr, old, size) };
        if !ptr.is_null() {
            adjust(0,size as isize - old.size() as isize,Some(size));
        }
        ptr
    }
}

#[global_allocator]
static GLOBAL: Allocations = Allocations;

fn state() -> Counters {
    METER.with(Cell::get)
}

fn fixture(count: usize) -> String {
    let rows: Vec<Value>=(0..count).map(|i| {
        let name=format!("feature/fixture-{i:04}");
        let summary=format!("Summary {i:04}{:x<84}","");
        assert_eq!(name.len(),20);
        assert_eq!(summary.len(),96);
        json!({"name":name,"upstream":format!("origin/{name}"),"last_commit_time":1803978000,
               "last_commit_summary":summary,"author":"Synthetic Author"})
    }).collect();
    json!({"current":"other-header","branches":rows,"truncated":false}).to_string()
}

fn report(count: usize) {
    let host = Host::default();
    let before_git=state();
    let mut git = Git::default();
    let base=state();
    let parsed: Value=serde_json::from_str(&fixture(count)).unwrap();
    let ptr=parsed["branches"].get(0).and_then(|row| row["name"].as_str()).map(str::as_ptr);
    let cold0=state();
    load_catalogue(&mut git,black_box(parsed));
    let retained=state();
    let (len,capacity,slot,stored_first)=stored(&git);
    let moved=usize::from(ptr.is_some() && ptr==stored_first);
    assert_eq!(len,count);
    let warm0=state();
    let names=black_box(git.branch_list(&host).unwrap());
    let warm=state();
    assert_eq!(names.len(),count);
    let returned_first=access_first(&names);
    let borrowed=usize::from(stored_first.is_some() && stored_first==returned_first);
    std::hint::black_box(&names);
    release_returned(names);
    let after_return=state();
    assert_eq!((retained.live,retained.blocks),(after_return.live,after_return.blocks));
    git.invalidate_refs();
    assert!(git.branches.is_none());
    assert_eq!((state().live,state().blocks),(base.live,base.blocks));
    drop(git);
    assert_eq!((state().live,state().blocks),(before_git.live,before_git.blocks));
    println!("\nbranch {count} {capacity} {slot} {} {} {moved} {borrowed} {} {} {} {}",
        retained.blocks-base.blocks,retained.live-base.live,
        retained.calls-cold0.calls,retained.requested-cold0.requested,
        warm.calls-warm0.calls,warm.requested-warm0.requested);
}

#[test]
fn measure_branch_catalogue_owned_and_warm_boundaries() {
    for count in [0,8,64,1000] {
        report(count);
    }
}
