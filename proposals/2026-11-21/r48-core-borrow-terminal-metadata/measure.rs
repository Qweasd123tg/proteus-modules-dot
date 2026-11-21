use super::*;
use crate::{
    contracts::ToolTerminalRef,
    core::{
        JOURNAL_SCHEMA_VERSION, JournalProjection, ToolCallRecorded, ToolResultRecorded,
        TurnOpened, TurnSettled, TurnSettlementStatus,
    },
    domain::{AgentTask, ExecutionId, ToolCall, ToolCallResolution, ToolResult},
    r48_alloc::measure,
};
use serde_json::{Value, json};
use uuid::Uuid;

fn terminal(i: usize) -> ToolTerminalRef {
    ToolTerminalRef {
        id: Uuid::from_u128(100_000 + i as u128),
        title: "tool run 🪴".into(),
        tty: i % 2 == 0,
    }
}

fn fixture(count: usize, mode: &str) -> JournalProjection {
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
    for i in 0..count {
        let id = format!("call_fixture_{i:024}");
        let call = ToolCall::new(id.clone(), "fixture-tool", json!({"path":"fixture-data"}));
        push(
            JournalEntry::ToolCallRecorded(ToolCallRecorded {
                call: call.clone(),
                phase: ToolCallRecordPhase::Requested {
                    owner: OperationOwner::Workflow,
                },
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
        let mut metadata = json!({"fixture":"keep"});
        match mode {
            "valid" => {
                metadata["tool_terminal"] = json!(terminal(i));
            }
            "unknown" => {
                let mut subtree = json!(terminal(i));
                subtree["unrecognized"] = json!({"synthetic_nested": [
                    "x".repeat(4096), {"extra_array":[1,2,3]}
                ]});
                metadata["tool_terminal"] = subtree;
            }
            "absent" => {}
            _ => unreachable!(),
        }
        push(
            JournalEntry::ToolResultRecorded(ToolResultRecorded {
                result: ToolResult::ok(id, "fixture output").with_metadata(metadata),
            }),
            true,
        );
    }
    push(
        JournalEntry::TurnSettled(TurnSettled {
            status: TurnSettlementStatus::Success,
            output: None,
            error: None,
        }),
        false,
    );
    JournalProjection::build(session, journal).unwrap()
}

#[test]
fn cold_terminal_allocation_fixture() {
    let mut output = Vec::new();
    for (n, mode) in [
        (0, "absent"),
        (1, "absent"),
        (1, "valid"),
        (64, "valid"),
        (512, "valid"),
        (16, "unknown"),
        (64, "unknown"),
    ] {
        let projection = fixture(n, mode);
        let (rows, stats) = measure(|| from_records(&projection.records, None).unwrap());
        assert_eq!(rows.len(), n);
        for (i, row) in rows.iter().enumerate() {
            let tool = row.tool.as_ref().unwrap();
            assert_eq!(tool.status, "done");
            assert_eq!(tool.metadata["fixture"], "keep");
            assert_eq!(tool.result.as_deref(), Some("fixture output"));
            assert_eq!(tool.terminal, (mode == "valid").then(|| terminal(i)));
            if mode == "unknown" {
                assert_eq!(
                    tool.metadata["tool_terminal"]["unrecognized"]["synthetic_nested"][0],
                    Value::String("x".repeat(4096))
                );
            }
        }
        println!(
            "r48 n={n} mode={mode} calls={} bytes={}",
            stats.calls, stats.bytes
        );
        output.push(rows);
    }
    std::fs::write(
        std::env::var_os("PROTEUS_TRANSCRIPT_PROBE_OUTPUT").unwrap(),
        serde_json::to_vec(&output).unwrap(),
    )
    .unwrap();
}
