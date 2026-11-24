#![allow(dead_code)]
#[path = "../work/proteus-process-host/src/framing.rs"]
mod after;
#[path = "../baseline/proteus-process-host/src/framing.rs"]
mod before;
use proteus_contracts::{contracts::*, domain::*, model_standard::*, storage::journal::*};
use serde_json::{Value, json};
use std::hint::black_box;
use uuid::Uuid;

#[repr(C)]
struct Timespec {
    s: i64,
    ns: i64,
}
unsafe extern "C" {
    fn clock_gettime(clock: i32, t: *mut Timespec) -> i32;
}
fn thread_ns() -> u128 {
    let mut t = Timespec { s: 0, ns: 0 };
    assert_eq!(unsafe { clock_gettime(3, &mut t) }, 0);
    (t.s as u128) * 1_000_000_000 + (t.ns as u128)
}

fn history(n: usize, repeats: usize, strict: bool) -> Vec<u8> {
    let messages: Vec<_> = (0..n)
        .map(|index| {
            let text = format!(
                "Fixture row {index}\n{}",
                "Синтетический текст для замера памяти и прокрутки. ".repeat(repeats)
            );
            let mut m = CanonicalMessage::text(
                if index % 2 == 0 {
                    MessageRole::User
                } else {
                    MessageRole::Assistant
                },
                text,
            )
            .with_id(Uuid::from_u128(index as u128 + 100));
            m.parts[0].part_id = Uuid::from_u128(index as u128 + 100 + n as u128);
            m
        })
        .collect();
    let revision = StorageRevision {
        session_seq: 1,
        history_revision: 1,
    };
    let session = SessionLocator {
        session_id: Uuid::from_u128(1),
        key: "test-50k".into(),
    };
    let snapshot = StorageSnapshot {
        session: session.clone(),
        snapshot_id: "read-1".into(),
        revision,
        content_sha256: "b".repeat(64),
    };
    let (request, response) = if strict {
        (
            SessionStorageRequest::ReadRecords {
                snapshot: snapshot.clone(),
                after_seq: 0,
                limit: 64,
            },
            SessionStorageResponse::Records {
                page: StorageRecordPage {
                    snapshot,
                    next_after_seq: None,
                    records: vec![JournalRecord {
                        schema_version: JOURNAL_SCHEMA_VERSION,
                        record_id: Uuid::from_u128(99),
                        timestamp_ms: 1001,
                        session_id: session.session_id,
                        session_seq: 1,
                        execution_id: None,
                        thread_id: None,
                        turn_id: None,
                        entry: JournalEntry::HistoryMutated(HistoryMutated {
                            previous_revision: 0,
                            new_revision: 1,
                            mutation: HistoryMutationKind::Append,
                            messages,
                            tool_results: vec![],
                            compaction: None,
                        }),
                    }],
                },
            },
        )
    } else {
        let state = StorageResumeState {
            conversation: StorageConversation {
                messages,
                revision,
                model_context: vec![],
            },
            usage: SessionUsageSnapshot {
                session_id: session.session_id,
                revision: 0,
                latest_turn_id: None,
                requests: vec![],
            },
            last_history_turn: None,
            interrupted_turns: vec![],
        };
        (
            SessionStorageRequest::OpenDisplaySnapshot { session },
            SessionStorageResponse::DisplaySnapshot {
                projection: Some(StorageDisplaySnapshot { snapshot, state }),
            },
        )
    };
    request.validate().unwrap();
    request.validate_response(&response).unwrap();
    let mut wire =
        serde_json::to_vec(&json!({"jsonrpc":"2.0","id":"h:1:1","result":response})).unwrap();
    wire.push(b'\n');
    wire
}

use std::io::{BufRead, BufReader, Cursor};

fn original<R: BufRead>(r: &mut R, limit: usize) -> anyhow::Result<Value> {
    before::Framing::read_frame(&before::NewlineJsonFraming::new(limit), r)
}
fn candidate<R: BufRead>(r: &mut R, limit: usize) -> anyhow::Result<Value> {
    after::Framing::read_frame(&after::NewlineJsonFraming::new(limit), r)
}
fn boundary(r: &BufReader<Cursor<&[u8]>>) -> usize {
    r.get_ref().position() as usize - r.buffer().len()
}
fn oracle(wire: &[u8], cap: usize, limit: usize) {
    let mut a = BufReader::with_capacity(cap, Cursor::new(wire));
    let mut b = BufReader::with_capacity(cap, Cursor::new(wire));
    for _ in 0..2 {
        let x = original(&mut a, limit).map_err(|e| format!("{e:#}"));
        let y = candidate(&mut b, limit).map_err(|e| format!("{e:#}"));
        assert_eq!(x, y);
        assert_eq!(boundary(&a), boundary(&b));
    }
}
fn checks() -> usize {
    let mut n = 0;
    for tail in ["", "\n", "\r\n", "x\n", "\n{}\n"] {
        let valid = format!("{{\"v\":\"{}\"}}{tail}", "🦀text\\n".repeat(5000)).into_bytes();
        for malformed in [false, true] {
            let mut frame = valid.clone();
            if malformed {
                let off = frame.len() - tail.len() - 2;
                frame[off] = 0xff;
            }
            let boundary = frame
                .iter()
                .position(|&b| b == b'\n')
                .map_or(frame.len(), |i| i + 1);
            for cap in [511, 1023, 1024, 1025, 2048, 8191, 8192, 8193, 16384] {
                for limit in [boundary - 1, boundary, boundary + 1] {
                    oracle(&frame, cap, limit);
                    n += 1;
                }
            }
        }
    }
    n
}
#[inline(never)]
fn measure(use_new: bool, wire: &[u8], n: usize) -> u128 {
    const LIMIT: usize = 128 * 1024 * 1024;
    let t = thread_ns();
    for _ in 0..n {
        let mut reader = BufReader::new(Cursor::new(black_box(wire)));
        let v = if use_new {
            candidate(&mut reader, LIMIT)
        } else {
            original(&mut reader, LIMIT)
        };
        black_box(v.unwrap());
        assert_eq!(boundary(&reader), wire.len());
    }
    thread_ns() - t
}
fn main() {
    let cases = checks();
    for shape in [
        "small",
        "projected-50k-x4",
        "strict-50k-x5",
        "unescaped-8MiB",
        "escaped-1MiB",
    ] {
        let (wire, calls) = match shape {
            "small" => (
                br#"{ "jsonrpc":"2.0","id":"h:1:2","result":"ok" }"#
                    .iter()
                    .copied()
                    .chain([b'\n'])
                    .collect(),
                20000,
            ),
            "projected-50k-x4" => (history(50000, 4, false), 1),
            "strict-50k-x5" => (history(50000, 5, true), 1),
            "unescaped-8MiB" => (
                format!("\"{}\"\n", "x".repeat(8 * 1024 * 1024)).into_bytes(),
                3,
            ),
            "escaped-1MiB" => (
                format!("\"{}\"\n", "\\t\\u0000".repeat(131072)).into_bytes(),
                3,
            ),
            _ => unreachable!(),
        };
        oracle(&wire, 8192, 128 * 1024 * 1024);
        measure(false, &wire, calls);
        measure(true, &wire, calls);
        let (mut a, mut b) = (vec![], vec![]);
        for i in 0..10 {
            if i % 2 == 0 {
                a.push(measure(false, &wire, calls));
                b.push(measure(true, &wire, calls));
            } else {
                b.push(measure(true, &wire, calls));
                a.push(measure(false, &wire, calls));
            }
        }
        println!(
            "{}",
            json!({"shape":shape,"wire":wire.len(),"calls":calls,"checks":cases,"before_cpu_ns":a,"after_cpu_ns":b,"ordered":cfg!(feature="ordered")})
        );
    }
}
