#[test]
fn r63_usage_projection_allocation_counts() {
    for (label, kind) in [("jsonl", BackendKind::Jsonl), ("sqlite", BackendKind::Sqlite)] {
        for turns in [0, 320] {
            let mut f = Fixture::new(kind);
            let mut retained = Vec::new();
            for index in 0..turns {
                add_turn(&mut f, index % 97 == 96);
                let row = text("ordinary retained text in the preceding turn");
                f.append(vec![row.clone()]);
                retained.push(row);
                if index % 16 == 15 {
                    let input = retained.len();
                    retained.drain(..input - 4);
                    let mut report = HistoryCompactionReport::unchanged(input, None);
                    report.changed = true;
                    report.output_messages = retained.len();
                    let revision = f.revision.history_revision;
                    let attribution = StorageRecordAttribution {
                        execution_id: None,
                        thread_id: Some(f.thread),
                        turn_id: None,
                    };
                    commit(
                        &mut f,
                        attribution,
                        JournalEntry::HistoryMutated(HistoryMutated {
                            previous_revision: revision,
                            new_revision: revision + 1,
                            mutation: HistoryMutationKind::Replace,
                            messages: retained.clone(),
                            compaction: Some(report),
                            tool_results: vec![],
                        }),
                    );
                }
            }
            f.service
                .execute(SessionStorageRequest::ReleaseWriter {
                    lease: f.lease.clone(),
                })
                .unwrap();
            let snapshot = f.snapshot();
            let before = std::fs::read(f.descriptor.record_location.as_ref().unwrap()).ok();
            let mut reference = None;
            let mut stats = [Vec::new(), Vec::new()];
            for full in [true, false, false, true] {
                let request = SessionStorageRequest::ReadUsage {
                    snapshot: snapshot.clone(),
                };
                crate::diagnostics::reset();
                let (out, counts) = crate::r63_probe::measure(full, || {
                    f.service.execute(request.clone()).unwrap()
                });
                request.validate_response(&out).unwrap();
                assert_eq!(
                    crate::diagnostics::get().decoded,
                    snapshot.revision.session_seq,
                    "both variants decode every canonical record"
                );
                let SessionStorageResponse::Usage { usage } = &out else { panic!("missing usage"); };
                assert_eq!(usage.requests.len(), turns);
                assert_eq!(
                    usage.requests.iter().filter(|r| r.status == ModelUsageStatus::Error).count(),
                    turns / 97
                );
                let raw = serde_json::to_vec(&out).unwrap();
                assert_eq!(reference.get_or_insert(raw.clone()), &raw);
                assert_eq!(
                    counts.2,
                    if full { snapshot.revision.session_seq } else { 0 }
                );
                let index = usize::from(full);
                stats[index].push(counts);
                println!(
                    "R63 scope={label} turns={turns} records={} full={full} alloc_calls={} alloc_bytes={} context_visits={} serialized_sha256={}",
                    snapshot.revision.session_seq,
                    counts.0, counts.1, counts.2,
                    crate::io::sha256_hex(&raw),
                );
            }
            assert_eq!(stats[1].len(), 2);
            assert_eq!(stats[0].len(), 2);
            for (old, reduced) in stats[1].iter().zip(&stats[0]) {
                if turns == 0 {
                    assert_eq!(old, reduced);
                } else {
                    assert!(old.0 > reduced.0 && old.1 > reduced.1, "paired {old:?} {reduced:?}");
                }
            }
            assert_eq!(
                std::fs::read(f.descriptor.record_location.as_ref().unwrap()).ok(),
                before
            );
        }
    }
}

#[test]
fn r63_usage_replay_keeps_the_same_failed_read_and_stale_revision() {
    use crate::{
        backend::{JournalBackend, Jsonl, RecordSnapshot, SourceVersion},
        snapshot::SnapshotState,
    };
    struct EofFault(Box<dyn RecordSnapshot>);
    impl RecordSnapshot for EofFault {
        fn reset(&mut self) -> anyhow::Result<()> { self.0.reset() }
        fn source_version(&self) -> anyhow::Result<Option<SourceVersion>> {
            self.0.source_version()
        }
        fn verify_fixed_prefix(&self) -> anyhow::Result<()> { self.0.verify_fixed_prefix() }
        fn next(&mut self) -> anyhow::Result<Option<JournalRecord>> {
            match self.0.next()? {
                Some(record) => Ok(Some(record)),
                None => Err(std::io::Error::other("injected ordinary EOF read failure").into()),
            }
        }
        fn fingerprint(&self) -> &str { self.0.fingerprint() }
        fn read_hash(&self) -> ring::digest::Context { self.0.read_hash() }
        fn extent(&self) -> u64 { self.0.extent() }
        fn prefix_fingerprint(&mut self, sequence: u64) -> anyhow::Result<Option<String>> {
            self.0.prefix_fingerprint(sequence)
        }
    }
    let mut f=Fixture::new(BackendKind::Jsonl);
    f.append(vec![text("ordinary validated prefix")]);
    add_turn(&mut f,false);
    let snapshot=f.snapshot();
    let root=f.descriptor.local_path.as_ref().unwrap();
    let source=|| Jsonl::new().snapshot(root, snapshot.session.session_id).unwrap();
    let mut failing=SnapshotState::new(snapshot.clone(), Box::new(EofFault(source())),false,None).unwrap();
    let old=failing.fold().err().unwrap();
    let new=failing.fold_usage().err().unwrap();
    assert_eq!(old.to_string(),new.to_string());
    assert!(new.downcast_ref::<std::io::Error>().is_some());
    assert!(!failing.is_verified_unchanged().unwrap());

    let mut wrong=snapshot.clone();
    wrong.revision.history_revision+=1;
    let mut stale=SnapshotState::new(wrong,source(),false,None).unwrap();
    let old=stale.fold().err().unwrap();
    let new=stale.fold_usage().err().unwrap();
    assert_eq!(old.to_string(),"snapshot revision changed");
    assert_eq!(old.to_string(),new.to_string());
    assert!(!stale.is_verified_unchanged().unwrap());
}
