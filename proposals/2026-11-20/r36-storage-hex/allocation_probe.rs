// Temporary crate-root unit-test module, not part of the candidate.
use crate::backend::{JournalBackend, Jsonl, Sqlite};
use crate::types::*;
use proteus_contracts::model_standard::{CanonicalMessage, MessageRole};
use std::alloc::{GlobalAlloc, Layout, System};
use std::cell::Cell;
use uuid::Uuid;

struct Count;
#[global_allocator]
static ALLOC: Count = Count;
thread_local! {
    static TOTAL: Cell<Option<(u64,u64)>> = const { Cell::new(None) };
}
fn note(n: usize) {
    let _ = TOTAL.try_with(|slot| {
        if let Some((a,b)) = slot.get() {
            slot.set(Some((a+1, b+n as u64)));
        }
    });
}
unsafe impl GlobalAlloc for Count {
    unsafe fn alloc(&self, layout: Layout) -> *mut u8 {
        note(layout.size());
        unsafe { System.alloc(layout) }
    }
    unsafe fn alloc_zeroed(&self, layout: Layout) -> *mut u8 {
        note(layout.size());
        unsafe { System.alloc_zeroed(layout) }
    }
    unsafe fn dealloc(&self, p: *mut u8, layout: Layout) {
        unsafe { System.dealloc(p, layout) }
    }
    unsafe fn realloc(&self, p: *mut u8, layout: Layout, n: usize) -> *mut u8 {
        note(n);
        unsafe { System.realloc(p, layout, n) }
    }
}


fn sample<T>(f: impl FnOnce() -> T) -> (T, (u64, u64)) {
    TOTAL.set(Some((0,0)));
    let value = f();
    (value, TOTAL.replace(None).unwrap())
}
fn old_hash(bytes: &[u8]) -> String {
    ring::digest::digest(&ring::digest::SHA256,bytes).as_ref().iter()
        .map(|b| format!("{b:02x}")).collect()
}
fn log(phase:&str, pass:usize, counts:(u64,u64), digest:&str) {
    if pass != 0 { println!("DIGEST,{phase},{pass},{},{},{digest}",counts.0, counts.1); }
}
#[test]
fn measure_storage_digest_allocations() {
    for i in 0u32..4096 {
        let input = i.to_le_bytes();
        assert_eq!(crate::io::sha256_hex(&input), old_hash(&input));
    }
    let size=128;
        let mut message = CanonicalMessage::text(MessageRole::User, "Q".repeat(size));
        message.id = Uuid::from_u128(3);
        message.parts[0].part_id = Uuid::from_u128(4);
        let record = JournalRecord {
            schema_version: JOURNAL_SCHEMA_VERSION, record_id: Uuid::from_u128(1),
            session_seq: 1, timestamp_ms: 1234, session_id: Uuid::from_u128(2),
            execution_id: None, thread_id: None, turn_id: None,
            entry: JournalEntry::HistoryMutated(HistoryMutated {
                previous_revision: 0, new_revision: 1, mutation: HistoryMutationKind::Append,
                messages: vec![message], compaction: None, tool_results: vec![],
            }),
        };

    for (name, mut backend) in [
        ("jsonl", Box::new(Jsonl::new()) as Box<dyn JournalBackend>),
        ("sqlite", Box::new(Sqlite::default()) as Box<dyn JournalBackend>)
    ] {
        let dir = tempfile::tempdir().unwrap();
        backend.recover(dir.path(), record.session_id).unwrap();
        let append=backend.append(dir.path(), &record).unwrap();
        let reference=old_hash(&append.bytes);
        for pass in 0..=3 {
            let (mut snapshot,counts)=sample(|| backend.snapshot(dir.path(), record.session_id).unwrap());
            assert_eq!(snapshot.fingerprint(), reference);
            log(&format!("{name}_snapshot"),pass,counts,&reference);
            assert_eq!(snapshot.next().unwrap().unwrap(),record);
            let (got,counts)=sample(|| snapshot.consumed_fingerprint());
            assert_eq!(got, reference);
            log(&format!("{name}_consumed"),pass,counts,&reference);
            assert!(snapshot.next().unwrap().is_none());
        }
    }
    let mut seed=7u64;
    let original:Vec<u8>=(0..4*1024*1024).map(|_| {
        seed ^= seed << 13; seed ^= seed >> 7; seed ^= seed << 17;
        (seed >> 17) as u8
    }).collect();
    let dir = tempfile::tempdir().unwrap();
    let packed=crate::blob_codec::pack(dir.path(),&original).unwrap();
    let reference=old_hash(&original);
    let manifest=old_hash(&packed);
    println!("FIXTURE,{},{},{},{reference},{manifest}",original.len(),packed.len(),
        crate::blob_codec::chunk_files(&packed).unwrap().len());
    for pass in 0..=3 {
        let (got,counts)=sample(|| crate::blob_codec::unpack_expected(dir.path(), &packed,&reference,original.len() as u64).unwrap());
        assert_eq!(got.as_ref(),original);
        log("unpack_verified_4m",pass,counts,&reference);
    }
}
