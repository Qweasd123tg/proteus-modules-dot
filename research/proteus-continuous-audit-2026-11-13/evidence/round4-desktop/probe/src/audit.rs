use crate::transcript::{Transcript, Change};
use proteus_contracts::domain::{Event, ToolCall, ToolResult};
use serde_json::json;
use uuid::Uuid;

fn start(transcript: &mut Transcript, child: Uuid) {
    transcript.apply_runtime(Uuid::from_u128(1), &Event::SubagentStarted {
        role: "explorer".into(), description: None, child_thread_id: child,
    });
}
fn request(id: &str) -> Event {
    Event::ToolCallRequested { call: ToolCall::new(id, "read_file", json!({"path":"fixture.txt"})) }
}
fn finish(id: &str, body: &str) -> Event {
    Event::ToolFinished { result: ToolResult::ok(id.to_owned(), body) }
}

#[test]
fn audit_live_subagent_discards_every_tool_after_first_64() {
    let child = Uuid::from_u128(2);
    let mut transcript = Transcript::default();
    start(&mut transcript, child);
    for n in 0..64 {
        let id = format!("call_{n}");
        transcript.apply_runtime(child, &request(&id));
        transcript.apply_runtime(child, &finish(&id, "completed"));
    }
    assert_eq!(transcript.apply_runtime(child, &request("call_64")), Change::Updated(0));
    let tools = &transcript.entries()[0].subagent.as_ref().unwrap().tools;
    assert_eq!(tools.len(), 64);
    assert!(!tools.iter().any(|t| t.call_id == "call_64"), "reproduces silent dropped newest call");
    assert_eq!(transcript.apply_runtime(child, &finish("call_64", "latest result")), Change::None);
    for n in 65..100 {
        let id = format!("call_{n}");
        transcript.apply_runtime(child, &request(&id));
        assert_eq!(transcript.apply_runtime(child, &finish(&id, "new result")), Change::None);
    }
    let tools = &transcript.entries()[0].subagent.as_ref().unwrap().tools;
    assert_eq!(tools.last().unwrap().call_id, "call_63");
    println!("Reproduced: 100 completed child calls, 64 visible, newest retained ID call_63; all 36 later results ignored.");
}

#[test]
fn audit_same_call_id_in_different_children_updates_wrong_child() {
    let a = Uuid::from_u128(2);
    let b = Uuid::from_u128(3);
    let mut transcript = Transcript::default();
    start(&mut transcript, a);
    start(&mut transcript, b);
    transcript.apply_runtime(a, &request("call_1"));
    transcript.apply_runtime(b, &request("call_1"));
    let changed = transcript.apply_runtime(a, &finish("call_1", "A own result"));
    assert_eq!(changed, Change::Updated(1));
    let a_tool = &transcript.entries()[0].subagent.as_ref().unwrap().tools[0];
    let b_tool = &transcript.entries()[1].subagent.as_ref().unwrap().tools[0];
    assert_eq!(a_tool.status, "running");
    assert_eq!(a_tool.result, None);
    assert_eq!(b_tool.status, "done");
    assert_eq!(b_tool.result.as_deref(), Some("A own result"));
    println!("Reproduced: finishing child A marks child B done with A's result; A remains running.");
}
