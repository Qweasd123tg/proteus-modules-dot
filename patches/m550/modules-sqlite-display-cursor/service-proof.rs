use super::*;
use crate::backend::{JournalBackend, Sqlite};
use proteus_contracts::domain::{new_record_id, new_thread_id};
use ring::digest::{Context, SHA256};
use std::{
    cell::Cell,
    io::{BufWriter, Write},
    path::Path,
};

thread_local! { static QUERIES: Cell<(u64,u64)> = const { Cell::new((0,0)) }; }
pub(crate) fn row_query(batched: bool) {
    let (single, bulk) = QUERIES.get();
    QUERIES.set(if batched {
        (single, bulk + 1)
    } else {
        (single + 1, bulk)
    });
}

const ROWS: u64 = 50_000;
fn record(session: proteus_contracts::domain::SessionId, i: u64, repeats: usize) -> JournalRecord {
    let content = format!(
        "Fixture row {i}\n{}",
        "Синтетический текст для замера памяти и прокрутки. ".repeat(repeats)
    );
    JournalRecord {
        schema_version: JOURNAL_SCHEMA_VERSION,
        session_id: session,
        record_id: new_record_id(),
        session_seq: i,
        timestamp_ms: 100 + i as i64,
        execution_id: None,
        thread_id: Some(new_thread_id()),
        turn_id: None,
        entry: JournalEntry::HistoryMutated(HistoryMutated {
            previous_revision: i - 1,
            new_revision: i,
            mutation: HistoryMutationKind::Append,
            messages: vec![CanonicalMessage::text(
                if i % 2 == 0 {
                    MessageRole::User
                } else {
                    MessageRole::Assistant
                },
                content,
            )],
            compaction: None,
            tool_results: vec![],
        }),
    }
}
fn seed_file(f: &Fixture, kind: BackendKind, repeats: usize) {
    let dir = f.descriptor.local_path.as_ref().unwrap();
    let id = f.descriptor.session.session_id;
    let count = ROWS;
    match kind {
        BackendKind::Jsonl => {
            let mut out = BufWriter::with_capacity(
                128 * 1024,
                std::fs::File::create(dir.join(crate::codec::JOURNAL_FILE)).unwrap(),
            );
            for i in 1..=count {
                // Real production encoder; no fixture can elide envelope fields.
                let (line, blobs) = crate::codec::encode(
                    dir,
                    &record(id, i, repeats),
                    crate::codec::DEFAULT_BLOB_THRESHOLD,
                )
                .unwrap();
                assert!(blobs.is_empty());
                out.write_all(&line).unwrap();
            }
            out.flush().unwrap();
            out.get_ref().sync_data().unwrap();
        }
        BackendKind::Sqlite => {
            // Real production DDL/identity and canonical non-hook row encoder.
            // Batch insertion accelerates fixture construction only.
            Sqlite::default().recover(dir, id).unwrap();
            let mut c = rusqlite::Connection::open(dir.join("journal.sqlite")).unwrap();
            let tx = c.transaction().unwrap();
            {
                let mut stmt = tx
                    .prepare("INSERT INTO journal(sequence,record_id,payload) VALUES(?1,?2,?3)")
                    .unwrap();
                for i in 1..=count {
                    let rec = record(id, i, repeats);
                    let payload = serde_json::to_vec(&rec).unwrap();
                    stmt.execute(rusqlite::params![
                        i as i64,
                        rec.record_id.to_string(),
                        payload
                    ])
                    .unwrap();
                }
            }
            tx.commit().unwrap();
            c.execute_batch("PRAGMA wal_checkpoint(TRUNCATE);").unwrap();
        }
    }
}
type Corpus = Vec<(String, usize, SessionLocator)>;
fn seed(path: &Path) {
    let mut data = Corpus::new();
    for kind in backends() {
        for repeats in [4, 5] {
            let f = Fixture::new(kind);
            f.service
                .execute(SessionStorageRequest::ReleaseWriter {
                    lease: f.lease.clone(),
                })
                .unwrap();
            seed_file(&f, kind, repeats);
            data.push((format!("{kind:?}"), repeats, f.descriptor.session.clone()));
            let Fixture {
                root, _workspace, ..
            } = f;
            let _dir = root.keep();
            let _workspace = _workspace.keep();
        }
    }
    let mut f = std::fs::OpenOptions::new()
        .create_new(true)
        .write(true)
        .open(path)
        .unwrap();
    serde_json::to_writer(&mut f, &data).unwrap();
    f.flush().unwrap();
}
struct HashWriter(Context);
impl Write for HashWriter {
    fn write(&mut self, bytes: &[u8]) -> std::io::Result<usize> {
        self.0.update(bytes);
        Ok(bytes.len())
    }
    fn flush(&mut self) -> std::io::Result<()> {
        Ok(())
    }
}
fn check_request(s: &StorageService, req: SessionStorageRequest) -> SessionStorageResponse {
    let rep = s.execute(req.clone()).unwrap();
    req.validate_response(&rep).unwrap();
    rep
}
fn read_fixture(path: &Path) {
    let data: Corpus = serde_json::from_reader(std::fs::File::open(path).unwrap()).unwrap();
    for (name, repeats, session) in data {
        let kind = match name.as_str() {
            "Jsonl" => BackendKind::Jsonl,
            "Sqlite" => BackendKind::Sqlite,
            _ => panic!(),
        };
        let s = StorageService::new(kind);
        QUERIES.set((0, 0));
        crate::diagnostics::reset();
        let open = check_request(
            &s,
            SessionStorageRequest::OpenDisplaySnapshot {
                session: session.clone(),
            },
        );
        let open_d = crate::diagnostics::get();
        assert_eq!(open_d.decoded, ROWS);
        let (single, bulk) = QUERIES.get();
        let SessionStorageResponse::DisplaySnapshot { projection } = open else {
            panic!("expected display snapshot")
        };
        if repeats == 5 {
            assert!(
                projection.is_none(),
                "untouched serialized state cap and fallback"
            );
            let SessionStorageResponse::Snapshot { snapshot } =
                check_request(&s, SessionStorageRequest::OpenSnapshot { session })
            else {
                panic!("missing fallback snapshot")
            };
            assert_eq!(snapshot.revision.session_seq, ROWS);
            let SessionStorageResponse::Records { page } = check_request(
                &s,
                SessionStorageRequest::ReadRecords {
                    snapshot,
                    after_seq: 0,
                    limit: 2,
                },
            ) else {
                panic!("missing first canonical page")
            };
            assert_eq!(page.records.len(), 2);
            assert_eq!(page.next_after_seq, Some(2));
            println!(
                "CAP {name} {repeats} {} {} {single} {bulk}",
                open_d.decoded, open_d.fingerprint_bytes
            );
            continue;
        }
        let display = projection.expect("fixture fits current 32 MiB state cap");
        assert_eq!(display.snapshot.revision.session_seq, ROWS);
        assert_eq!(display.state.conversation.messages.len(), ROWS as usize);
        let state_size = crate::codec::encoded_bytes(&display.state).unwrap();
        drop(display.state);
        let snapshot = display.snapshot;
        let mut after = 0;
        let mut pages = 0;
        let mut wire = HashWriter(Context::new(&SHA256));
        let mut bytes = 0;
        crate::diagnostics::reset();
        loop {
            let req = SessionStorageRequest::ReadDisplayRecords {
                snapshot: snapshot.clone(),
                after_seq: after,
                limit: 250,
            };
            let SessionStorageResponse::Records { page } = check_request(&s, req) else {
                panic!("expected display page")
            };
            pages += 1;
            for record in page.records {
                after += 1;
                assert_eq!(record.session_seq, after);
                serde_json::to_writer(&mut wire, &record).unwrap();
                wire.0.update(b"\n");
                bytes += crate::codec::encoded_bytes(&record).unwrap() + 1;
            }
            if let Some(next) = page.next_after_seq {
                assert_eq!(after, next);
            } else {
                break;
            }
        }
        assert_eq!(after, ROWS);
        assert_eq!(
            crate::diagnostics::get().decoded,
            0,
            "do not re-read canonical source"
        );
        println!(
            "DISPLAY {name} {repeats} {state_size} {after} {pages} {bytes} {single} {bulk} {} {} {}",
            crate::io::digest_hex(wire.0.finish()),
            open_d.fingerprint_bytes,
            snapshot.content_sha256
        );
        // Lost-ACK retry and non-monotonic page recovery after EOF.
        let result = check_request(
            &s,
            SessionStorageRequest::ReadDisplayRecords {
                snapshot: snapshot.clone(),
                after_seq: 999,
                limit: 1,
            },
        );
        assert_eq!(
            result,
            check_request(
                &s,
                SessionStorageRequest::ReadDisplayRecords {
                    snapshot,
                    after_seq: 999,
                    limit: 1
                }
            )
        );
    }
}
#[test]
#[ignore = "requires shared synthetic durable corpus"]
fn sqlite_display_scan_large_corpus() {
    let path = std::path::PathBuf::from(std::env::var_os("PROTEUS_STAGE_CORPUS").unwrap());
    match std::env::var("PROTEUS_STAGE_MODE").unwrap().as_str() {
        "seed" => seed(&path),
        "read" => read_fixture(&path),
        _ => panic!("unexpected fixture mode"),
    }
}

fn display(
    service: &StorageService,
    session: &SessionLocator,
) -> anyhow::Result<StorageDisplaySnapshot> {
    let request = SessionStorageRequest::OpenDisplaySnapshot {
        session: session.clone(),
    };
    let response = service.execute(request.clone())?;
    request.validate_response(&response)?;
    let SessionStorageResponse::DisplaySnapshot {
        projection: Some(display),
    } = response
    else {
        panic!("expected fixture projection")
    };
    Ok(display)
}

fn sqlite_file(f: &Fixture) -> rusqlite::Connection {
    rusqlite::Connection::open(f.descriptor.record_location.as_ref().unwrap()).unwrap()
}

#[test]
fn sqlite_display_legacy_tables_and_views_keep_the_seek_oracle() {
    for alternate in ["table", "view"] {
        let mut f = Fixture::new(BackendKind::Sqlite);
        let a = text("first exact payload");
        let b = text("second exact payload");
        f.append(vec![a.clone()]);
        f.append(vec![b.clone()]);
        let expected = display(&f.service, &f.descriptor.session).unwrap();
        f.service
            .execute(SessionStorageRequest::ReleaseWriter {
                lease: f.lease.clone(),
            })
            .unwrap();
        let c = sqlite_file(&f);
        match alternate {
            "table" => c
                .execute_batch(
                    "ALTER TABLE journal RENAME TO original;
                CREATE TABLE journal (sequence INTEGER, record_id TEXT, payload BLOB);
                INSERT INTO journal SELECT * FROM original;",
                )
                .unwrap(),
            "view" => c
                .execute_batch(
                    "ALTER TABLE journal RENAME TO original;
                CREATE VIEW journal AS SELECT sequence,record_id,payload FROM original;",
                )
                .unwrap(),
            _ => unreachable!(),
        }
        let s = StorageService::new(BackendKind::Sqlite);
        QUERIES.set((0, 0));
        let now = display(&s, &f.descriptor.session).unwrap();
        assert_eq!(QUERIES.get(), (3, 0));
        assert_eq!(now.state, expected.state);
        assert_eq!(
            now.snapshot.content_sha256,
            expected.snapshot.content_sha256
        );
        assert_eq!(now.state.conversation.messages, [a, b]);
        let SessionStorageResponse::Records { page } = check_request(
            &s,
            SessionStorageRequest::ReadDisplayRecords {
                snapshot: now.snapshot,
                after_seq: 0,
                limit: 2,
            },
        ) else {
            panic!("alternate display records")
        };
        assert_eq!(page.records.len(), 2);
        assert!(page.next_after_seq.is_none());
    }
}

#[test]
fn sqlite_display_rejects_corrupt_prefix_with_original_errors() {
    let cases = [
        ("identity", "UPDATE journal SET payload=(SELECT payload FROM journal WHERE sequence=1) WHERE sequence=2;",
            "SQLite journal record identity mismatch"),
        ("gap", "DELETE FROM journal WHERE sequence=2;", "journal sequence mismatch"),
        ("full-hash", "PRAGMA ignore_check_constraints=ON;
            INSERT INTO journal SELECT -1, 'deliberately invalid sequence',payload FROM journal WHERE sequence=1;",
            "SQLite snapshot prefix changed"),
    ];
    for (kind, statement, error) in cases {
        let mut f = Fixture::new(BackendKind::Sqlite);
        for _ in 0..3 {
            f.append(vec![text("strict fixed journal")]);
        }
        let snap = display(&f.service, &f.descriptor.session).unwrap();
        f.service
            .execute(SessionStorageRequest::ReleaseWriter {
                lease: f.lease.clone(),
            })
            .unwrap();
        sqlite_file(&f).execute_batch(statement).unwrap();
        let s = StorageService::new(BackendKind::Sqlite);
        for _ in 0..2 {
            let err = display(&s, &f.descriptor.session).unwrap_err();
            assert!(err.to_string().contains(error), "{kind}: {err:?}");
        }
        // Previously opened SQLite snapshot and its staged page remain fixed.
        let SessionStorageResponse::Records { page } = check_request(
            &f.service,
            SessionStorageRequest::ReadDisplayRecords {
                snapshot: snap.snapshot,
                after_seq: 0,
                limit: 3,
            },
        ) else {
            panic!("lost previously verified pinned source")
        };
        assert_eq!(page.records.len(), 3);
        assert_eq!(page.records[1].session_seq, 2);
    }
}

type PendingWrite = (std::path::PathBuf, Vec<u8>);
thread_local! {
    static WRITE_AFTER_DECODE: std::cell::RefCell<Option<PendingWrite>> = const { std::cell::RefCell::new(None) };
}

pub(crate) fn row_decoded(sequence: u64) {
    if sequence == 1 {
        let next = WRITE_AFTER_DECODE.with(|w| w.borrow_mut().take());
        if let Some((file, payload)) = next {
            let c = rusqlite::Connection::open(file).unwrap();
            assert_eq!(
                c.execute("UPDATE journal SET payload=?1 WHERE sequence=2", [payload])
                    .unwrap(),
                1
            );
        }
    }
}

#[test]
fn sqlite_display_keeps_transaction_pinned_after_first_replayed_row() {
    let mut f = Fixture::new(BackendKind::Sqlite);
    f.append(vec![text("first fixed value")]);
    f.append(vec![text("second OLD value")]);
    f.service
        .execute(SessionStorageRequest::ReleaseWriter {
            lease: f.lease.clone(),
        })
        .unwrap();
    let c = sqlite_file(&f);
    let payload: Vec<u8> = c
        .query_row("SELECT payload FROM journal WHERE sequence=2", [], |r| {
            r.get(0)
        })
        .unwrap();
    let json = String::from_utf8(payload).unwrap();
    assert_eq!(json.matches("second OLD value").count(), 1);
    let new = json
        .replace("second OLD value", "second NEW value")
        .into_bytes();
    let path = f.descriptor.record_location.clone().unwrap();
    drop(c);

    let reader = StorageService::new(BackendKind::Sqlite);
    WRITE_AFTER_DECODE.with(|w| *w.borrow_mut() = Some((path, new)));
    let old = display(&reader, &f.descriptor.session).unwrap();
    assert!(WRITE_AFTER_DECODE.with(|w| w.borrow().is_none()));
    assert_eq!(
        old.state.conversation.messages[1].display_text(),
        "second OLD value"
    );
    let new = display(&reader, &f.descriptor.session).unwrap();
    assert_eq!(
        new.state.conversation.messages[1].display_text(),
        "second NEW value"
    );
    assert_ne!(new.snapshot.content_sha256, old.snapshot.content_sha256);
    assert_eq!(
        check_request(
            &reader,
            SessionStorageRequest::CompareSnapshots {
                snapshot: new.snapshot,
                prefix: old.snapshot.clone(),
            }
        ),
        SessionStorageResponse::SnapshotPrefix { matches: false }
    );
    let SessionStorageResponse::Records { page } = check_request(
        &reader,
        SessionStorageRequest::ReadDisplayRecords {
            snapshot: old.snapshot,
            after_seq: 1,
            limit: 1,
        },
    ) else {
        panic!("lost pinned page")
    };
    let JournalEntry::HistoryMutated(m) = &page.records[0].entry else {
        panic!("lost history record")
    };
    assert_eq!(m.messages[0].display_text(), "second OLD value");
}
