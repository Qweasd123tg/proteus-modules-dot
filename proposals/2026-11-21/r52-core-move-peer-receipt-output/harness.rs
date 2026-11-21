// Test-only entry point copied into proteus-contracts/tests by probe.py.
#![allow(dead_code)]
pub use proteus_contracts::{contracts, domain};

use serde_json::{Value, json};

#[path = "r52_peer_cases/base.rs"]
mod base;
#[path = "r52_peer_cases/candidate.rs"]
mod candidate;
#[path = "../src/test_alloc.rs"]
mod test_alloc;

mod child {
    pub struct ChildProcess;
    impl ChildProcess {
        pub async fn send(
            &mut self,
            _: &proteus_contracts::app_protocol::StdioRequest,
        ) -> anyhow::Result<()> {
            unreachable!("the allocator probe covers receipt handling, not outbound sends")
        }
    }
}

struct Case<'a> {
    name: &'a str,
    id: &'a str,
    ok: bool,
    error: Option<&'a str>,
    output: Option<Value>,
    expected_kind: &'a str,
}

#[test]
fn actual_peer_receipt_handler_is_byte_equal_and_moves_owned_payload() {
    let text = "second result: Привет 🌍\r\n\0";
    let large_text = "a".repeat(65_536);
    // Representative shaped values, not captured messages or workload frequency.
    let report = json!({
        "agent_messages_delivered": 1,
        "model_ref": {"provider": "fixture", "model": "local"},
        "usage": {"input_tokens": 508, "output_tokens": 1024},
        "sources": (0..16).map(|n| format!("ref-{n:02}")).collect::<Vec<_>>(),
    });
    let nested_report = json!({
        "phases": (0..24).map(|n| json!({
            "step":n, "summary":format!("step {n:02} {}", "b".repeat(120))
        })).collect::<Vec<_>>(),
        "inner": {"cached":true,"score":1.75},
    });
    let mut all = Vec::new();
    for Case {
        name,
        id,
        ok,
        error,
        output,
        expected_kind,
    } in [
        Case {
            name: "unknown",
            id: "primary",
            ok: true,
            error: None,
            output: Some(json!({"text":"primary answer","metadata":report})),
            expected_kind: "unrelated",
        },
        Case {
            name: "rejected_default",
            id: "receipt",
            ok: false,
            error: None,
            output: None,
            expected_kind: "error",
        },
        Case {
            name: "rejected_explicit",
            id: "receipt",
            ok: false,
            error: Some("declined locally"),
            output: Some(json!({"text":"not accepted","metadata":null})),
            expected_kind: "error",
        },
        Case {
            name: "queued",
            id: "receipt",
            ok: true,
            error: None,
            output: Some(json!({"queued":true,"accepted":true})),
            expected_kind: "queued",
        },
        Case {
            name: "queued_rejected",
            id: "receipt",
            ok: true,
            error: None,
            output: Some(
                json!({"queued":true,"accepted":false,"text":"do not accept","metadata":null}),
            ),
            expected_kind: "error",
        },
        Case {
            name: "queued_missing_status",
            id: "receipt",
            ok: true,
            error: None,
            output: Some(json!({"queued":true})),
            expected_kind: "error",
        },
        Case {
            name: "missing_output",
            id: "receipt",
            ok: true,
            error: None,
            output: None,
            expected_kind: "error",
        },
        Case {
            name: "null_output",
            id: "receipt",
            ok: true,
            error: None,
            output: Some(Value::Null),
            expected_kind: "error",
        },
        Case {
            name: "wrong_text_type",
            id: "receipt",
            ok: true,
            error: None,
            output: Some(json!({"text":5,"metadata":null})),
            expected_kind: "error",
        },
        Case {
            name: "invalid_positional_shape",
            id: "receipt",
            ok: true,
            error: None,
            output: Some(json!([null, {}])),
            expected_kind: "error",
        },
        Case {
            name: "unknown_fields",
            id: "receipt",
            ok: true,
            error: None,
            output: Some(
                json!({"text":text,"metadata":null,"ignored_extra":"preserve existing behavior"}),
            ),
            expected_kind: "complete",
        },
        Case {
            name: "queued_string_not_ack",
            id: "receipt",
            ok: true,
            error: None,
            output: Some(json!({"text":text,"metadata":null,"queued":"true"})),
            expected_kind: "complete",
        },
        Case {
            name: "unicode_text",
            id: "receipt",
            ok: true,
            error: None,
            output: Some(json!({"text":text,"metadata":null})),
            expected_kind: "complete",
        },
        Case {
            name: "large_text",
            id: "receipt",
            ok: true,
            error: None,
            output: Some(json!({"text":large_text,"metadata":null})),
            expected_kind: "complete",
        },
        Case {
            name: "summary_metadata",
            id: "receipt",
            ok: true,
            error: None,
            output: Some(json!({"text":text,"metadata":report})),
            expected_kind: "complete",
        },
        Case {
            name: "nested_metadata",
            id: "receipt",
            ok: true,
            error: None,
            output: Some(json!({"text":text,"metadata":nested_report})),
            expected_kind: "complete",
        },
    ] {
        let old = base::proof_cases::run(id, ok, output.clone(), error);
        let new = candidate::proof_cases::run(id, ok, output.clone(), error);
        assert_eq!(
            serde_json::to_vec(&old.0).unwrap(),
            serde_json::to_vec(&new.0).unwrap(),
            "{name}: serialized payload/error/settlement changed"
        );
        assert_eq!(new.0["kind"], expected_kind, "{name}");
        if expected_kind == "unrelated" {
            assert_eq!(old.2, output, "{name}: baseline lost primary Send payload");
            assert_eq!(new.2, output, "{name}: candidate lost primary Send payload");
        } else if ok {
            assert!(
                new.2.is_none(),
                "{name}: candidate did not take its owned receipt"
            );
        } else {
            assert_eq!(new.2, output, "{name}: failure should not take receipt");
        }
        match name {
            "unknown"
            | "rejected_default"
            | "rejected_explicit"
            | "queued"
            | "queued_rejected"
            | "queued_missing_status"
            | "missing_output"
            | "null_output" => assert_eq!(
                (old.1.calls, old.1.bytes),
                (new.1.calls, new.1.bytes),
                "{name}"
            ),
            _ => {
                assert!(new.1.calls < old.1.calls, "{name}");
                assert!(new.1.bytes < old.1.bytes, "{name}");
            }
        }
        println!(
            "r52 {name}: calls {}->{}, bytes {}->{}",
            old.1.calls, new.1.calls, old.1.bytes, new.1.bytes
        );
        all.push(json!([name, new.0]));
    }
    let snapshot = std::env::var("R52_RECEIPT_SNAPSHOT").expect("output path");
    std::fs::write(snapshot, serde_json::to_vec(&all).unwrap()).unwrap();
}
