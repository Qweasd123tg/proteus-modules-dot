// Appended as an ordinary test module in both copies of the pinned crate.
use super::*;
use crate::{
    backend::{JournalBackend, Jsonl, Sqlite},
    diagnostics,
};
use proteus_contracts::{
    contracts::{ModelCallOrigin, ModelContextObservation, OperationOwner},
    domain::{
        AgentOutput, AgentTask, ExchangeId, ModelRef, new_exchange_id, new_execution_id,
        new_turn_id,
    },
    model_standard::{
        CanonicalModelRequest, CanonicalModelResponse, FinishReason, ModelFailure,
        ModelFailureKind, TokenUsage,
    },
};
use serde_json::{Value, json};
use std::{fs, path::PathBuf};
mod meter;

const CATALOG: &str = ".storage-catalog-v1.json";
fn backend(kind: BackendKind) -> Box<dyn JournalBackend> {
    match kind {
        BackendKind::Jsonl => Box::new(Jsonl::new()),
        BackendKind::Sqlite => Box::new(Sqlite::default()),
    }
}
fn run(s: &StorageService, req: SessionStorageRequest) -> SessionStorageResponse {
    let out = s.execute(req.clone()).unwrap();
    req.validate_response(&out).unwrap();
    out
}
fn request(session: &SessionLocator) -> SessionStorageRequest {
    SessionStorageRequest::OpenSnapshot {
        session: session.clone(),
    }
}
fn open(s: &StorageService, session: &SessionLocator) -> StorageSnapshot {
    let SessionStorageResponse::Snapshot { snapshot } = run(s, request(session)) else {
        panic!()
    };
    snapshot
}
fn identity(s: &StorageSnapshot) -> (&SessionLocator, StorageRevision, &str) {
    (&s.session, s.revision, &s.content_sha256)
}
fn suppress_catalog(f: &Fixture) {
    let dir = f.descriptor.local_path.as_ref().unwrap();
    let p = dir.join(CATALOG);
    if p.is_file() {
        fs::rename(&p, dir.join("r274-catalog-fixture-backup")).unwrap();
    }
}
fn release(f: &Fixture) {
    assert_eq!(
        run(
            &f.service,
            SessionStorageRequest::ReleaseWriter {
                lease: f.lease.clone()
            }
        ),
        SessionStorageResponse::Done
    );
}
fn commit(f: &mut Fixture, at: &StorageRecordAttribution, entry: JournalEntry) {
    let req = SessionStorageRequest::Commit {
        commit: StorageCommit {
            lease: f.lease.clone(),
            operation_id: new_record_id(),
            expected: f.revision,
            timestamp_ms: f.revision.session_seq as i64 + 100,
            attribution: at.clone(),
            entry,
        },
    };
    let SessionStorageResponse::Committed { ack } = run(&f.service, req) else {
        panic!()
    };
    f.revision = ack.revision;
}
fn fail_outcome() -> ModelResponseOutcome {
    ModelResponseOutcome::Error {
        failure: ModelFailure::new(
            ModelFailureKind::ContextWindowExceeded,
            "synthetic direct context exhaustion",
        ),
    }
}
fn model_response(x: ExchangeId, failure: bool) -> JournalEntry {
    JournalEntry::ModelResponseRecorded(ModelResponseRecorded {
        exchange_id: x,
        outcome: if failure {
            fail_outcome()
        } else {
            ModelResponseOutcome::Response {
                response: CanonicalModelResponse::new(
                    CanonicalMessage::text(MessageRole::Assistant, "synthetic completion"),
                    vec![],
                    FinishReason::Stop,
                )
                .with_usage(TokenUsage::new(121, 31)),
            }
        },
    })
}
fn begin(f: &mut Fixture) -> StorageRecordAttribution {
    let at = StorageRecordAttribution {
        execution_id: Some(new_execution_id()),
        thread_id: Some(f.thread),
        turn_id: Some(new_turn_id()),
    };
    let rev = f.revision.history_revision;
    let workspace = f.descriptor.workspace_path.clone();
    commit(
        f,
        &at,
        JournalEntry::TurnOpened(TurnOpened {
            task: AgentTask::new("cold snapshot proof", workspace),
            intent: None,
            base_history_revision: rev,
            module_epoch: 0,
            config_snapshot: json!({}),
        }),
    );
    at
}
fn add_request(f: &mut Fixture, at: &StorageRecordAttribution, tag: usize) -> ExchangeId {
    let x = new_exchange_id();
    let mut req = CanonicalModelRequest::new(
        ModelRef::new("synthetic", format!("test-{tag:04}-{}", "m".repeat(250))),
        vec![text("ordinary synthetic prompt")],
    );
    req.limits.max_input_tokens = Some(8192);
    commit(
        f,
        at,
        JournalEntry::ModelRequestRecorded(ModelRequestRecorded {
            exchange_id: x,
            origin: ModelCallOrigin::Direct,
            owner: OperationOwner::Workflow,
            request: req,
        }),
    );
    x
}
fn add_turn(f: &mut Fixture, i: usize) -> StorageRecordAttribution {
    let at = begin(f);
    let x = add_request(f, &at, i);
    let error = i % 2 == 1;
    commit(f, &at, model_response(x, error));
    commit(
        f,
        &StorageRecordAttribution {
            execution_id: None,
            ..at.clone()
        },
        JournalEntry::TurnSettled(TurnSettled {
            status: if error {
                TurnSettlementStatus::Error
            } else {
                TurnSettlementStatus::Success
            },
            output: (!error).then(|| AgentOutput::text("ok")),
            error: error.then(|| "synthetic direct context exhaustion".into()),
        }),
    );
    at
}
fn catalog(f: &Fixture) -> Value {
    let bytes = fs::read(f.descriptor.local_path.as_ref().unwrap().join(CATALOG)).unwrap();
    serde_json::from_slice(&bytes).unwrap()
}
fn hash_at(f: &Fixture, k: BackendKind) -> String {
    backend(k)
        .snapshot(
            f.descriptor.local_path.as_ref().unwrap(),
            f.descriptor.session.session_id,
        )
        .unwrap()
        .fingerprint()
        .to_owned()
}
fn mk_fixture(k: BackendKind, n: usize) -> (Fixture, Option<StorageRecordAttribution>, String) {
    let mut f = Fixture::new(k);
    let history = "synthetic user history";
    f.append(vec![text(history)]);
    let at = (0..n).map(|i| add_turn(&mut f, i)).last();
    release(&f);
    suppress_catalog(&f);
    (f, at, history.into())
}
fn verify_catalog(f: &Fixture, s: &StorageSnapshot, preview: &str) {
    let file = catalog(f);
    assert_eq!(
        file["data"]["revision"],
        serde_json::to_value(s.revision).unwrap()
    );
    assert_eq!(file["data"]["fingerprint"], s.content_sha256);
    assert_eq!(
        file["data"]["summary"]["message_count"],
        s.revision.history_revision
    );
    assert_eq!(file["data"]["summary"]["preview"], preview);
    assert_eq!(
        file["data"]["summary"]["descriptor"]["session"],
        serde_json::to_value(&s.session).unwrap()
    );
}
fn write_request(s: &StorageSnapshot, value: Value) -> SessionStorageRequest {
    SessionStorageRequest::WriteCache {
        session: s.session.clone(),
        key: "display-r274".into(),
        source: s.clone(),
        value,
    }
}
fn has_cache(f: &Fixture) -> bool {
    fs::read_dir(f.descriptor.local_path.as_ref().unwrap())
        .unwrap()
        .any(|e| {
            e.unwrap()
                .file_name()
                .to_string_lossy()
                .starts_with(".storage-cache-")
        })
}

#[test]
fn r274_native_cold_open_usage_context_and_cache() {
    for k in backends() {
        let (f, at, history) = mk_fixture(k, 8);
        let who = &f.descriptor.session;
        let expected = hash_at(&f, k);
        let cold = StorageService::new(k);
        diagnostics::reset();
        let s = open(&cold, who);
        let counters = diagnostics::get();
        assert_eq!(counters.decoded, 33);
        assert!(counters.fingerprint_bytes > 0);
        assert_eq!(s.revision, f.revision);
        assert_eq!(s.content_sha256, expected);
        verify_catalog(&f, &s, &history);
        let durable = StorageService::new(k);
        diagnostics::reset();
        let d = open(&durable, who);
        assert_eq!(identity(&s), identity(&d));
        assert_eq!(diagnostics::get().decoded, 0);
        assert_eq!(diagnostics::get().fingerprint_bytes, 0);
        let SessionStorageResponse::Records { page } = run(
            &cold,
            SessionStorageRequest::ReadRecords {
                snapshot: s.clone(),
                after_seq: 0,
                limit: 100,
            },
        ) else {
            panic!()
        };
        assert_eq!(page.records.len(), 33);
        let conversation = run(
            &cold,
            SessionStorageRequest::ReadConversation {
                snapshot: s.clone(),
                point: StorageHistoryPoint::Current,
            },
        );
        let usage = run(
            &cold,
            SessionStorageRequest::ReadUsage {
                snapshot: s.clone(),
            },
        );
        let before = run(
            &cold,
            SessionStorageRequest::ReadModelContextBeforeTurn {
                snapshot: s.clone(),
                turn_id: at.unwrap().turn_id.unwrap(),
            },
        );
        let SessionStorageResponse::Conversation { conversation } = conversation else {
            panic!()
        };
        let SessionStorageResponse::Usage { usage } = usage else {
            panic!()
        };
        assert_eq!(conversation.messages.len(), 1);
        assert_eq!(
            conversation.messages[0].parts[0].payload,
            ContentPart::Text {
                text: history.clone()
            }
        );
        assert_eq!(conversation.model_context.len(), 8);
        assert!(matches!(
            conversation.model_context.last(),
            Some(ModelContextObservation::ContextWindowExceeded {
                max_input_tokens: 8192
            })
        ));
        assert_eq!(usage.requests.len(), 8);
        assert_eq!(usage.requests[0].usage, Some(TokenUsage::new(121, 31)));
        assert_eq!(usage.requests[7].usage, None);
        assert_eq!(
            before,
            SessionStorageResponse::ModelContext {
                observations: conversation.model_context[..7].to_vec()
            }
        );
        let SessionStorageResponse::DisplaySnapshot {
            projection: Some(display),
        } = run(
            &cold,
            SessionStorageRequest::OpenDisplaySnapshot {
                session: who.clone(),
            },
        )
        else {
            panic!()
        };
        assert_eq!(identity(&s), identity(&display.snapshot));
        assert_eq!(display.state.conversation, conversation);
        assert_eq!(display.state.usage, usage);
        suppress_catalog(&f);
        let v = json!({"test":["typed",null,77]});
        diagnostics::reset();
        let mut stale = s.clone();
        stale.content_sha256 = "f".repeat(64);
        let rejected = run(&StorageService::new(k), write_request(&stale, v.clone()));
        assert_eq!(
            rejected,
            SessionStorageResponse::CacheWritten { etag: None }
        );
        assert_eq!(diagnostics::get().decoded, 33);
        assert!(!has_cache(&f));
        verify_catalog(&f, &s, &history);
        suppress_catalog(&f);
        let cold_writer = StorageService::new(k);
        diagnostics::reset();
        let stored = run(&cold_writer, write_request(&s, v.clone()));
        assert_eq!(diagnostics::get().decoded, 33);
        let etag = proteus_contracts::contracts::session_storage::storage_value_etag(&v).unwrap();
        assert_eq!(
            stored,
            SessionStorageResponse::CacheWritten {
                etag: Some(etag.clone())
            }
        );
        let read = run(
            &cold_writer,
            SessionStorageRequest::ReadCache {
                session: who.clone(),
                key: "display-r274".into(),
                source: Some(s.clone()),
            },
        );
        assert_eq!(
            read,
            SessionStorageResponse::Metadata {
                document: Some(StorageMetadataDocument { etag, value: v })
            }
        );
        assert!(has_cache(&f));
        println!(
            "R274_SEMANTIC {k:?} strict_decode=33 context=8 before_turn=7 usage=8 warm_decode=0 write_cache=fresh+stale"
        );
    }
}

#[test]
fn r274_native_remembered_prefix_after_append() {
    for k in backends() {
        let mut f = Fixture::new(k);
        let reader = StorageService::new(k);
        let zero = open(&reader, &f.descriptor.session);
        assert_eq!(zero.revision.session_seq, 0);
        f.append(vec![text("old boundary")]);
        for i in 0..6 {
            add_turn(&mut f, i);
        }
        release(&f);
        suppress_catalog(&f);
        let old = open(&reader, &f.descriptor.session);
        diagnostics::reset();
        assert_eq!(
            run(
                &reader,
                SessionStorageRequest::CompareSnapshots {
                    snapshot: old.clone(),
                    prefix: zero.clone()
                }
            ),
            SessionStorageResponse::SnapshotPrefix { matches: true }
        );
        assert_eq!(diagnostics::get().decoded, 0);
        let SessionStorageResponse::Writer { lease, revision } = run(
            &f.service,
            SessionStorageRequest::AcquireWriter {
                session: f.descriptor.session.clone(),
            },
        ) else {
            panic!()
        };
        f.lease = lease;
        f.revision = revision;
        f.append(vec![text("new tail")]);
        release(&f);
        suppress_catalog(&f);
        diagnostics::reset();
        let head = open(&reader, &f.descriptor.session);
        assert_eq!(diagnostics::get().decoded, 26);
        assert_eq!(head.revision.session_seq, old.revision.session_seq + 1);
        assert_eq!(
            head.revision.history_revision,
            old.revision.history_revision + 1
        );
        let compare = |prefix: StorageSnapshot| {
            run(
                &reader,
                SessionStorageRequest::CompareSnapshots {
                    snapshot: head.clone(),
                    prefix,
                },
            )
        };
        diagnostics::reset();
        assert_eq!(
            compare(old.clone()),
            SessionStorageResponse::SnapshotPrefix { matches: true }
        );
        assert_eq!(diagnostics::get().decoded, 0);
        let mut wrong = old;
        wrong.revision.history_revision -= 1;
        assert_eq!(
            compare(wrong),
            SessionStorageResponse::SnapshotPrefix { matches: false }
        );
        assert_eq!(diagnostics::get().decoded, 0);
        diagnostics::reset();
        assert_eq!(
            compare(zero),
            SessionStorageResponse::SnapshotPrefix { matches: true }
        );
        assert!(
            diagnostics::get().decoded > 0,
            "discarded cut must use the validated fallback"
        );

        let invalid = complete_record(
            &f,
            &StorageRecordAttribution {
                execution_id: None,
                thread_id: Some(f.thread),
                turn_id: None,
            },
            JournalEntry::HistoryMutated(HistoryMutated {
                previous_revision: 999,
                new_revision: 1000,
                mutation: HistoryMutationKind::Append,
                messages: vec![text("invalid tail")],
                compaction: None,
                tool_results: vec![],
            }),
        );
        raw_append(&f, k, &invalid);
        suppress_catalog(&f);
        // Keep the same reader: its previous cut is now still resident but stale.
        diagnostics::reset();
        let err = reader.execute(request(&f.descriptor.session)).unwrap_err();
        assert!(err.to_string().contains("history revision mismatch"));
        assert_eq!(diagnostics::get().decoded, 27);
        assert!(!dir(&f).join(CATALOG).exists());
        println!(
            "R274_SEMANTIC {k:?} zero+earlier_boundary=verified full_decode=26 compare_decode=0 old_cut_fallback tail_failure_after_cut"
        );
    }
}

fn dir(f: &Fixture) -> &std::path::Path {
    f.descriptor.local_path.as_ref().unwrap()
}
fn journal(f: &Fixture) -> PathBuf {
    f.descriptor.record_location.clone().unwrap()
}
fn raw_append(f: &Fixture, k: BackendKind, r: &JournalRecord) {
    let mut io = backend(k);
    io.recover(dir(f), f.descriptor.session.session_id).unwrap();
    io.append(dir(f), r).unwrap();
}
fn complete_record(
    f: &Fixture,
    at: &StorageRecordAttribution,
    entry: JournalEntry,
) -> JournalRecord {
    JournalRecord {
        schema_version: JOURNAL_SCHEMA_VERSION,
        session_id: f.descriptor.session.session_id,
        record_id: new_record_id(),
        session_seq: f.revision.session_seq + 1,
        timestamp_ms: 2048,
        execution_id: at.execution_id,
        thread_id: at.thread_id,
        turn_id: at.turn_id,
        entry,
    }
}
fn reject(f: &Fixture, k: BackendKind, old: &StorageSnapshot, want: &str) {
    assert!(!dir(f).join(CATALOG).exists());
    let cold = StorageService::new(k);
    let first = cold.execute(request(&f.descriptor.session)).unwrap_err();
    assert!(
        format!("{first:#}").contains(want),
        "{k:?}: expected {want}, got {first:#}"
    );
    let second = cold
        .execute(write_request(old, json!({"not":"written"})))
        .unwrap_err();
    assert_eq!(format!("{first:#}"), format!("{second:#}"));
    assert!(!dir(f).join(CATALOG).exists());
    assert!(!has_cache(f));
}
#[test]
fn r274_native_strict_validation_failures() {
    for k in backends() {
        for (case, want) in [
            ("no-request", "no preceding request"),
            ("duplicate", "duplicate model exchange response"),
            ("wrong-owner", "lifecycle owner"),
            ("bad-session", "another session"),
            ("bad-schema", "schema"),
            ("bad-sequence", "sequence"),
            ("bad-json", "key must be a string"),
        ] {
            let mut f = Fixture::new(k);
            f.append(vec![text("valid earlier prefix")]);
            let old = f.snapshot();
            let at = begin(&mut f);
            let x = if case == "no-request" {
                new_exchange_id()
            } else {
                add_request(&mut f, &at, 17)
            };
            if case == "duplicate" {
                commit(&mut f, &at, model_response(x, false));
            }
            let mut record = complete_record(&f, &at, model_response(x, false));
            release(&f);
            suppress_catalog(&f);
            match case {
                "wrong-owner" => record.thread_id = Some(new_thread_id()),
                "bad-session" => record.session_id = new_session_id(),
                "bad-schema" => record.schema_version += 1,
                "bad-sequence" => record.session_seq += 1,
                _ => (),
            }
            // Bypass semantic admission only to author *synthetic* corrupt input.
            // Preserve the ordinary real decoder and service validation on reads.
            match (k, case) {
                (
                    BackendKind::Sqlite,
                    "bad-schema" | "bad-sequence" | "bad-json" | "bad-session",
                ) => {
                    let sql = rusqlite::Connection::open(journal(&f)).unwrap();
                    let payload = if case == "bad-json" {
                        b"{oops".to_vec()
                    } else {
                        serde_json::to_vec(&record).unwrap()
                    };
                    sql.execute(
                        "INSERT INTO journal(sequence,record_id,payload) VALUES(?1,?2,?3)",
                        rusqlite::params![
                            i64::try_from(f.revision.session_seq + 1).unwrap(),
                            record.record_id.to_string(),
                            payload
                        ],
                    )
                    .unwrap();
                }
                (BackendKind::Jsonl, "bad-json") => {
                    use std::io::Write;
                    fs::OpenOptions::new()
                        .append(true)
                        .open(journal(&f))
                        .unwrap()
                        .write_all(b"{oops\n")
                        .unwrap();
                }
                _ => raw_append(&f, k, &record),
            }
            let want = if matches!(
                (k, case),
                (
                    BackendKind::Sqlite,
                    "bad-schema" | "bad-sequence" | "bad-session"
                )
            ) {
                "SQLite journal record identity mismatch"
            } else {
                want
            };
            reject(&f, k, &old, want);
        }
        println!("R274_SEMANTIC {k:?} corrupt_complete_rows=7 no_catalog_or_cache_published");
    }
}

#[test]
fn r274_native_jsonl_external_blob_and_torn_tail() {
    use std::io::Write;
    let k = BackendKind::Jsonl;
    let mut f = Fixture::new(k);
    f.append(vec![text("valid start")]);
    let old = f.snapshot();
    f.append(vec![text(&"synthetic external content".repeat(15_000))]);
    release(&f);
    suppress_catalog(&f);
    let clean = hash_at(&f, k);
    let j = journal(&f);
    fs::OpenOptions::new()
        .append(true)
        .open(&j)
        .unwrap()
        .write_all(b"{unfinished")
        .unwrap();
    let s = open(&StorageService::new(k), &f.descriptor.session);
    assert_eq!(s.content_sha256, clean);
    assert_eq!(s.revision, f.revision);
    assert!(fs::read(&j).unwrap().ends_with(b"{unfinished"));
    suppress_catalog(&f);
    let p = fs::read_dir(dir(&f).join("blobs"))
        .unwrap()
        .map(|e| e.unwrap().path())
        .find(|p| p.is_file())
        .expect("externalized history");
    let mut bytes = fs::read(&p).unwrap();
    bytes[0] ^= 1;
    fs::write(&p, bytes).unwrap();
    reject(&f, k, &old, "blob");
    println!("R274_SEMANTIC Jsonl corrupt_blob_rejected incomplete_tail_unchanged");
}

#[test]
fn r274_native_profile() {
    let (Some(mode), Some(pair)) = (
        std::env::var_os("R274_PAIR_MODE"),
        std::env::var_os("R274_PAIR_DIR"),
    ) else {
        return;
    };
    let pair = PathBuf::from(pair);
    assert!(pair.is_dir());
    let mode = mode.to_str().unwrap();
    for k in backends() {
        for turns in [0, 120] {
            let seed_file = pair.join(format!("profile-{k:?}-{turns}.json"));
            if mode == "seed" {
                let (f, _, _) = mk_fixture(k, turns);
                fs::write(seed_file, serde_json::to_vec(&f.descriptor).unwrap()).unwrap();
                let _ = f.root.keep();
                let _ = f._workspace.keep();
                continue;
            }
            assert!(matches!(mode, "stock" | "candidate"));
            let descriptor: StorageSessionDescriptor =
                serde_json::from_slice(&fs::read(seed_file).unwrap()).unwrap();
            let known_catalog = descriptor.local_path.as_ref().unwrap().join(CATALOG);
            if known_catalog.is_file() {
                fs::rename(
                    &known_catalog,
                    known_catalog.with_extension("proof-previous"),
                )
                .unwrap();
            }
            let ((seed, measured, fingerprint_bytes), end) = meter::scope(|| {
                let s = StorageService::new(k);
                let q = request(&descriptor.session);
                diagnostics::reset();
                let seed = meter::phase();
                let r = std::hint::black_box(s.execute(q)).unwrap();
                let m = meter::snapshot();
                let counters = diagnostics::get();
                assert_eq!(counters.decoded as usize, turns * 4 + 1);
                assert!(counters.fingerprint_bytes > 0);
                drop(r);
                drop(s);
                (seed, m, counters.fingerprint_bytes)
            });
            assert_eq!(end.live, 0);
            println!(
                "R274_ALLOC {k:?} turns={turns} seed={seed} at_return={} peak={} requested={} allocs={} reallocs={} fingerprint_bytes={fingerprint_bytes}",
                measured.live, measured.peak, measured.req, measured.allocs, measured.reallocs
            );
        }
    }
}
#[derive(Clone, Copy)]
enum VersionFault {
    RewriteAtEof,
    AppendAtEof,
}
thread_local! {
    static VERSION_FAULT: std::cell::Cell<Option<VersionFault>> = const { std::cell::Cell::new(None) };
}

// Test-only synchronization at the exact boundary after the strict loop reached
// EOF, before the real backend's second source_version/verify_fixed_prefix.
pub(crate) fn mutate_at_version_recheck(dir: &std::path::Path) -> anyhow::Result<()> {
    use std::io::{Seek, SeekFrom, Write};
    let Some(mode) = VERSION_FAULT.take() else {
        return Ok(());
    };
    assert!(
        !dir.join(CATALOG).exists(),
        "catalog must not precede final validation"
    );
    let file = dir.join("journal.jsonl");
    let mut output = fs::OpenOptions::new().write(true).open(&file)?;
    match mode {
        VersionFault::RewriteAtEof => {
            let data = fs::read(file)?;
            let marker = b"synthetic user history";
            let index = data
                .windows(marker.len())
                .position(|w| w == marker)
                .expect("inline source exists");
            output.seek(SeekFrom::Start(index as u64))?;
            output.write_all(b"X")?;
        }
        VersionFault::AppendAtEof => {
            output.seek(SeekFrom::End(0))?;
            output.write_all(b"{uncommitted synthetic suffix")?;
        }
    }
    // Distinct from the captured time even on filesystems with coarse timestamps.
    let time = std::time::UNIX_EPOCH + std::time::Duration::from_secs(19);
    output.set_times(fs::FileTimes::new().set_modified(time))?;
    output.sync_all()?;
    Ok(())
}

#[test]
fn r274_native_source_changed_after_eof() {
    for mode in [VersionFault::RewriteAtEof, VersionFault::AppendAtEof] {
        let k = BackendKind::Jsonl;
        let (f, _, _) = mk_fixture(k, 2);
        let expected = hash_at(&f, k);
        let bytes = fs::metadata(journal(&f)).unwrap().len();
        let s = StorageService::new(k);
        diagnostics::reset();
        VERSION_FAULT.set(Some(mode));
        let outcome = s.execute(request(&f.descriptor.session));
        assert!(VERSION_FAULT.take().is_none());
        assert!(!dir(&f).join(CATALOG).exists());
        assert_eq!(diagnostics::get().decoded, 9);
        assert_eq!(
            diagnostics::get().fingerprint_bytes,
            bytes * 2,
            "real post-EOF revalidation must hash the same full pinned prefix a second time"
        );
        match mode {
            VersionFault::RewriteAtEof => assert!(
                outcome
                    .unwrap_err()
                    .to_string()
                    .contains("journal complete prefix changed during snapshot read")
            ),
            VersionFault::AppendAtEof => {
                let SessionStorageResponse::Snapshot { snapshot } = outcome.unwrap() else {
                    panic!()
                };
                assert_eq!(snapshot.content_sha256, expected);
                assert_eq!(snapshot.revision, f.revision);
            }
        }
    }
    println!(
        "R274_SEMANTIC Jsonl deterministic_eof_rewrite_rejected suffix_retained_as_uncommitted two_full_hashes"
    );
}

// A second gate reads the *same* immutable physical input in both executables.
// Only separately random snapshot_id fields are normalized on response JSON.
#[test]
fn r274_native_byte_pair() {
    let (Some(mode), Some(pair)) = (
        std::env::var_os("R274_PAIR_MODE"),
        std::env::var_os("R274_PAIR_DIR"),
    ) else {
        return;
    };
    let pair = PathBuf::from(pair);
    assert!(pair.is_dir());
    let mode = mode.to_str().unwrap();
    for k in backends() {
        let tag = match k {
            BackendKind::Jsonl => "jsonl",
            BackendKind::Sqlite => "sqlite",
        };
        let seed = pair.join(format!("{tag}-seed.json"));
        if mode == "seed" {
            let (f, last, _) = mk_fixture(k, 12);
            let last = last.unwrap().turn_id.unwrap();
            fs::write(seed, serde_json::to_vec(&(&f.descriptor, last)).unwrap()).unwrap();
            // These are the proof's private TMPDIR fixtures, retained for the
            // next process so directory stamps and all journal bytes stay exact.
            let _ = f.root.keep();
            let _ = f._workspace.keep();
            continue;
        }
        assert!(matches!(mode, "stock" | "candidate"));
        let (descriptor, last): (StorageSessionDescriptor, proteus_contracts::domain::TurnId) =
            serde_json::from_slice(&fs::read(seed).unwrap()).unwrap();
        let dir = descriptor.local_path.as_deref().unwrap();
        let cat = dir.join(CATALOG);
        let cache_key = "display-r274";
        let cache = dir.join(format!(
            ".storage-cache-{}.json",
            crate::io::sha256_hex(cache_key.as_bytes())
        ));
        for out in [&cat, &cache] {
            if out.is_file() {
                fs::rename(out, out.with_extension("proof-previous")).unwrap();
            }
        }
        let s = StorageService::new(k);
        diagnostics::reset();
        let snapshot = open(&s, &descriptor.session);
        let counters = diagnostics::get();
        assert_eq!(counters.decoded, 49);
        assert!(counters.fingerprint_bytes > 0);
        let receipt = [
            SessionStorageResponse::Snapshot {
                snapshot: snapshot.clone(),
            },
            run(
                &s,
                SessionStorageRequest::ReadRecords {
                    snapshot: snapshot.clone(),
                    after_seq: 0,
                    limit: 100,
                },
            ),
            run(
                &s,
                SessionStorageRequest::ReadConversation {
                    snapshot: snapshot.clone(),
                    point: StorageHistoryPoint::Current,
                },
            ),
            run(
                &s,
                SessionStorageRequest::ReadUsage {
                    snapshot: snapshot.clone(),
                },
            ),
            run(
                &s,
                SessionStorageRequest::ReadModelContextBeforeTurn {
                    snapshot: snapshot.clone(),
                    turn_id: last,
                },
            ),
            run(
                &s,
                SessionStorageRequest::OpenDisplaySnapshot {
                    session: descriptor.session.clone(),
                },
            ),
        ];
        let mut stable_source = snapshot.clone();
        stable_source.snapshot_id = "00000000-0000-4000-8000-000000000274".into();
        let v = json!({"fixture":"typed","n":9,"a":[true,null]});
        let w = run(&s, write_request(&stable_source, v));
        let r = run(
            &s,
            SessionStorageRequest::ReadCache {
                session: descriptor.session,
                key: cache_key.into(),
                source: Some(stable_source),
            },
        );
        fn normalize(value: &mut Value) {
            match value {
                Value::Array(items) => items.iter_mut().for_each(normalize),
                Value::Object(fields) => {
                    for (name, value) in fields.iter_mut() {
                        if name == "snapshot_id" {
                            *value = json!("normalized live id");
                        } else {
                            normalize(value);
                        }
                    }
                }
                _ => (),
            }
        }
        let mut wire = serde_json::to_value((receipt, w, r)).unwrap();
        normalize(&mut wire);
        for (category, bytes) in [
            ("response", serde_json::to_vec(&wire).unwrap()),
            ("catalog", fs::read(cat).unwrap()),
            ("cache", fs::read(cache).unwrap()),
        ] {
            fs::write(pair.join(format!("{tag}-{mode}-{category}.bytes")), bytes).unwrap();
        }
        println!(
            "R274_PAIR {tag} same_source_records=49 fingerprint_bytes={}",
            counters.fingerprint_bytes
        );
    }
}
