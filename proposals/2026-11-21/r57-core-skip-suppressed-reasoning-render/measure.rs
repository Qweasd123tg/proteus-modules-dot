// Paired presenter using fixed in-memory provider events and the production emitter.
use super::*;
use crate::{
    contracts::{
        CancellationToken, EventEmitter, EventSink, ExecutionScope, NoopExecutionRecorder,
    },
    domain::{
        EventEnvelope, SessionId, ThreadId, TurnId, new_session_id, new_thread_id, new_turn_id,
    },
    model_standard::{
        CanonicalMessage, CanonicalModelResponse, ContentPart, FinishReason, MessageRole,
    },
    r57_alloc::{Allocations, measure},
};
use futures_util::TryStreamExt;
use std::sync::{Arc, Mutex};

#[derive(Default)]
struct Capture(Mutex<Vec<Event>>);
#[async_trait::async_trait]
impl EventSink for Capture {
    async fn append(&self, e: EventEnvelope) -> anyhow::Result<()> {
        self.0.lock().unwrap().push(e.event);
        Ok(())
    }
}

fn drive(
    rt: &tokio::runtime::Runtime,
    events: Vec<ModelStreamEvent>,
    ids: (SessionId, ThreadId, TurnId),
    stock: bool,
    suppress: bool,
    cancelled: bool,
) -> ((Vec<ModelStreamEvent>, Vec<Event>), Allocations) {
    let sink = Arc::new(Capture::default());
    let token = CancellationToken::new();
    if cancelled {
        token.cancel();
    }
    let binding = ModelExecutionBinding::for_turn(
        ExecutionScope::fresh(token.clone()),
        Arc::new(EventEmitter::new(sink.clone())),
        ids.0,
        ids.1,
        ids.2,
        Arc::new(NoopExecutionRecorder),
    );
    let input: ModelEventStream = Box::pin(futures_util::stream::iter(events.into_iter().map(Ok)));
    let output = if stock {
        stock_present_stream(input, binding, suppress, None, token)
    } else {
        present_stream(input, binding, suppress, None, token)
    };
    let (canonical, alloc) = measure(|| rt.block_on(output.try_collect::<Vec<_>>()).unwrap());
    let published = std::mem::take(&mut *sink.0.lock().unwrap());
    ((canonical, published), alloc)
}

fn item(text: &str, count: usize) -> CanonicalMessage {
    let mut parts = vec![ContentPart::Text {
        text: " visible output 🌍 ".into(),
    }];
    for i in 0..count {
        parts.push(if i % 2 == 0 {
            ContentPart::ReasoningSummary {
                text: text.to_owned(),
            }
        } else {
            ContentPart::Reasoning {
                text: text.to_owned(),
                signature: Some("not for UI".into()),
            }
        });
    }
    CanonicalMessage::new(MessageRole::Assistant, parts)
}

#[test]
fn r57_paired_presentation_preserves_complete_stream_and_events() {
    let rt = tokio::runtime::Builder::new_current_thread()
        .enable_all()
        .build()
        .unwrap();
    rt.block_on(async {});
    let short = " readable мысль 🌍\r\n ";
    let large = "a".repeat(65_536);
    let mut snapshots = vec![];
    // expected counts: anonymous progress, identified deltas, reasoning complete, answer complete.
    for (
        label,
        text,
        part_count,
        n,
        anon,
        early,
        late,
        terminal_only,
        suppress,
        cancelled,
        expected,
    ) in [
        (
            "anonymous_short",
            short,
            1,
            1,
            true,
            false,
            false,
            false,
            false,
            false,
            (1, 0, 0, 1),
        ),
        (
            "anonymous_long",
            large.as_str(),
            1,
            1,
            true,
            false,
            false,
            false,
            false,
            false,
            (1, 0, 0, 1),
        ),
        (
            "anonymous_32_multi",
            short,
            4,
            32,
            true,
            false,
            false,
            false,
            false,
            false,
            (1, 0, 0, 32),
        ),
        (
            "identified_with_anonymous",
            short,
            4,
            1,
            true,
            true,
            false,
            false,
            false,
            false,
            (1, 1, 1, 1),
        ),
        (
            "late_identified",
            short,
            4,
            1,
            true,
            false,
            true,
            false,
            false,
            false,
            (1, 1, 1, 1),
        ),
        (
            "mixed_identified_ids",
            short,
            1,
            2,
            true,
            true,
            false,
            false,
            false,
            false,
            (1, 1, 1, 2),
        ),
        (
            "without_anonymous",
            short,
            1,
            1,
            false,
            false,
            false,
            false,
            false,
            false,
            (0, 0, 1, 1),
        ),
        (
            "terminal_only",
            short,
            1,
            1,
            false,
            false,
            false,
            true,
            false,
            false,
            (0, 0, 1, 1),
        ),
        (
            "empty_suppressed",
            "\u{2003}\n",
            1,
            1,
            true,
            false,
            false,
            false,
            false,
            false,
            (1, 0, 0, 1),
        ),
        (
            "transport_suppressed",
            short,
            4,
            1,
            true,
            true,
            false,
            false,
            true,
            false,
            (0, 0, 0, 0),
        ),
        (
            "cancelled",
            short,
            4,
            1,
            true,
            false,
            false,
            false,
            false,
            true,
            (0, 0, 0, 0),
        ),
    ] {
        let messages: Vec<_> = (0..n).map(|_| item(text, part_count)).collect();
        let mut events = vec![];
        if anon {
            events.push(ModelStreamEvent::ReasoningSummaryDelta {
                text: "anonymous progress".into(),
            });
        }
        let identified = || ModelStreamEvent::ReasoningDelta {
            message_id: messages[0].id,
            text: "identified progress".into(),
        };
        if early {
            events.push(identified());
        }
        if !terminal_only {
            events.extend(
                messages
                    .iter()
                    .cloned()
                    .map(|message| ModelStreamEvent::MessageCompleted { message }),
            );
        }
        if late {
            events.push(identified());
        }
        events.push(ModelStreamEvent::Response {
            response: CanonicalModelResponse::from_messages(messages, vec![], FinishReason::Stop),
        });
        let ids = (new_session_id(), new_thread_id(), new_turn_id());
        let (old, a) = drive(&rt, events.clone(), ids, true, suppress, cancelled);
        let (new, b) = drive(&rt, events.clone(), ids, false, suppress, cancelled);
        let old_wire = serde_json::to_vec(&old).unwrap();
        let new_wire = serde_json::to_vec(&new).unwrap();
        assert_eq!(new_wire, old_wire, "{label}: serialized output parity");
        assert_eq!(new.0, events, "{label}: provider stream changed");
        let mut counts = (0, 0, 0, 0);
        for event in &new.1 {
            match event {
                Event::AssistantReasoningDelta { .. } => counts.0 += 1,
                Event::AssistantReasoningTextDelta { .. } => counts.1 += 1,
                Event::AssistantReasoningMessageCompleted { .. } => counts.2 += 1,
                Event::AssistantMessageCompleted { .. } => counts.3 += 1,
                _ => panic!("unexpected event"),
            }
        }
        assert_eq!(counts, expected, "{label}");
        if label.starts_with("anonymous_")
            || label == "late_identified"
            || label == "mixed_identified_ids"
        {
            assert!(
                b.calls < a.calls && b.bytes < a.bytes,
                "{label}: expected savings"
            );
        } else {
            assert_eq!(
                (a.calls, a.bytes),
                (b.calls, b.bytes),
                "{label}: control allocations"
            );
        }
        println!(
            "r57 {label}: calls {}->{}, bytes {}->{}",
            a.calls, b.calls, a.bytes, b.bytes
        );
        snapshots.push(new_wire);
    }
    let bytes = snapshots.concat();
    std::fs::write(std::env::var("R57_PRESENTATION_SNAPSHOT").unwrap(), bytes).unwrap();
}
