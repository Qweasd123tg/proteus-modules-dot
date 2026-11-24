//! Durable synthetic fixture for strict fallback and small projected/canonical controls.
use proteus_contracts::{
    contracts::*,
    domain::{new_record_id, new_session_id, new_thread_id},
    model_standard::{CanonicalMessage, MessageRole},
    storage::journal::*,
};
use ::session_storage::{BackendKind, StorageService};
use std::{collections::BTreeMap, fs, path::Path};

fn same_text(first: usize, end: usize, multiplier: usize) -> Vec<CanonicalMessage> {
    let suffix = "Синтетический текст для замера памяти и прокрутки. ".repeat(multiplier);
    (first..=end)
        .map(|i| {
            CanonicalMessage::text(
                if i % 2 == 0 {
                    MessageRole::User
                } else {
                    MessageRole::Assistant
                },
                format!("Fixture row {i}\n{suffix}"),
            )
        })
        .collect()
}

fn seed(kind: BackendKind, root: &Path, rows: [Vec<CanonicalMessage>; 3]) -> SessionLocator {
    let cfg = root.join("config");
    let ws = root.join("workspace");
    fs::create_dir_all(&cfg).unwrap();
    fs::create_dir_all(&ws).unwrap();
    let s = StorageService::new(kind);
    let SessionStorageResponse::Session { descriptor } = s
        .execute(SessionStorageRequest::Create {
            config_root: cfg,
            workspace_path: ws,
            session_id: new_session_id(),
            parent_session_id: None,
        })
        .unwrap()
    else {
        panic!("missing session");
    };
    let SessionStorageResponse::Writer {
        lease,
        mut revision,
    } = s
        .execute(SessionStorageRequest::AcquireWriter {
            session: descriptor.session.clone(),
        })
        .unwrap()
    else {
        panic!("missing lease");
    };
    let thread_id = Some(new_thread_id());
    for messages in rows {
        let SessionStorageResponse::Committed { ack } = s
            .execute(SessionStorageRequest::Commit {
                commit: StorageCommit {
                    lease: lease.clone(),
                    operation_id: new_record_id(),
                    expected: revision,
                    timestamp_ms: 1234,
                    attribution: StorageRecordAttribution {
                        execution_id: None,
                        thread_id,
                        turn_id: None,
                    },
                    entry: JournalEntry::HistoryMutated(HistoryMutated {
                        previous_revision: revision.history_revision,
                        new_revision: revision.history_revision + 1,
                        mutation: HistoryMutationKind::Append,
                        messages,
                        compaction: None,
                        tool_results: vec![],
                    }),
                },
            })
            .unwrap()
        else {
            panic!("missing durable ACK");
        };
        revision = ack.revision;
    }
    assert_eq!(revision.session_seq, 3);
    s.execute(SessionStorageRequest::ReleaseWriter { lease }).unwrap();
    descriptor.session
}

fn main() {
    let arg = std::env::args_os().nth(1).unwrap();
    let out = Path::new(&arg);
    fs::create_dir(out).unwrap();
    let mut strict = Vec::new();
    let mut small = BTreeMap::new();
    for kind in [BackendKind::Jsonl, BackendKind::Sqlite] {
        let key = format!("{kind:?}").to_ascii_lowercase();
        let session = seed(
            kind,
            &out.join(format!("{key}-strict")),
            [
                vec![CanonicalMessage::text(MessageRole::User, "tiny predecessor")],
                same_text(1, 50_000, 5),
                vec![CanonicalMessage::text(
                    MessageRole::User,
                    "short final record",
                )],
            ],
        );
        strict.push((format!("{kind:?}"), session));
        let session = seed(
            kind,
            &out.join(format!("{key}-multi")),
            [
                same_text(1, 3500, 4),
                same_text(3501, 7000, 4),
                same_text(7001, 10500, 4),
            ],
        );
        small.insert(key, BTreeMap::from([("multi", session)]));
    }
    serde_json::to_writer(fs::File::create(out.join("strict.json")).unwrap(), &strict).unwrap();
    serde_json::to_writer(fs::File::create(out.join("small.json")).unwrap(), &small).unwrap();
}
