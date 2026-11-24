use super::*;
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use std::{
    fs::{self, File, FileTimes, OpenOptions},
    io::Write as _,
    path::{Path, PathBuf},
    time::{Duration, UNIX_EPOCH},
};

mod meter;
const INDEX: &str = ".storage-catalog-v1.json";
const MANY: usize = 24;

#[derive(Serialize, Deserialize)]
struct Seed {
    root: PathBuf,
    workspace: PathBuf,
    unavailable: PathBuf,
    descriptor: StorageSessionDescriptor,
    journals: Vec<PathBuf>,
}
fn run(service: &StorageService, request: SessionStorageRequest) -> SessionStorageResponse {
    let response = service.execute(request.clone()).unwrap();
    request.validate_response(&response).unwrap();
    response
}
fn open_request(path: PathBuf) -> SessionStorageRequest {
    SessionStorageRequest::Open { path }
}
fn candidates(seed: &Seed, workspace: Option<PathBuf>) -> SessionStorageRequest {
    SessionStorageRequest::ListCandidates {
        config_root: seed.root.clone(),
        workspace_path: workspace,
    }
}
fn list(seed: &Seed, audit: bool) -> SessionStorageRequest {
    SessionStorageRequest::List {
        config_root: seed.root.clone(),
        workspace_path: Some(seed.workspace.clone()),
        audit,
    }
}
fn stable_modified(file: &File, seconds: u64) {
    file.set_times(FileTimes::new().set_modified(UNIX_EPOCH + Duration::from_secs(seconds)))
        .unwrap();
}
fn make(kind: BackendKind, fault: &str, count: usize) -> Seed {
    let root = tempfile::tempdir().unwrap();
    let workspace = tempfile::tempdir().unwrap();
    let unavailable = workspace.path().join("workspace-with-no-history");
    fs::create_dir(&unavailable).unwrap();
    let root = root.keep();
    let workspace = workspace.keep();
    let service = StorageService::new(kind);
    let mut descriptor = None;
    let mut journals = Vec::new();
    for i in 0..count {
        let SessionStorageResponse::Session { descriptor: d } = run(
            &service,
            SessionStorageRequest::Create {
                config_root: root.clone(),
                workspace_path: workspace.clone(),
                session_id: new_session_id(),
                parent_session_id: None,
            },
        ) else {
            panic!("creation route")
        };
        let SessionStorageResponse::Writer { lease, revision } = run(
            &service,
            SessionStorageRequest::AcquireWriter {
                session: d.session.clone(),
            },
        ) else {
            panic!("writer route")
        };
        let commit = StorageCommit {
            lease: lease.clone(),
            operation_id: new_record_id(),
            expected: revision,
            timestamp_ms: 1234,
            attribution: StorageRecordAttribution {
                execution_id: None,
                thread_id: Some(new_thread_id()),
                turn_id: None,
            },
            entry: JournalEntry::HistoryMutated(HistoryMutated {
                previous_revision: revision.history_revision,
                new_revision: revision.history_revision + 1,
                mutation: HistoryMutationKind::Append,
                messages: vec![text(&format!("row {i} – Ёж 🦀"))],
                compaction: None,
                tool_results: vec![],
            }),
        };
        run(&service, SessionStorageRequest::Commit { commit });
        run(&service, SessionStorageRequest::ReleaseWriter { lease });
        let journal = d.record_location.as_ref().unwrap();
        if fault == "missing" {
            fs::remove_file(journal).unwrap();
        } else {
            if fault != "none" {
                assert!(matches!(kind, BackendKind::Jsonl));
                let mut journal = OpenOptions::new().append(true).open(journal).unwrap();
                match fault {
                    "torn" => journal.write_all(b"uncommitted tail").unwrap(),
                    "broken" => journal.write_all(b"{broken}\n").unwrap(),
                    _ => unreachable!(),
                }
            }
            // Equal recency for half the sessions exercises the locator tie-break.
            stable_modified(&File::open(journal).unwrap(), 100 + (i % 2) as u64);
        }
        let parent = journal.parent().unwrap();
        let sidecar = parent.join(INDEX);
        if sidecar.exists() {
            fs::remove_file(&sidecar).unwrap();
        }
        if fault == "missing" {
            stable_modified(&File::open(parent).unwrap(), 30);
        }
        journals.push(journal.clone());
        descriptor.get_or_insert(d);
    }
    Seed {
        root,
        workspace,
        unavailable,
        descriptor: descriptor.unwrap(),
        journals,
    }
}
fn expected_count(response: &SessionStorageResponse, n: usize) {
    let SessionStorageResponse::Candidates { sessions } = response else {
        panic!("candidate route")
    };
    assert_eq!(sessions.len(), n);
    assert!(sessions.windows(2).all(|x| {
        (x[0].updated_at_ms, &x[0].session.key) >= (x[1].updated_at_ms, &x[1].session.key)
    }));
}
fn measure(
    kind: BackendKind,
    request: &SessionStorageRequest,
    case: &str,
    expected: Result<Option<usize>, ()>,
) {
    let ((seed, counted, c), end) = meter::scope(|| {
        let service = StorageService::new(kind);
        let req = request.clone();
        crate::diagnostics::reset();
        let seed = meter::phase();
        let result = std::hint::black_box(service.execute(std::hint::black_box(req)));
        let counted = meter::snapshot();
        let c = crate::diagnostics::get();
        match (&result, expected) {
            (Ok(response), Ok(Some(n))) => expected_count(response, n),
            (Ok(SessionStorageResponse::Session { .. }), Ok(None)) | (Err(_), Err(())) => {}
            _ => panic!("unexpected measured result"),
        }
        drop(result);
        drop(service);
        (seed, counted, c)
    });
    assert_eq!(end.live, 0);
    assert_eq!((c.decoded, c.fingerprint_bytes), (0, 0));
    println!(
        "R276F {}",
        json!({"case":case, "seed":seed, "peak":counted.peak, "live":counted.live,
               "requested":counted.req, "allocs":counted.allocs, "reallocs":counted.reallocs,
               "decoded":c.decoded, "fingerprint_bytes":c.fingerprint_bytes})
    );
}
fn observed(response: &SessionStorageResponse) -> &StorageSessionDescriptor {
    let SessionStorageResponse::Session { descriptor } = response else {
        panic!("wrong response")
    };
    descriptor
}
fn raw_identity(seed: &Seed) -> Vec<(Option<Vec<u8>>, Vec<u8>)> {
    seed.journals
        .iter()
        .map(|p| {
            (
                match fs::read(p) {
                    Ok(bytes) => Some(bytes),
                    Err(error) if error.kind() == std::io::ErrorKind::NotFound => None,
                    Err(error) => panic!("{p:?}: {error}"),
                },
                fs::read(p.with_file_name("session.json")).unwrap(),
            )
        })
        .collect()
}
fn checked_list(
    seed: &Seed,
    service: &StorageService,
    audit: bool,
    expected: usize,
) -> SessionStorageResponse {
    let response = run(service, list(seed, audit));
    match &response {
        SessionStorageResponse::Sessions { sessions } => {
            assert_eq!(sessions.len(), expected);
            assert!(sessions.iter().all(|s| s.message_count == 1));
            assert!(sessions.windows(2).all(|x| {
                (x[0].descriptor.updated_at_ms, &x[0].descriptor.session.key)
                    >= (x[1].descriptor.updated_at_ms, &x[1].descriptor.session.key)
            }));
        }
        _ => panic!("not a sessions listing"),
    }
    response
}
fn verified_bytes(seed: &Seed, kind: BackendKind, case: &str, pair: &Path, arm: &str) {
    let service = StorageService::new(kind);
    let initial = raw_identity(seed);
    let directory = seed.descriptor.local_path.as_ref().unwrap();
    let journal = seed.descriptor.record_location.as_ref().unwrap();
    let by_dir = run(&service, open_request(directory.clone()));
    let by_file = run(&service, open_request(journal.clone()));
    assert_eq!(by_file, by_dir);
    assert_eq!(observed(&by_dir).record_location.as_ref(), Some(journal));
    assert_eq!(observed(&by_dir).local_path.as_ref(), Some(directory));
    let describe = run(
        &service,
        SessionStorageRequest::Describe {
            session: seed.descriptor.session.clone(),
        },
    );
    let existing_create = run(
        &service,
        SessionStorageRequest::Create {
            config_root: seed.root.clone(),
            workspace_path: seed.workspace.clone(),
            session_id: seed.descriptor.session.session_id,
            parent_session_id: seed.descriptor.parent_session_id,
        },
    );
    assert_eq!(describe, by_dir);
    assert_eq!(existing_create, by_dir);
    let scoped = run(&service, candidates(seed, Some(seed.workspace.clone())));
    let global = run(&service, candidates(seed, None));
    let other = run(&service, candidates(seed, Some(seed.unavailable.clone())));
    let n = seed.journals.len();
    expected_count(&scoped, n);
    expected_count(&global, n);
    expected_count(&other, 0);
    assert_eq!(global, scoped);
    assert!(
        seed.journals
            .iter()
            .all(|p| !p.with_file_name(INDEX).exists())
            || arm == "candidate"
    );
    assert_eq!(initial, raw_identity(seed));
    let mut traces = vec![
        json!(by_dir),
        json!(describe),
        json!(existing_create),
        json!(scoped),
        json!(global),
        json!(other),
    ];

    if case.ends_with("-missing") {
        assert_eq!(observed(&by_dir).updated_at_ms, 30_000);
        assert!(!journal.exists());
    } else if case.ends_with("-broken") {
        let before = crate::diagnostics::get();
        let empty = checked_list(seed, &service, false, 0);
        let err = service.execute(list(seed, true)).unwrap_err();
        assert!(format!("{err:#}").contains("invalid journal record"));
        assert!(crate::diagnostics::get().decoded > before.decoded);
        assert!(!journal.with_file_name(INDEX).exists());
        traces.push(json!(empty));
        traces.push(json!(format!("{err:#}")));
    } else {
        // One small dedicated run per kind, and one real JSONL torn tail.
        if !case.ends_with("-many") {
            let catalog = journal.with_file_name(INDEX);
            let crossed_warm = if arm == "candidate" {
                let crossed = fs::read(&catalog).unwrap();
                crate::diagnostics::reset();
                let warm = checked_list(seed, &StorageService::new(kind), false, n);
                let reuse = crate::diagnostics::get();
                assert_eq!((reuse.decoded, reuse.fingerprint_bytes), (0, 0));
                assert_eq!(crossed, fs::read(&catalog).unwrap());
                fs::remove_file(&catalog).unwrap();
                Some((warm, crossed))
            } else {
                assert!(!catalog.exists());
                None
            };
            crate::diagnostics::reset();
            let cold = checked_list(seed, &service, false, n);
            let scan = crate::diagnostics::get();
            assert_eq!(scan.decoded, 1);
            let bytes = fs::read(&catalog).unwrap();
            if let Some((warm, golden)) = crossed_warm {
                assert_eq!(cold, warm);
                assert_eq!(bytes, golden);
            }
            let parsed: Value = serde_json::from_slice(&bytes).unwrap();
            let mut true_extent = 0;
            if matches!(kind, BackendKind::Jsonl) {
                let raw = initial[0].0.as_ref().unwrap();
                true_extent = raw.iter().rposition(|&b| b == b'\n').unwrap() + 1;
                assert_eq!(scan.fingerprint_bytes, true_extent as u64);
                assert_eq!(parsed["data"]["extent"], true_extent);
                assert_eq!(
                    parsed["data"]["fingerprint"],
                    crate::io::sha256_hex(&raw[..true_extent])
                );
                assert_eq!(raw.len() != true_extent, case.ends_with("-torn"));
            } else {
                assert_eq!(parsed["data"]["extent"], 1);
            }
            crate::diagnostics::reset();
            let warm = checked_list(seed, &StorageService::new(kind), false, n);
            let reuse = crate::diagnostics::get();
            assert_eq!((reuse.decoded, reuse.fingerprint_bytes), (0, 0));
            assert_eq!(cold, warm);
            crate::diagnostics::reset();
            let audit = checked_list(seed, &service, true, n);
            assert_eq!(crate::diagnostics::get().decoded, 1);
            assert_eq!(cold, audit);
            assert_eq!(bytes, fs::read(&catalog).unwrap());
            fs::write(pair.join(format!("{case}-{arm}-catalog.bytes")), bytes).unwrap();
            traces.extend([
                json!(cold), json!(warm), json!(audit),
                json!({"decoded":scan.decoded,"hash_bytes":scan.fingerprint_bytes,"extent":true_extent}),
            ]);
        }
        if case.ends_with("-one") {
            let wrong_kind = match kind {
                BackendKind::Sqlite => BackendKind::Jsonl,
                BackendKind::Jsonl => BackendKind::Sqlite,
            };
            let wrong = StorageService::new(wrong_kind)
                .execute(open_request(directory.clone()))
                .unwrap_err()
                .to_string();
            assert!(wrong.contains("another canonical journal format"));
            traces.push(json!(wrong));
            let path = directory.join("nonexistent");
            let missing = service.execute(open_request(path)).unwrap_err().to_string();
            assert!(missing.contains("session"));
            traces.push(json!(missing));
            let wal = PathBuf::from(format!("{}-wal", journal.to_string_lossy()));
            if let Ok(meta) = fs::metadata(&wal) {
                assert_eq!(
                    meta.len(),
                    0,
                    "no canonical WAL records left after writer release"
                );
                fs::remove_file(&wal).unwrap();
            }
            let mut file = File::create(&wal).unwrap();
            stable_modified(&file, 300);
            let empty_wal = run(&service, open_request(journal.clone()));
            let want = if matches!(kind, BackendKind::Sqlite) {
                100_000
            } else {
                300_000
            };
            assert_eq!(observed(&empty_wal).updated_at_ms, want);
            file.write_all(b"nonempty ordinary file").unwrap();
            stable_modified(&file, 301);
            drop(file);
            let nonempty_wal = run(&service, open_request(journal.clone()));
            assert_eq!(observed(&nonempty_wal).updated_at_ms, 301_000);
            fs::remove_file(wal).unwrap();
            traces.extend([json!(empty_wal), json!(nonempty_wal)]);
        }
    }

    assert_eq!(initial, raw_identity(seed));
    fs::write(
        pair.join(format!("{case}-{arm}-response.bytes")),
        serde_json::to_vec(&traces).unwrap(),
    )
    .unwrap();
}

#[test]
fn r276_fallback_pair() {
    let (Some(mode), Some(pair)) = (
        std::env::var_os("R276F_MODE"),
        std::env::var_os("R276F_PAIR"),
    ) else {
        return;
    };
    let mode = mode.to_str().unwrap();
    let pair = PathBuf::from(pair);
    for (label, kind) in [
        ("jsonl", BackendKind::Jsonl),
        ("sqlite", BackendKind::Sqlite),
    ] {
        let mut cases = vec![("one", "none", 1), ("many", "none", MANY)];
        if matches!(kind, BackendKind::Jsonl) {
            cases.extend([
                ("missing", "missing", 1),
                ("torn", "torn", 1),
                ("broken", "broken", 1),
            ]);
        }
        for (case, fault, n) in cases {
            let name = format!("{label}-{case}");
            let p = pair.join(format!("{name}.seed"));
            if mode == "seed" {
                let seeded = make(kind, fault, n);
                fs::write(p, serde_json::to_vec(&seeded).unwrap()).unwrap();
                continue;
            }
            let seed = serde_json::from_slice::<Seed>(&fs::read(p).unwrap()).unwrap();
            if case == "one" {
                let directory = seed.descriptor.local_path.as_ref().unwrap();
                let journal = seed.descriptor.record_location.as_ref().unwrap();
                measure(
                    kind,
                    &open_request(directory.clone()),
                    &format!("{label}-directory"),
                    Ok(None),
                );
                measure(
                    kind,
                    &open_request(journal.clone()),
                    &format!("{label}-journal"),
                    Ok(None),
                );
                measure(
                    kind,
                    &open_request(directory.join("nonexistent")),
                    &format!("{label}-absent"),
                    Err(()),
                );
                measure(
                    kind,
                    &candidates(&seed, Some(seed.unavailable.clone())),
                    &format!("{label}-zero"),
                    Ok(Some(0)),
                );
            }
            if case == "one" || case == "many" {
                measure(
                    kind,
                    &candidates(&seed, Some(seed.workspace.clone())),
                    &format!("{label}-{case}"),
                    Ok(Some(n)),
                );
            }
            verified_bytes(&seed, kind, &name, &pair, mode);
        }
    }
}
