// Appended as a test-only child of backend::sqlite in a temporary pinned checkout.
use super::*;
use proteus_contracts::model_standard::{CanonicalMessage, MessageRole};
use std::{env, fs, time::Instant};
use uuid::Uuid;

#[test]
#[ignore = "local measurement driver; invoke from native_benchmark.py"]
fn measure() {
    let mode = env::var("JOURNAL_BENCH_MODE").unwrap();
    let dir = PathBuf::from(env::var_os("JOURNAL_BENCH_DIR").unwrap());
    let n: u64 = env::var("JOURNAL_BENCH_ROWS").unwrap().parse().unwrap();
    let id = Uuid::from_u128(42);
    if mode == "seed" {
        let bytes: usize = env::var("JOURNAL_BENCH_BYTES").unwrap().parse().unwrap();
        fs::create_dir_all(&dir).unwrap();
        let mut backend = Sqlite::default();
        backend.recover(&dir, id).unwrap();
        for seq in 1..=n {
            let mut message = CanonicalMessage::text(MessageRole::User, "x".repeat(bytes));
            message.id = Uuid::from_u128(20_000 + u128::from(seq));
            message.parts[0].part_id = Uuid::from_u128(40_000 + u128::from(seq));
            let record = JournalRecord {
                schema_version: JOURNAL_SCHEMA_VERSION,
                record_id: Uuid::from_u128(u128::from(seq)),
                session_seq: seq,
                timestamp_ms: 1234,
                session_id: id,
                execution_id: None,
                thread_id: None,
                turn_id: None,
                entry: JournalEntry::HistoryMutated(HistoryMutated {
                    previous_revision: seq - 1,
                    new_revision: seq,
                    mutation: HistoryMutationKind::Append,
                    messages: vec![message],
                    compaction: None,
                    tool_results: vec![],
                }),
            };
            backend.append(&dir, &record).unwrap();
        }
        return;
    }

    let expected = env::var("JOURNAL_BENCH_SHA256").unwrap();
    let hint = PrefixHint { extent: n, fingerprint: expected.clone() };
    let mut backend = Sqlite::default();
    let started = Instant::now();
    match mode.as_str() {
        "next" => {
            let mut source = backend.snapshot_warm(&dir, id, &hint).unwrap();
            for seq in 1..=n {
                let record = source.next().unwrap().unwrap();
                assert_eq!(record.session_seq, seq);
                assert_eq!(record.record_id, Uuid::from_u128(u128::from(seq)));
            }
            assert!(source.next().unwrap().is_none()); // Production compares the ordered hash at EOF.
        }
        "cold_hash" => {
            let snapshot = backend.snapshot(&dir, id).unwrap();
            assert_eq!(snapshot.extent(), n);
            assert_eq!(snapshot.fingerprint(), expected);
        }
        "prefix_hash" => {
            let mut source = backend.snapshot_warm(&dir, id, &hint).unwrap();
            assert_eq!(source.prefix_fingerprint(n).unwrap().as_deref(), Some(expected.as_str()));
        }
        _ => panic!("unknown benchmark mode"),
    }
    let micros = started.elapsed().as_micros();
    let status = fs::read_to_string("/proc/self/status").unwrap();
    let rss_kib: u64 = status.lines().find(|s| s.starts_with("VmHWM:")).unwrap()
        .split_whitespace().nth(1).unwrap().parse().unwrap();
    println!("MEASURE mode={mode} rows={n} us={micros} rss_kib={rss_kib} sqlite={}", rusqlite::version());
}
