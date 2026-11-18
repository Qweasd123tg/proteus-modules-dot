// Temporary release example for the pinned session-storage crate. Not part of the patch.
use anyhow::{Context, Result, ensure};
use proteus_contracts::{
    contracts::*,
    model_standard::{CanonicalMessage, MessageRole},
    storage::journal::*,
};
use ::session_storage::{BackendKind, StorageService};
use std::{
    fs,
    io::{Read, Seek, SeekFrom, Write},
    path::Path,
    time::Instant,
};
use uuid::Uuid;

fn message(i: u64, bytes: usize) -> CanonicalMessage {
    let role = if i % 2 == 1 { MessageRole::User } else { MessageRole::Assistant };
    let mut m = CanonicalMessage::text(role, format!("{i:08}:{}", "x".repeat(bytes)));
    m.id = Uuid::from_u128(20_000 + u128::from(i));
    m.parts[0].part_id = Uuid::from_u128(40_000 + u128::from(i));
    m
}

fn main() -> Result<()> {
    let args = std::env::args().collect::<Vec<_>>();
    let (mode, dir, n, bytes) = (&args[1], Path::new(&args[2]), args[3].parse::<u64>()?, args[4].parse::<usize>()?);
    let svc = StorageService::new(BackendKind::Jsonl);
    let descriptor_file = dir.join("descriptor.json");
    if mode == "seed" {
        let config_root = dir.join("config");
        let workspace_path = dir.join("work");
        fs::create_dir_all(&workspace_path)?;
        fs::create_dir_all(&config_root)?;
        let SessionStorageResponse::Session { descriptor } = svc.execute(SessionStorageRequest::Create {
            config_root, workspace_path, session_id: Uuid::from_u128(42), parent_session_id: None,
        })? else { anyhow::bail!("wrong response to create") };
        let SessionStorageResponse::Writer { lease, mut revision } = svc.execute(SessionStorageRequest::AcquireWriter {
            session: descriptor.session.clone(),
        })? else { anyhow::bail!("wrong response to acquire") };
        for i in 1..=n {
            let commit = StorageCommit {
                lease: lease.clone(), operation_id: Uuid::from_u128(u128::from(i)), expected: revision,
                timestamp_ms: 1234, attribution: StorageRecordAttribution {
                    execution_id: None, thread_id: Some(Uuid::from_u128(222_222)), turn_id: None,
                },
                entry: JournalEntry::HistoryMutated(HistoryMutated {
                    previous_revision: i - 1, new_revision: i, mutation: HistoryMutationKind::Append,
                    messages: vec![message(i, bytes)], compaction: None, tool_results: vec![],
                }),
            };
            let SessionStorageResponse::Committed { ack } = svc.execute(SessionStorageRequest::Commit { commit })?
                else { anyhow::bail!("wrong response to commit") };
            revision = ack.revision;
        }
        svc.execute(SessionStorageRequest::ReleaseWriter { lease })?;
        fs::write(descriptor_file, serde_json::to_vec(&descriptor)?)?;
        return Ok(());
    }
    let descriptor: StorageSessionDescriptor = serde_json::from_slice(&fs::read(descriptor_file)?)?;
    let SessionStorageResponse::Snapshot { snapshot } = svc.execute(SessionStorageRequest::OpenSnapshot {
        session: descriptor.session.clone(),
    })? else { anyhow::bail!("wrong response to snapshot") };
    let req = SessionStorageRequest::ReadConversation { snapshot, point: StorageHistoryPoint::Current };
    if mode == "error" {
        // Only this driver's own fixture. Invalidate the first previously pinned complete record.
        let mut file = fs::OpenOptions::new().read(true).write(true).open(
            descriptor.local_path.context("missing fixture directory")?.join("journal.jsonl"))?;
        let mut first = [0];
        file.read_exact(&mut first)?;
        ensure!(first == [b'{']);
        file.seek(SeekFrom::Start(0))?;
        file.write_all(b"!")?;
        file.sync_all()?;
        let outcome = svc.execute(req);
        file.seek(SeekFrom::Start(0))?;
        file.write_all(&first)?;
        file.sync_all()?;
        let error = format!("{:#}", outcome.unwrap_err());
        ensure!(error.contains("invalid journal record"));
        println!("{}", serde_json::json!({"error":error}));
        return Ok(());
    }
    let start = Instant::now();
    let SessionStorageResponse::Conversation { conversation } = svc.execute(req)?
        else { anyhow::bail!("wrong response to read") };
    let nanos = start.elapsed().as_nanos();
    // Sample before constructing ANY expected message or serializing the reply. VmHWM
    // includes opening and validating the snapshot above as well as the measured request.
    let status = fs::read_to_string("/proc/self/status")?;
    let peak: u64 = status.lines().find(|s| s.starts_with("VmHWM:")).unwrap().split_whitespace().nth(1).unwrap().parse()?;
    ensure!(conversation.revision.session_seq == n && conversation.revision.history_revision == n);
    ensure!(conversation.model_context.is_empty());
    ensure!(conversation.messages.len() == n as usize);
    for (i, m) in conversation.messages.iter().enumerate() {
        ensure!(*m == message(i as u64 + 1, bytes), "incorrect complete message or order at {i}");
    }
    println!("{}", serde_json::json!({"ns":nanos,"rss_kib":peak,"messages":n,"text_bytes_each":bytes+9}));
    Ok(())
}
