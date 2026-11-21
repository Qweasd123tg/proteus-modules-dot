// Disposable test instrumentation; no production allocator change.
use super::*;
use crate::r49_alloc::measure;
use serde_json::{Value, json};

#[test]
fn r49_prompt_text_parity_and_cost() {
    let text = |s: &str| json!({"type":"text", "text":s});
    let link = || json!({"type":"resource_link", "name":"résumé", "uri":"file:///doc/item"});
    let image = || json!({"type":"image", "data":"aGVsbG8=", "mimeType":"image/png"});
    let large = "a".repeat(65536);
    let mixed = " 	Привет 🌍\n ";
    let mut out = vec![];
    for (case, wire, ok) in [
        ("none", json!([]), None),
        ("single_empty", json!([text("")]), None),
        ("single_blank", json!([text(" \u{2002}\r\n")]), None),
        ("single_ascii", json!([text("hello")]), Some("hello")),
        ("single_unicode", json!([text(mixed)]), Some(mixed)),
        ("single_64k", json!([text(&large)]), Some(large.as_str())),
        (
            "annotations",
            json!([{"type":"text", "text":" annotated ", "annotations":{"priority":0.5}}]),
            Some(" annotated "),
        ),
        (
            "split",
            json!([text(""), text("a\n"), text(" β ")]),
            Some("\na\n\n β "),
        ),
        ("multi_blank", json!([text(" "), text("\u{2003}")]), None),
        (
            "link_only",
            json!([link()]),
            Some("résumé (file:///doc/item)"),
        ),
        (
            "link_text",
            json!([text(""), link(), text("📃")]),
            Some("\nrésumé (file:///doc/item)\n📃"),
        ),
        ("image_only", json!([image()]), None),
        ("blank_then_image", json!([text(" "), image()]), None),
        ("image_then_text", json!([image(), text("later")]), None),
    ] {
        // Build the same typed ACP DTO from wire JSON, outside the measured operation.
        let blocks: Vec<ContentBlock> =
            serde_json::from_slice(&serde_json::to_vec(&wire).unwrap()).unwrap();
        let (result, stats) = measure(|| input::prompt_text(blocks));
        let snapshot = match (result, ok) {
            (Ok(actual), Some(expected)) => {
                assert_eq!(actual, expected, "{case}");
                json!({"text": actual})
            }
            (Err(error), None) => {
                let error = serde_json::to_value(error).unwrap();
                let expected = if case.contains("image") {
                    "unsupported prompt content; use text or resource_link"
                } else {
                    "prompt must not be empty"
                };
                assert_eq!(error["data"], Value::String(expected.into()), "{case}");
                json!({"error": error})
            }
            mismatch => panic!("{case}: {mismatch:?}"),
        };
        out.push(snapshot);
        println!(
            "r49 case={case} calls={} bytes={}",
            stats.calls, stats.bytes
        );
    }
    std::fs::write(
        std::env::var("R49_ACP_SNAPSHOT").unwrap(),
        serde_json::to_vec(&out).unwrap(),
    )
    .unwrap();
}
