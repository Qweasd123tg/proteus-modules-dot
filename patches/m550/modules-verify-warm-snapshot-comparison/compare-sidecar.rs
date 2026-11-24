// Test-only sidecar appended to tests/usage.rs. Real fixture commits,
// unchanged old-SDK contracts, and the public StorageService API.
mod warm_compare_probe {
    use super::*;
    use serde_json::Value;
    use std::{
        alloc::{GlobalAlloc, Layout, System},
        cell::Cell,
        path::PathBuf,
    };

    #[derive(Clone, Copy, Default)]
    struct Counts {
        events: usize,
        requested: usize,
        live: isize,
        peak: isize,
    }
    thread_local! { static ALLOC: Cell<Option<Counts>> = const { Cell::new(None) }; }
    fn sample(bytes: usize, delta: isize, record_event: bool) {
        let _ = ALLOC.try_with(|s| {
            if let Some(mut a) = s.get() {
                a.events += record_event as usize;
                a.requested += bytes;
                a.live += delta;
                a.peak = a.peak.max(a.live);
                s.set(Some(a));
            }
        });
    }
    struct ClockedHeap;
    unsafe impl GlobalAlloc for ClockedHeap {
        unsafe fn alloc(&self, l: Layout) -> *mut u8 {
            let p = unsafe { System.alloc(l) };
            if !p.is_null() {
                sample(l.size(), l.size() as isize, true);
            }
            p
        }
        unsafe fn alloc_zeroed(&self, l: Layout) -> *mut u8 {
            let p = unsafe { System.alloc_zeroed(l) };
            if !p.is_null() {
                sample(l.size(), l.size() as isize, true);
            }
            p
        }
        unsafe fn realloc(&self, p: *mut u8, l: Layout, n: usize) -> *mut u8 {
            let p = unsafe { System.realloc(p, l, n) };
            if !p.is_null() {
                sample(n, n as isize - l.size() as isize, true);
            }
            p
        }
        unsafe fn dealloc(&self, p: *mut u8, l: Layout) {
            sample(0, -(l.size() as isize), false);
            unsafe { System.dealloc(p, l) };
        }
    }
    #[global_allocator]
    static ALLOCATOR: ClockedHeap = ClockedHeap;

    fn open(service: &StorageService, source: &SessionLocator) -> StorageSnapshot {
        let SessionStorageResponse::Snapshot { snapshot } = service
            .execute(SessionStorageRequest::OpenSnapshot {
                session: source.clone(),
            })
            .unwrap()
        else {
            panic!("snapshot missing")
        };
        snapshot
    }

    fn comparison(
        s: &StorageService,
        head: &StorageSnapshot,
        prefix: &StorageSnapshot,
    ) -> anyhow::Result<bool> {
        let req = SessionStorageRequest::CompareSnapshots {
            snapshot: head.clone(),
            prefix: prefix.clone(),
        };
        match s.execute(req.clone()) {
            Ok(v) => {
                req.validate_response(&v)?;
                let SessionStorageResponse::SnapshotPrefix { matches } = v else {
                    panic!("unexpected comparison response")
                };
                Ok(matches)
            }
            Err(e) => Err(e),
        }
    }

    fn response(s: &StorageService, req: SessionStorageRequest) -> SessionStorageResponse {
        let got = s.execute(req.clone()).unwrap();
        req.validate_response(&got).unwrap();
        got
    }
    fn digest(value: &impl serde::Serialize) -> String {
        crate::io::sha256_hex(&serde_json::to_vec(value).unwrap())
    }

    type Corpus = Vec<(String, StorageSnapshot)>;
    #[test]
    #[ignore = "shared durable warm-CompareSnapshots proof"]
    fn compare_warm_rich_prefix() {
        let path = PathBuf::from(std::env::var_os("PROTEUS_WARM_COMPARE_CORPUS").unwrap());
        match std::env::var("PROTEUS_WARM_COMPARE_MODE").unwrap().as_str() {
            "seed" => {
                let mut corpus = Corpus::new();
                for kind in backends() {
                    let mut f = Fixture::new(kind);
                    f.append(vec![text("warm retained canonical row")]);
                    for n in 0..128 {
                        add_turn(&mut f, n % 2 == 1);
                    }
                    let prefix = f.snapshot();
                    assert_eq!(prefix.revision.session_seq, 513);
                    f.service
                        .execute(SessionStorageRequest::ReleaseSnapshot {
                            snapshot: prefix.clone(),
                        })
                        .unwrap();
                    f.append(vec![text("later committed first")]);
                    add_turn(&mut f, false);
                    f.append(vec![text("later committed terminal")]);
                    assert_eq!(f.revision.session_seq, 519);
                    f.service
                        .execute(SessionStorageRequest::ReleaseWriter {
                            lease: f.lease.clone(),
                        })
                        .unwrap();
                    corpus.push((format!("{kind:?}"), prefix));
                    let Fixture {
                        root, _workspace, ..
                    } = f;
                    let _ = root.keep();
                    let _ = _workspace.keep();
                }
                let dst = std::fs::OpenOptions::new()
                    .write(true)
                    .create_new(true)
                    .open(path)
                    .unwrap();
                serde_json::to_writer(dst, &corpus).unwrap();
            }
            "read" => {
                let fixtures: Corpus =
                    serde_json::from_reader(std::fs::File::open(&path).unwrap()).unwrap();
                for (kind, previous) in fixtures {
                    let backend = match kind.as_str() {
                        "Jsonl" => BackendKind::Jsonl,
                        "Sqlite" => BackendKind::Sqlite,
                        _ => panic!("wrong backend"),
                    };
                    let service = StorageService::new(backend);
                    let first = open(&service, &previous.session);
                    crate::diagnostics::reset();
                    let warm = open(&service, &previous.session);
                    let warm_d = crate::diagnostics::get();
                    assert_eq!(
                        warm_d.decoded, 0,
                        "must start from provisional warm descriptor"
                    );
                    assert_eq!(first.revision, warm.revision);
                    assert_eq!(warm.revision.session_seq, 519);
                    assert_eq!(warm.content_sha256, first.content_sha256);
                    let req = SessionStorageRequest::CompareSnapshots {
                        snapshot: warm.clone(),
                        prefix: previous.clone(),
                    };
                    for turn in 0..3 {
                        crate::diagnostics::reset();
                        let q = req.clone();
                        assert!(ALLOC.replace(Some(Counts::default())).is_none());
                        let got = service.execute(q).unwrap();
                        let a = ALLOC.replace(None).unwrap();
                        req.validate_response(&got).unwrap();
                        assert_eq!(
                            got,
                            SessionStorageResponse::SnapshotPrefix { matches: true }
                        );
                        let d = crate::diagnostics::get();
                        // JSONL authenticates through its decoder during the
                        // prefix-fingerprint pass; SQLite hashes raw rows.
                        let scans = if kind == "Jsonl" { 2 } else { 1 };
                        assert_eq!(d.decoded, scans * warm.revision.session_seq);
                        println!(
                            "FOLD {kind} {turn} {} {} {} {} {} {}",
                            d.decoded,
                            d.fingerprint_bytes,
                            a.events,
                            a.requested,
                            a.peak,
                            digest(&got)
                        );
                    }

                    let mut wrong = previous.clone();
                    wrong.revision.history_revision -= 1;
                    assert!(!comparison(&service, &warm, &wrong).unwrap());
                    wrong = previous.clone();
                    wrong.content_sha256 = "0".repeat(64);
                    assert!(!comparison(&service, &warm, &wrong).unwrap());
                    assert!(comparison(&service, &warm, &warm).unwrap());

                    // Usage/model context are still built when a caller asks.
                    let usage = response(
                        &service,
                        SessionStorageRequest::ReadUsage {
                            snapshot: warm.clone(),
                        },
                    );
                    let SessionStorageResponse::Usage { usage: u } = &usage else {
                        panic!("usage absent")
                    };
                    assert_eq!(u.requests.len(), 129);
                    assert_eq!(u.requests[0].status, ModelUsageStatus::Completed);
                    assert_eq!(u.requests[1].status, ModelUsageStatus::Error);
                    let conv = response(
                        &service,
                        SessionStorageRequest::ReadConversation {
                            snapshot: warm.clone(),
                            point: StorageHistoryPoint::Current,
                        },
                    );
                    let SessionStorageResponse::Conversation {
                        conversation: conv_value,
                    } = &conv
                    else {
                        panic!("conversation absent")
                    };
                    assert_eq!(conv_value.revision, warm.revision);
                    assert_eq!(conv_value.messages.len(), 3);
                    assert!(!conv_value.model_context.is_empty());
                    println!("OTHER {kind} {} {}", digest(&usage), digest(&conv));

                    // The requested prefix is intact, but a later immutable
                    // suffix record must still be checked by the comparator.
                    // Repair and retry the *same* warm handle before exit.
                    if kind == "Jsonl"
                        && std::env::var("PROTEUS_WARM_COMPARE_SERIAL_CORRUPTION").is_ok()
                    {
                        let locator: Value = serde_json::from_str(&previous.session.key).unwrap();
                        let journal =
                            PathBuf::from(locator["path"].as_str().unwrap()).join("journal.jsonl");
                        let good = std::fs::read(&journal).unwrap();
                        let mut damaged = good.clone();
                        let last_start = damaged[..damaged.len() - 1]
                            .iter()
                            .rposition(|&b| b == b'\n')
                            .unwrap()
                            + 1;
                        assert_eq!(damaged[last_start], b'{');
                        damaged[last_start] = b'[';
                        std::fs::write(&journal, &damaged).unwrap();
                        let e1 = comparison(&service, &warm, &previous).unwrap_err();
                        let e2 = comparison(&service, &warm, &previous).unwrap_err();
                        assert_eq!(e1.to_string(), e2.to_string());
                        std::fs::write(&journal, &good).unwrap();
                        assert!(comparison(&service, &warm, &previous).unwrap());
                        println!("REPAIRED {kind} {}", e1);
                    }
                }
            }
            _ => panic!("unknown mode"),
        }
    }
}
