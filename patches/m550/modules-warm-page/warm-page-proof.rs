use super::*;
use proteus_contracts::{
    contracts::{ModelCallOrigin, OperationOwner},
    domain::{
        AgentOutput, AgentTask, ModelRef, ModelUsageStatus, new_exchange_id, new_execution_id,
        new_turn_id,
    },
    model_standard::{
        CanonicalModelRequest, CanonicalModelResponse, FinishReason, ModelFailure,
        ModelFailureKind, TokenUsage,
    },
};
use std::{
    alloc::{GlobalAlloc, Layout, System},
    cell::Cell,
    time::Instant,
};

#[derive(Clone, Copy, Default)]
struct Work {
    allocations: usize,
    bytes: usize,
    live: isize,
    peak: isize,
}
struct PageMeter;
thread_local! { static METER: Cell<Option<Work>> = const { Cell::new(None) }; }
fn account(bytes: usize, delta: isize, allocation: bool) {
    let _ = METER.try_with(|m| {
        if let Some(mut w) = m.get() {
            w.allocations += usize::from(allocation);
            w.bytes += bytes;
            w.live += delta;
            w.peak = w.peak.max(w.live);
            m.set(Some(w));
        }
    });
}
unsafe impl GlobalAlloc for PageMeter {
    unsafe fn alloc(&self, l: Layout) -> *mut u8 {
        let p = unsafe { System.alloc(l) };
        if !p.is_null() {
            account(l.size(), l.size() as isize, true);
        }
        p
    }
    unsafe fn alloc_zeroed(&self, l: Layout) -> *mut u8 {
        let p = unsafe { System.alloc_zeroed(l) };
        if !p.is_null() {
            account(l.size(), l.size() as isize, true);
        }
        p
    }
    unsafe fn realloc(&self, p: *mut u8, l: Layout, n: usize) -> *mut u8 {
        let p = unsafe { System.realloc(p, l, n) };
        if !p.is_null() {
            account(n, n as isize - l.size() as isize, true);
        }
        p
    }
    unsafe fn dealloc(&self, p: *mut u8, l: Layout) {
        account(0, -(l.size() as isize), false);
        unsafe { System.dealloc(p, l) };
    }
}
#[global_allocator]
static ALLOCATOR: PageMeter = PageMeter;

fn commit(f: &mut Fixture, attribution: StorageRecordAttribution, entry: JournalEntry) {
    let SessionStorageResponse::Committed { ack } = f
        .service
        .execute(SessionStorageRequest::Commit {
            commit: StorageCommit {
                lease: f.lease.clone(),
                operation_id: new_record_id(),
                expected: f.revision,
                timestamp_ms: 100 + f.revision.session_seq as i64,
                attribution,
                entry,
            },
        })
        .unwrap()
    else {
        panic!("missing commit")
    };
    f.revision = ack.revision;
}

fn add_turn(f: &mut Fixture, bad_window: bool) -> proteus_contracts::domain::TurnId {
    let turn = new_turn_id();
    let attribution = StorageRecordAttribution {
        execution_id: Some(new_execution_id()),
        thread_id: Some(f.thread),
        turn_id: Some(turn),
    };
    let task = AgentTask::new(
        "actual storage fixture",
        f.descriptor.workspace_path.clone(),
    );
    let revision = f.revision.history_revision;
    commit(
        f,
        attribution.clone(),
        JournalEntry::TurnOpened(TurnOpened {
            task,
            intent: None,
            base_history_revision: revision,
            module_epoch: 0,
            config_snapshot: serde_json::json!({"module":"fixture","fixture":"module"}),
        }),
    );
    let exchange_id = new_exchange_id();
    let request = CanonicalModelRequest::new(
        ModelRef::new("fixture", "warm-page-validation"),
        vec![text("run previous turn")],
    )
    .with_limits(proteus_contracts::domain::ModelLimits::new(
        Some(32000),
        Some(1000),
    ));
    commit(
        f,
        attribution.clone(),
        JournalEntry::ModelRequestRecorded(ModelRequestRecorded {
            exchange_id,
            origin: ModelCallOrigin::Direct,
            owner: OperationOwner::Workflow,
            request,
        }),
    );
    let outcome = if bad_window {
        ModelResponseOutcome::Error {
            failure: ModelFailure::new(
                ModelFailureKind::ContextWindowExceeded,
                "fixture context window exceeded",
            ),
        }
    } else {
        ModelResponseOutcome::Response {
            response: CanonicalModelResponse::new(
                CanonicalMessage::text(MessageRole::Assistant, "fixture answer"),
                vec![],
                FinishReason::Stop,
            )
            .with_usage(TokenUsage::new(128, 64)),
        }
    };
    commit(
        f,
        attribution.clone(),
        JournalEntry::ModelResponseRecorded(ModelResponseRecorded {
            exchange_id,
            outcome,
        }),
    );
    commit(
        f,
        StorageRecordAttribution {
            execution_id: None,
            ..attribution
        },
        JournalEntry::TurnSettled(TurnSettled {
            status: if bad_window {
                TurnSettlementStatus::Error
            } else {
                TurnSettlementStatus::Success
            },
            output: (!bad_window).then(|| AgentOutput::text("done")),
            error: bad_window.then(|| "fixture context window exceeded".into()),
        }),
    );
    turn
}

fn open(s: &StorageService, session: &SessionLocator) -> StorageSnapshot {
    let SessionStorageResponse::Snapshot { snapshot } = s
        .execute(SessionStorageRequest::OpenSnapshot {
            session: session.clone(),
        })
        .unwrap()
    else {
        panic!("missing snapshot")
    };
    snapshot
}
fn request(snapshot: &StorageSnapshot, after_seq: u64, limit: u32) -> SessionStorageRequest {
    SessionStorageRequest::ReadRecords {
        snapshot: snapshot.clone(),
        after_seq,
        limit,
    }
}
fn records(s: &StorageService, req: SessionStorageRequest) -> StorageRecordPage {
    let reply = s.execute(req.clone()).unwrap();
    req.validate_response(&reply).unwrap();
    let SessionStorageResponse::Records { page } = reply else {
        panic!("missing records")
    };
    page
}
fn measure(s: &StorageService, req: SessionStorageRequest) -> (SessionStorageResponse, Work, u128) {
    crate::diagnostics::reset();
    let start = Instant::now();
    METER.with(|m| m.set(Some(Work::default())));
    let reply = s.execute(req).unwrap();
    let work = METER.with(|m| m.replace(None)).unwrap();
    (reply, work, start.elapsed().as_nanos())
}
#[test]
fn warm_page_projection_service_equivalence_and_allocation() {
    for kind in backends() {
        for turns in [0_usize, 16, 128] {
            let mut f = Fixture::new(kind);
            f.append(vec![text("initial-history fixture")]);
            let latest = (0..turns).map(|i| add_turn(&mut f, i % 2 == 1)).last();
            f.append(vec![text("final-history fixture")]);
            let session = f.descriptor.session.clone();
            let seq = f.revision.session_seq;
            let reader = StorageService::new(kind);
            let seed = open(&reader, &session);
            let warm = || {
                crate::diagnostics::reset();
                let s = open(&reader, &session);
                assert_eq!(s.revision, seed.revision);
                assert_eq!(s.content_sha256, seed.content_sha256);
                assert_eq!(
                    crate::diagnostics::get().decoded,
                    0,
                    "open must actually take the warm route"
                );
                s
            };
            let head = records(&reader, request(&seed, 0, 1)).records;
            let tail = records(&reader, request(&seed, seq - 1, 1)).records;
            for (tag, after, expected) in [("head", 0, &head), ("terminal", seq - 1, &tail)] {
                let s = warm();
                let req = request(&s, after, 1);
                let (reply, w, elapsed) = measure(&reader, req.clone());
                req.validate_response(&reply).unwrap();
                let SessionStorageResponse::Records { page } = reply else {
                    panic!("missing records")
                };
                assert_eq!(&page.records, expected);
                assert_eq!(
                    &serde_json::to_vec(&page.records).unwrap(),
                    &serde_json::to_vec(expected).unwrap()
                );
                assert_eq!(page.snapshot, s);
                assert_eq!(page.next_after_seq, (after == 0).then_some(1));
                let d = crate::diagnostics::get();
                assert!(
                    d.decoded >= seq,
                    "warm disclosure must validate and replay the complete fixed prefix"
                );
                println!(
                    "WARM {kind:?} {turns} {tag} {} {} {} {} {} {elapsed}",
                    w.allocations, w.bytes, w.peak, d.decoded, d.fingerprint_bytes
                );
                assert_eq!(records(&reader, req), page, "retry same cursor");
                if after == 0 {
                    let next = records(&reader, request(&s, 1, 2));
                    assert_eq!(next.records[0].session_seq, 2);
                }
            }
            let s = warm();
            let req = request(&s, 0, 1);
            let before_append = records(&reader, req.clone());
            f.append(vec![text("after pinned snapshot")]);
            assert_eq!(records(&reader, req), before_append);
            assert_eq!(records(&reader, request(&s, seq - 1, 1)).records, tail);
            let SessionStorageResponse::Usage { usage } = reader
                .execute(SessionStorageRequest::ReadUsage {
                    snapshot: s.clone(),
                })
                .unwrap()
            else {
                panic!("missing usage after page")
            };
            assert_eq!(usage.requests.len(), turns);
            for (i, usage) in usage.requests.iter().enumerate() {
                if i % 2 == 0 {
                    assert_eq!(usage.status, ModelUsageStatus::Completed);
                    assert_eq!(usage.usage, Some(TokenUsage::new(128, 64)));
                } else {
                    assert_eq!(usage.status, ModelUsageStatus::Error);
                    assert_eq!(usage.usage, None);
                }
            }
            let SessionStorageResponse::Conversation { conversation } = reader
                .execute(SessionStorageRequest::ReadConversation {
                    snapshot: s.clone(),
                    point: StorageHistoryPoint::Current,
                })
                .unwrap()
            else {
                panic!("missing conversation")
            };
            assert_eq!(
                conversation
                    .messages
                    .iter()
                    .map(|m| m.display_text())
                    .collect::<Vec<_>>(),
                ["initial-history fixture", "final-history fixture"]
            );
            assert_eq!(conversation.model_context.len(), turns);
            if let Some(turn) = latest {
                let SessionStorageResponse::ModelContext { observations } = reader
                    .execute(SessionStorageRequest::ReadModelContextBeforeTurn {
                        snapshot: s,
                        turn_id: turn,
                    })
                    .unwrap()
                else {
                    panic!("missing before-turn context")
                };
                assert_eq!(&observations, &conversation.model_context[..turns - 1]);
            }
        }
    }
}

#[test]
#[ignore = "requires shared immutable fixture across two binaries"]
fn warm_page_same_corpus_allocator() {
    let mode = std::env::var("PROTEUS_PAGE_METER_MODE").unwrap();
    let manifest =
        std::path::PathBuf::from(std::env::var_os("PROTEUS_PAGE_METER_MANIFEST").unwrap());
    type Rows = Vec<(String, usize, SessionLocator, StorageRevision, String)>;
    match mode.as_str() {
        "seed" => {
            let mut rows = Rows::new();
            for kind in backends() {
                for turns in [0, 16, 128] {
                    let mut f = Fixture::new(kind);
                    f.append(vec![text("initial-history fixture")]);
                    for i in 0..turns {
                        add_turn(&mut f, i % 2 == 1);
                    }
                    f.append(vec![text("final-history fixture")]);
                    f.service
                        .execute(SessionStorageRequest::ReleaseWriter {
                            lease: f.lease.clone(),
                        })
                        .unwrap();
                    let session = f.descriptor.session.clone();
                    let snapshot = open(&f.service, &session);
                    rows.push((
                        format!("{kind:?}"),
                        turns,
                        session,
                        snapshot.revision,
                        snapshot.content_sha256,
                    ));
                    let Fixture {
                        root, _workspace, ..
                    } = f;
                    // This deliberately persists test-only roots under the runner's TMPDIR.
                    let _durable_dir = root.keep();
                    let _workspace_dir = _workspace.keep();
                }
            }
            let bytes = serde_json::to_vec(&rows).unwrap();
            std::fs::OpenOptions::new()
                .create_new(true)
                .write(true)
                .open(manifest)
                .and_then(|mut out| std::io::Write::write_all(&mut out, &bytes))
                .unwrap();
        }
        "read" => {
            let rows: Rows = serde_json::from_slice(&std::fs::read(manifest).unwrap()).unwrap();
            for (kind, turns, session, revision, hash) in rows {
                let b = match &*kind {
                    "Jsonl" => BackendKind::Jsonl,
                    "Sqlite" => BackendKind::Sqlite,
                    _ => panic!(),
                };
                let s = StorageService::new(b);
                let seed = open(&s, &session);
                assert_eq!(seed.revision, revision);
                assert_eq!(seed.content_sha256, hash);
                for (tag, after) in [("head", 0), ("terminal", revision.session_seq - 1)] {
                    for _ in 0..7 {
                        crate::diagnostics::reset();
                        let snap = open(&s, &session);
                        assert_eq!(crate::diagnostics::get().decoded, 0);
                        assert_eq!(snap.revision, revision);
                        assert_eq!(snap.content_sha256, hash);
                        let req = request(&snap, after, 1);
                        let (reply, w, _) = measure(&s, req.clone());
                        req.validate_response(&reply).unwrap();
                        let d = crate::diagnostics::get();
                        let SessionStorageResponse::Records { page } = reply else {
                            panic!()
                        };
                        assert_eq!(page.snapshot, snap);
                        assert_eq!(page.next_after_seq, (after == 0).then_some(1));
                        let wire = serde_json::to_vec(&page.records).unwrap();
                        let wire = crate::io::sha256_hex(&wire);
                        println!(
                            "PAIRED {kind} {turns} {tag} {} {} {} {} {} {wire}",
                            w.allocations, w.bytes, w.peak, d.decoded, d.fingerprint_bytes
                        );
                        s.execute(SessionStorageRequest::ReleaseSnapshot { snapshot: snap })
                            .unwrap();
                    }
                }
            }
        }
        _ => panic!("invalid meter mode"),
    }
}
