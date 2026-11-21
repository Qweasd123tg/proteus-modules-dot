#![allow(dead_code)]

mod candidate;
mod stock;
use std::hint::black_box;

#[derive(Debug, PartialEq, Eq)]
struct Snapshot {
    live: Vec<u8>,
    selected: Option<u8>,
    pending: Option<u8>,
    presence: [bool; 4],
}

mod counter {
    use std::alloc::{GlobalAlloc, Layout, System};
    use std::sync::atomic::{AtomicUsize, Ordering::Relaxed};
    struct Counter;
    static CALLS: AtomicUsize = AtomicUsize::new(0);
    static BYTES: AtomicUsize = AtomicUsize::new(0);
    #[global_allocator]
    static A: Counter = Counter;
    unsafe impl GlobalAlloc for Counter {
        unsafe fn alloc(&self, layout: Layout) -> *mut u8 {
            CALLS.fetch_add(1, Relaxed);
            BYTES.fetch_add(layout.size(), Relaxed);
            unsafe { System.alloc(layout) }
        }
        unsafe fn dealloc(&self, p: *mut u8, layout: Layout) {
            unsafe { System.dealloc(p, layout) }
        }
        unsafe fn realloc(&self, p: *mut u8, layout: Layout, new: usize) -> *mut u8 {
            CALLS.fetch_add(1, Relaxed);
            BYTES.fetch_add(new, Relaxed);
            unsafe { System.realloc(p, layout, new) }
        }
    }
    pub fn read() -> (usize, usize) {
        (CALLS.load(Relaxed), BYTES.load(Relaxed))
    }
}

fn parity() {
    // Every ordered old and new list up to length three; repeated IDs are
    // intentional. Several IDs have the same string in different variants.
    let mut lists = Vec::new();
    for n in 0..=3 {
        for mut encoding in 0..6u32.pow(n) {
            let mut list = Vec::new();
            for _ in 0..n {
                list.push((encoding % 6) as u8);
                encoding /= 6;
            }
            lists.push(list);
        }
    }
    let mut cases = 0;
    for incoming in &lists {
        let seen_a: Vec<_> = incoming.iter().map(|&id| stock::probe_id(id)).collect();
        let seen_b: Vec<_> = incoming.iter().map(|&id| candidate::probe_id(id)).collect();
        for previous in &lists {
            for selected in (0..8).map(Some).chain([None]) {
                let mut old = stock::DockState::probe_from(previous, selected);
                let mut new = candidate::DockState::probe_from(previous, selected);
                old.probe_sync(&seen_a);
                new.probe_sync(&seen_b);
                assert_eq!(
                    old.probe_snapshot(),
                    new.probe_snapshot(),
                    "live {:?} rendered {:?} selected {:?}",
                    previous,
                    incoming,
                    selected,
                );
                cases += 1;
            }
        }
    }
    assert_eq!(cases, 603_729);
    println!("PASS {cases} dock transitions (live order, selection, keyboard target and presence)");
}

fn allocation<T>(arm: &str, name: &str, call: impl FnOnce() -> T) {
    let before = counter::read();
    let result = black_box(call());
    let after = counter::read();
    black_box(&result);
    println!(
        "alloc\t{arm}\t{name}\t{}\t{}",
        after.0 - before.0,
        after.1 - before.1
    );
}

fn allocations(arm: &str) {
    for (name, previous, incoming, selected) in [
        ("empty", &[][..], &[][..], None),
        ("same-extension", &[2][..], &[2][..], Some(2)),
        ("same-pending-folded", &[0, 1, 2][..], &[0, 1, 2][..], None),
        ("same-pending-open", &[0, 1, 2][..], &[0, 1, 2][..], Some(1)),
        ("reorder", &[0, 1, 2][..], &[1, 2, 0][..], Some(1)),
        ("fresh-approval", &[2][..], &[2, 0][..], Some(2)),
        ("stale-unchanged", &[0, 1, 2][..], &[0, 1, 2][..], Some(7)),
        ("request-completed", &[0, 1, 2][..], &[1, 2][..], Some(0)),
    ] {
        match arm {
            "stock" => {
                let args: Vec<_> = incoming.iter().map(|&id| stock::probe_id(id)).collect();
                let mut state = stock::DockState::probe_from(previous, selected);
                allocation(arm, name, || {
                    state.probe_sync(black_box(&args));
                    black_box(&state);
                });
            }
            "candidate" => {
                let args: Vec<_> = incoming.iter().map(|&id| candidate::probe_id(id)).collect();
                let mut state = candidate::DockState::probe_from(previous, selected);
                allocation(arm, name, || {
                    state.probe_sync(black_box(&args));
                    black_box(&state);
                });
            }
            _ => panic!("expected arm"),
        }
    }
}

fn main() {
    let arm = std::env::args().nth(1).expect("arm");
    if arm == "parity" {
        parity();
    } else {
        allocations(&arm);
    }
}
