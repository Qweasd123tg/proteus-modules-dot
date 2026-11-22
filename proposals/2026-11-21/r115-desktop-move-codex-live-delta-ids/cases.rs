use crate::agents::codex::{Event, Item, ItemKind, projection};
use crate::transcript::{Change, Role, Transcript};
use serde_json::{Value, json};
use std::sync::Arc;
const CAP: usize = 128 * 1024;
const TURN: &str = "turn-00000000-0000-4000-8000-000000000001";
const ITEM: &str = "item-00000000-0000-4000-8000-000000000001";

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
struct Outcome {
    change: Change,
    trimmed: Change,
    append_bound: Option<usize>,
    output: bool,
}
#[derive(Default)]
struct State {
    output: bool,
}
struct Session {
    transcript: Transcript,
}
struct Binding {
    live_headroom: usize,
}
struct Carrier {
    session: Session,
    state: State,
    codex: Option<Binding>,
}
impl Carrier {
    fn new(mut transcript: Transcript) -> Self {
        let (_, live_headroom) = transcript.external_trim_budget(50, 8 * 1024 * 1024);
        Self {
            session: Session { transcript },
            state: State::default(),
            codex: Some(Binding { live_headroom }),
        }
    }
    fn transcript(&self) -> &Transcript {
        &self.session.transcript
    }
    fn row(&self, n: usize) -> &crate::transcript::Entry {
        &self.transcript().entries()[n]
    }
}
include!("lifted.rs");

fn assistant(turn: &str, id: &str, text: &str, done: bool) -> Item {
    Item {
        id: id.into(),
        turn_id: turn.into(),
        kind: ItemKind::Assistant { text: text.into() },
        status: if done {
            "completed".into()
        } else {
            "inProgress".into()
        },
        timestamp_ms: Some(19),
    }
}
fn delta(kind: usize, turn: &str, id: &str, text: &str) -> Event {
    let method = match kind {
        0 => "item/agentMessage/delta",
        1 => "item/reasoning/summaryTextDelta",
        2 => "item/commandExecution/outputDelta",
        _ => "item/fileChange/outputDelta",
    };
    projection::notification(
        method,
        &json!({"threadId":"fixture","turnId":turn,"itemId":id,"delta":text}),
    )
    .unwrap()
}
fn work(label: &str, carrier: &mut Carrier, events: Vec<Event>) -> Vec<Outcome> {
    let ids = events
        .iter()
        .map(|ev| match ev {
            Event::TextDelta { id, turn_id, .. }
            | Event::ReasoningDelta { id, turn_id, .. }
            | Event::ToolOutputDelta { id, turn_id, .. } => (
                usize::from(!id.is_empty()) + usize::from(!turn_id.is_empty()),
                id.len() + turn_id.len(),
            ),
            _ => unreachable!(),
        })
        .collect::<Vec<_>>();
    let n = events.len();
    let count = ids.iter().map(|p| p.0).sum::<usize>();
    let total = ids.iter().map(|p| p.1).sum::<usize>();
    let mut outputs = Vec::with_capacity(n);
    let (_, calls, bytes) = crate::measurement(|| {
        for ev in events {
            outputs.push(carrier.fold(std::hint::black_box(ev)));
        }
    });
    eprintln!("WORK {label} {}", json!([n, count, total, calls, bytes]));
    outputs
}
fn trace(label: &str, carrier: &Carrier, outcomes: &[Outcome]) {
    let t = carrier.transcript();
    let rows=t.entries().iter().map(|e| {
        let (turn,id)=t.external_identity(e.key).unwrap();
        assert!(t.external_contains(turn,id));
        json!({"key":e.key,"identity":[turn,id],"role":format!("{:?}",e.role),"text":e.text.as_ref(),
              "message_id":e.message_id,"images":e.images,"tool":e.tool,"subagent":e.subagent,
              "time":e.time,"streaming":e.streaming,"retained":e.retained_bytes()})
    }).collect::<Vec<_>>();
    eprintln!(
        "TRACE {label} {}",
        json!({"rows":rows,"output":carrier.state.output,
          "headroom":carrier.codex.as_ref().unwrap().live_headroom,
          "outcomes":outcomes.iter().map(|o|format!("{o:?}")).collect::<Vec<_>>() })
    );
}

#[test]
fn ordinary_128_projected_assistant_fragments_with_existing_identity() {
    eprintln!("ARM {}", env!("R115_ARM"));
    let mut t = Transcript::default();
    t.external_upsert(assistant(TURN, ITEM, "prefix: ", false));
    t.external_upsert(assistant("peer", ITEM, "different turn", false));
    let peer = Arc::clone(&t.entries()[1].text);
    let mut carrier = Carrier::new(t);
    let parts = (0..128).map(|i| format!("é{i} 🦀 ")).collect::<Vec<_>>();
    let events = parts.iter().map(|s| delta(0, TURN, ITEM, s)).collect();
    let receipts = work("ordinary-live-128", &mut carrier, events);
    assert_eq!(receipts.len(), 128);
    for (r, p) in receipts.iter().zip(&parts) {
        assert_eq!(
            *r,
            Outcome {
                change: Change::Updated(0),
                trimmed: Change::None,
                append_bound: Some(p.len()),
                output: true
            }
        );
    }
    assert_eq!(
        carrier.row(0).text.as_ref(),
        format!("prefix: {}", parts.concat())
    );
    assert_eq!(carrier.row(0).key, 1);
    assert_eq!(carrier.row(0).time, Some(19));
    assert_eq!(carrier.row(1).key, 2);
    assert!(Arc::ptr_eq(&carrier.row(1).text, &peer));
    trace("ordinary-live-128", &carrier, &receipts);
}

#[test]
fn unseen_reasoning_tool_and_answer_move_through_the_existing_provisional_path() {
    let mut c = Carrier::new(Transcript::default());
    let events = vec![
        delta(1, "turn-甲", "reason-🦀", "début"),
        delta(2, "turn-甲", "tool-🦀", "A\n"),
        delta(0, "turn-甲", "answer-🦀", "salut"),
    ];
    let missing = work("first-fragments", &mut c, events);
    assert_eq!(
        missing.iter().map(|r| r.change).collect::<Vec<_>>(),
        [Change::Pushed; 3]
    );
    assert_eq!(
        missing.iter().map(|r| r.output).collect::<Vec<_>>(),
        [false, true, true]
    );
    assert!(
        [0, 1, 2]
            .into_iter()
            .all(|i| c.row(i).streaming && c.row(i).time.is_none() && c.row(i).key == i as u64 + 1)
    );
    assert_eq!(c.row(0).role, Role::Reasoning);
    assert_eq!(c.row(1).role, Role::System);
    assert_eq!(c.row(2).role, Role::Assistant);
    let tool = c.row(1).tool.as_ref().unwrap();
    assert_eq!(tool.name, "Инструмент");
    assert_eq!(tool.call_id, "tool-🦀");
    assert_eq!(tool.status, "running");
    assert_eq!(tool.args, Value::Null);
    assert_eq!(tool.result.as_deref(), Some("A\n"));
    assert_eq!(c.row(0).text.as_ref(), "début");
    let updates = work(
        "mixed-existing",
        &mut c,
        vec![
            delta(1, "turn-甲", "reason-🦀", " raisonné"),
            delta(3, "turn-甲", "tool-🦀", "B\t🦀"),
            delta(0, "turn-甲", "answer-🦀", " voici"),
        ],
    );
    assert_eq!(
        updates.iter().map(|r| r.change).collect::<Vec<_>>(),
        [Change::Updated(0), Change::Updated(1), Change::Updated(2)]
    );
    assert_eq!(c.row(0).text.as_ref(), "début raisonné");
    assert_eq!(
        c.row(1).tool.as_ref().unwrap().result.as_deref(),
        Some("A\nB\t🦀")
    );
    assert_eq!(c.row(2).text.as_ref(), "salut voici");
    let empty_miss = c.fold(delta(2, "", "empty-tool", ""));
    assert_eq!(empty_miss.change, Change::Pushed);
    let empty_tool = c.row(3).tool.as_ref().unwrap();
    assert_eq!(empty_tool.call_id, "empty-tool");
    assert!(empty_tool.result.is_none());
    assert!(c.row(3).streaming);
    let mut both = missing;
    both.extend(updates);
    both.push(empty_miss);
    trace("first-and-mixed", &c, &both);
}

#[test]
fn completed_empty_and_utf8_boundaries_preserve_bytes_and_keys() {
    let mut t = Transcript::default();
    t.external_upsert(assistant("t", "completed", "fixed", true));
    t.external_upsert(assistant("t", "edge", &"x".repeat(CAP - 1), false));
    t.external_upsert(assistant("", "", "empty IDs", false));
    let mut c = Carrier::new(t);
    let done = work(
        "ignored-existing",
        &mut c,
        vec![
            delta(0, "t", "completed", "late"),
            delta(0, "t", "edge", ""),
            delta(0, "t", "edge", "🦀"),
        ],
    );
    assert!(
        done.iter()
            .all(|o| o.change == Change::None && o.trimmed == Change::None)
    );
    assert_eq!(c.row(0).text.as_ref(), "fixed");
    assert_eq!(c.row(1).text.len(), CAP - 1);
    assert_eq!(
        c.fold(delta(0, "t", "edge", "z")).change,
        Change::Updated(1)
    );
    assert_eq!(c.fold(delta(0, "t", "edge", "!")).change, Change::None);
    assert_eq!(c.row(1).text.len(), CAP);
    assert!(c.row(1).text.ends_with('z'));
    let empty = work("empty-identity", &mut c, vec![delta(0, "", "", "!")]);
    assert_eq!(empty[0].change, Change::Updated(2));
    assert_eq!(c.row(2).text.as_ref(), "empty IDs!");
    // Wrong-kind tool output still returns Updated as before, without fabricating a tool.
    assert_eq!(
        c.fold(delta(2, "", "", "ignored")).change,
        Change::Updated(2)
    );
    assert!(c.row(2).tool.is_none());
    trace("guards-and-boundaries", &c, &[done, empty].concat());
}

#[test]
fn first_oversized_projection_replay_and_exact_live_trim() {
    let mut c = Carrier::new(Transcript::default());
    let huge = "🦀".repeat(CAP / 4 + 1);
    let event = delta(1, "t", "wide", &huge);
    let Event::ReasoningDelta { delta: shown, .. } = &event else {
        unreachable!()
    };
    assert!(shown.len() > CAP && shown.ends_with("128 КиБ]"));
    let expected = shown.clone();
    let first = c.fold(event);
    assert_eq!(first.change, Change::Pushed);
    assert_eq!(c.row(0).text.as_ref(), expected);
    assert_eq!(c.fold(delta(1, "t", "wide", "more")).change, Change::None);
    let mut changes = vec![first];
    for i in 0..50 {
        let id = format!("fresh{i}");
        changes.push(c.fold(delta(0, "t", &id, "inert")));
    }
    assert_eq!(
        changes.last().unwrap().trimmed,
        Change::Spliced {
            start: 0,
            removed: 1,
            inserted: 0
        }
    );
    assert_eq!(c.transcript().entries().len(), 50);
    assert!(c.transcript().external_identity(1).is_none());
    assert!(!c.transcript().external_contains("t", "wide"));
    assert_eq!(c.row(0).key, 2);
    assert_eq!(c.row(49).key, 51);
    let after = c.fold(delta(1, "t", "wide", "recreated"));
    assert_eq!(after.change, Change::Pushed);
    assert_eq!(
        after.trimmed,
        Change::Spliced {
            start: 0,
            removed: 1,
            inserted: 0
        }
    );
    assert_eq!(c.row(49).key, 52);
    assert_eq!(c.row(49).text.as_ref(), "recreated");
    changes.push(after);
    trace("trim-and-replay", &c, &changes);
}
