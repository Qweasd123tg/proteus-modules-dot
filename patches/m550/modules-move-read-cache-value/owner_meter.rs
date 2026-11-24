extern crate self as proteus_module_sdk; // Only the unchanged SDK re-export.
pub use proteus_contracts as contracts;
mod display_reply;

use ::session_storage::{BackendKind, StorageService};
use contracts::{
    contracts::*,
    domain::{new_record_id, new_session_id, new_thread_id},
    model_standard::{CanonicalMessage, MessageRole},
    storage::journal::*,
};
use serde_json::Value;
use std::{
    alloc::{GlobalAlloc, Layout, System},
    cell::Cell,
    io::Write,
};

#[derive(Clone, Copy, Default)]
struct Meter {
    events: usize,
    requested: usize,
    live: isize,
    peak: isize,
}
thread_local! { static MARK: Cell<Option<Meter>> = const { Cell::new(None) }; }
fn update(bytes: usize, delta: isize, event: bool) {
    let _ = MARK.try_with(|slot| {
        if let Some(mut m) = slot.get() {
            m.events += event as usize;
            m.requested += bytes;
            m.live += delta;
            m.peak = m.peak.max(m.live);
            slot.set(Some(m));
        }
    });
}
struct Heap;
unsafe impl GlobalAlloc for Heap {
    unsafe fn alloc(&self, l: Layout) -> *mut u8 {
        let a = unsafe { System.alloc(l) };
        if !a.is_null() {
            update(l.size(), l.size() as isize, true);
        }
        a
    }
    unsafe fn alloc_zeroed(&self, l: Layout) -> *mut u8 {
        let a = unsafe { System.alloc_zeroed(l) };
        if !a.is_null() {
            update(l.size(), l.size() as isize, true);
        }
        a
    }
    unsafe fn realloc(&self, p: *mut u8, l: Layout, n: usize) -> *mut u8 {
        let a = unsafe { System.realloc(p, l, n) };
        if !a.is_null() {
            update(n, n as isize - l.size() as isize, true);
        }
        a
    }
    unsafe fn dealloc(&self, p: *mut u8, l: Layout) {
        update(0, -(l.size() as isize), false);
        unsafe { System.dealloc(p, l) };
    }
}
#[global_allocator]
static HEAP: Heap = Heap;

fn parse(input: &[u8]) -> SessionStorageResponse {
    let mut v: Value = serde_json::from_slice(input).unwrap();
    serde_json::from_value(v["result"].take()).unwrap()
}

fn content(v: &SessionStorageResponse) -> &Value {
    match v {
        SessionStorageResponse::Metadata {
            document: Some(document),
        } => &document.value,
        _ => panic!("fixture must be an actual hit"),
    }
}

fn strings(v: &Value, out: &mut Vec<(usize, usize)>) {
    match v {
        Value::Array(values) => {
            for v in values {
                strings(v, out);
            }
        }
        Value::Object(values) => {
            for (key, v) in values {
                out.push((key.as_ptr() as usize, key.len()));
                strings(v, out);
            }
        }
        Value::String(value) if !value.is_empty() => {
            out.push((value.as_ptr() as usize, value.len()))
        }
        _ => (),
    }
}

struct Digest(ring::digest::Context);
impl Write for Digest {
    fn write(&mut self, bs: &[u8]) -> std::io::Result<usize> {
        self.0.update(bs);
        Ok(bs.len())
    }
    fn flush(&mut self) -> std::io::Result<()> {
        Ok(())
    }
}

fn now(r: SessionStorageResponse, optimized: bool) -> (Meter, usize, usize, usize, String) {
    let mut original = Vec::new();
    strings(content(&r), &mut original);
    MARK.set(Some(Meter::default()));
    let v = if optimized {
        display_reply::into_value(r).unwrap()
    } else {
        serde_json::to_value(r).unwrap()
    };
    let meter = MARK.replace(None).unwrap();
    let mut moved = Vec::new();
    strings(&v["document"]["value"], &mut moved);
    assert_eq!(original.len(), moved.len());
    let mut identical = 0;
    let mut text_bytes = 0;
    for ((before, old_len), (after, new_len)) in original.iter().zip(moved) {
        assert_eq!(*old_len, new_len);
        identical += usize::from(*before == after);
        text_bytes += new_len;
    }
    let mut d = Digest(ring::digest::Context::new(&ring::digest::SHA256));
    serde_json::to_writer(&mut d, &v).unwrap();
    let digest: String =
        d.0.finish()
            .as_ref()
            .iter()
            .map(|b| format!("{b:02x}"))
            .collect();
    (meter, original.len(), identical, text_bytes, digest)
}

fn qualify(label: &str, make: impl Fn() -> SessionStorageResponse) {
    let (old, n, old_moved, bytes, a) = now(make(), false);
    let (new, m, new_moved, size, b) = now(make(), true);
    assert_eq!((n, bytes, &a), (m, size, &b));
    assert_eq!(old_moved, 0);
    assert_eq!(new_moved, n);
    println!(
        "{label} {n} {bytes} {old_moved} {new_moved} {} {} {} {} {} {} {a}",
        old.events, old.requested, old.peak, new.events, new.requested, new.peak
    );
    assert!(old.requested - new.requested >= bytes);
    assert!(old.events - new.events >= n);
    assert!(old.peak.saturating_sub(new.peak) >= bytes as isize);
}

fn check_shape() {
    for document in [
        None,
        Some(StorageMetadataDocument {
            etag: "fixture".into(),
            value: Value::Null,
        }),
        Some(StorageMetadataDocument {
            etag: "fixture".into(),
            value: serde_json::json!({
                "z":[{"β":"a\u{0000}\n","x":1.25},0],
                "a":false,
                "map":{"x":[],"a":null},
            }),
        }),
    ] {
        let r = SessionStorageResponse::Metadata { document };
        let want = serde_json::to_vec(&serde_json::to_value(&r).unwrap()).unwrap();
        let got = serde_json::to_vec(&display_reply::into_value(r).unwrap()).unwrap();
        assert_eq!(got, want);
    }
}

fn ready(
    kind: BackendKind,
) -> (
    StorageService,
    StorageSnapshot,
    tempfile::TempDir,
    tempfile::TempDir,
) {
    let d = tempfile::tempdir().unwrap();
    let work = tempfile::tempdir().unwrap();
    let s = StorageService::new(kind);
    let SessionStorageResponse::Session { descriptor } = s
        .execute(SessionStorageRequest::Create {
            config_root: d.path().into(),
            workspace_path: work.path().into(),
            session_id: new_session_id(),
            parent_session_id: None,
        })
        .unwrap()
    else {
        panic!("fixture create")
    };
    let session = descriptor.session;
    let SessionStorageResponse::Writer { lease, revision } = s
        .execute(SessionStorageRequest::AcquireWriter {
            session: session.clone(),
        })
        .unwrap()
    else {
        panic!("fixture writer")
    };
    s.execute(SessionStorageRequest::Commit {
        commit: StorageCommit {
            lease: lease.clone(),
            operation_id: new_record_id(),
            expected: revision,
            timestamp_ms: 17,
            attribution: StorageRecordAttribution {
                execution_id: None,
                thread_id: Some(new_thread_id()),
                turn_id: None,
            },
            entry: JournalEntry::HistoryMutated(HistoryMutated {
                previous_revision: 0,
                new_revision: 1,
                mutation: HistoryMutationKind::Append,
                messages: vec![CanonicalMessage::text(
                    MessageRole::User,
                    "canonical fixture",
                )],
                compaction: None,
                tool_results: vec![],
            }),
        },
    })
    .unwrap();
    s.execute(SessionStorageRequest::ReleaseWriter { lease })
        .unwrap();
    let SessionStorageResponse::Snapshot { snapshot } = s
        .execute(SessionStorageRequest::OpenSnapshot { session })
        .unwrap()
    else {
        panic!("fixture snapshot")
    };
    (s, snapshot, d, work)
}

fn pack_hit(kind: BackendKind, pack: &Value) {
    let (s, src, _d, _work) = ready(kind);
    let digest = storage_value_etag(pack).unwrap();
    let key = format!("display-data-{digest}");
    let write = SessionStorageRequest::WriteCache {
        session: src.session.clone(),
        source: src.clone(),
        key: key.clone(),
        value: pack.clone(),
    };
    let got = s.execute(write.clone()).unwrap();
    write.validate_response(&got).unwrap();
    assert_eq!(
        got,
        SessionStorageResponse::CacheWritten { etag: Some(digest) }
    );
    let read = SessionStorageRequest::ReadCache {
        session: src.session.clone(),
        key,
        source: Some(src),
    };
    qualify(&format!("OWNER_NATIVE_{kind:?}"), || {
        let got = s.execute(read.clone()).unwrap();
        read.validate_response(&got).unwrap();
        assert_eq!(content(&got), pack);
        got
    });
}

fn size_cap(kind: BackendKind) {
    // Native request and typed consumer response caps are separate from SDK stdio.
    let (s, src, _d, _work) = ready(kind);
    let max = SESSION_STORAGE_MAX_CACHE_BYTES;
    let key = "cache-value-exact";
    let write = |bytes| SessionStorageRequest::WriteCache {
        session: src.session.clone(),
        source: src.clone(),
        key: key.into(),
        value: Value::String("x".repeat(bytes - 2)),
    };
    let a = s.execute(write(max)).unwrap();
    assert!(matches!(
        a,
        SessionStorageResponse::CacheWritten { etag: Some(_) }
    ));
    let rejected = s.execute(write(max + 1)).unwrap_err();
    assert_eq!(
        rejected.to_string(),
        "storage record page exceeds its byte budget"
    );
    let req = SessionStorageRequest::ReadCache {
        session: src.session.clone(),
        key: key.into(),
        source: Some(src),
    };
    let make = || {
        let got = s.execute(req.clone()).unwrap();
        assert_eq!(content(&got).as_str().unwrap().len(), max - 2);
        req.validate_response(&got).unwrap();
        got
    };
    let (old, n, old_refs, bytes, a) = now(make(), false);
    let (new, m, moved, moved_bytes, b) = now(make(), true);
    assert_eq!((n, m, old_refs, moved), (1, 1, 0, 1));
    assert_eq!((bytes, moved_bytes), (max - 2, max - 2));
    assert_eq!(a, b);
    assert_eq!(old.requested - new.requested, max - 2);
    let sent = SessionStorageResponse::Metadata {
        document: Some(StorageMetadataDocument {
            etag: "unchanged-consumer-cap".into(),
            value: Value::String("x".repeat(max - 1)),
        }),
    };
    assert!(req.validate_response(&sent).is_err());
    println!("CAP_{kind:?} exact={max} rejected={}", max + 1);
}

fn main() {
    check_shape();
    let mut args = std::env::args_os().skip(1);
    let raw = std::fs::read(args.next().unwrap()).unwrap();
    let pack: Value =
        serde_json::from_reader(std::fs::File::open(args.next().unwrap()).unwrap()).unwrap();
    assert_eq!(content(&parse(&raw)), &pack);
    qualify("OWNER_FRAME", || parse(&raw));
    for kind in [BackendKind::Jsonl, BackendKind::Sqlite] {
        pack_hit(kind, &pack);
        if args.len() > 0 {
            size_cap(kind);
        }
    }
}
