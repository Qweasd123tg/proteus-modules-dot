// Public HistoryCapture API controls. Crafted malformed suffixes are not
// asserted to be reachable via strict journal validation or live checkpoint.
use crate::{OBS, meter, proof};
use proteus_contracts::{
    contracts::WorkflowToolResultBinding,
    domain::{ToolCall, ToolContent, ToolResult},
    model_standard::{CanonicalMessage, ContentPart, MessageRole},
};
use proteus_session_semantics::journal::HistoryCapture;
use serde_json::{Value, json};
use uuid::Uuid;

fn row(id: u128, role: MessageRole, parts: Vec<ContentPart>) -> CanonicalMessage {
    let mut m = CanonicalMessage::new(role, parts);
    m.id = Uuid::from_u128(id);
    for (i, p) in m.parts.iter_mut().enumerate() {
        p.part_id = Uuid::from_u128(id + 1 + i as u128);
    }
    m
}
fn result(call: &str) -> ToolResult {
    ToolResult::new(
        call.into(),
        false,
        "héllo\n\"\\".repeat(17),
        vec![
            ToolContent::Text {
                text: "first\n".into(),
            },
            ToolContent::Json {
                value: json!({"ordered":{"z":2,"a":1},"arr":[true,{"other":"🍰"}]}),
            },
        ],
        Some("synthetic failure with raw output".repeat(7)),
        json!({"second": {"x": 3, "b": 4}, "first": ["雪", 0]}),
    )
}
fn fixture(ids: &[&str]) -> (Vec<CanonicalMessage>, Vec<WorkflowToolResultBinding>) {
    let parts = ids
        .iter()
        .map(|id| ContentPart::ToolCall {
            call: ToolCall::new(*id, "probe", json!({"synthetic":1})),
        })
        .collect();
    let m = row(347100, MessageRole::Assistant, parts);
    let bindings = ids
        .iter()
        .enumerate()
        .map(|(i, id)| {
            let mut b =
                WorkflowToolResultBinding::new(ToolCall::new(*id, "probe", json!({"synthetic":1})));
            b.message_id = Uuid::from_u128(347200 + i as u128 * 10);
            b.part_id = Uuid::from_u128(347201 + i as u128 * 10);
            b
        })
        .collect();
    (vec![m], bindings)
}

fn call_of(m: &CanonicalMessage) -> &str {
    match &m.parts[0].payload {
        ContentPart::ToolResult { result } => &result.call_id,
        _ => "",
    }
}
fn rebase_case(candidate: bool, mode: &str) -> (Value, Value) {
    let ids: &[&str] = if mode == "mismatch-duplicate" {
        &["b", "a"]
    } else {
        &["a", "b"]
    };
    proof::configure(candidate, None);
    let (prefix, bindings) = fixture(ids);
    let mut cap = HistoryCapture::new(&prefix, &bindings).unwrap();
    let mut current = prefix.clone();
    let mut proposed = prefix;
    if mode == "mismatch-duplicate" {
        assert!(cap.record(&mut current, &result("b")).unwrap());
    }
    assert!(cap.record(&mut current, &result("a")).unwrap());

    let last = current.last_mut().unwrap();
    match mode {
        "mismatch-unknown" | "mismatch-other" | "mismatch-duplicate" => {
            let ContentPart::ToolResult { result } = &mut last.parts[0].payload else {
                unreachable!();
            };
            result.call_id = if mode == "mismatch-unknown" {
                "unknown"
            } else {
                "b"
            }
            .into();
        }
        "canonical-changed" => {
            // Do not touch the selected ToolResult: another canonical field
            // must still be checked even if the whole typed payload matches.
            last.role = MessageRole::Assistant;
        }
        "suffix-missing" => {
            last.parts[0].payload = ContentPart::Text {
                text: "changed".into(),
            };
        }
        _ => {}
    }
    proposed.push(row(
        347400,
        MessageRole::Assistant,
        vec![ContentPart::Text {
            text: "new prefix".into(),
        }],
    ));
    if mode == "prefix-loss" {
        proposed[0].name = Some("mutated canonical prefix".into());
    } else if mode == "untracked-extra" {
        current.push(bindings[1].message(result("b")));
    }
    let declare = if mode.starts_with("first-duplicate") {
        let exact = current.last().unwrap().clone();
        let mut altered = exact.clone();
        altered.parts[0].payload = ContentPart::Text {
            text: "changed".into(),
        };
        if mode == "first-duplicate-equal" {
            proposed.extend([exact, altered]);
        } else {
            proposed.extend([altered, exact]);
        }
        &[][..]
    } else {
        &bindings
    };

    let snapshot = current.clone();
    proof::configure(candidate, Some(OBS));
    meter::start();
    let rebased = proof::rebase(&cap, &current, &proposed, declare, false);
    let stats = meter::take();
    proof::configure(candidate, None);
    assert_eq!(current, snapshot);
    let expect_error = match mode {
        "mismatch-duplicate" => Some("checkpoint received a duplicate tool result"),
        "canonical-changed" | "suffix-missing" => Some("checkpoint result suffix was changed"),
        "first-duplicate-unequal" => Some("checkpoint changed a committed tool result"),
        "prefix-loss" | "untracked-extra" => {
            Some("checkpoint discarded committed history without a new compaction")
        }
        _ => None,
    };
    let outcome = if let Some(expected) = expect_error {
        assert_eq!(rebased.unwrap_err().to_string(), expected);
        json!({"error":expected})
    } else {
        let (mut new_cap, mut h) = rebased.unwrap();
        let mut expected = proposed.clone();
        if mode == "mismatch-other" {
            let new_row = bindings[1].message(result("b"));
            assert_eq!(call_of(&h[proposed.len()]), "b");
            expected.push(new_row);
        }
        assert_eq!(h, expected);
        assert_eq!(
            serde_json::to_vec(&h).unwrap(),
            serde_json::to_vec(&expected).unwrap()
        );
        // Unknown mismatch must not leave the raw source binding marked.
        // Other mismatch must mark b but leave a pending.
        if mode.starts_with("mismatch") {
            let index = new_cap.record_at(&mut h, &result("a")).unwrap();
            assert_eq!(index, Some(proposed.len()));
            if mode == "mismatch-other" {
                assert_eq!(
                    new_cap
                        .record_at(&mut h, &result("b"))
                        .unwrap_err()
                        .to_string(),
                    "checkpoint received a duplicate tool result"
                );
            }
        }
        json!({
            "error":null,
            "result_ids":expected[proposed.len()..].iter().map(|m| m.id).collect::<Vec<_>>(),
            "subsequent_ids":h[proposed.len()..].iter().map(|m|m.id).collect::<Vec<_>>(),
            "wire_sha256":crate::digest(&expected),
        })
    };
    (outcome, stats)
}

fn record_case(candidate: bool, mode: &str) -> (Value, Value) {
    proof::configure(candidate, None);
    let (prefix, bindings) = fixture(&["a", "b"]);
    let mut cap = HistoryCapture::new(&prefix, &bindings).unwrap();
    let mut history = prefix;
    if mode == "record-duplicate" {
        assert_eq!(cap.record_at(&mut history, &result("b")).unwrap(), Some(1));
    } else if mode == "record-lost" {
        history.clear();
    }
    let before = history.clone();
    proof::configure(candidate, Some(OBS));
    meter::start();
    let recorded = cap.record_at(
        &mut history,
        &result(match mode {
            "record-unbound" => "unknown",
            "record-duplicate" => "b",
            _ => "a",
        }),
    );
    let stats = meter::take();
    proof::configure(candidate, None);
    let v = match mode {
        "record-unbound" => {
            assert_eq!(recorded.unwrap(), None);
            assert_eq!(history, before);
            json!({"index":null,"error":null})
        }
        "record-duplicate" | "record-lost" => {
            let err = if mode == "record-lost" {
                "checkpoint history suffix was lost"
            } else {
                "checkpoint received a duplicate tool result"
            };
            assert_eq!(recorded.unwrap_err().to_string(), err);
            assert_eq!(history, before);
            json!({"error":err})
        }
        "record-bound" => {
            assert_eq!(recorded.unwrap(), Some(1));
            let mut expected = before;
            expected.push(bindings[0].message(result("a")));
            assert_eq!(expected, history);
            assert_eq!(
                serde_json::to_vec(&expected).unwrap(),
                serde_json::to_vec(&history).unwrap()
            );
            json!({"index":1,"error":null,"wire_sha256":crate::digest(&history)})
        }
        _ => unreachable!(),
    };
    (v, stats)
}
pub(crate) fn run() {
    for mode in [
        "mismatch-unknown",
        "mismatch-other",
        "mismatch-duplicate",
        "canonical-changed",
        "suffix-missing",
        "first-duplicate-equal",
        "first-duplicate-unequal",
        "prefix-loss",
        "untracked-extra",
        "record-unbound",
        "record-duplicate",
        "record-lost",
        "record-bound",
    ] {
        let run = |candidate| {
            if mode.starts_with("record-") {
                record_case(candidate, mode)
            } else {
                rebase_case(candidate, mode)
            }
        };
        let (stock, as_) = run(false);
        let (candidate, ac) = run(true);
        assert_eq!(stock, candidate, "{mode}");
        println!(
            "{}",
            json!({"direct":mode,"outcome":stock,"meters":{"stock":as_,"candidate":ac}})
        );
    }
}
