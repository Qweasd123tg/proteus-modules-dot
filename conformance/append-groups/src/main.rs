//! Existing public append groups: API-cost evidence, not a Core patch or general speedup.
mod allocation;

use anyhow::{Context, Result, bail, ensure};
use proteus_contracts::{
    domain::{MessageId, PartId, new_session_id, new_thread_id},
    model_standard::{CanonicalMessage, MessageRole},
};
use proteus_core::core::{DEFAULT_BLOB_THRESHOLD_BYTES, JournalEntry, SessionStore};
use serde_json::{Value, json};
use std::{fs, io::Write, path::Path, time::Instant};

#[global_allocator]
static ALLOCATOR: allocation::CountingAllocator = allocation::CountingAllocator;
const PIN: &str = "1fc3ef223d10322815dd9290a50d045bc95402bb";
const CORPUS_COUNT: usize = 256;

fn runtime() -> Result<tokio::runtime::Runtime> {
    Ok(tokio::runtime::Builder::new_current_thread()
        .enable_all()
        .build()?)
}
fn emit(value: Value) -> Result<()> {
    println!("{}", serde_json::to_string(&value)?);
    Ok(())
}
fn deterministic_corpus() -> Vec<CanonicalMessage> {
    (0..CORPUS_COUNT)
        .map(|index| {
            let mut message = CanonicalMessage::text(
                MessageRole::User,
                format!("{index:04}:{}", "x".repeat(251)),
            );
            // Authored disposable fixture identities; never used in a production session.
            message.id =
                MessageId::from_u128(0x11111111_1111_4111_8111_000000000000 + index as u128);
            message.parts[0].part_id =
                PartId::from_u128(0x22222222_2222_4222_8222_000000000000 + index as u128);
            message
        })
        .collect()
}
fn create_file(path: &Path, bytes: &[u8]) -> Result<()> {
    let mut file = fs::OpenOptions::new()
        .write(true)
        .create_new(true)
        .open(path)?;
    file.write_all(bytes)?;
    Ok(())
}
fn generate(path: &Path) -> Result<()> {
    let bytes = serde_json::to_vec(&deterministic_corpus())?;
    create_file(path, &bytes)?;
    emit(
        json!({"event":"corpus", "core_pin":PIN, "messages":CORPUS_COUNT,
        "message_text_bytes":256,"corpus_bytes":bytes.len(),"deterministic_ids_and_values":true}),
    )
}
fn read_corpus(path: &Path) -> Result<Vec<CanonicalMessage>> {
    ensure!(
        fs::metadata(path)?.len() <= 2 * 1024 * 1024,
        "corpus exceeds bound"
    );
    let messages: Vec<CanonicalMessage> = serde_json::from_slice(&fs::read(path)?)?;
    ensure!(
        messages == deterministic_corpus(),
        "corpus differs from deterministic authored values"
    );
    Ok(messages)
}
fn fresh_store(root: &Path) -> Result<SessionStore> {
    fs::create_dir(root).context("fresh fixture root required")?;
    let workspace = root.join("workspace");
    fs::create_dir(&workspace)?;
    SessionStore::new(&root.join("config"), &workspace, new_session_id())
}
fn validate(store: &SessionStore, messages: &[CanonicalMessage], batch: usize) -> Result<Value> {
    let projection = store.load_projection()?;
    let count = messages.len() / batch;
    ensure!(
        projection.history == messages,
        "final exact canonical history differs"
    );
    ensure!(
        projection.records.len() == count && projection.history_revision == count as u64,
        "unexpected record/revision count"
    );
    for (index, record) in projection.records.iter().enumerate() {
        ensure!(
            record.session_seq == index as u64 + 1,
            "nonconsecutive sequence"
        );
        let JournalEntry::HistoryMutated(change) = &record.entry else {
            bail!("unexpected journal entry");
        };
        ensure!(
            change.previous_revision == index as u64 && change.new_revision == index as u64 + 1,
            "unexpected per-group revision"
        );
        ensure!(
            change.messages == messages[index * batch..(index + 1) * batch],
            "stored group differs from input slice"
        );
    }
    ensure!(
        store.load_messages()? == messages,
        "message loader differs from strict projection"
    );
    let journal = fs::read(store.journal_path())?;
    ensure!(
        journal.len() <= 8 * 1024 * 1024,
        "journal exceeds fixture bound"
    );
    let mut payload_bytes = Vec::new();
    for line in journal
        .split(|byte| *byte == b'\n')
        .filter(|line| !line.is_empty())
    {
        let record: Value = serde_json::from_slice(line)?;
        ensure!(
            record["payload"]["storage"] == "inline",
            "blob-storage confound; stop row"
        );
        let size = serde_json::to_vec(&record["payload"]["value"])?.len();
        ensure!(
            size < DEFAULT_BLOB_THRESHOLD_BYTES,
            "payload crossed default blob threshold"
        );
        payload_bytes.push(size);
    }
    ensure!(payload_bytes.len() == count, "stored line count differs");
    Ok(
        json!({"history_matches_exact_corpus":true,"records":count,"revision":projection.history_revision,
        "consecutive_sequences":true,"all_payloads_inline":true,"payload_bytes":payload_bytes,
        "default_blob_threshold_bytes":DEFAULT_BLOB_THRESHOLD_BYTES,"journal_bytes":journal.len()}),
    )
}
fn run(root: &Path, corpus: &Path, count: usize, batch: usize) -> Result<()> {
    ensure!(
        [64, 256].contains(&count) && [1, 8, 64, 256].contains(&batch) && count % batch == 0,
        "unsupported bounded workload"
    );
    let all = read_corpus(corpus)?;
    let messages = &all[..count];
    let rt = runtime()?;
    let store = fresh_store(root)?;
    let thread = new_thread_id();
    let mut samples = Vec::with_capacity(count / batch);
    for (index, group) in messages.chunks_exact(batch).enumerate() {
        let before = allocation::Counts::read();
        let started = Instant::now();
        rt.block_on(store.append_history(thread, None, group))?;
        let elapsed_ns = started.elapsed().as_nanos();
        let allocations = allocation::Counts::read().since(before);
        samples.push(json!({"append_index":index+1,"messages_in_group":batch,
            "cold_writer_initialization":index==0,"elapsed_ns":elapsed_ns,"allocations":allocations}));
    }
    let result = validate(&store, messages, batch)?;
    let history_file = root.join("final-history.json");
    create_file(
        &history_file,
        &serde_json::to_vec(&store.load_projection()?.history)?,
    )?;
    emit(
        json!({"event":"append_groups","core_pin":PIN,"messages":count,"batch_size":batch,
        "session_dir":store.session_dir(),"final_history_file":history_file,"validation":result,
        "append_samples":samples,"measurement":"debug whole public append call; allocation requests not RSS; sync remains inside; no fsync-isolation claim",
        "transaction_boundaries_differ":true}),
    )
}
fn reopen(session: &Path, corpus: &Path, count: usize, batch: usize) -> Result<()> {
    ensure!(
        [64, 256].contains(&count) && [1, 8, 64, 256].contains(&batch) && count % batch == 0,
        "unsupported bounded reopen"
    );
    let all = read_corpus(corpus)?;
    let store = SessionStore::open(session.to_owned())?;
    let before = fs::read(store.journal_path())?;
    let result = validate(&store, &all[..count], batch)?;
    ensure!(
        fs::read(store.journal_path())? == before,
        "reopen changed canonical bytes"
    );
    emit(
        json!({"event":"reopen","core_pin":PIN,"messages":count,"batch_size":batch,
        "validation":result,"journal_unchanged":true}),
    )
}
fn rollback(root: &Path, corpus: &Path, kind: &str) -> Result<()> {
    ensure!(
        ["active", "incoming"].contains(&kind),
        "unknown rollback kind"
    );
    let all = read_corpus(corpus)?;
    let rt = runtime()?;
    let store = fresh_store(root)?;
    let thread = new_thread_id();
    rt.block_on(store.append_history(thread, None, &all[..1]))?;
    let before = fs::read(store.journal_path())?;
    let prior = store.load_projection()?;
    create_file(&root.join("before-rejection.journal.jsonl"), &before)?;
    let last = if kind == "active" { &all[0] } else { &all[1] };
    let invalid = vec![all[1].clone(), all[2].clone(), last.clone()];
    let error = rt
        .block_on(store.append_history(thread, None, &invalid))
        .expect_err("late duplicate accepted");
    let expected_diagnostic = format!("active history contains duplicate message id {}", last.id);
    let error_leaf = error.root_cause().to_string();
    ensure!(
        error_leaf == expected_diagnostic,
        "unrelated rollback error: {error:#}"
    );
    let rejected = store.load_projection()?;
    let after_rejection = fs::read(store.journal_path())?;
    create_file(
        &root.join("after-rejection.journal.jsonl"),
        &after_rejection,
    )?;
    ensure!(
        after_rejection == before
            && rejected.records == prior.records
            && rejected.history == prior.history
            && rejected.history_revision == prior.history_revision,
        "rejected group changed committed source/state"
    );
    // Reuse exactly the new IDs from the failed candidate: no known-part/index poisoning.
    rt.block_on(store.append_history(thread, None, &all[1..3]))?;
    let after = store.load_projection()?;
    ensure!(
        after.history == all[..3] && after.records.len() == 2 && after.history_revision == 2,
        "valid group after rejection differs"
    );
    ensure!(
        after
            .records
            .iter()
            .map(|record| record.session_seq)
            .collect::<Vec<_>>()
            == vec![1, 2],
        "failed group consumed sequence"
    );
    emit(
        json!({"event":"rollback","core_pin":PIN,"kind":kind,"expected_diagnostic":expected_diagnostic,
        "error":format!("{error:#}"),"error_leaf":error_leaf,"rejected_journal_and_projection_unchanged":true,
        "valid_prefix_reused_same_ids":true,"final_messages":3,"final_records":2,"final_revision":2,
        "final_sequences":[1,2],"session_dir":store.session_dir()}),
    )
}
fn main() -> Result<()> {
    let args = std::env::args().collect::<Vec<_>>();
    match args.as_slice() {
        [_, cmd, corpus] if cmd == "generate" => generate(Path::new(corpus)),
        [_, cmd, root, corpus, count, batch] if cmd == "run" => run(
            Path::new(root),
            Path::new(corpus),
            count.parse()?,
            batch.parse()?,
        ),
        [_, cmd, session, corpus, count, batch] if cmd == "reopen" => reopen(
            Path::new(session),
            Path::new(corpus),
            count.parse()?,
            batch.parse()?,
        ),
        [_, cmd, root, corpus, kind] if cmd == "rollback" => {
            rollback(Path::new(root), Path::new(corpus), kind)
        }
        _ => bail!(
            "generate CORPUS | run ROOT CORPUS COUNT BATCH | reopen SESSION CORPUS COUNT BATCH | rollback ROOT CORPUS active|incoming"
        ),
    }
}
