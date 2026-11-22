// Test-only preview/selector requested-allocation counters; never part of the product patch.
use super::*;
use serde_json::json;

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

fn catalogue(n: usize) -> Vec<Value> {
    (0..n).map(|i| {
        let preview = if i % 2 == 0 {
            format!("Discuss fixture {i:02}: planning a careful serialization change and reviewing the existing saved-session semantics.")
        } else {
            format!("Условный проект {i:02}: согласуем очередность правок и сверяем готовые изменения.")
        };
        json!({"session_dir":format!("/synthetic-session-{i:02}"),"message_count":3*i+1,"preview":preview})
    }).collect()
}

fn edge() -> Vec<Value> {
    vec![
        json!({"preview":"   ", "message_count":-1.75}),
        json!({"session_dir":null,"preview":false,"message_count":"14"}),
        json!({"preview":format!("{}🧪\u{200d}e\u{301}", "λ".repeat(59))}),
        json!({"session_dir":"/synthetic-session-00","preview":"First equal row"}),
        json!({"session_dir":"/synthetic-session-00","preview":"Second equal row"}),
        json!({"session_dir":17,"preview":false}),
        json!({"session_dir":false,"preview":"☕"}),
        json!({"session_dir":["other"],"preview":""}),
        json!({"session_dir":"/blank","preview":null}),
        json!(19),
    ]
}

fn reference_label(row: &Value) -> String {
    let preview: String = row
        .opt_str("preview")
        .filter(|text| !text.is_empty())
        .unwrap_or("Новая сессия")
        .chars()
        .take(60)
        .collect();
    format!(
        "{preview} · {} сообщ.",
        row.i64("message_count").unwrap_or(0)
    )
}

fn labels(case: &str, rows: &[Value]) {
    let mut output = Vec::with_capacity(rows.len());
    let ((), calls, bytes) = scope(|| {
        for row in rows {
            output.push(format_preview(std::hint::black_box(row)));
        }
    });
    let expected: Vec<_> = rows.iter().map(reference_label).collect();
    assert_eq!(output, expected, "{case}");
    let len: usize = output.iter().map(String::len).sum();
    let cap: usize = output.iter().map(String::capacity).sum();
    println!("\nops {case} {} {len} {cap} {calls} {bytes}", rows.len());
    println!("tree {case} {}", json!(output));
}

fn picker(case: &str, rows: Value, selected: Option<&str>) {
    let mut analytics = Analytics::new(None);
    let mut host = Host::default();
    host.session = selected.map(str::to_owned);
    let key = (
        "/sessions".to_owned(),
        host.session.clone(),
        "[]".to_owned(),
    );
    let options: Vec<_> = rows
        .as_array()
        .into_iter()
        .flatten()
        .map(|row| {
            let selected = selected.map(Value::from).unwrap_or(Value::Null);
            json!({"label":reference_label(row), "value":row.at("session_dir"),
               "selected": row.at("session_dir") == &selected})
        })
        .collect();
    let title = options
        .iter()
        .find(|option| option.bool("selected"))
        .map(|option| option.str("label"))
        .unwrap_or("Сохранённая сессия");
    let _ = analytics.remember(key, rows);
    let budget = analytics.bytes;
    let (out, calls, bytes) = scope(|| analytics.session_picker(&host).unwrap());
    assert_eq!(analytics.bytes, budget);
    assert_eq!(
        out,
        json!({"type":"select","id":"session","label":title,
                          "action":"session","options":options}),
        "{case}"
    );
    let string = |value: &Value| match value {
        Value::String(s) => (s.len(), s.capacity()),
        _ => panic!(),
    };
    let (len, cap) = out
        .list("options")
        .iter()
        .map(|item| string(&item["label"]))
        .fold(string(&out["label"]), |(n, c), (extra, room)| {
            (n + extra, c + room)
        });
    println!("\nops {case} {} {len} {cap} {calls} {bytes}", options.len());
    println!("tree {case} {}", serde_json::to_string(&out).unwrap());
}

#[test]
fn measure_session_previews() {
    let selected = Some("/synthetic-session-00");
    let twenty = catalogue(20);
    let fifty = catalogue(50);
    let edge = edge();
    let _ = format_preview(&twenty[0]);
    labels("label-empty", &[]);
    labels("label-fallback", &edge[1..2]);
    labels("label-twenty", &twenty);
    labels("label-fifty", &fifty);
    labels("label-edges", &edge);
    picker("warm-empty", json!({}), selected);
    picker("warm-twenty", json!(twenty), selected);
    picker("warm-fifty", json!(fifty), selected);
    picker("warm-duplicate", json!(edge), selected);
    picker("warm-null", json!(edge), None);
}
