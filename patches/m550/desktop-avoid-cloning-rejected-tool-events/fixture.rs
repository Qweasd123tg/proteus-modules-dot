use crate::{
    meter::{Count, measure},
    transcript::{Change, Transcript},
};
use proteus_contracts::{
    app_protocol::{AppServerEvent, AppTranscriptSubagent},
    domain::{Event, EventContext, EventEnvelope, ToolCall},
};
use serde_json::{Value, json};
use std::{
    hash::{DefaultHasher, Hash, Hasher},
    sync::Arc,
};
use uuid::Uuid;

const ROOT: u128 = 881;
const CHILD: u128 = 882;
const OTHER: u128 = 883;
const TIMESTAMP: i64 = 1_763_467_000_020;
fn uid(n: u128) -> Uuid {
    Uuid::from_u128(n)
}
fn begin(t: &mut Transcript, n: u128) {
    assert_eq!(
        t.apply_runtime(
            uid(ROOT),
            &Event::SubagentStarted {
                role: "fixture".into(),
                description: Some("context".into()),
                child_thread_id: uid(n),
            },
        ),
        Change::Pushed
    );
}
fn fixture(n: usize) -> Transcript {
    let mut t = Transcript::default();
    t.set_root_thread(Some(uid(ROOT)));
    begin(&mut t, CHILD);
    for i in 0..n {
        let call = ToolCall::new(format!("kept-{i}"), "synthetic", json!({"i":i}));
        assert_eq!(
            t.apply_runtime(uid(CHILD), &Event::ToolCallRequested { call }),
            Change::Updated(0)
        );
    }
    t
}
fn child(t: &Transcript, index: usize) -> &Arc<AppTranscriptSubagent> {
    t.entries()[index].subagent.as_ref().unwrap()
}
fn large_args() -> Value {
    json!({
        "z_value":"абвЖ:fixture-".repeat(96_000),
        "m_metadata":{"b":2,"a":[0,2,3],"c":"block".repeat(80_000)},
        "a_records": (0..64).map(|i|json!({"offset":i,"alias":"sample".repeat(640)})).collect::<Vec<_>>()
    })
}
fn request(n: u128, key: &str, args: Value) -> (AppServerEvent, usize) {
    let mut envelope = EventEnvelope::new(
        EventContext::new(uid(101), uid(n), Some(uid(102))),
        19,
        Event::ToolCallRequested {
            call: ToolCall::new(key, "synthetic", args),
        },
    );
    envelope.timestamp_ms = TIMESTAMP;
    envelope.event_id = uid(103);
    let wire = serde_json::to_vec(&AppServerEvent::Runtime {
        envelope: Box::new(envelope),
    })
    .unwrap();
    let len = wire.len();
    (serde_json::from_slice(&wire).unwrap(), len)
}
fn route(t: &mut Transcript, event: &AppServerEvent) -> Change {
    let AppServerEvent::Runtime { envelope } = event else {
        panic!("expected typed runtime");
    };
    // Same production reducer and timestamp route as Chat's typed event pump.
    let change = t.apply_runtime(envelope.thread_id, &envelope.event);
    t.stamp(change, envelope.timestamp_ms);
    change
}
fn canonical(t: &Transcript) -> u64 {
    let mut h = DefaultHasher::new();
    for e in t.entries() {
        (
            e.key,
            e.message_id,
            e.role,
            &*e.text,
            e.time,
            e.streaming,
            e.retained_bytes(),
        )
            .hash(&mut h);
        serde_json::to_vec(&e.images).unwrap().hash(&mut h);
        serde_json::to_vec(&e.tool.as_deref()).unwrap().hash(&mut h);
        serde_json::to_vec(&e.subagent.as_deref())
            .unwrap()
            .hash(&mut h);
    }
    h.finish()
}
fn emit(name: &str, count: Count, wire: usize, t: &Transcript) {
    println!(
        "M404_TOOL {name} {} {} {} {} {} {} {} {}",
        count.requests,
        count.bytes,
        count.live,
        count.peak,
        count.largest,
        wire,
        t.entries().len(),
        canonical(t)
    );
}
#[test]
fn typed_full_child_does_not_detach_or_grow_under_extra_large_requests() {
    let (request, wire) = request(CHILD, "above-cap", large_args());
    assert!((2_000_000..4_000_000).contains(&wire));
    let mut t = fixture(64);
    let archive = t.clone();
    assert!(Arc::ptr_eq(child(&t, 0), child(&archive, 0)));
    let before = canonical(&t);
    let ((), alloc) = measure(|| {
        for _ in 0..4 {
            assert_eq!(route(&mut t, &request), Change::Updated(0));
        }
    });
    assert!(Arc::ptr_eq(child(&t, 0), child(&archive, 0)));
    assert_eq!(child(&t, 0).tools.len(), 64);
    assert_eq!(t.entries().len(), 1);
    assert_eq!(canonical(&archive), before);
    assert_eq!(canonical(&t), before);
    assert_eq!(alloc.live, 0);
    emit("four-large-over-cap", alloc, wire, &t);
}
#[test]
fn at_limit_is_admitted_with_complete_typed_arguments_and_consistent_cow() {
    let args = large_args();
    let (add, wire) = request(CHILD, "at-64", args.clone());
    let mut t = fixture(63);
    let archive = t.clone();
    let (change, alloc) = measure(|| route(&mut t, &add));
    assert_eq!(change, Change::Updated(0));
    assert_eq!(t.entries().len(), 1);
    let live = child(&t, 0);
    assert!(!Arc::ptr_eq(live, child(&archive, 0)));
    assert_eq!(child(&archive, 0).tools.len(), 63);
    assert_eq!(live.tools.len(), 64);
    let tool = &live.tools.last().unwrap();
    assert_eq!(tool.call_id, "at-64");
    assert_eq!(tool.status, "running");
    assert!(tool.terminal.is_none() && tool.result.is_none() && tool.metadata.is_null());
    assert_eq!(tool.args, args);
    assert_eq!(
        serde_json::to_vec(&tool.args).unwrap(),
        serde_json::to_vec(&args).unwrap()
    );
    emit("large-at-limit", alloc, wire, &t);
    let (reject, wire) = request(CHILD, "at-65", Value::Null);
    let (change, alloc) = measure(|| route(&mut t, &reject));
    assert_eq!(change, Change::Updated(0));
    assert_eq!(child(&t, 0).tools.last().unwrap().call_id, "at-64");
    emit("small-over-cap", alloc, wire, &t);
}
#[test]
fn root_missing_completed_and_last_running_duplicate_routes_are_preserved() {
    let mut t = fixture(64);
    for (name, thread) in [("root-tool", ROOT), ("unknown-thread-tool", OTHER)] {
        let (request, wire) = request(thread, name, json!({"exact": [3,2,1]}));
        let (change, alloc) = measure(|| route(&mut t, &request));
        assert_eq!(change, Change::Pushed);
        let row = t.entries().last().unwrap();
        assert_eq!(row.tool.as_deref().unwrap().call_id, name);
        assert_eq!(row.time, Some(TIMESTAMP));
        emit(name, alloc, wire, &t);
    }
    assert_eq!(
        t.apply_runtime(
            uid(ROOT),
            &Event::SubagentFinished {
                status: "completed".into(),
                iterations: 64,
                role: "fixture".into(),
                child_thread_id: uid(CHILD),
            },
        ),
        Change::Updated(0)
    );
    let (after_end, wire) = request(CHILD, "after-end", json!({"kind":"standalone"}));
    let (change, alloc) = measure(|| route(&mut t, &after_end));
    assert_eq!(change, Change::Pushed);
    assert_eq!(
        t.entries().last().unwrap().tool.as_deref().unwrap().call_id,
        "after-end"
    );
    emit("completed-child-tool", alloc, wire, &t);
    // A later running child with the same durable id wins.
    begin(&mut t, CHILD);
    let (active_duplicate, wire) = request(CHILD, "new-active-child", json!({"kind":"nested"}));
    let (change, alloc) = measure(|| route(&mut t, &active_duplicate));
    assert_eq!(change, Change::Updated(4));
    assert_eq!(child(&t, 4).tools[0].call_id, "new-active-child");
    assert_eq!(child(&t, 0).tools.len(), 64);
    emit("new-running-duplicate", alloc, wire, &t);
}
