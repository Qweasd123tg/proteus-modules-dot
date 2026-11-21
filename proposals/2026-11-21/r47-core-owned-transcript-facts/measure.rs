use super::*;
use crate::{
    core::{
        JOURNAL_SCHEMA_VERSION, JournalProjection, ToolCallRecorded, ToolResultRecorded,
        TurnOpened, TurnSettled, TurnSettlementStatus,
    },
    domain::{
        AgentTask, ExecutionId, SubagentSessionBinding, ToolCall, ToolCallResolution, ToolResult,
    },
    r47_alloc::measure,
};
use serde_json::json;
use uuid::Uuid;

fn fixture(count: usize, linked: bool) -> JournalProjection {
    let session = Uuid::from_u128(1);
    let thread = Uuid::from_u128(2);
    let turn = Uuid::from_u128(3);
    let execution = ExecutionId::from_uuid(Uuid::from_u128(4));
    let mut journal = Vec::new();
    let mut push = |entry, is_execution: bool| {
        let seq = journal.len() as u64 + 1;
        journal.push(JournalRecord {
            schema_version: JOURNAL_SCHEMA_VERSION,
            record_id: Uuid::from_u128(10_000 + u128::from(seq)),
            session_seq: seq,
            timestamp_ms: seq as i64 + 400,
            session_id: session,
            execution_id: is_execution.then_some(execution),
            thread_id: Some(thread),
            turn_id: Some(turn),
            entry,
        });
    };
    if count > 0 {
        push(
            JournalEntry::TurnOpened(TurnOpened {
                intent: None,
                task: AgentTask::new("fixture", "/fixture".into()),
                base_history_revision: 0,
                module_epoch: 0,
                config_snapshot: json!({}),
            }),
            true,
        );
    }
    let mut links = Vec::new();
    let tenant = "workspace-a";
    for i in 0..count {
        let id = format!("call_fixture_{i:024}");
        let call = ToolCall::new(id.clone(), "fixture-tool", json!({"path":"fixture-data"}));
        let phase = ToolCallRecordPhase::Requested {
            owner: if i % 2 == 0 {
                OperationOwner::Workflow
            } else {
                OperationOwner::Tool {
                    call_id: format!("parent-{}", i - 1),
                }
            },
        };
        push(
            JournalEntry::ToolCallRecorded(ToolCallRecorded {
                call: call.clone(),
                phase,
            }),
            true,
        );
        push(
            JournalEntry::ToolCallRecorded(ToolCallRecorded {
                call,
                phase: ToolCallRecordPhase::Resolved {
                    resolution: ToolCallResolution::Allowed,
                },
            }),
            true,
        );
        if i % 2 == 0 {
            push(
                JournalEntry::ToolEffectRecorded(ToolResultRecorded {
                    result: ToolResult::ok(id.clone(), "fixture output")
                        .with_metadata(json!({"stage":"effect"})),
                }),
                true,
            );
        }
        push(
            JournalEntry::ToolResultRecorded(ToolResultRecorded {
                result: ToolResult::ok(id.clone(), "fixture output")
                    .with_metadata(json!({"stage":"final"})),
            }),
            true,
        );
        if linked {
            links.push(SubagentSessionBinding {
                source_call_id: id,
                child_thread_id: Uuid::from_u128(100_000 + i as u128),
                session_id: Uuid::from_u128(200_000 + i as u128),
                session_dir: format!("/fixture/sessions/{tenant}/subagents/turn/{i:024}/state")
                    .into(),
            });
        }
    }
    if count > 0 {
        push(
            JournalEntry::TurnSettled(TurnSettled {
                status: TurnSettlementStatus::Canceled,
                output: None,
                error: None,
            }),
            false,
        );
    }
    for link in links {
        push(JournalEntry::SubagentSessionBoundRecorded(link), true);
    }
    JournalProjection::build(session, journal).unwrap()
}

#[test]
fn cold_fact_traffic_and_final_cards() {
    let mut output = Vec::new();
    for (n, bound) in [
        (0, false),
        (1, false),
        (1, true),
        (64, false),
        (64, true),
        (512, false),
        (512, true),
    ] {
        let p = fixture(n, bound);
        let (rows, all) = measure(|| from_records(&p.records, None).unwrap());
        let mut passes = Vec::new();
        let per_pass = transcript_from_scan(
            |visit| {
                let mut calls = 0;
                let mut bytes = 0;
                for record in &p.records {
                    let record = record.clone();
                    let (status, stats) = measure(|| visit(record));
                    status?;
                    calls += stats.calls;
                    bytes += stats.bytes;
                }
                passes.push((calls, bytes));
                Ok(())
            },
            None,
        )
        .unwrap();
        let full = serde_json::to_vec(&rows).unwrap();
        assert_eq!(full, serde_json::to_vec(&per_pass).unwrap());
        let live = from_records(&p.records, Some(Uuid::from_u128(3))).unwrap();
        assert!(live.is_empty());
        assert_eq!(rows.len(), if n > 0 { n + 1 } else { 0 });
        for row in rows.iter().take(n) {
            let tool = row.tool.as_ref().unwrap();
            assert_eq!(tool.status, "done");
            assert_eq!(tool.metadata["stage"], "final");
            assert_eq!(tool.metadata.get("subagent_session").is_some(), bound);
        }
        assert_eq!(passes.len(), if n == 0 { 2 } else { 4 });
        let (first_calls, first_bytes) = passes[0];
        let (second_calls, second_bytes) = passes[1];
        println!(
            "r47 n={n} bound={} all_calls={} all_bytes={} first_calls={first_calls} first_bytes={first_bytes} second_calls={second_calls} second_bytes={second_bytes}",
            u8::from(bound),
            all.calls,
            all.bytes
        );
        output.push(full);
    }
    std::fs::write(
        std::env::var_os("PROTEUS_TRANSCRIPT_PROBE_OUTPUT").unwrap(),
        serde_json::to_vec(&output).unwrap(),
    )
    .unwrap();
}
