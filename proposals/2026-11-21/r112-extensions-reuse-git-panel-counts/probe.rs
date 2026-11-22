// Test-only real Git panel render counters; never part of the product patch.
use super::*;

use std::alloc::{GlobalAlloc, Layout, System};
use std::cell::Cell;

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

thread_local! {
    static VISITS: Cell<Option<(usize, usize)>> = const { Cell::new(None) };
}

pub(crate) fn count_call() {
    VISITS.with(|m| {
        if let Some((calls, visits)) = m.get() {
            m.set(Some((calls + 1, visits)));
        }
    });
}

pub(crate) fn entry_visit() {
    VISITS.with(|m| {
        if let Some((calls, visits)) = m.get() {
            m.set(Some((calls, visits + 1)));
        }
    });
}

fn snapshot(n: usize, repository: Value, all_staged: bool, truncated: bool) -> Value {
    let entries: Vec<_> = (0..n)
        .map(|i| {
            let (status, staged, unstaged) = match (all_staged, i % 8) {
                (true, _) => (json!("modified"), json!("modified"), Value::Null),
                (_, 0) => (json!("modified"), json!("modified"), json!("modified")),
                (_, 1) => (json!("deleted"), Value::Null, json!("deleted")),
                (_, 2) => (json!("untracked"), Value::Null, json!("untracked")),
                (_, 3) => (json!("conflict"), json!("conflict"), json!("conflict")),
                (_, 4) => (json!("added"), json!("added"), Value::Null),
                (_, 5) => (json!("renamed"), json!("renamed"), Value::Null),
                (_, 6) => (json!("opaque"), json!(false), json!([])),
                (_, _) => (json!(17), json!({}), json!({"marker": true})),
            };
            json!({
                "path": format!("src/fixture-{i:02}-данные.txt"), "status": status,
                "staged": staged, "unstaged": unstaged, "added": i+1, "deleted": i%3,
            })
        })
        .collect();
    json!({"repository": repository, "branch": "fixture-main", "entries": entries,
           "truncated": truncated})
}

fn sample(name: &str, git: &mut Git, host: &Host, n: usize, expect_ok: bool) {
    assert!(VISITS.replace(Some((0, 0))).is_none());
    let (result, allocations, requested) = scope(|| git.panel(host, "fixture", "fixture-main"));
    let (calls, visits) = VISITS.take().unwrap();
    assert_eq!(result.is_ok(), expect_ok, "{name}");
    println!("\nops {name} {n} {calls} {visits} {allocations} {requested}");
    match result {
        Ok(root) => println!("tree {name} {}", serde_json::to_string(&root).unwrap()),
        Err(error) => println!(
            "tree {name} {}",
            serde_json::to_string(&error.to_string()).unwrap()
        ),
    }
}

#[test]
fn measure_panel_counts() {
    let host = Host::default();
    let mut git = Git {
        branches: Some(Vec::new()),
        ..Git::default()
    };
    git.changes = Rc::new(snapshot(1, json!(true), true, false));
    let _ = git.panel(&host, "fixture", "fixture-main").unwrap();
    sample("one", &mut git, &host, 1, true);
    git.changes = Rc::new(snapshot(32, json!(true), false, false));
    sample("ordinary", &mut git, &host, 32, true);
    sample("warm", &mut git, &host, 32, true);
    git.group = Group::Staging;
    sample("staging", &mut git, &host, 32, true);
    git.editor_collapsed = true;
    git.message = "Synthetic note".into();
    git.changes = Rc::new(snapshot(64, json!(true), true, true));
    sample("next-generation", &mut git, &host, 64, true);
    git.changes = Rc::new(snapshot(0, json!(true), false, true));
    sample("empty", &mut git, &host, 0, true);
    git.changes = Rc::new(snapshot(32, json!("true"), false, false));
    sample("no-repository", &mut git, &host, 32, true);
    git.branches = None;
    git.changes = Rc::new(snapshot(32, json!(true), false, false));
    sample("footer-failure", &mut git, &host, 32, false);
}
