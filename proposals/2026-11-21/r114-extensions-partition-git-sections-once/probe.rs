// Test-only Git partition counters; never part of the product patch.
use super::*;
use crate::model::{Section, Staging, section_staging, sections};

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
    static VISITS: Cell<Option<(usize, usize, usize)>> = const { Cell::new(None) };
}

pub(crate) fn entry_visit() {
    VISITS.with(|m| {
        if let Some((visits, status, flags)) = m.get() {
            m.set(Some((visits + 1, status, flags)));
        }
    });
}

pub(crate) fn read_status(value: &str) -> &str {
    VISITS.with(|m| {
        if let Some((visits, status, flags)) = m.get() {
            m.set(Some((visits, status + 1, flags)));
        }
    });
    value
}

pub(crate) fn read_flag(value: &Value) -> &Value {
    VISITS.with(|m| {
        if let Some((visits, status, flags)) = m.get() {
            m.set(Some((visits, status, flags + 1)));
        }
    });
    value
}

fn fixture(n: usize, all_staged: bool) -> Vec<Value> {
    (0..n)
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
            let mut entry = json!({
                "path": format!("src/fixture-{i:02}-данные.txt"), "status": status,
                "staged": staged, "unstaged": unstaged, "added": i+1, "deleted": i%3,
            });
            if i % 8 == 5 {
                entry["original"] = json!(format!("old/fixture-{i:02}.txt"));
            }
            entry
        })
        .collect()
}

// The untouched baseline selection rule, independent of the compiled helper.
fn reference(entries: &[Value], group: Group) -> Vec<(Section, Vec<&Value>)> {
    let order = match group {
        Group::Status => [Section::Conflicts, Section::Tracked, Section::New],
        Group::Staging => [Section::Conflicts, Section::Staged, Section::Unstaged],
    };
    order
        .into_iter()
        .filter_map(|section| {
            let items: Vec<_> = entries
                .iter()
                .filter(|entry| {
                    let status = entry.str("status");
                    if status == "conflict" || section == Section::Conflicts {
                        return status == "conflict" && section == Section::Conflicts;
                    }
                    match section {
                        Section::Conflicts => unreachable!(),
                        Section::Tracked => !matches!(status, "untracked" | "added"),
                        Section::New => matches!(status, "untracked" | "added"),
                        Section::Staged => entry.at("staged").truthy(),
                        Section::Unstaged => entry.at("unstaged").truthy(),
                    }
                })
                .collect();
            (!items.is_empty()).then_some((section, items))
        })
        .collect()
}

fn projection(entries: &[Value], buckets: &[(Section, Vec<&Value>)]) -> Value {
    let indices = |item: &&Value| {
        entries
            .iter()
            .position(|entry| std::ptr::eq(entry, *item))
            .expect("must borrow the exact input row")
    };
    let buckets: Vec<_> = buckets
        .iter()
        .map(|(section, entries)| {
            let state = section_staging(*section, entries);
            let unstage = state == Staging::Staged;
            let flag = if unstage { "staged" } else { "unstaged" };
            // Purely project the existing action's selected items, without
            // opening any host or executing a command/operation.
            let eligible: Vec<_> = entries
                .iter()
                .filter(|entry| entry.at(flag).truthy())
                .map(|entry| (indices(entry), entry.str("path")))
                .collect();
            json!({"key": section.key(), "checked": format!("{state:?}"),
                   "indices": entries.iter().map(indices).collect::<Vec<_>>(),
                   "unstage": unstage, "eligible": eligible})
        })
        .collect();
    json!(buckets)
}

fn sample(name: &str, entries: &[Value], group: Group) {
    let n = entries.len();
    let conflicts = entries
        .iter()
        .filter(|row| row.str("status") == "conflict")
        .count();
    assert!(VISITS.replace(Some((0, 0, 0))).is_none());
    let (buckets, allocs, bytes) = scope(|| sections(std::hint::black_box(entries), group));
    let (visits, status, flags) = VISITS.take().unwrap();
    let m = usize::from(group == Group::Staging);
    let bucket_cap: usize = buckets.iter().map(|(_, rows)| rows.capacity()).sum();
    println!(
        "\nops {name} {m} {n} {conflicts} {visits} {status} {flags} {} {} {bucket_cap} {allocs} {bytes}",
        buckets.len(),
        buckets.capacity()
    );
    let tree = projection(entries, &buckets);
    assert_eq!(
        tree,
        projection(entries, &reference(entries, group)),
        "{name}"
    );
    let rows = panel::change_rows(
        entries,
        group,
        &HashSet::from(["conflicts"]),
        (group == Group::Staging).then_some("staged:src/fixture-00-данные.txt"),
    );
    println!("tree {name} {}", json!({"partition":tree, "rows":rows}));
}

#[test]
fn measure_sections_once() {
    let one = fixture(1, false);
    let medium = fixture(32, false);
    let larger = fixture(64, false);
    let indexed = fixture(64, true);
    let mut weird = vec![
        json!({"path":"src/fixture-00-данные.txt", "status":"modified", "staged":[0], "unstaged":{"marker":false}}),
        json!({"path":"src/fixture-00-данные.txt", "status":"untracked", "unstaged":"false"}),
        json!({"path":"conflict-a", "status":"conflict", "staged":true, "unstaged":true}),
        json!({"path":"conflict-b", "status":"conflict", "staged":false, "unstaged":false}),
        json!({"path":"nonstring", "status":17, "staged":-1, "unstaged":0}),
        json!({"path":"missing", "staged":{}, "unstaged":[]}),
        json!({"path":"new", "status":"added", "staged":"", "unstaged":null}),
        json!({"path":"case", "status":"Conflict", "staged":true}),
        json!(7),
    ];
    weird.reverse();
    let _ = sections(&one, Group::Status);
    sample("empty-status", &[], Group::Status);
    sample("empty-staging", &[], Group::Staging);
    sample("one-status", &one, Group::Status);
    sample("one-staging", &one, Group::Staging);
    sample("ordinary-status", &medium, Group::Status);
    sample("ordinary-staging", &medium, Group::Staging);
    sample("larger-status", &larger, Group::Status);
    sample("larger-staging", &larger, Group::Staging);
    sample("all-staged", &indexed, Group::Staging);
    sample("malformed-status", &weird, Group::Status);
    sample("malformed-staging", &weird, Group::Staging);
}
