// Test-only diagnostic included under the package's private model tests.
use crate::Git;
use proteus_extension::{Host, Value, ValueExt, json};
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

const PAGE: usize = 100;

fn fixture(count: usize) -> Value {
    let entries: Vec<_> = (0..count).map(|i| {
        let hash = format!("{i:040x}");
        let parents = if i>0 && i%19==0 {
            vec![format!("{:040x}", i+1),format!("{:040x}", i+2)]
        } else if i==count-1 {
            vec![]
        } else {
            vec![format!("{:040x}",i+1)]
        };
        let refs = match i {
            0 => json!([{"name":"HEAD","kind":"head"},{"name":"main","kind":"branch"},
                        {"name":"origin/main","kind":"remote"}]),
            53 => json!([{"name":"v1.4.2","kind":"tag"}]),
            _ => json!([]),
        };
        json!({"hash":hash,"short":format!("{i:07x}"),"parents":parents,
            "summary":format!("Keep history page in order · исправить {i:04}"),
            "author":"Synthetic Author", "email":"author@example.invalid",
            "time":1700000000-86400*i,"refs":refs})
    }).collect();
    let text = json!({"head":"0000000","has_more":true,"entries":entries}).to_string();
    serde_json::from_str(&text).unwrap()
}

fn report(count: usize, slots: usize) {
    assert!((1..=2).contains(&slots));
    let host = Host::default();
    let before_git = state();
    let mut git = Git::default();
    let base = state();
    let mut cold_calls = 0;
    let mut cold_bytes = 0;
    let mut peak_additional_requests = 0;
    let mut borrowed = 0;
    let mut capacity = 0;
    let mut projected_buffers_moved = 0;
    let mut warm_calls = 0;
    let mut warm_bytes = 0;
    let mut slot_size = 0;
    for all in [false,true].into_iter().take(slots) {
        let parsed = fixture(count);
        let Some(items) = parsed["entries"].as_array() else { panic!("fixture"); };
        let owners = items.first().map(|row| (
            row.str("hash").as_ptr(),
            row["parents"].as_array().unwrap().as_ptr(),
            row["refs"].as_array().unwrap().as_ptr(),
        ));
        let cold0=state();
        let log=admit(black_box(parsed));
        let admitted=state();
        cold_calls+=admitted.calls-cold0.calls;
        cold_bytes+=admitted.requested-cold0.requested;
        // Upper bound on additional requested bytes while both representations are in scope.
        peak_additional_requests = peak_additional_requests.max(admitted.requested-cold0.requested);
        let (len,cap,slot,retained_owners)=storage(&log);
        assert_eq!(len,count);
        assert!(log.more);
        capacity+=cap;
        slot_size=slot;
        if let (Some(a),Some(b))=(owners,retained_owners) {
            projected_buffers_moved+=usize::from(a.0==b.0)+usize::from(count>1 && a.1==b.1)+usize::from(a.2==b.2);
        }
        *(if all { &mut git.graph } else { &mut git.log })=Some(log);
        let w0=state();
        let warm=warm_boundary(black_box(&mut git), &host, all);
        let w1=state();
        if count!=0 && retained_owners.map(|own| own.0)==warm {
            borrowed+=1;
        }
        warm_calls+=w1.calls-w0.calls;
        warm_bytes+=w1.requested-w0.requested;
        assert_eq!((w0.live,w0.blocks),(w1.live,w1.blocks));
    }
    let held=state();
    git.invalidate_refs();
    assert!(git.log.is_none() && git.graph.is_none());
    assert_eq!((state().live,state().blocks),(base.live,base.blocks));
    drop(git);
    assert_eq!((state().live,state().blocks),(before_git.live,before_git.blocks));

    println!("\nrows {count} {slots} {capacity} {slot_size} {} {} {projected_buffers_moved} {borrowed} \
              {cold_calls} {cold_bytes} {peak_additional_requests} {warm_calls} {warm_bytes}",
             held.blocks-base.blocks,held.live-base.live);
}

#[test]
fn measure_retained_log_cache() {
    for (count,slots) in [(0,1),(1,1),(PAGE,1),(PAGE,2)] {
        report(count,slots);
    }
}
