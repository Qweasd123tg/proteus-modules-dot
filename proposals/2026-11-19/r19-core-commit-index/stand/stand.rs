#![allow(dead_code, unused_imports)]
use std::alloc::{GlobalAlloc, Layout, System};
use std::sync::atomic::{AtomicIsize, Ordering::Relaxed};
struct Counter;
static LIVE: AtomicIsize = AtomicIsize::new(0);
#[global_allocator]
static A: Counter = Counter;
unsafe impl GlobalAlloc for Counter {
    unsafe fn alloc(&self, l: Layout) -> *mut u8 {
        let p = unsafe { System.alloc(l) };
        if !p.is_null() {
            LIVE.fetch_add(l.size() as isize, Relaxed);
        }
        p
    }
    unsafe fn dealloc(&self, p: *mut u8, l: Layout) {
        LIVE.fetch_sub(l.size() as isize, Relaxed);
        unsafe {
            System.dealloc(p, l);
        }
    }
}
pub use proteus_contracts::{contracts, domain, model_standard};
pub mod core {
    use super::{LIVE, Relaxed};
    pub use proteus_contracts::storage::journal::*;
    use std::time::Instant;
    pub struct JournalReadSnapshot {
        pub records: Vec<JournalRecord>,
        pub stats: Vec<(isize, u128)>,
    }
    impl JournalReadSnapshot {
        pub fn scan_display(
            &mut self,
            mut consume: impl FnMut(JournalRecord) -> anyhow::Result<()>,
        ) -> anyhow::Result<()> {
            let before = LIVE.load(Relaxed);
            let start = Instant::now();
            for r in &self.records {
                consume(r.clone())?
            }
            self.stats
                .push((LIVE.load(Relaxed) - before, start.elapsed().as_micros()));
            Ok(())
        }
    }
}
mod transcript;
fn main() {
    use core::*;
    use model_standard::*;
    let n: usize = std::env::args().nth(1).unwrap().parse().unwrap();
    let id = domain::SessionId::from_u128(1);
    let mut records = Vec::with_capacity(n.div_ceil(50));
    for offset in (0..n).step_by(50) {
        let messages = (offset..n.min(offset + 50))
            .map(|i| {
                let mut m = CanonicalMessage::text(MessageRole::User, format!("row {i}"));
                m.id = domain::MessageId::from_u128(1 + i as u128);
                m.parts[0].part_id = domain::PartId::from_u128(1 + i as u128);
                m
            })
            .collect();
        let seq = records.len() as u64 + 1;
        records.push(JournalRecord {
            schema_version: JOURNAL_SCHEMA_VERSION,
            record_id: domain::RecordId::from_u128(seq as u128),
            session_id: id,
            session_seq: seq,
            timestamp_ms: seq as i64,
            execution_id: None,
            thread_id: None,
            turn_id: None,
            entry: JournalEntry::HistoryMutated(HistoryMutated {
                previous_revision: seq - 1,
                new_revision: seq,
                mutation: HistoryMutationKind::Append,
                messages,
                compaction: None,
                tool_results: vec![],
            }),
        });
    }
    let mut source = JournalReadSnapshot {
        records,
        stats: Vec::with_capacity(5),
    };
    let rows = transcript::journal_transcript_from_source(&mut source, None).unwrap();
    assert_eq!(source.stats.len(), 2);
    assert_eq!(rows.len(), n);
    for (i, r) in rows.iter().enumerate() {
        assert_eq!(r.text, format!("row {i}"));
        assert_eq!(r.timestamp_ms, Some((i / 50 + 1) as i64));
    }
    let digest =
        proteus_contracts::contracts::storage_value_etag(&serde_json::to_value(&rows).unwrap())
            .unwrap();
    println!(
        "n={n} scans={} rows={} etag={digest} retained_scan1={} elapsed_scan1_us={} elapsed_scan2_us={}",
        source.stats.len(),
        rows.len(),
        source.stats[0].0,
        source.stats[0].1,
        source.stats[1].1
    );
}
