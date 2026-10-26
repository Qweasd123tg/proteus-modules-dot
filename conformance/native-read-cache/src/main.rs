//! Authored read-cache experiment; no private Core API, module process, or model call.
mod allocation;

use anyhow::{Result, bail, ensure};
use proteus_contracts::domain::{new_session_id, new_thread_id};
use proteus_contracts::model_standard::{CanonicalMessage, MessageRole};
use proteus_core::{
    app_server::AgentAppServer,
    core::{
        AppConfig, HistoryMutated, HistoryMutationKind, JournalEntry, SessionStore,
        list_session_summaries_for_audit, list_workspace_session_summaries,
    },
};
use serde_json::{Value, json};
use std::{
    fs,
    path::Path,
    time::{Duration, Instant},
};

#[global_allocator]
static ALLOCATOR: allocation::CountingAllocator = allocation::CountingAllocator;
const PIN: &str = "1fc3ef223d10322815dd9290a50d045bc95402bb";

fn runtime() -> Result<tokio::runtime::Runtime> {
    Ok(tokio::runtime::Builder::new_current_thread()
        .enable_all()
        .build()?)
}
fn emit(value: Value) -> Result<()> {
    println!("{}", serde_json::to_string(&value)?);
    Ok(())
}
fn config(root: &Path) -> Result<AppConfig> {
    // Use serde defaults, not AppConfig::default(), which selects a fake provider.
    let config: AppConfig = serde_json::from_value(json!({
        "active_provider": null, "providers": {}, "components": {}, "commands": {},
        "instructions": [], "modules": {"hooks":[]}, "module_config": {},
        "addons": {"plugins":[]}, "tools": {"enabled":[], "mcp_servers":[]},
        "agent_control": {"surface":"none"},
        "event_log": {"path":root.join("events.jsonl")}
    }))?;
    ensure!(
        config.providers.is_empty()
            && config.components.is_empty()
            && config.addons.plugins.is_empty()
            && config.active_provider.is_none(),
        "nonempty execution config"
    );
    Ok(config)
}
fn store(path: &Path) -> Result<SessionStore> {
    SessionStore::open(path.to_owned())
}
fn checked_snapshot(store: &SessionStore, count: usize) -> Result<()> {
    let projection = store.load_projection()?;
    let snapshot = store.conversation_snapshot()?;
    ensure!(
        projection.history.len() == count
            && snapshot.messages == projection.history
            && snapshot.revision == projection.history_revision,
        "snapshot/projection mismatch"
    );
    ensure!(
        store.load_messages()? == projection.history,
        "messages/projection mismatch"
    );
    Ok(())
}
fn sample<T>(api: &str, call: impl FnOnce() -> Result<T>) -> Result<(T, Value)> {
    let before = allocation::Counts::read();
    let start = Instant::now();
    let value = call()?;
    let elapsed_ns = start.elapsed().as_nanos();
    let counts = allocation::Counts::read().since(before);
    std::hint::black_box(&value);
    Ok((
        value,
        json!({"api":api,"elapsed_ns":elapsed_ns,"allocations":counts}),
    ))
}

fn prepare(root: &Path, count: usize) -> Result<()> {
    ensure!((1..=256).contains(&count), "count must be1..256");
    fs::create_dir(root)?;
    fs::create_dir(root.join("workspace"))?;
    let rt = runtime()?;
    let session = SessionStore::new(
        &root.join("config"),
        &root.join("workspace"),
        new_session_id(),
    )?;
    let thread = new_thread_id();
    for index in 0..count {
        rt.block_on(session.append_history(
            thread,
            None,
            &[CanonicalMessage::text(
                MessageRole::User,
                format!("{index:04}:{}", "x".repeat(251)),
            )],
        ))?;
    }
    let before = fs::read(session.journal_path())?;
    let app = rt.block_on(AgentAppServer::launch_resumed(
        config(root)?,
        root.join("workspace"),
        None,
        session.session_dir().to_owned(),
    ))?;
    let transcript = rt.block_on(app.transcript())?;
    ensure!(
        transcript.len() == count,
        "native transcript count mismatch"
    );
    rt.block_on(app.shutdown());
    ensure!(
        session.session_dir().join(".read-view.json").is_file(),
        "native view cache not produced"
    );
    ensure!(
        session.session_dir().join(".read-summary.json").is_file(),
        "native summary cache not produced"
    );
    ensure!(
        fs::read(session.journal_path())? == before,
        "read-model producer changed journal"
    );
    checked_snapshot(&session, count)?;
    emit(
        json!({"event":"prepared","core_pin":PIN,"session_dir":session.session_dir(),
        "session_id":session.session_id(),"records":count,"native_producer":"AgentAppServer::launch_resumed",
        "no_modules":true,"no_provider":true,"journal_unchanged_by_producer":true}),
    )
}

fn read(path: &Path, count: usize) -> Result<()> {
    let session = store(path)?;
    let rt = runtime()?;
    let journal = fs::read(session.journal_path())?;
    let baseline = session.load_projection()?;
    ensure!(
        baseline.history.len() == count,
        "unexpected baseline history"
    );
    let mut samples = Vec::new();
    for _ in 0..3 {
        let (view, observation) =
            sample("conversation_snapshot", || session.conversation_snapshot())?;
        ensure!(
            view.messages == baseline.history && view.revision == baseline.history_revision,
            "conversation mismatch"
        );
        samples.push(observation);
        let (projection, observation) = sample("load_projection", || session.load_projection())?;
        ensure!(
            projection.history == baseline.history && projection.records == baseline.records,
            "projection mismatch"
        );
        samples.push(observation);
        let (history, observation) = sample("load_messages", || session.load_messages())?;
        ensure!(history == baseline.history, "history mismatch");
        samples.push(observation);
        let (usage, observation) = sample("usage_snapshot_cold_store", || {
            rt.block_on(session.usage_snapshot())
        })?;
        ensure!(
            usage.session_id == session.session_id() && usage.requests.is_empty(),
            "usage mismatch"
        );
        samples.push(observation);
    }
    ensure!(
        fs::read(session.journal_path())? == journal,
        "reads changed journal"
    );
    emit(
        json!({"event":"read","core_pin":PIN,"messages":count,"equivalent":true,"samples":samples,
        "scope":"fresh process, uninitialized writer; warm-or-unspecified pagecache; debug whole calls; no cachehit inferred solely from equivalence"}),
    )
}

fn only(path: &Path, api: &str, count: usize) -> Result<()> {
    let session = store(path)?;
    let messages = match api {
        "snapshot" => session.conversation_snapshot()?.messages.len(),
        "projection" => session.load_projection()?.history.len(),
        "messages" => session.load_messages()?.len(),
        _ => bail!("unsupported API"),
    };
    ensure!(messages == count, "only API wrong count");
    emit(json!({"event":"only","core_pin":PIN,"api":api,"messages":messages}))
}

fn reopen(root: &Path, path: &Path, count: usize) -> Result<()> {
    let rt = runtime()?;
    let session = store(path)?;
    let before = fs::read(session.journal_path())?;
    let app = rt.block_on(AgentAppServer::launch_resumed(
        config(root)?,
        root.join("workspace"),
        None,
        path.to_owned(),
    ))?;
    let mut samples = vec![];
    for _ in 0..3 {
        let (transcript, observation) =
            sample("native_app_transcript", || rt.block_on(app.transcript()))?;
        ensure!(transcript.len() == count, "reopened transcript mismatch");
        samples.push(observation);
    }
    rt.block_on(app.shutdown());
    checked_snapshot(&session, count)?;
    ensure!(
        fs::read(session.journal_path())? == before,
        "native reopen changed journal"
    );
    emit(
        json!({"event":"reopen","core_pin":PIN,"messages":count,"samples":samples,"journal_unchanged":true}),
    )
}

fn rollback(path: &Path, count: usize) -> Result<()> {
    let rt = runtime()?;
    let session = store(path)?;
    let projection = session.load_projection()?;
    ensure!(
        projection.history.len() == count && count > 0,
        "rollback requires history"
    );
    let journal = fs::read(session.journal_path())?;
    let view = fs::read(path.join(".read-view.json"))?;
    let summary = fs::read(path.join(".read-summary.json"))?;
    let thread = new_thread_id();
    let invalid = JournalEntry::HistoryMutated(HistoryMutated {
        previous_revision: 0,
        new_revision: 1,
        mutation: HistoryMutationKind::Append,
        messages: vec![CanonicalMessage::text(MessageRole::User, "invalid")],
        compaction: None,
        tool_results: vec![],
    });
    let early = rt
        .block_on(session.append_journal_entry(thread, None, invalid))
        .expect_err("stale revision accepted");
    ensure!(
        early.to_string().contains("history revision mismatch"),
        "wrong early failure"
    );
    let late = rt
        .block_on(session.append_history(thread, None, &[projection.history[0].clone()]))
        .expect_err("duplicate accepted");
    ensure!(
        late.to_string().contains("duplicate message id"),
        "wrong late failure"
    );
    checked_snapshot(&session, count)?;
    ensure!(
        fs::read(session.journal_path())? == journal
            && fs::read(path.join(".read-view.json"))? == view
            && fs::read(path.join(".read-summary.json"))? == summary,
        "rollback changed committed source/cache"
    );
    emit(
        json!({"event":"rollback","core_pin":PIN,"messages":count,"early_error":format!("{early:#}"),
        "late_error":format!("{late:#}"),"journal_and_cache_unchanged":true}),
    )
}

fn append(root: &Path, path: &Path, count: usize) -> Result<()> {
    let rt = runtime()?;
    let session = store(path)?;
    let old_view = fs::read(path.join(".read-view.json"))?;
    rt.block_on(session.append_history(
        new_thread_id(),
        None,
        &[CanonicalMessage::text(
            MessageRole::Assistant,
            "committed update",
        )],
    ))?;
    checked_snapshot(&session, count + 1)?;
    // Read-only fresh-snapshot API falls back; it does not rewrite the stale view.
    ensure!(
        fs::read(path.join(".read-view.json"))? == old_view,
        "unexpected view rewrite"
    );
    let first = list_workspace_session_summaries(&root.join("config"), &root.join("workspace"))?;
    ensure!(
        first.len() == 1 && first[0].message_count == count,
        "expected native stale catalog placeholder"
    );
    let deadline = Instant::now() + Duration::from_secs(5);
    loop {
        let next = list_workspace_session_summaries(&root.join("config"), &root.join("workspace"))?;
        if next.len() == 1 && next[0].message_count == count + 1 {
            break;
        }
        ensure!(
            Instant::now() < deadline,
            "bounded background summary refresh timed out"
        );
        std::thread::sleep(Duration::from_millis(10));
    }
    let audit =
        list_session_summaries_for_audit(&root.join("config"), Some(&root.join("workspace")))?;
    ensure!(
        audit.len() == 1 && audit[0].message_count == count + 1,
        "audit stale after append"
    );
    emit(
        json!({"event":"append","core_pin":PIN,"messages":count+1,"fresh_snapshot_matches_strict":true,
        "view_left_stale":true,"catalog_initial_messages":count,"catalog_eventual_messages":count+1}),
    )
}

fn positive_source(root: &Path, path: &Path, count: usize) -> Result<()> {
    let rt = runtime()?;
    let session = store(path)?;
    let before = fs::read(session.journal_path())?;
    checked_snapshot(&session, count)?;
    let usage = rt.block_on(session.usage_snapshot())?;
    ensure!(
        usage.session_id == session.session_id() && usage.requests.is_empty(),
        "positive cold usage mismatch"
    );
    let audit =
        list_session_summaries_for_audit(&root.join("config"), Some(&root.join("workspace")))?;
    ensure!(
        audit.len() == 1 && audit[0].message_count == count,
        "positive audit mismatch"
    );
    ensure!(
        fs::read(session.journal_path())? == before,
        "positive reads changed journal"
    );
    emit(
        json!({"event":"positive_source","core_pin":PIN,"messages":count,
        "snapshot_projection_messages_usage_audit_passed":true,"journal_unchanged":true}),
    )
}

fn invalid_source(root: &Path, path: &Path, old_count: usize, damage: &str) -> Result<()> {
    let rt = runtime()?;
    let session = store(path)?;
    let before = fs::read(session.journal_path())?;
    let projection = session
        .load_projection()
        .expect_err("corrupt canonical projection accepted");
    let snapshot = session
        .conversation_snapshot()
        .expect_err("stale cache hid corrupt canonical snapshot");
    let history = session
        .load_messages()
        .expect_err("corrupt canonical history accepted");
    let usage = rt
        .block_on(session.usage_snapshot())
        .expect_err("cold usage accepted corrupt journal");
    let audit =
        list_session_summaries_for_audit(&root.join("config"), Some(&root.join("workspace")))
            .expect_err("strict audit accepted corrupt journal");
    let expected = match damage {
        "malformed" => "failed to parse journal",
        "schema" => "unsupported journal schema_version 0",
        _ => bail!("unknown canonical damage kind"),
    };
    for (api, error) in [
        ("projection", &projection),
        ("snapshot", &snapshot),
        ("history", &history),
        ("usage", &usage),
        ("audit", &audit),
    ] {
        ensure!(
            format!("{error:#}").contains(expected),
            "{api} rejected for unrelated reason: {error:#}"
        );
    }
    let display = list_workspace_session_summaries(&root.join("config"), &root.join("workspace"))?;
    ensure!(
        display.len() == 1 && display[0].message_count == old_count,
        "documented stale display unavailable"
    );
    ensure!(
        fs::read(session.journal_path())? == before,
        "read path modified damaged canonical source"
    );
    emit(
        json!({"event":"invalid_source","core_pin":PIN,"strict_rejected":true,"expected_diagnostic":expected,
        "errors":{"projection":format!("{projection:#}"),"snapshot":format!("{snapshot:#}"),
        "history":format!("{history:#}"),"usage":format!("{usage:#}"),"audit":format!("{audit:#}")},
        "stale_display_messages":display[0].message_count,"journal_unchanged":true}),
    )
}

fn main() -> Result<()> {
    let a = std::env::args().collect::<Vec<_>>();
    match a.as_slice() {
        [_, cmd, root, n] if cmd == "prepare" => prepare(Path::new(root), n.parse()?),
        [_, cmd, path, n] if cmd == "read" => read(Path::new(path), n.parse()?),
        [_, cmd, path, api, n] if cmd == "only" => only(Path::new(path), api, n.parse()?),
        [_, cmd, root, path, n] if cmd == "reopen" => {
            reopen(Path::new(root), Path::new(path), n.parse()?)
        }
        [_, cmd, path, n] if cmd == "rollback" => rollback(Path::new(path), n.parse()?),
        [_, cmd, root, path, n] if cmd == "append" => {
            append(Path::new(root), Path::new(path), n.parse()?)
        }
        [_, cmd, root, path, n] if cmd == "positive-source" => {
            positive_source(Path::new(root), Path::new(path), n.parse()?)
        }
        [_, cmd, root, path, n, damage] if cmd == "invalid-source" => {
            invalid_source(Path::new(root), Path::new(path), n.parse()?, damage)
        }
        _ => bail!(
            "prepare ROOT N | read SESSION N | only SESSION snapshot|projection|messages N | reopen ROOT SESSION N | rollback SESSION N | append ROOT SESSION N | positive-source ROOT SESSION N | invalid-source ROOT SESSION N malformed|schema"
        ),
    }
}
