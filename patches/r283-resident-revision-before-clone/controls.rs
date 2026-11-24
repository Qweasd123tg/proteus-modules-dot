use crate::{contracts::*, model_standard::*};
use proteus_contracts::domain::{ToolCall, ToolContent, ToolResult};
use serde_json::{Value, json};
use std::hash::{DefaultHasher, Hash, Hasher};
use uuid::Uuid;

pub fn seed(rows: usize, mixed: bool) -> Vec<CanonicalMessage> {
    let mut messages = crate::core::public_rows(rows, 4);
    for (i, m) in messages.iter_mut().enumerate() {
        if mixed {
            match i % 3 {
                0 => {
                    *m = CanonicalMessage::new(
                        MessageRole::Assistant,
                        vec![
                            ContentPart::Text {
                                text: "проверка\n".into(),
                            },
                            ContentPart::ToolCall {
                                call: ToolCall::new("id🦀", "search", json!({"α":["я",2]}))
                                    .with_raw_arguments(" { \"k\":true } "),
                            },
                            ContentPart::Reasoning {
                                text: "два".into(),
                                signature: Some("signature".into()),
                            },
                        ],
                    )
                    .with_name("assistant/name")
                    .with_metadata(json!({"z":[false,"мета"]}))
                }
                1 => {
                    *m = CanonicalMessage::new(
                        MessageRole::Tool,
                        vec![ContentPart::ToolResult {
                            result: ToolResult::ok("id🦀".into(), "out 🦀")
                                .with_content(vec![
                                    ToolContent::Text {
                                        text: "ответ".into(),
                                    },
                                    ToolContent::Json {
                                        value: json!({"ключ":[["x"],{}]}),
                                    },
                                ])
                                .with_metadata(json!({"nested":[1,"μ"]})),
                        }],
                    )
                    .with_tool_call_id("id🦀".into())
                }
                _ => {
                    m.metadata = json!([true, [], "\u{0}\n/"]);
                    m.name = Some("user".into());
                }
            }
        }
        m.id = Uuid::from_u128(0x100000 + i as u128);
        for (j, p) in m.parts.iter_mut().enumerate() {
            p.part_id = Uuid::from_u128(0x200000 + i as u128 + 0x100000 * j as u128)
        }
    }
    messages
}
pub fn observations() -> Vec<ModelContextObservation> {
    vec![
        ModelContextObservation::Usage {
            total_tokens: 8597777,
            last_tokens: 516,
        },
        ModelContextObservation::HistoryCompacted,
        ModelContextObservation::ContextWindowExceeded {
            max_input_tokens: 4096,
        },
    ]
}

pub fn caps(orig: &Vec<CanonicalMessage>, out: &ConversationSnapshot) -> u64 {
    assert_eq!(out.messages, *orig);
    assert_eq!(out.model_context, observations());
    let mut h = DefaultHasher::new();
    cv(orig, &out.messages, &mut h);
    out.model_context.capacity().hash(&mut h);
    for (a, b) in orig.iter().zip(&out.messages) {
        cv(&a.parts, &b.parts, &mut h);
        for (x, y) in a
            .name
            .iter()
            .zip(&b.name)
            .chain(a.tool_call_id.iter().zip(&b.tool_call_id))
        {
            cs(x, y, &mut h)
        }
        cj(&a.metadata, &b.metadata, &mut h);
        for (p, q) in a.parts.iter().zip(&b.parts) {
            match (&p.payload, &q.payload) {
                (ContentPart::Text { text: x }, ContentPart::Text { text: y }) => cs(x, y, &mut h),
                (
                    ContentPart::Reasoning {
                        text: x,
                        signature: s,
                    },
                    ContentPart::Reasoning {
                        text: y,
                        signature: t,
                    },
                ) => {
                    cs(x, y, &mut h);
                    for (x, y) in s.iter().zip(t) {
                        cs(x, y, &mut h)
                    }
                }
                (ContentPart::ToolCall { call: x }, ContentPart::ToolCall { call: y }) => {
                    cs(&x.id, &y.id, &mut h);
                    cs(&x.name, &y.name, &mut h);
                    cj(&x.args, &y.args, &mut h);
                    for (s, t) in x.raw_arguments.iter().zip(&y.raw_arguments) {
                        cs(s, t, &mut h)
                    }
                }
                (ContentPart::ToolResult { result: x }, ContentPart::ToolResult { result: y }) => {
                    cs(&x.call_id, &y.call_id, &mut h);
                    cs(&x.output, &y.output, &mut h);
                    cj(&x.metadata, &y.metadata, &mut h);
                    cv(&x.content, &y.content, &mut h);
                    for (l, r) in x.content.iter().zip(&y.content) {
                        match (l, r) {
                            (ToolContent::Text { text: p }, ToolContent::Text { text: q }) => {
                                cs(p, q, &mut h)
                            }
                            (ToolContent::Json { value: p }, ToolContent::Json { value: q }) => {
                                cj(p, q, &mut h)
                            }
                            _ => panic!("unhandled test tool content"),
                        }
                    }
                }
                _ => panic!("unhandled test content part"),
            }
        }
    }
    h.finish()
}
fn cv<T>(x: &Vec<T>, y: &Vec<T>, h: &mut DefaultHasher) {
    assert_eq!(x.len(), y.len());
    if !x.is_empty() {
        assert_ne!(x.as_ptr(), y.as_ptr())
    }
    y.capacity().hash(h);
}
fn cs(x: &String, y: &String, h: &mut DefaultHasher) {
    assert_eq!(x, y);
    if !x.is_empty() {
        assert_ne!(x.as_ptr(), y.as_ptr());
    }
    y.capacity().hash(h);
}
fn cj(x: &Value, y: &Value, h: &mut DefaultHasher) {
    match (x, y) {
        (Value::String(a), Value::String(b)) => cs(a, b, h),
        (Value::Array(a), Value::Array(b)) => {
            cv(a, b, h);
            for (p, q) in a.iter().zip(b) {
                cj(p, q, h)
            }
        }
        (Value::Object(a), Value::Object(b)) => {
            for ((k, p), (l, q)) in a.iter().zip(b) {
                cs(k, l, h);
                cj(p, q, h)
            }
        }
        _ => assert_eq!(x, y),
    }
}
