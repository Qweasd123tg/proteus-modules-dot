use domain::{
    Event, EventContext, EventEnvelope, ToolCall, ToolResult, new_session_id, new_thread_id,
    new_turn_id,
};
pub(crate) use proteus_contracts::{contracts, domain, model_standard};
use serde_json::{Value, json};

mod test_alloc;
mod transcript {
    pub use proteus_contracts::app_protocol::{
        AppTranscriptMessage, AppTranscriptSubagent, AppTranscriptTool,
    };
}

// The production modules and all their existing tests are included without editing their bodies.
macro_rules! projection {
    ($version:ident) => {
        mod $version {
            use crate::{
                domain::EventEnvelope,
                test_alloc::{Allocations, measure},
                transcript,
            };
            mod turn_progress;
            pub(super) fn run(
                events: &[EventEnvelope],
            ) -> (serde_json::Value, Allocations, Allocations) {
                let mut state = turn_progress::TurnProgress::default();
                state.apply(&events[0]);
                state.apply(&events[1]);
                let (_, args_cost) = measure(|| state.apply(&events[2]));
                let (_, metadata_cost) = measure(|| state.apply(&events[3]));
                (
                    serde_json::to_value(state.snapshot()).unwrap(),
                    args_cost,
                    metadata_cost,
                )
            }
        }
    };
}
projection!(baseline);
projection!(candidate);

fn projection_fixture(v: Value) -> Vec<EventEnvelope> {
    let session = new_session_id();
    let root = new_thread_id();
    let child = new_thread_id();
    let turn = Some(new_turn_id());
    let mut result = ToolResult::ok("child-call".into(), "ok");
    result.metadata = v.clone();
    [
        (
            root,
            Event::ToolCallRequested {
                call: ToolCall::new("spawn", "spawn_agent", json!({"task_name":"scan"})),
            },
        ),
        (
            root,
            Event::SubagentStarted {
                role: "worker".into(),
                description: Some("scan".into()),
                child_thread_id: child,
            },
        ),
        (
            child,
            Event::ToolCallRequested {
                call: ToolCall::new("child-call", "example", v),
            },
        ),
        (child, Event::ToolFinished { result }),
    ]
    .into_iter()
    .enumerate()
    .map(|(i, (thread, event))| {
        EventEnvelope::new(EventContext::new(session, thread, turn), i as u64, event)
    })
    .collect()
}

#[test]
fn same_snapshots_and_bounded_allocation_for_requests_and_results() {
    const LIMIT: usize = 8000;
    for (case, value) in [
        ("small", json!({"path":"src/пример.rs"})),
        ("8000", Value::String("a".repeat(LIMIT - 2))),
        ("8001", Value::String("a".repeat(LIMIT - 1))),
        ("utf8_split", Value::String("a".repeat(LIMIT - 3) + "😀x")),
        ("64KiB-flat", Value::String("x".repeat(65536))),
        ("4MiB-flat", Value::String("x".repeat(4194304))),
        (
            "nested_escaped",
            json!({"rows":vec![json!({"description":"цена\n\"😀","score":42});32768]}),
        ),
    ] {
        let encoded = value.to_string();
        let events = projection_fixture(value.clone());
        let before = baseline::run(&events);
        let after = candidate::run(&events);
        assert_eq!(before.0, after.0, "{case}");
        let card = &after.0[1]["subagent"]["tools"][0];
        let expected = if encoded.len() > LIMIT {
            let end = encoded.floor_char_boundary(LIMIT);
            json!({"truncated":true,"preview":&encoded[..end]})
        } else {
            value
        };
        assert_eq!(card["args"], expected, "{case}");
        assert_eq!(card["metadata"], expected, "{case}");
        assert_eq!(card["status"], "done");
        eprintln!(
            "{case} encoded={} request: {} -> {} bytes ({} -> {} calls); result: {} -> {} bytes ({} -> {} calls)",
            encoded.len(),
            before.1.bytes,
            after.1.bytes,
            before.1.calls,
            after.1.calls,
            before.2.bytes,
            after.2.bytes,
            before.2.calls,
            after.2.calls
        );
        if encoded.len() > 65536 {
            assert!(
                after.1.bytes < 5 * LIMIT && after.2.bytes < 5 * LIMIT,
                "{case}"
            );
            assert!(
                before.1.bytes >= encoded.len() && before.2.bytes >= encoded.len(),
                "{case}"
            );
        }
    }
}
