#[test]
fn jsonl_display_fold_reuses_bounded_fallback_scratch() {
    use crate::backend::{JournalBackend, Jsonl};

    let mut f = Fixture::new(BackendKind::Jsonl);
    let entries: Vec<_> = [
        42_000, 47_000, 51_000, 45_000, 43_000, 180_000, 42_000, 43_000, 44_000, 45_000,
    ]
    .into_iter()
    .map(|n| f.append(vec![text(&"x".repeat(n))]).entry)
    .collect();
    let dir = f.descriptor.local_path.clone().unwrap();
    let id = f.descriptor.session.session_id;
    let raw = std::fs::read(f.descriptor.record_location.as_ref().unwrap()).unwrap();
    let mut source = Jsonl::new().snapshot(&dir, id).unwrap();
    let mut regular = Jsonl::new().snapshot(&dir, id).unwrap();
    let mut scratch = Vec::new();
    let mut consumed = 0;
    let mut reused = false;
    for (i, raw_line) in raw.split_inclusive(|&b| b == b'\n').enumerate() {
        let old = (scratch.as_ptr(), scratch.capacity());
        let record = source.next_with_scratch(&mut scratch).unwrap().unwrap();
        assert_eq!(record, regular.next().unwrap().unwrap());
        assert_eq!(record.entry, entries[i]);
        let crosses_buffer =
            consumed / (64 * 1024) != (consumed + raw_line.len() - 1) / (64 * 1024);
        consumed += raw_line.len();
        assert_eq!(
            source.consumed_fingerprint(),
            crate::io::sha256_hex(&raw[..consumed])
        );
        if i == 5 {
            assert_eq!(scratch.capacity(), 0, "do not retain an oversized line");
        } else {
            assert!(scratch.capacity() <= 128 * 1024);
            if crosses_buffer {
                assert!(scratch == raw_line || scratch == &raw_line[..raw_line.len() - 1]);
                reused |= old.1 != 0 && old == (scratch.as_ptr(), scratch.capacity());
            }
        }
    }
    assert!(reused, "ordinary fallback records reused the allocation");
    assert_eq!(consumed, raw.len());
    assert!(source.next_with_scratch(&mut scratch).unwrap().is_none());
    assert!(regular.next().unwrap().is_none());
    assert_eq!(source.fingerprint(), regular.fingerprint());
    assert!(source.confirm_verified_data().unwrap());
    source.reset().unwrap();
    assert_eq!(
        source
            .next_with_scratch(&mut scratch)
            .unwrap()
            .unwrap()
            .entry,
        entries[0]
    );

    // Exercise actual display publication and an ordinary append while an older
    // projection is held. The old handle still exposes exactly its fixed prefix.
    let projection = open(&f);
    f.append(vec![text("later append")]);
    let command = SessionStorageRequest::ReadDisplayRecords {
        snapshot: projection.snapshot.clone(),
        after_seq: 0,
        limit: 64,
    };
    let result = f.service.execute(command.clone()).unwrap();
    command.validate_response(&result).unwrap();
    let SessionStorageResponse::Records { page } = result else {
        panic!("missing display page");
    };
    assert_eq!(page.next_after_seq, None);
    assert_eq!(
        page.records
            .into_iter()
            .map(|r| r.entry)
            .collect::<Vec<_>>(),
        entries
    );

    // Ordinary external payloads retain the stricter blob-bearing proof rule.
    let external = f.append(vec![text(&"blob".repeat(80_000))]);
    let mut blob_source = Jsonl::new().snapshot(&dir, id).unwrap();
    let mut last = None;
    while let Some(row) = blob_source.next_with_scratch(&mut scratch).unwrap() {
        last = Some(row);
    }
    assert_eq!(last.unwrap().entry, external.entry);
    assert!(!blob_source.confirm_verified_data().unwrap());
}
