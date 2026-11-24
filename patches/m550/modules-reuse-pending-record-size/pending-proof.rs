use super::*;
use crate::{backend::RecordSnapshot, snapshot::SnapshotState};
use ring::digest::{Context, SHA256};
use std::{cell::RefCell, collections::VecDeque, io::Write};

thread_local! {
    static SPY: RefCell<Option<Vec<(u64,usize)>>> = const { RefCell::new(None) };
}
pub(crate) fn measure(record: &JournalRecord) -> anyhow::Result<usize> {
    let bytes = crate::codec::encoded_bytes(record)?;
    SPY.with(|s| {
        if let Some(x) = s.borrow_mut().as_mut() {
            x.push((record.session_seq, bytes));
        }
    });
    Ok(bytes)
}
fn ingest<T>(f: impl FnOnce() -> T) -> (T, Vec<(u64, usize)>) {
    SPY.with(|s| assert!(s.replace(Some(vec![])).is_none()));
    let x = f();
    let counts = SPY.with(|s| s.replace(None).unwrap());
    (x, counts)
}
fn query(
    s: &StorageService,
    snapshot: &StorageSnapshot,
    after_seq: u64,
    limit: u32,
) -> anyhow::Result<StorageRecordPage> {
    let req = SessionStorageRequest::ReadRecords {
        snapshot: snapshot.clone(),
        after_seq,
        limit,
    };
    let v = s.execute(req.clone())?;
    // Do not instrument the separate SDK response validation pass.
    req.validate_response(&v)?;
    let SessionStorageResponse::Records { page } = v else {
        panic!("expected record page")
    };
    Ok(page)
}
fn strict(s: &StorageService, session: &SessionLocator) -> StorageSnapshot {
    let SessionStorageResponse::Snapshot { snapshot } = s
        .execute(SessionStorageRequest::OpenSnapshot {
            session: session.clone(),
        })
        .unwrap()
    else {
        panic!("no snapshot")
    };
    snapshot
}
fn seq(p: &StorageRecordPage) -> Vec<u64> {
    p.records.iter().map(|r| r.session_seq).collect()
}
fn fixture_page(rows: &[JournalRecord], mut id: StorageSnapshot) -> SnapshotState {
    id.revision = StorageRevision {
        session_seq: rows.len() as u64,
        history_revision: rows.len() as u64,
    };
    let source = Rows(rows.iter().cloned().collect());
    SnapshotState::new(id, Box::new(source), true, None).unwrap()
}
struct Rows(VecDeque<JournalRecord>);
impl RecordSnapshot for Rows {
    fn reset(&mut self) -> anyhow::Result<()> {
        Ok(())
    }
    fn next(&mut self) -> anyhow::Result<Option<JournalRecord>> {
        Ok(self.0.pop_front())
    }
    fn read_hash(&self) -> Context {
        Context::new(&SHA256)
    }
    fn fingerprint(&self) -> &str {
        ""
    }
    fn extent(&self) -> u64 {
        0
    }
    fn prefix_fingerprint(&mut self, _: u64) -> anyhow::Result<Option<String>> {
        unreachable!()
    }
}
fn record(id: &StorageSnapshot, seq: u64, text_: String) -> JournalRecord {
    JournalRecord {
        schema_version: JOURNAL_SCHEMA_VERSION,
        record_id: new_record_id(),
        session_id: id.session.session_id,
        timestamp_ms: 1234,
        session_seq: seq,
        thread_id: Some(new_thread_id()),
        execution_id: None,
        turn_id: None,
        entry: JournalEntry::HistoryMutated(HistoryMutated {
            previous_revision: seq - 1,
            new_revision: seq,
            mutation: HistoryMutationKind::Append,
            messages: vec![CanonicalMessage::text(MessageRole::User, text_)],
            compaction: None,
            tool_results: vec![],
        }),
    }
}
fn exact(id: &StorageSnapshot, seq: u64, want: usize) -> JournalRecord {
    let empty = record(id, seq, String::new());
    let overhead = crate::codec::encoded_bytes(&empty).unwrap();
    let r = record(id, seq, "a".repeat(want - overhead));
    assert_eq!(crate::codec::encoded_bytes(&r).unwrap(), want);
    r
}

#[test]
fn exact_nominal_cap_and_plus_one_still_make_the_same_page_cut() {
    let f = Fixture::new(BackendKind::Jsonl);
    let id = f.snapshot();
    let small = record(&id, 1, "small".into());
    let base = crate::codec::encoded_bytes(&small).unwrap();
    for extra in [0, 1] {
        let size = SESSION_STORAGE_PAGE_BYTE_BUDGET - base + extra;
        let mut s = fixture_page(&[small.clone(), exact(&id, 2, size)], id.clone());
        let (out, counts) = ingest(|| s.page(0, 9).unwrap());
        assert_eq!(counts, [(1, base), (2, size)]);
        if extra == 0 {
            assert_eq!(seq(&out), [1, 2]);
            assert_eq!(out.next_after_seq, None);
        } else {
            assert_eq!(seq(&out), [1]);
            assert_eq!(out.next_after_seq, Some(1));
            let (out, second_count) = ingest(|| s.page(1, 9).unwrap());
            assert_eq!(seq(&out), [2]);
            assert_eq!(out.next_after_seq, None);
            assert!(second_count.is_empty() || second_count == [(2, size)]);
            println!("EDGE +1 count {}", second_count.len());
        }
    }
}

#[test]
fn maximum_and_serde_failure_happen_before_releasing_the_prior_tiny_page() {
    let f = Fixture::new(BackendKind::Jsonl);
    let id = f.snapshot();
    let tiny = record(&id, 1, "prior tiny".into());
    for size in [
        SESSION_STORAGE_MAX_RECORD_BYTES,
        SESSION_STORAGE_MAX_RECORD_BYTES + 1,
    ] {
        // Move rather than clone the very large typed row into this boundary fixture.
        let source = Rows(VecDeque::from(vec![tiny.clone(), exact(&id, 2, size)]));
        let mut i = id.clone();
        i.revision = StorageRevision {
            session_seq: 2,
            history_revision: 2,
        };
        let mut s = SnapshotState::new(i, Box::new(source), true, None).unwrap();
        let (page, counts) = ingest(|| s.page(0, 9));
        assert_eq!(counts[1], (2, size));
        if size == SESSION_STORAGE_MAX_RECORD_BYTES {
            assert_eq!(seq(&page.unwrap()), [1]);
            let next = s.page(1, 9).unwrap();
            assert_eq!(seq(&next), [2]);
        } else {
            assert_eq!(
                page.unwrap_err().to_string(),
                "canonical record exceeds maximum"
            );
        }
    }
    #[cfg(unix)]
    {
        use std::{ffi::OsString, os::unix::ffi::OsStringExt};
        let mut bad = record(&id, 2, "skip me not".into());
        let JournalEntry::HistoryMutated(h) = &mut bad.entry else {
            panic!()
        };
        h.messages[0].parts[0].payload = ContentPart::FileRef {
            path: OsString::from_vec(vec![0xff]).into(),
            content: None,
        };
        let mut s = fixture_page(&[tiny, bad], id);
        let err = s.page(0, 9).unwrap_err();
        assert!(err.to_string().contains("valid UTF-8"), "{err:#}");
    }
}

#[test]
fn reset_and_warm_terminal_must_never_borrow_a_prior_count() {
    for kind in backends() {
        let mut f = Fixture::new(kind);
        f.append(vec![text("prior tiny")]);
        f.append(vec![text(&"a".repeat(5 * 1024 * 1024))]);
        f.append(vec![text("new tail, distinct size")]);
        let id = f.snapshot();
        let reset_get = || ingest(|| query(&f.service, &id, 0, 2).unwrap());
        let (a, w) = reset_get();
        assert_eq!(seq(&a), [1]);
        assert_eq!(w.iter().map(|x| x.0).collect::<Vec<_>>(), [1, 2]);
        // Retry repositions. It must newly size the record it fetches, even at
        // the same sequence, and the old deferred count cannot transfer.
        let (b, again) = reset_get();
        assert_eq!(a, b);
        assert_eq!(w, again);
        let (tiny, v) = ingest(|| query(&f.service, &id, 0, 1).unwrap());
        assert_eq!(seq(&tiny), [1]);
        assert_eq!(v, [w[0]]);
        let (direct, u) = ingest(|| query(&f.service, &id, 1, 1).unwrap());
        assert_eq!(seq(&direct), [2]);
        assert_eq!(u, [w[1]]);
        let (_new, _) = reset_get();
        let _ = f.conversation(id.clone(), StorageHistoryPoint::Current);
        let (again, seen) = ingest(|| query(&f.service, &id, 1, 1).unwrap());
        assert_eq!(again, direct);
        assert_eq!(seen, [w[1]]);
        let warm = f.snapshot();
        let (tail, counts) = ingest(|| query(&f.service, &warm, 2, 1).unwrap());
        assert_eq!(seq(&tail), [3]);
        assert_eq!(counts.len(), 1);
        assert_eq!(counts[0].0, 3);
        assert_ne!(counts[0].1, w[1].1);
    }
}

#[test]
fn corrupt_fixed_jsonl_prefix_never_exposes_a_pending_record() {
    let mut f = Fixture::new(BackendKind::Jsonl);
    f.append(vec![text("prior tiny marker")]);
    f.append(vec![text(&"Z".repeat(5 * 1024 * 1024))]);
    let id = f.snapshot();
    let a = query(&f.service, &id, 0, 2).unwrap();
    assert_eq!(seq(&a), [1]);
    assert_eq!(a.next_after_seq, Some(1));
    let path = f.descriptor.record_location.as_ref().unwrap();
    let good = std::fs::read(path).unwrap();
    let mut broken = good.clone();
    broken[0] = b'[';
    std::fs::write(path, broken).unwrap();
    assert!(query(&f.service, &id, 1, 1).is_err());
    std::fs::write(path, good).unwrap();
    let (b, counts) = ingest(|| query(&f.service, &id, 1, 1).unwrap());
    assert_eq!(seq(&b), [2]);
    assert_eq!(counts.len(), 1);
    assert_eq!(
        counts[0].0, 2,
        "a new guarded replay cannot reuse its discarded predecessor's count"
    );
}

fn commit_owned(f: &mut Fixture, messages: Vec<CanonicalMessage>) {
    let commit = StorageCommit {
        lease: f.lease.clone(),
        operation_id: new_record_id(),
        expected: f.revision,
        timestamp_ms: 1234,
        attribution: StorageRecordAttribution {
            execution_id: None,
            turn_id: None,
            thread_id: Some(f.thread),
        },
        entry: JournalEntry::HistoryMutated(HistoryMutated {
            previous_revision: f.revision.history_revision,
            new_revision: f.revision.history_revision + 1,
            mutation: HistoryMutationKind::Append,
            messages,
            compaction: None,
            tool_results: vec![],
        }),
    };
    let SessionStorageResponse::Committed { ack } = f
        .service
        .execute(SessionStorageRequest::Commit { commit })
        .unwrap()
    else {
        panic!("missing ack")
    };
    f.revision = ack.revision;
}

struct Digest(Context);
impl Write for Digest {
    fn write(&mut self, bs: &[u8]) -> std::io::Result<usize> {
        self.0.update(bs);
        Ok(bs.len())
    }
    fn flush(&mut self) -> std::io::Result<()> {
        Ok(())
    }
}
fn wire(p: &StorageRecordPage) -> String {
    let mut d = Digest(Context::new(&SHA256));
    serde_json::to_writer(&mut d, &p.records).unwrap();
    crate::io::digest_hex(d.0.finish())
}
fn synthetic() -> Vec<CanonicalMessage> {
    let suffix = "Синтетический текст для замера памяти и прокрутки. ".repeat(5);
    (1..=50000)
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
type Corpus = Vec<(String, SessionLocator)>;
#[test]
#[ignore = "shared durable large strict fallback corpus"]
fn large_strict_pending_count_same_corpus() {
    let path = std::path::PathBuf::from(std::env::var_os("PROTEUS_PENDING_CORPUS").unwrap());
    match std::env::var("PROTEUS_PENDING_MODE").unwrap().as_str() {
        "seed" => {
            let mut c = Corpus::new();
            for kind in backends() {
                let mut f = Fixture::new(kind);
                commit_owned(&mut f, vec![text("tiny predecessor")]);
                commit_owned(&mut f, synthetic());
                commit_owned(&mut f, vec![text("short final record")]);
                f.service
                    .execute(SessionStorageRequest::ReleaseWriter {
                        lease: f.lease.clone(),
                    })
                    .unwrap();
                c.push((format!("{kind:?}"), f.descriptor.session.clone()));
                let Fixture {
                    root, _workspace, ..
                } = f;
                let _ = root.keep();
                let _ = _workspace.keep();
            }
            let f = std::fs::OpenOptions::new()
                .create_new(true)
                .write(true)
                .open(path)
                .unwrap();
            serde_json::to_writer(f, &c).unwrap();
        }
        "read" => {
            let sessions: Corpus =
                serde_json::from_reader(std::fs::File::open(path).unwrap()).unwrap();
            for (kind, session) in sessions {
                let b = match kind.as_str() {
                    "Jsonl" => BackendKind::Jsonl,
                    "Sqlite" => BackendKind::Sqlite,
                    _ => panic!(),
                };
                let s = StorageService::new(b);
                assert_eq!(
                    s.execute(SessionStorageRequest::OpenDisplaySnapshot {
                        session: session.clone()
                    })
                    .unwrap(),
                    SessionStorageResponse::DisplaySnapshot { projection: None }
                );
                let snap = strict(&s, &session);
                let mut after = 0;
                for want in [1, 2, 3] {
                    crate::diagnostics::reset();
                    let (page, counts) = ingest(|| query(&s, &snap, after, 2).unwrap());
                    let diag = crate::diagnostics::get();
                    assert_eq!(seq(&page), [want]);
                    assert_eq!(page.snapshot, snap);
                    assert_eq!(page.next_after_seq, (want != 3).then_some(want));
                    if want == 2 {
                        let JournalEntry::HistoryMutated(h) = &page.records[0].entry else {
                            panic!()
                        };
                        assert_eq!(h.messages.len(), 50_000);
                    }
                    let counts = counts
                        .iter()
                        .map(|(i, x)| format!("{i}:{x}"))
                        .collect::<Vec<_>>()
                        .join(",");
                    let counts = if counts.is_empty() {
                        "-".into()
                    } else {
                        counts
                    };
                    println!(
                        "STRICT {kind} {want} {counts} {} {} {} {}",
                        diag.decoded,
                        diag.fingerprint_bytes,
                        snap.content_sha256,
                        wire(&page)
                    );
                    after = want;
                }
            }
        }
        _ => panic!("unexpected meter mode"),
    }
}

#[test]
fn jsonl_warm_terminal_capture_sizes_once_without_a_second_decode() {
    let mut f = Fixture::new(BackendKind::Jsonl);
    f.append(vec![text("inline first")]);
    f.append(vec![text("inline terminal")]);
    let original = f.snapshot();
    let warm = f.snapshot();
    assert_eq!(warm.revision, original.revision);
    assert_eq!(warm.content_sha256, original.content_sha256);
    crate::diagnostics::reset();
    let (page, counts) = ingest(|| query(&f.service, &warm, 1, 1).unwrap());
    assert_eq!(seq(&page), [2]);
    assert_eq!(page.next_after_seq, None);
    assert_eq!(
        crate::diagnostics::get().decoded,
        2,
        "authenticated terminal capture did not rescan"
    );
    assert_eq!(
        counts,
        [(2, crate::codec::encoded_bytes(&page.records[0]).unwrap())],
        "terminal capture did not reuse a count it never measured"
    );
}
