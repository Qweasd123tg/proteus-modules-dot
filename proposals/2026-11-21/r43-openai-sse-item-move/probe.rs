use super::{before, stream_state};
use serde_json::{Value, json};
use std::{
    alloc::{GlobalAlloc, Layout, System},
    cell::Cell,
    collections::HashMap,
    hint::black_box,
};

#[derive(Clone, Copy, Debug, Default, PartialEq, Eq, PartialOrd, Ord)]
struct Cost {
    calls: usize,
    bytes: usize,
}

thread_local! { static COUNTS: Cell<Option<Cost>> = const { Cell::new(None) }; }
fn count(n: usize) {
    COUNTS.with(|c| {
        if let Some(mut v) = c.get() {
            v.calls += 1;
            v.bytes += n;
            c.set(Some(v));
        }
    });
}
struct Meter;
#[global_allocator]
static ALLOC: Meter = Meter;
unsafe impl GlobalAlloc for Meter {
    unsafe fn alloc(&self, l: Layout) -> *mut u8 {
        count(l.size());
        unsafe { System.alloc(l) }
    }
    unsafe fn alloc_zeroed(&self, l: Layout) -> *mut u8 {
        count(l.size());
        unsafe { System.alloc_zeroed(l) }
    }
    unsafe fn realloc(&self, p: *mut u8, l: Layout, n: usize) -> *mut u8 {
        count(n);
        unsafe { System.realloc(p, l, n) }
    }
    unsafe fn dealloc(&self, p: *mut u8, l: Layout) {
        unsafe { System.dealloc(p, l) }
    }
}
fn measure(f: impl FnOnce()) -> Cost {
    COUNTS.with(|c| c.set(Some(Cost::default())));
    f();
    COUNTS.with(|c| c.replace(None).unwrap())
}
fn item_event(kind: &str, item: &Value) -> String {
    json!({"type":format!("response.output_item.{kind}"),"output_index":0,"item":item}).to_string()
}
fn compare_cost(name: &str, kind: &str, item: Value) {
    let event = item_event(kind, &item);
    let old = || {
        let mut s = before::OpenAiStreamState::default();
        measure(|| {
            black_box(s.translate(black_box(&event)));
            black_box(&s);
        })
    };
    let new = || {
        let mut s = stream_state::OpenAiStreamState::default();
        measure(|| {
            black_box(s.translate(black_box(&event)));
            black_box(&s);
        })
    };
    let mut a = Vec::new();
    let mut b = Vec::new();
    for i in 0..35 {
        let (x, y) = if i % 2 == 0 {
            (old(), new())
        } else {
            let y = new();
            (old(), y)
        };
        if i >= 4 {
            a.push(x);
            b.push(y);
        }
    }
    a.sort();
    b.sort();
    let x = a[a.len() / 2];
    let y = b[b.len() / 2];
    println!(
        "{name},{kind},{},{},{},{},{}",
        event.len(),
        x.calls,
        y.calls,
        x.bytes,
        y.bytes
    );
    if kind == "added" {
        assert_eq!(x, y);
    } else {
        assert!(y.bytes < x.bytes);
    }
}

// Map only generated canonical IDs, bijectively across a whole trace. Provider
// payloads, raw call IDs and all other return fields remain exact.
fn normalize(v: &mut Value, ids: &mut HashMap<String, usize>) {
    match v {
        Value::Array(a) => {
            for x in a {
                normalize(x, ids)
            }
        }
        Value::Object(o) => {
            let message = o.contains_key("role") && o.contains_key("parts");
            for (key, x) in o {
                if key == "provider_metadata" || key == "data" || key == "metadata" {
                    continue;
                }
                if (key == "message_id" || key == "part_id" || (message && key == "id"))
                    && let Some(s) = x.as_str()
                {
                    let n = ids.len();
                    *x = json!(format!("id#{}", ids.entry(s.to_owned()).or_insert(n)));
                } else {
                    normalize(x, ids);
                }
            }
        }
        _ => {}
    }
}
fn compare_trace(compact: bool, input: &[String]) {
    let mut old = before::OpenAiStreamState::for_compaction(compact);
    let mut new = stream_state::OpenAiStreamState::for_compaction(compact);
    let (mut a, mut b) = (HashMap::new(), HashMap::new());
    for event in input {
        let mut x = serde_json::to_value(old.translate(event)).unwrap();
        let mut y = serde_json::to_value(new.translate(event)).unwrap();
        normalize(&mut x, &mut a);
        normalize(&mut y, &mut b);
        assert_eq!(x, y, "compact={compact} event={event}");
    }
}

#[test]
fn parity_and_allocation() {
    let message = json!({"id":"m","type":"message","role":"assistant","phase":"final_answer",
        "content":[{"type":"output_text","text":"Hi!","annotations":[]},{"type":"refusal","refusal":"No"}]});
    let reason = json!({"type":"reasoning","id":"r","summary":[{"type":"summary_text","text":"trace"}],
        "encrypted_content":"opaque"});
    let custom = json!({"id":"fc","type":"custom_tool_call","name":"read","call_id":"tool-1","input":"raw\nписать"});
    let tool = json!({"id":"fc","type":"function_call","name":"lookup","call_id":"tool-1","arguments":"{ \"q\":true }"});
    let checkpoint = json!({"type":"compaction_summary","id":"cp","encrypted_content":"checkpoint","nested":[true,null,1]});
    let unknown = json!({"type":"unknown","payload":{"u":["π",null]}});
    let samples = [
        message.clone(),
        reason.clone(),
        tool.clone(),
        custom.clone(),
        checkpoint.clone(),
        unknown.clone(),
        json!(null),
        json!([1, 2]),
        json!("extension"),
        json!({"type":"reasoning","summary":[]}),
        json!({"type":"message","role":"user","content":[]}),
        json!({"type":"message","phase":"invalid"}),
        json!({"type":"function_call","call_id":""}),
        json!({"type":"compaction","encrypted_content":""}),
        json!({"type":"web_search_call","id":"web","status":"completed","action":{"type":"search","query":"пример"}}),
        json!({"type":"file_search_call","id":"fs","status":"completed","queries":["x"],"results":[]}),
    ];
    let mut traces = 0;
    for one in &samples {
        for two in &samples {
            for compact in [false, true] {
                for authoritative in [false, true] {
                    let terminal=json!({"type":"response.completed","response":{"status":"completed","output":
            if authoritative {json!([message])} else {json!([])}}}).to_string();
                    compare_trace(
                        compact,
                        &[
                            "{".into(),
                            r#"{"type":"response.output_item.done"}"#.into(),
                            item_event("added", two),
                            item_event("done", one),
                            r#"{"type":"response.output_text.delta","item_id":"m","delta":"Hi!"}"#
                                .into(),
                            item_event("done", two),
                            terminal.clone(),
                            terminal,
                        ],
                    );
                    traces += 1;
                }
            }
        }
    }
    println!("normalized event trace parity: {traces} x 8");
    println!(
        "case,kind,wire_bytes,alloc_calls_before,alloc_calls_after,requested_bytes_before,requested_bytes_after"
    );
    compare_cost("short text", "done", message.clone());
    compare_cost(
        "ordinary text 64 KiB",
        "done",
        json!({"type":"message","id":"m","role":"assistant","content":[{"type":"output_text","text":"text".repeat(16384)}]}),
    );
    compare_cost(
        "reasoning 256 KiB",
        "done",
        json!({"type":"reasoning","id":"r","encrypted_content":"x".repeat(262144),"summary":[]}),
    );
    compare_cost(
        "checkpoint 1 MiB",
        "done",
        json!({"type":"compaction","id":"cp","encrypted_content":"x".repeat(1048576)}),
    );
    compare_cost(
        "unknown nested 512 entries",
        "done",
        json!({"type":"unknown","nested":(0..512).map(|i|json!({"n":i,"v":"entry"})).collect::<Vec<_>>()}),
    );
    compare_cost("short text control", "added", message);
    compare_cost(
        "checkpoint 1 MiB control",
        "added",
        json!({"type":"compaction","id":"cp","encrypted_content":"x".repeat(1048576)}),
    );
}
