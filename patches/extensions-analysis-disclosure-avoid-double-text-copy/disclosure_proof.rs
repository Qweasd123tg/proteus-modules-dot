use crate::{details, nodes, summary};
use proteus_extension::{Value, json};
use std::{
    alloc::{GlobalAlloc, Layout, System},
    cell::Cell,
    fs,
    hint::black_box,
    path::PathBuf,
};

#[allow(dead_code)]
#[path = "r265_stock_nodes.rs"]
mod stock;

#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
struct Requests {
    alloc: usize,
    realloc: usize,
    bytes: usize,
}

thread_local! {
    static METER: Cell<Option<Requests>> = const { Cell::new(None) };
}

fn count(size: usize, realloc: bool) {
    let _ = METER.try_with(|meter| {
        if let Some(mut requests) = meter.get() {
            if realloc {
                requests.realloc += 1;
            } else {
                requests.alloc += 1;
            }
            requests.bytes += size;
            meter.set(Some(requests));
        }
    });
}

struct Meter;
unsafe impl GlobalAlloc for Meter {
    unsafe fn alloc(&self, layout: Layout) -> *mut u8 {
        count(layout.size(), false);
        unsafe { System.alloc(layout) }
    }

    unsafe fn alloc_zeroed(&self, layout: Layout) -> *mut u8 {
        count(layout.size(), false);
        unsafe { System.alloc_zeroed(layout) }
    }

    unsafe fn realloc(&self, pointer: *mut u8, layout: Layout, size: usize) -> *mut u8 {
        count(size, true);
        unsafe { System.realloc(pointer, layout, size) }
    }

    unsafe fn dealloc(&self, pointer: *mut u8, layout: Layout) {
        unsafe { System.dealloc(pointer, layout) }
    }
}

#[global_allocator]
static ALLOCATOR: Meter = Meter;

fn measured(f: impl FnOnce() -> Value) -> (Value, Requests) {
    METER.with(|meter| assert_eq!(meter.replace(Some(Requests::default())), None));
    let result = black_box(f());
    let requests = METER.with(|meter| meter.replace(None)).unwrap();
    (result, requests)
}

fn keys(widget: &Value) -> Vec<&str> {
    widget
        .as_object()
        .unwrap()
        .keys()
        .map(String::as_str)
        .collect()
}

fn check_widget<'a>(
    widget: &'a Value,
    key: &str,
    title: &str,
    wrap: bool,
    open: bool,
    height: u64,
) -> &'a String {
    assert_eq!(keys(widget), ["type", "id", "label", "children", "open"]);
    assert_eq!(widget["type"], "disclosure");
    assert_eq!(widget["id"], key);
    assert_eq!(widget["label"], title);
    assert_eq!(widget["open"], open);
    assert_eq!(widget["children"].as_array().unwrap().len(), 1);
    let code = &widget["children"][0];
    let mut expected_keys = vec!["type", "id", "text", "language", "height"];
    if wrap {
        expected_keys.push("wrap");
        assert_eq!(code["wrap"], true);
    } else {
        assert!(code.get("wrap").is_none());
    }
    assert_eq!(keys(code), expected_keys);
    assert_eq!(code["type"], "code");
    assert_eq!(code["id"], format!("analysis-{key}"));
    assert_eq!(code["language"], if wrap { "text" } else { "json" });
    assert_eq!(code["height"], height);
    let Value::String(text) = &code["text"] else {
        panic!("disclosure text is not a string");
    };
    assert_eq!(text.capacity(), text.len());
    text
}

fn bytes(widget: &Value) -> Vec<u8> {
    serde_json::to_vec(widget).unwrap()
}

fn long_fixture(marker: &str) -> String {
    format!("{marker}:{}", "Ж🙂\r\n\0\"\\\t\u{2028}".repeat(80_000))
}

#[test]
fn direct_wire_and_capacity_match_exact_stock() {
    let cases = [
        ("step:raw", json!(""), "—".to_owned(), 48),
        ("step:args", json!(null), "null".to_owned(), 48),
        ("step:summary", json!(-3.5), "-3.5".to_owned(), 48),
        ("step:output", json!(false), "false".to_owned(), 48),
        (
            "step:raw",
            json!({"z": ["Ж🙂\r\n\0\"\\", null], "a": 0}),
            "{\n  \"z\": [\n    \"Ж🙂\\r\\n\\u0000\\\"\\\\\",\n    null\n  ],\n  \"a\": 0\n}"
                .to_owned(),
            142,
        ),
        (
            "step:other",
            json!("\r\n".repeat(19)),
            "\r\n".repeat(19),
            358,
        ),
        (
            "step:answer",
            json!("\r\n".repeat(20)),
            "\r\n".repeat(20),
            360,
        ),
        ("step:raw", json!("я".repeat(331)), "я".repeat(331), 88),
    ];
    for (key, body, expected, height) in cases {
        let title = "Заголовок 🙂\r\n\"\0";
        let original = bytes(&body);
        let old = stock::disclosure(key, title, &body, &stock::Open);
        let new = nodes::disclosure(key, title, &body, &nodes::Open);
        let open = matches!(
            key,
            "step:args" | "step:output" | "step:answer" | "step:summary"
        );
        let a = check_widget(&old, key, title, body.is_string(), open, height);
        let b = check_widget(&new, key, title, body.is_string(), open, height);
        assert_eq!(a, &expected);
        assert_eq!(b, &expected);
        assert_eq!(bytes(&old), bytes(&new));
        assert_eq!(original, bytes(&body));
        if let Some(input) = body.as_str().filter(|s| !s.is_empty()) {
            assert_ne!(b.as_ptr(), input.as_ptr());
        }
    }
}

fn child<'a>(widget: &'a Value, id: &str) -> &'a Value {
    widget["children"]
        .as_array()
        .unwrap()
        .iter()
        .find(|node| node["id"] == id)
        .unwrap()
}

#[test]
fn actual_analysis_entry_points_emit_full_payloads() {
    let answer = long_fixture("Answer");
    let output = long_fixture("ToolResult");
    assert!(answer.len() > 1_048_576 && output.len() > 1_048_576);
    let config = json!({"z_config": true, "a_config": ["Ж🙂", null]});
    let turn = json!({
        "turn_id": "fixture",
        "task": {"text": "я\r\n🙂".repeat(200)},
        "output": {"text": answer.as_str()},
        "config_snapshot": &config,
        "module_epoch": 7,
    });
    let tool = json!({
        "sequence": 3,
        "data": {
            "kind": "tool",
            "call": {"id": "synthetic", "args": {"z": true, "a": false}},
            "result": {"output": output.as_str()},
        },
    });
    let turn_before = bytes(&turn);
    let tool_before = bytes(&tool);
    let turn_root = summary::turn_summary(&turn, &json!(1), &Value::Null, &nodes::Open);
    let tool_root = details::step_card(&tool, &nodes::Open);
    let answer_id = "turn:fixture:output";
    let tool_id = "3:output";
    let config_id = "turn:fixture:config";
    let raw_id = "3:raw";
    assert_eq!(
        check_widget(
            child(&turn_root, answer_id),
            answer_id,
            "Итоговый ответ",
            true,
            true,
            360
        ),
        &answer,
    );
    assert_eq!(
        check_widget(
            child(&tool_root, tool_id),
            tool_id,
            "Результат",
            true,
            true,
            360
        ),
        &output,
    );
    assert_eq!(
        check_widget(
            child(&turn_root, config_id),
            config_id,
            "Конфигурация при запуске · epoch 7",
            false,
            false,
            142
        ),
        &serde_json::to_string_pretty(&config).unwrap(),
    );
    assert_eq!(
        check_widget(
            child(&tool_root, raw_id),
            raw_id,
            "Полная запись",
            false,
            false,
            360
        ),
        &serde_json::to_string_pretty(&tool).unwrap(),
    );
    assert_eq!(bytes(&turn), turn_before);
    assert_eq!(bytes(&tool), tool_before);
    let snapshots = PathBuf::from(std::env::var_os("R265_SNAPSHOTS").unwrap());
    fs::write(snapshots.join("turn.json"), bytes(&turn_root)).unwrap();
    fs::write(snapshots.join("tool.json"), bytes(&tool_root)).unwrap();
}

fn paired_requests(name: &str, body: &Value, saving: usize) {
    let key = black_box("stock:output");
    let title = black_box("Exact allocation window");
    let body = black_box(body);
    let (old, stock) = measured(|| stock::disclosure(key, title, body, &stock::Open));
    let (new, candidate) = measured(|| nodes::disclosure(key, title, body, &nodes::Open));
    let text = &new["children"][0]["text"];
    let Value::String(text) = text else {
        panic!("missing text");
    };
    assert_eq!(text.capacity(), text.len());
    assert_eq!(bytes(&old), bytes(&new));
    assert_eq!(stock.alloc, candidate.alloc + usize::from(saving != 0));
    assert_eq!(stock.realloc, candidate.realloc);
    assert_eq!(stock.bytes, candidate.bytes + saving);
    println!("{name}: stock {stock:?}; candidate {candidate:?}; saved {saving} requested bytes");
}

#[test]
fn optimized_helper_requests_match_controls() {
    let long = long_fixture("Allocation");
    let len = long.len();
    paired_requests("long borrowed UTF-8", &Value::String(long), len);
    paired_requests("empty text becomes em dash", &json!(""), "—".len());

    let pretty = |len: usize| json!({"z": "x".repeat(len), "a": true});
    let loose_short = pretty(1);
    let loose_large = pretty(800_000);
    for (name, value) in [
        ("loose short pretty", loose_short),
        ("loose large pretty", loose_large),
    ] {
        let text = serde_json::to_string_pretty(&value).unwrap();
        assert!(text.capacity() > text.len());
        paired_requests(name, &value, 0);
    }

    let tight = (1..128)
        .map(pretty)
        .find(|value| {
            let text = serde_json::to_string_pretty(value).unwrap();
            text.len() == text.capacity()
        })
        .expect("locked serde_json must produce an exact-capacity pretty witness");
    let text = serde_json::to_string_pretty(&tight).unwrap();
    assert_eq!(text.capacity(), text.len());
    paired_requests("tight pretty", &tight, text.len());
}
