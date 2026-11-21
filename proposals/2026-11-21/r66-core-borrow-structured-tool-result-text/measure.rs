#![allow(dead_code)]

mod candidate;
mod stock;
mod test_alloc;

mod domain {
    pub use proteus_contracts::domain::{HostedToolConfig, HostedToolKind};
    pub mod ids {
        pub use proteus_contracts::domain::CallId;
    }
}

use serde_json::{Value, json};
use std::{hint::black_box, io::Write as _};

fn wire(ok: bool, error: Option<&str>, output: &str, parts: Vec<Value>) -> Value {
    json!({
        "call_id": "synthetic",
        "ok": ok,
        "output": output,
        "content": parts,
        "error": error,
        "metadata": {"hidden_fixture": 921},
    })
}

fn text(text: &str) -> Value {
    json!({"type":"text","text":text})
}

fn structured_json(value: Value) -> Value {
    json!({"type":"json","value":value})
}

fn parts(seed: usize) -> Vec<Value> {
    let chunks = [
        text(""),
        text("string +\r\n😀\0"),
        text(" \t\u{2003} "),
        structured_json(Value::Null),
        structured_json(json!({"b": ["\n", "😀", 1], "a": true})),
        json!({"type":"image","mime_type":"image/png","data":"never shown"}),
        json!({"type":"binary","mime_type":"fictional/demo","data":"never shown"}),
        text("last"),
    ];
    (0..seed % 13)
        .map(|i| chunks[(seed * 3 + i * 5) % chunks.len()].clone())
        .collect()
}

#[test]
fn keeps_output_priority_fallback_and_exact_mixed_display() {
    for (input, expected) in [
        (wire(true, Some("error"), "output", parts(3)), "error"),
        (wire(false, Some(""), "output", parts(3)), "output"),
        (wire(true, None, " \t", parts(3)), " \t"),
        (wire(true, None, "", vec![text("")]), "(no output)"),
        (
            wire(false, None, "", vec![text("")]),
            "(tool failed without an error message)",
        ),
        (
            wire(
                false,
                Some(""),
                "",
                vec![
                    text("x\r\n😀\0"),
                    text(""),
                    structured_json(json!({"escape":"x\n"})),
                    json!({"type":"image","mime_type":"image/png","data":"hidden"}),
                    json!({"type":"binary","mime_type":"fixture\\example","data":"hidden"}),
                    text(" "),
                ],
            ),
            "x\r\n😀\0\n{\"escape\":\"x\\n\"}\n[image tool content: image/png]\n[binary tool content: fixture\\example]\n ",
        ),
    ] {
        let probe: candidate::ToolResult = serde_json::from_value(input).unwrap();
        let value = probe.text_or_status();
        assert_eq!(value.as_bytes(), expected.as_bytes());
    }
}

#[test]
fn exact_source_and_retained_stock_agree_on_wire_shape_and_display() {
    let file = std::fs::File::create(std::env::var_os("R66_SNAPSHOT").unwrap()).unwrap();
    let mut out = std::io::BufWriter::new(file);
    let mut count = 0;
    for status in [false, true] {
        for error in [None, Some(""), Some("ошибка 😀")] {
            for output in ["", " \t", "out\r\n😀\0"] {
                for seed in 0..48 {
                    let value = wire(status, error, output, parts(seed));
                    let old: stock::ToolResult = serde_json::from_value(value.clone()).unwrap();
                    let new: candidate::ToolResult = serde_json::from_value(value.clone()).unwrap();
                    let live: proteus_contracts::domain::ToolResult =
                        serde_json::from_value(value).unwrap();
                    let previous = old.text_or_status();
                    let next = new.text_or_status();
                    assert_eq!(previous, next);
                    assert_eq!(previous, live.text_or_status());
                    let old_wire = serde_json::to_vec(&old).unwrap();
                    assert_eq!(old_wire, serde_json::to_vec(&new).unwrap());
                    assert_eq!(old_wire, serde_json::to_vec(&live).unwrap());
                    for field in [next.as_bytes(), old_wire.as_slice()] {
                        out.write_all(&(field.len() as u64).to_le_bytes()).unwrap();
                        out.write_all(field).unwrap();
                    }
                    count += 1;
                }
            }
        }
    }
    out.flush().unwrap();
    assert_eq!(count, 864);
    println!(
        "{count} byte-identical result DTO and display pairs (also matched the linked stock library)"
    );
}

#[test]
fn allocation_requests_for_render_only() {
    let big = "語😀".repeat(9_365);
    for (fixture, value, borrowed_count) in [
        ("empty", wire(true, None, "", vec![]), 0),
        (
            "plain output",
            wire(true, None, "file contents", vec![text("ignored")]),
            0,
        ),
        (
            "structured text",
            wire(true, None, "", vec![text("read 17 files")]),
            1,
        ),
        (
            "mixed structured",
            wire(
                true,
                None,
                "",
                vec![
                    text("line one"),
                    structured_json(json!({"files":17})),
                    text("line two"),
                    json!({"type":"image","mime_type":"image/png","data":"not displayed"}),
                ],
            ),
            2,
        ),
        (
            "json only",
            wire(true, None, "", vec![structured_json(json!({"files":17}))]),
            0,
        ),
        (
            "65K UTF-8 text",
            wire(true, None, "", vec![text(&big), text("last")]),
            2,
        ),
    ] {
        let old: stock::ToolResult = serde_json::from_value(value.clone()).unwrap();
        let new: candidate::ToolResult = serde_json::from_value(value).unwrap();
        let (before, a) = test_alloc::measure(|| black_box(black_box(&old).text_or_status()));
        let (after, b) = test_alloc::measure(|| black_box(black_box(&new).text_or_status()));
        assert_eq!(before, after);
        assert_eq!(a.calls, b.calls + borrowed_count, "{fixture}");
        if borrowed_count == 0 {
            assert_eq!(a.bytes, b.bytes, "{fixture}");
        } else {
            assert!(a.bytes > b.bytes, "{fixture}");
        }
        println!(
            "{fixture:18} requests {:2} -> {:2}; bytes {:6} -> {:6}; output {}",
            a.calls,
            b.calls,
            a.bytes,
            b.bytes,
            after.len()
        );
    }
}
