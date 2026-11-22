// Context cache decision instrumentation; never part of the product patch.
use super::*;

use std::alloc::{GlobalAlloc, Layout, System};
use std::cell::{Cell, RefCell};

thread_local! {
    static METER: Cell<Option<(usize, usize)>> = const { Cell::new(None) };
}

fn record(size: usize) {
    let _ = METER.try_with(|meter| {
        if let Some((calls, bytes)) = meter.get() {
            meter.set(Some((calls + 1, bytes + size)));
        }
    });
}

struct Allocations;

unsafe impl GlobalAlloc for Allocations {
    unsafe fn alloc(&self, layout: Layout) -> *mut u8 {
        let ptr = unsafe { System.alloc(layout) };
        if !ptr.is_null() {
            record(layout.size());
        }
        ptr
    }

    unsafe fn alloc_zeroed(&self, layout: Layout) -> *mut u8 {
        let ptr = unsafe { System.alloc_zeroed(layout) };
        if !ptr.is_null() {
            record(layout.size());
        }
        ptr
    }

    unsafe fn dealloc(&self, ptr: *mut u8, layout: Layout) {
        unsafe { System.dealloc(ptr, layout) };
    }

    unsafe fn realloc(&self, ptr: *mut u8, old: Layout, size: usize) -> *mut u8 {
        let ptr = unsafe { System.realloc(ptr, old, size) };
        if !ptr.is_null() {
            record(size);
        }
        ptr
    }
}

#[global_allocator]
static GLOBAL: Allocations = Allocations;

fn scope<T>(op: impl FnOnce() -> T) -> (T, usize, usize) {
    assert!(METER.replace(Some((0, 0))).is_none());
    let out = std::hint::black_box(op());
    let (calls, bytes) = METER.take().unwrap();
    (out, calls, bytes)
}

#[derive(Clone, Copy, Debug, Default)]
struct Work {
    clone_count: usize,
    clone_bytes: usize,
    serializations: usize,
    key_builds: usize,
    key_bytes: usize,
    hit: usize,
    miss: usize,
    absent: usize,
}

thread_local! {
    static WORK: Cell<Option<Work>> = const { Cell::new(None) };
    static SHOWN: Cell<Option<bool>> = const { Cell::new(None) };
    static MISS_KEY: RefCell<Option<String>> = const { RefCell::new(None) };
}

fn track(update: impl FnOnce(&mut Work)) -> bool {
    WORK.with(|meter| {
        if let Some(mut r) = meter.get() {
            update(&mut r);
            meter.set(Some(r));
            true
        } else {
            false
        }
    })
}

pub(super) fn cloned_session(session: Option<String>) -> Option<String> {
    if let Some(text) = &session {
        track(|r| {
            r.clone_count += 1;
            r.clone_bytes += text.len();
        });
    }
    session
}

pub(super) fn serialized() {
    track(|r| r.serializations += 1);
}

pub(super) fn key_built(key: String) -> String {
    track(|r| {
        r.key_builds += 1;
        r.key_bytes += key.len();
    });
    key
}

pub(super) fn shown(host: &Host, view: &str) -> bool {
    SHOWN.with(|state| state.get().unwrap_or_else(|| host.is_shown(view)))
}

pub(super) fn active() -> bool {
    WORK.with(|state| state.get().is_some())
}

pub(super) fn no_session() -> bool {
    track(|r| r.absent += 1)
}

pub(super) fn cache_miss(key: String) {
    track(|r| r.miss += 1);
    assert!(MISS_KEY.with(|state| state.replace(Some(key))).is_none());
}

pub(super) fn cache_hit() -> bool {
    track(|r| r.hit += 1)
}

fn usage() -> Value {
    json!({"used":64000,"max":128000,"trigger":100000})
}

#[test]
fn measure_actual_popup_decision() {
    println!(); // libtest's prefix must not absorb the first metric
    check_key_matrix();
    let short = "/plan-context/cur";
    let long = format!("/synthetic-context/{}🧪", "segment-".repeat(7));
    let canonical = usage();
    let a = json!({"context":canonical});
    let b = json!({"context":{"used":64001,"max":128000,"trigger":100000}});
    let present_missing = json!({"execution":{"active":null}});
    let old = canonical.to_string();
    for (label, session, state, old_suffix, shown, repeats, expected_pick) in [
        ("short-one", Some(short), Some(&a), Some(old.as_str()), true, 1, "hit"),
        ("short-dozen", Some(short), Some(&a), Some(old.as_str()), true, 12, "hit"),
        ("long-one", Some(long.as_str()), Some(&a), Some(old.as_str()), true, 1, "hit"),
        ("long-dozen", Some(long.as_str()), Some(&a), Some(old.as_str()), true, 12, "hit"),
        ("cold", Some(long.as_str()), Some(&a), None, false, 1, "miss"),
        ("stale", Some(long.as_str()), Some(&b), Some(old.as_str()), true, 1, "miss"),
        ("new-view", Some(long.as_str()), Some(&a), Some(old.as_str()), false, 1, "miss"),
        ("no-session", None, Some(&a), None, true, 1, "absent"),
        ("absent-state", Some(short), None, Some("null"), true, 1, "miss"),
        ("field-missing", Some(short), Some(&present_missing), Some("null"), true, 1, "hit"),
    ] {
        let mut host = Host::default();
        host.session = session.map(str::to_owned);
        host.state = state.cloned();
        let mut context = Context {
            snapshot: old_suffix.map(|suffix| (format!("{}\n{suffix}", session.unwrap()), Value::Null)),
        };
        let old_pointer = context.snapshot.as_ref().map(|(s, _)| (s.as_ptr(), s.capacity()));
        assert!(SHOWN.replace(Some(shown)).is_none());
        assert!(WORK.replace(Some(Work::default())).is_none());
        let (last, allocs, requested) = scope(|| {
            let mut output = Value::Null;
            for _ in 0..repeats {
                output = std::hint::black_box(context.popup(&mut host, "probe")).unwrap();
            }
            output
        });
        assert_eq!(last, Value::Null);
        let read = WORK.take().unwrap();
        SHOWN.take();
        let fetch = MISS_KEY.with(|r| r.take());
        let current = context.snapshot.as_ref().map(|(s, _)| (s.as_ptr(), s.capacity()));
        assert_eq!(current, old_pointer, "lookup-only measurement changed retained key");

        let outcome = if read.absent > 0 { "absent" } else if read.miss > 0 { "miss" } else { "hit" };
        assert_eq!(outcome, expected_pick);
        let exact_new = session.map(|id| {
            let suffix = state.map(|v| v.at("context").to_string()).unwrap_or_default();
            format!("{id}\n{suffix}")
        });
        if outcome == "miss" {
            assert_eq!(fetch.as_deref(), exact_new.as_deref());
        } else {
            assert!(fetch.is_none());
        }
        let n = session.map(str::len).unwrap_or_default();
        let bytes = exact_new.as_ref().map(String::len).unwrap_or_default();
        let newcap = fetch.as_ref().map(String::capacity).unwrap_or_default();
        let oldcap = old_pointer.map(|(_, cap)| cap).unwrap_or_default();
        println!(
            "ops {label} {repeats} {n} {bytes} {} {} {} {} {} {} {} {} {newcap} {oldcap} {allocs} {requested}",
            read.clone_count, read.clone_bytes, read.serializations, read.key_builds, read.key_bytes,
            read.hit, read.miss, read.absent
        );
        println!("shape {label} {}", json!({"outcome":outcome,"fetched":fetch,
            "retained":context.snapshot.as_ref().map(|(key,_)| key)}));
    }
}

fn check_key_matrix() {
    let sessions = ["", "/same", "/same/longer", "сессия 🦀", "line\nbreak", "line"];
    let states = [
        None,
        Some(json!({})),
        Some(json!({"context":null})),
        Some(json!({"context":{"used":1,"max":128000,"trigger":null}})),
        Some(json!({"context":{"max":128000,"used":1,"trigger":null}})),
        Some(json!({"context":{"used":1.0,"max":128000,"trigger":null}})),
        Some(json!({"context":[1,{"nest":"скобки \n🦀"}]})),
        Some(json!({"context":"literal\nLF"})),
    ];
    let encodings = states.map(|state: Option<Value>| {
        state
            .as_ref()
            .map(|state| state.at("context").to_string())
            .unwrap_or_default()
    });
    assert_eq!(&encodings[..3], ["", "null", "null"]);
    assert_ne!(encodings[3], encodings[4]);
    assert_ne!(encodings[3], encodings[5]);

    for old_session in sessions {
        for old_usage in &encodings {
            let known = format!("{old_session}\n{old_usage}");
            for session in sessions {
                for usage in &encodings {
                    assert_eq!(
                        matches_compact_key(&known, session, usage),
                        known == format!("{session}\n{usage}")
                    );
                }
            }
        }
    }
    assert!(!matches_compact_key("/same:null", "/same", "null"));
}
