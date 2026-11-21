// Test-only instrumentation, using proteus-contracts' existing allocator.
use super::*;
use crate::test_alloc::measure;
use serde_json::json;

fn text(s: &str) -> ContentPart {
    ContentPart::Text { text: s.to_owned() }
}

fn reasoning(s: &str) -> ContentPart {
    ContentPart::Reasoning {
        text: s.to_owned(),
        signature: Some("private-signature".to_owned()),
    }
}

fn summary(s: &str) -> ContentPart {
    ContentPart::ReasoningSummary { text: s.to_owned() }
}

fn hidden() -> ContentPart {
    ContentPart::Opaque {
        format: "provider.fixture.opaque".into(),
        data: json!({"different_text":"private-opaque"}),
    }
}

fn old_projection(m: &CanonicalMessage, thought: bool) -> String {
    m.parts
        .iter()
        .filter_map(|p| match &p.payload {
            ContentPart::Text { text } if !thought && !text.trim().is_empty() => {
                Some(text.as_str())
            }
            ContentPart::Reasoning { text, .. } | ContentPart::ReasoningSummary { text }
                if thought && !text.trim().is_empty() =>
            {
                Some(text.as_str())
            }
            _ => None,
        })
        .collect::<Vec<_>>()
        .join("\n")
}

#[test]
fn r51_presentation_parity_and_cost() {
    let padded = "  Привет🌍\t\0\r\n ";
    let blank = "\u{2003}\u{202f}\r\n\t";
    let big = "b".repeat(65_536);
    let mut snapshots = vec![];
    for (case, payloads) in [
        ("none", vec![]),
        ("only_hidden", vec![hidden()]),
        ("blank", vec![text(blank), reasoning(" "), summary(blank)]),
        ("single_text", vec![text("hello")]),
        ("single_reasoning", vec![reasoning("thought")]),
        ("single_summary", vec![summary("thought")]),
        (
            "mixed_single",
            vec![text(blank), summary(padded), hidden(), text(padded)],
        ),
        ("text_64k", vec![text(&big)]),
        (
            "text_2",
            vec![text("zero"), reasoning("not text"), text("one")],
        ),
        (
            "thought_3",
            vec![
                summary("zero"),
                reasoning("one"),
                text("not thought"),
                hidden(),
                summary("two"),
            ],
        ),
        (
            "mixed_many",
            (0..128)
                .map(|n| {
                    if n % 2 == 0 {
                        text(padded)
                    } else {
                        reasoning(padded)
                    }
                })
                .collect(),
        ),
    ] {
        let m = CanonicalMessage::new(MessageRole::Assistant, payloads);
        let (display, a) = measure(|| m.display_text());
        let (thought, b) = measure(|| m.reasoning_text());
        assert_eq!(display, old_projection(&m, false), "{case} display");
        assert_eq!(thought, old_projection(&m, true), "{case} reasoning");
        println!(
            "r51 {case} display={} {} thought={} {}",
            a.calls, a.bytes, b.calls, b.bytes
        );
        snapshots.push(json!([case, display, thought]));
    }

    // Exhaustively interleave canonical parts from both visible channels, blanks
    // and opaque records, including followed-by-blank and multi-channel controls.
    let alphabet = [
        text(" 	δ\0 "),
        text(blank),
        reasoning("π"),
        summary(" ε\r\n "),
        hidden(),
    ];
    for key in 0usize..alphabet.len().pow(5) {
        let mut index = key;
        let parts = (0..5)
            .map(|_| {
                let p = alphabet[index % alphabet.len()].clone();
                index /= alphabet.len();
                p
            })
            .collect();
        let msg = CanonicalMessage::new(MessageRole::Assistant, parts);
        let d = msg.display_text();
        let r = msg.reasoning_text();
        assert_eq!(d, old_projection(&msg, false), "{key} display");
        assert_eq!(r, old_projection(&msg, true), "{key} reasoning");
        snapshots.push(json!([key, d, r]));
    }
    std::fs::write(
        std::env::var("R51_PRESENTATION_SNAPSHOT").unwrap(),
        serde_json::to_vec(&snapshots).unwrap(),
    )
    .unwrap();
}
