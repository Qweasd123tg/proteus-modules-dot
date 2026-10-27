//! Synthetic cold writer / strict projection probe; no model or external module execution.
use anyhow::{Result, bail, ensure};
use proteus_contracts::{
    contracts::{ExecutionAttribution, ModelCallOrigin, ModelContextObservation, OperationOwner},
    domain::{
        AgentTask, ModelRef, ModelUsageStatus, ThreadId, new_exchange_id, new_execution_id,
        new_session_id, new_thread_id, new_turn_id,
    },
    model_standard::{
        CanonicalMessage, CanonicalModelRequest, CanonicalModelResponse, FinishReason, MessageRole,
        ModelFailure, ModelFailureKind, TokenUsage,
    },
};
use proteus_core::core::{
    JournalEntry, ModelRequestRecorded, ModelResponseOutcome, ModelResponseRecorded, SessionStore,
    TurnOpened, TurnSettled, TurnSettlementStatus,
};
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use std::{
    io::{Read, Write},
    path::{Component, Path, PathBuf},
    time::{Duration, Instant},
};

#[derive(Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct Fixture {
    session: PathBuf,
    thread: ThreadId,
    snapshots: usize,
    kib: usize,
    continuation: CanonicalMessage,
}

fn bounded_read(path: &Path, cap: usize) -> Result<Vec<u8>> {
    let mut bytes = Vec::new();
    std::fs::File::open(path)?
        .take(cap as u64 + 1)
        .read_to_end(&mut bytes)?;
    ensure!(bytes.len() <= cap, "input exceeds explicit byte cap");
    Ok(bytes)
}

fn read_fixture(root: &Path) -> Result<Fixture> {
    let bytes = bounded_read(&root.join("fixture.json"), 16 * 1024)?;
    let fixture: Fixture = serde_json::from_slice(&bytes)?;
    ensure!(!fixture.session.as_os_str().is_empty());
    ensure!(
        fixture
            .session
            .components()
            .all(|c| matches!(c, Component::Normal(_)))
    );
    ensure!([(128, 128), (32, 512)].contains(&(fixture.snapshots, fixture.kib)));
    Ok(fixture)
}

async fn snapshot(store: &SessionStore) -> Result<Value> {
    let p = store.load_projection()?;
    let records: Vec<_> = p
        .records
        .iter()
        .map(|r| {
            json!({
                "schema_version": r.schema_version, "record_id": r.record_id,
                "session_seq": r.session_seq, "timestamp_ms": r.timestamp_ms,
                "session_id": r.session_id, "execution_id": r.execution_id,
                "thread_id": r.thread_id, "turn_id": r.turn_id, "entry": r.entry,
            })
        })
        .collect();
    let conversation = store.conversation_snapshot()?;
    ensure!(conversation.revision == p.history_revision);
    ensure!(conversation.messages == p.history);
    Ok(json!({
        "records": records, "history": p.history, "history_revision": p.history_revision,
        "interrupted_turns": p.interrupted_turns,
        "interrupted_model_exchanges": p.interrupted_model_exchanges,
        "interrupted_context_builds": p.interrupted_context_builds,
        "unresolved_tool_calls": p.unresolved_tool_calls, "unsettled_turns": p.unsettled_turns,
        "conversation": conversation, "usage": store.usage_snapshot().await?,
    }))
}

async fn seed(root: &Path, snapshots: usize, kib: usize) -> Result<()> {
    ensure!([(128, 128), (32, 512)].contains(&(snapshots, kib)));
    ensure!(!root.exists(), "seed root must be new");
    std::fs::create_dir_all(root.join("workspace"))?;
    let store = SessionStore::new(
        &root.join("config"),
        &root.join("workspace"),
        new_session_id(),
    )?;
    let thread = new_thread_id();
    let fixture = Fixture {
        session: store
            .session_dir()
            .strip_prefix(std::fs::canonicalize(root)?)?
            .to_owned(),
        thread,
        snapshots,
        kib,
        continuation: CanonicalMessage::text(MessageRole::Assistant, "fixed continuation"),
    };
    let mut current = None;
    for i in 0..snapshots {
        // Distinct obsolete identities/content, exactly kib*1024 logical text bytes.
        let mut text = format!("{i:08}:");
        text.push_str(&"x".repeat(kib * 1024 - text.len()));
        let message = CanonicalMessage::text(MessageRole::User, text);
        store
            .replace_history(thread, None, std::slice::from_ref(&message), None)
            .await?;
        current = Some(message);
    }
    let turn = new_turn_id();
    let attribution =
        ExecutionAttribution::for_turn(new_execution_id(), store.session_id(), thread, turn);
    store
        .append_execution_journal_entry(
            attribution,
            JournalEntry::TurnOpened(TurnOpened {
                task: AgentTask::new("synthetic cold recovery", root.join("workspace")),
                intent: None,
                base_history_revision: snapshots as u64,
                module_epoch: 0,
                config_snapshot: json!({}),
            }),
        )
        .await?;
    for index in 0..3 {
        let exchange_id = new_exchange_id();
        let mut request = CanonicalModelRequest::new(
            ModelRef::new("fixture", "offline"),
            vec![CanonicalMessage::text(
                MessageRole::User,
                format!("request {index}"),
            )],
        );
        request.limits.max_input_tokens = Some(100_000);
        store
            .append_execution_journal_entry(
                attribution,
                JournalEntry::ModelRequestRecorded(ModelRequestRecorded {
                    exchange_id,
                    origin: ModelCallOrigin::Direct,
                    owner: OperationOwner::Workflow,
                    request,
                }),
            )
            .await?;
        let outcome = match index {
            0 => ModelResponseOutcome::Response {
                response: CanonicalModelResponse::new(
                    CanonicalMessage::text(MessageRole::Assistant, "synthetic answer"),
                    vec![],
                    FinishReason::Stop,
                )
                .with_usage(TokenUsage::new(1000, 200).with_cached_input_tokens(Some(800))),
            },
            1 => ModelResponseOutcome::Error {
                failure: ModelFailure::new(
                    ModelFailureKind::ContextWindowExceeded,
                    "synthetic overflow",
                ),
            },
            _ => continue,
        };
        store
            .append_execution_journal_entry(
                attribution,
                JournalEntry::ModelResponseRecorded(ModelResponseRecorded {
                    exchange_id,
                    outcome,
                }),
            )
            .await?;
    }
    store
        .append_journal_entry(
            thread,
            Some(turn),
            JournalEntry::TurnSettled(TurnSettled {
                status: TurnSettlementStatus::Canceled,
                output: None,
                error: Some("synthetic canceled".into()),
            }),
        )
        .await?;
    let usage = store.usage_snapshot().await?;
    ensure!(usage.requests.len() == 3);
    ensure!(usage.requests[0].status == ModelUsageStatus::Completed);
    ensure!(
        usage.requests[0].usage.as_ref()
            == Some(&TokenUsage::new(1000, 200).with_cached_input_tokens(Some(800)))
    );
    ensure!(usage.requests[1].status == ModelUsageStatus::Error);
    ensure!(usage.requests[2].status == ModelUsageStatus::Canceled);
    ensure!(usage.requests[1].usage.is_none() && usage.requests[2].usage.is_none());
    ensure!(usage.revision == snapshots as u64 + 7);
    ensure!(usage.latest_turn_id == Some(turn));
    let conversation = store.conversation_snapshot()?;
    ensure!(conversation.messages == vec![current.expect("nonempty fixture")]);
    ensure!(
        conversation.model_context
            == vec![
                ModelContextObservation::Usage {
                    total_tokens: 1200,
                    last_tokens: 1200
                },
                ModelContextObservation::ContextWindowExceeded {
                    max_input_tokens: 100_000
                },
            ]
    );
    let oracle = snapshot(&store).await?;
    ensure!(oracle["records"].as_array().unwrap().len() == snapshots + 7);
    std::fs::write(root.join("fixture.json"), serde_json::to_vec(&fixture)?)?;
    std::fs::write(root.join("oracle.json"), serde_json::to_vec(&oracle)?)?;
    println!(
        "{}",
        json!({"seed_records": snapshots + 7, "logical_text_bytes": snapshots*kib*1024})
    );
    Ok(())
}

fn verify_snapshot(
    mut actual: Value,
    expected: &Value,
    fixture: &Fixture,
    appended: bool,
) -> Result<()> {
    let records = actual["records"]
        .as_array_mut()
        .ok_or_else(|| anyhow::anyhow!("records absent"))?;
    let count = fixture.snapshots + 7;
    ensure!(
        records.len() == count + usize::from(appended),
        "wrong record count"
    );
    for (index, r) in records.iter().enumerate() {
        ensure!(r["session_seq"] == json!(index + 1), "sequence");
    }
    if !appended {
        ensure!(actual == *expected, "strict pre-state differs");
        return Ok(());
    }
    let last = records.pop().expect("append");
    ensure!(last["record_id"].as_str().is_some(), "append record ID");
    ensure!(
        records.iter().all(|r| r["record_id"] != last["record_id"]),
        "append reused a record ID"
    );
    ensure!(last["timestamp_ms"].as_i64().is_some(), "append timestamp");
    let before_last = expected["records"].as_array().unwrap().last().unwrap();
    ensure!(last["schema_version"] == before_last["schema_version"]);
    ensure!(last["session_id"] == before_last["session_id"]);
    ensure!(last["session_seq"] == json!(count + 1));
    ensure!(last["thread_id"] == json!(fixture.thread));
    ensure!(last["turn_id"].is_null() && last["execution_id"].is_null());
    ensure!(
        last["entry"]
            == json!({
                "kind": "history_mutated",
                "payload": {"previous_revision": fixture.snapshots,
                    "new_revision": fixture.snapshots+1, "mutation":"append",
                    "messages":[fixture.continuation], "compaction": null, "tool_results":[]}
            }),
        "append entry changed"
    );
    // Only the added record's nondeterministic envelope ID/time are unconstrained.
    // Every old record and all canonical message/part identities are exact.
    let mut wanted = expected.clone();
    wanted["history"]
        .as_array_mut()
        .unwrap()
        .push(json!(fixture.continuation));
    wanted["history_revision"] = json!(fixture.snapshots + 1);
    wanted["conversation"]["messages"]
        .as_array_mut()
        .unwrap()
        .push(json!(fixture.continuation));
    wanted["conversation"]["revision"] = json!(fixture.snapshots + 1);
    ensure!(
        actual == wanted,
        "full history/context/usage/projection state differs"
    );
    Ok(())
}

#[tokio::main(worker_threads = 2)]
async fn main() -> Result<()> {
    let args: Vec<_> = std::env::args().collect();
    ensure!(
        args.len() >= 3,
        "seed ROOT COUNT KIB | recover/projection/audit/verify-before/verify-after ROOT"
    );
    let mode = args[1].as_str();
    let root = PathBuf::from(&args[2]);
    if mode == "seed" {
        ensure!(args.len() == 5);
        return seed(&root, args[3].parse()?, args[4].parse()?).await;
    }
    ensure!(args.len() == 3);
    let fixture = read_fixture(&root)?;
    let store = SessionStore::open(root.join(&fixture.session))?;
    if mode.starts_with("verify-") || mode == "audit" {
        let bytes = bounded_read(&root.join("oracle.json"), 32 * 1024 * 1024)?;
        let expected: Value = serde_json::from_slice(&bytes)?;
        if mode == "audit" {
            store
                .append_history(
                    fixture.thread,
                    None,
                    std::slice::from_ref(&fixture.continuation),
                )
                .await?;
            // Same live writer; unlike cold read this observes the recovered usage cache.
            ensure!(
                json!(store.usage_snapshot().await?) == expected["usage"],
                "live cached usage differs"
            );
        }
        let actual = snapshot(&store).await?;
        verify_snapshot(
            actual,
            &expected,
            &fixture,
            mode == "verify-after" || mode == "audit",
        )?;
        ensure!(["verify-before", "verify-after", "audit"].contains(&mode));
        println!("{}", json!({"verified":true, "mode":mode}));
        return Ok(());
    }
    let started = Instant::now();
    match mode {
        "recover" => {
            store
                .append_history(
                    fixture.thread,
                    None,
                    std::slice::from_ref(&fixture.continuation),
                )
                .await?;
            let elapsed_ns = started.elapsed().as_nanos();
            println!(
                "{}",
                json!({"mode":mode, "elapsed_ns":elapsed_ns, "pid":std::process::id()})
            );
            std::io::stdout().flush()?;
            tokio::time::sleep(Duration::from_millis(100)).await;
            std::hint::black_box(&store);
        }
        "projection" => {
            let projection = store.load_projection()?;
            let elapsed_ns = started.elapsed().as_nanos();
            println!(
                "{}",
                json!({"mode":mode, "elapsed_ns":elapsed_ns, "pid":std::process::id()})
            );
            std::io::stdout().flush()?;
            tokio::time::sleep(Duration::from_millis(100)).await;
            std::hint::black_box(&projection);
        }
        _ => bail!("unknown mode"),
    }
    Ok(())
}
