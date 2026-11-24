// Renderer-only adversarial corpus. Duplicate, detached and wrong-root hints are
// deliberately not passed through the strict store validator as accepted records.
use anyhow::{Result, bail};
use proteus_contracts::{
    app_protocol::AppTranscriptMessage,
    contracts::OperationOwner,
    domain::{AgentTask, ThreadId, ToolCall, ToolResult, TurnId},
    model_standard::{CanonicalMessage, MessageRole},
    storage::journal::*,
};
use serde_json::json;
use uuid::Uuid;

fn id(i: u128) -> Uuid {
    Uuid::from_u128(i)
}
fn rec(
    i: u64,
    thread: Option<ThreadId>,
    turn: Option<TurnId>,
    entry: JournalEntry,
) -> JournalRecord {
    JournalRecord {
        schema_version: JOURNAL_SCHEMA_VERSION,
        record_id: id((1000 + i) as u128),
        session_seq: i,
        timestamp_ms: 3000 - i as i64 * 7,
        session_id: id(900),
        execution_id: None,
        thread_id: thread,
        turn_id: turn,
        entry,
    }
}
fn root(i: u64, thread: ThreadId, turn: TurnId) -> JournalRecord {
    rec(
        i,
        Some(thread),
        Some(turn),
        JournalEntry::TurnOpened(TurnOpened {
            task: AgentTask::new("fixture", "/w".into()),
            intent: None,
            base_history_revision: 0,
            module_epoch: 0,
            config_snapshot: json!({}),
        }),
    )
}
fn req(i: u64, thread: ThreadId, turn: TurnId, name: &str, owner: OperationOwner) -> JournalRecord {
    rec(
        i,
        Some(thread),
        Some(turn),
        JournalEntry::ToolCallRecorded(ToolCallRecorded {
            call: ToolCall::new(name, "fixture-tool", json!({"q":"/x"})),
            phase: ToolCallRecordPhase::Requested { owner },
        }),
    )
}
fn result(
    i: u64,
    thread: Option<ThreadId>,
    turn: Option<TurnId>,
    name: &str,
    out: &str,
    effect: bool,
) -> JournalRecord {
    let t = ToolResultRecorded {
        result: ToolResult::ok(name.into(), out).with_metadata(json!({"sentinel":out,"small":1})),
    };
    rec(
        i,
        thread,
        turn,
        if effect {
            JournalEntry::ToolEffectRecorded(t)
        } else {
            JournalEntry::ToolResultRecorded(t)
        },
    )
}
fn call_row<'a>(rows: &'a [AppTranscriptMessage], id: &str) -> Option<&'a AppTranscriptMessage> {
    rows.iter()
        .find(|row| row.tool.as_ref().is_some_and(|v| v.call_id == id))
}
fn lines(set: &str, records: Vec<JournalRecord>, live: Option<TurnId>, late: bool) {
    let mut metrics = Vec::new();
    let mut previous = None;
    for changed in [false, true] {
        crate::CHANGED.set(changed);
        crate::meter::reset();
        crate::meter::begin_replay();
        let mut passes = 0;
        let result: Result<Vec<AppTranscriptMessage>> = crate::render::transcript_from_scan(
            |visit| {
                passes += 1;
                for r in &records {
                    let mut owned = r.clone();
                    if set == "edge"
                        && let JournalEntry::ToolResultRecorded(tool) = &mut owned.entry
                        && matches!(
                            tool.result.call_id.as_str(),
                            "loose-error" | "empty-reserved-error"
                        )
                    {
                        tool.result.error.as_mut().unwrap().reserve(256);
                    }
                    visit(owned)?;
                }
                if late && passes == 4 {
                    bail!("injected late scan error after final callback");
                }
                Ok(())
            },
            live,
        );
        crate::meter::end_replay();
        let expected_passes = if set == "causal-text" { 2 } else { 4 };
        assert_eq!(passes, expected_passes);
        let value = match result {
            Ok(rows) => {
                assert!(!late);
                if set == "lineage" {
                    let win = call_row(&rows, "win").unwrap();
                    assert_eq!(win.timestamp_ms, Some(records[1].timestamp_ms));
                    let win = win.tool.as_ref().unwrap();
                    assert_eq!(win.result.as_deref(), Some("winning 🌱"));
                    assert_eq!(win.status, "done");
                    assert_eq!(win.metadata["sentinel"], "winning 🌱");
                    let borrowed = call_row(&rows, "effect-only")
                        .unwrap()
                        .tool
                        .as_ref()
                        .unwrap();
                    assert_eq!(borrowed.result.as_deref(), Some("effect-only-body"));
                    assert_eq!(borrowed.status, "done");
                    for s in ["no-request", "live", "detached"] {
                        assert!(call_row(&rows, s).is_none());
                    }
                    assert_ne!(
                        call_row(&rows, "wrong-root")
                            .unwrap()
                            .tool
                            .as_ref()
                            .unwrap()
                            .result
                            .as_deref(),
                        Some("wrong-root-body")
                    );
                } else if set == "edge" {
                    for (id, text, status) in [
                        ("loose-error", "win-long-error", "done"),
                        ("empty-reserved-error", "wins-output", "failed"),
                    ] {
                        let t = call_row(&rows, id).unwrap().tool.as_ref().unwrap();
                        assert_eq!(t.result.as_deref(), Some(text));
                        assert_eq!(t.status, status);
                        assert_eq!(t.result.as_ref().unwrap().capacity(), text.len());
                    }
                } else if set == "causal-text" {
                    assert_eq!(rows.len(), 1);
                    assert_eq!(rows[0].text, "plain causal");
                    assert!(rows[0].tool.is_none());
                } else {
                    assert!(rows.iter().any(|r| r.text == "post-reset"));
                    assert!(
                        !rows
                            .iter()
                            .any(|r| r.tool.as_ref().is_some_and(|v| v.call_id == "old"))
                    );
                    let fallback = call_row(&rows, "missing").unwrap();
                    assert_eq!(fallback.timestamp_ms, Some(records[3].timestamp_ms));
                    let fallback = fallback.tool.as_ref().unwrap();
                    assert_eq!(fallback.result.as_deref(), Some("fallback-after-reset"));
                    assert_eq!(fallback.name, "tool");
                }
                json!({"rows":rows,"capacities":rows.iter().map(|r|r.tool.as_ref().and_then(|t|t.result.as_ref().map(String::capacity))).collect::<Vec<_>>()})
            }
            Err(e) => {
                assert!(late);
                assert_eq!(
                    e.to_string(),
                    "injected late scan error after final callback"
                );
                json!({"error":e.to_string()})
            }
        };
        if let Some(before) = &previous {
            assert_eq!(before, &value);
        } else {
            previous = Some(value);
        }
        metrics.push(crate::meter::take());
    }
    println!(
        "{}",
        json!({"route":"adversarial","kind":"renderer-only","case":set,"passes":if set=="causal-text"{2}else{4},
        "error":late,"passed":true,"meters":{"stock":metrics.remove(0),"candidate":metrics.remove(0)}})
    );
}
pub(crate) fn supplement() {
    let t = id(71);
    let th = id(72);
    let other = id(73);
    let live = id(74);
    let lineage = vec![
        root(1, th, t),
        req(2, th, t, "win", OperationOwner::Workflow),
        result(3, Some(th), Some(t), "win", "earlier-effect", true),
        result(4, Some(th), Some(t), "win", "winning 🌱", false),
        result(5, Some(th), Some(t), "win", "duplicate-later", false),
        req(6, th, t, "effect-only", OperationOwner::Workflow),
        result(
            7,
            Some(th),
            Some(t),
            "effect-only",
            "effect-only-body",
            true,
        ),
        req(
            8,
            th,
            t,
            "wrong-root",
            OperationOwner::Tool {
                call_id: "win".into(),
            },
        ),
        result(
            9,
            Some(other),
            Some(t),
            "wrong-root",
            "wrong-root-body",
            false,
        ),
        result(
            10,
            Some(th),
            Some(t),
            "no-request",
            "no-request-body",
            false,
        ),
        result(11, None, None, "detached", "detached-body", false),
        root(12, th, live),
        req(13, th, live, "live", OperationOwner::Workflow),
        result(14, Some(th), Some(live), "live", "live-body", false),
    ];
    lines("lineage", lineage.clone(), Some(live), false);
    lines("late-scan", lineage, Some(live), true);
    let frontier = vec![
        root(1, th, t),
        req(2, th, t, "old", OperationOwner::Workflow),
        result(3, Some(th), Some(t), "old", "before-frontier", false),
        req(4, th, t, "missing", OperationOwner::Workflow),
        rec(
            5,
            Some(th),
            Some(t),
            JournalEntry::HistoryMutated(HistoryMutated {
                previous_revision: 0,
                new_revision: 1,
                mutation: HistoryMutationKind::Replace,
                messages: vec![CanonicalMessage::text(MessageRole::User, "post-reset")],
                compaction: None,
                tool_results: vec![],
            }),
        ),
        result(
            6,
            Some(th),
            Some(t),
            "missing",
            "fallback-after-reset",
            false,
        ),
    ];
    lines("frontier", frontier, None, false);
    let edge = vec![
        root(1, th, t),
        req(2, th, t, "loose-error", OperationOwner::Workflow),
        rec(
            3,
            Some(th),
            Some(t),
            JournalEntry::ToolResultRecorded(ToolResultRecorded {
                result: ToolResult::new(
                    "loose-error".into(),
                    true,
                    "tight but masked".into(),
                    vec![],
                    Some("win-long-error".into()),
                    json!({}),
                ),
            }),
        ),
        req(4, th, t, "empty-reserved-error", OperationOwner::Workflow),
        rec(
            5,
            Some(th),
            Some(t),
            JournalEntry::ToolResultRecorded(ToolResultRecorded {
                result: ToolResult::new(
                    "empty-reserved-error".into(),
                    false,
                    "wins-output".into(),
                    vec![],
                    Some(String::new()),
                    json!({}),
                ),
            }),
        ),
    ];
    lines("edge", edge, None, false);
    lines(
        "causal-text",
        vec![
            root(1, th, t),
            rec(
                2,
                Some(th),
                Some(t),
                JournalEntry::HistoryMutated(HistoryMutated {
                    previous_revision: 0,
                    new_revision: 1,
                    mutation: HistoryMutationKind::Append,
                    messages: vec![CanonicalMessage::text(MessageRole::User, "plain causal")],
                    compaction: None,
                    tool_results: vec![],
                }),
            ),
        ],
        None,
        false,
    );
}
