use super::*;
use crate::transport::ModuleTransport;
use proteus_contracts::contracts::{StorageBlobRef, StorageMetadataDocument};
use serde_json::json;
use std::{
    alloc::{GlobalAlloc, Layout, System},
    cell::RefCell,
    io::{self, Write},
    sync::{
        Arc, Mutex,
        atomic::{AtomicBool, AtomicUsize, Ordering},
        mpsc::sync_channel,
    },
    thread,
    time::Duration,
};

const N: usize = 256 * 1024 + 4;
const FLOOR: usize = 128 * 1024;
const ID: &str = "00000000-0000-0000-0000-000000000001";
const IS_CANDIDATE: bool = false; // Rewritten only for the candidate test overlay.
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
struct Owner {
    ptr: usize,
    size: usize,
    generation: usize,
}
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
struct Counts {
    calls: usize,
    requested: usize,
    live: usize,
    peak: usize,
}
#[derive(Default)]
struct Ledger {
    counts: Counts,
    slots: [Owner; 16],
}
thread_local! { static LEDGER: RefCell<Option<Ledger>> = const { RefCell::new(None) }; }
struct Tracked;
#[global_allocator]
static A: Tracked = Tracked;
fn update(old: usize, new: usize, size: usize) {
    let _ = LEDGER.try_with(|cell| {
        let mut cell = cell.borrow_mut();
        let Some(l) = cell.as_mut() else { return };
        if old != 0
            && let Some(slot) = l.slots.iter_mut().find(|slot| slot.ptr == old)
        {
            l.counts.live -= slot.size;
            *slot = Owner::default();
        }
        if new != 0 && size >= FLOOR {
            l.counts.calls += 1;
            l.counts.requested += size;
            l.counts.live += size;
            l.counts.peak = l.counts.peak.max(l.counts.live);
            let slot = l.slots.iter_mut().find(|s| s.ptr == 0).unwrap();
            *slot = Owner {
                ptr: new,
                size,
                generation: l.counts.calls,
            };
        }
    });
}
unsafe impl GlobalAlloc for Tracked {
    unsafe fn alloc(&self, lay: Layout) -> *mut u8 {
        let p = unsafe { System.alloc(lay) };
        update(0, p as usize, lay.size());
        p
    }
    unsafe fn alloc_zeroed(&self, lay: Layout) -> *mut u8 {
        let p = unsafe { System.alloc_zeroed(lay) };
        update(0, p as usize, lay.size());
        p
    }
    unsafe fn dealloc(&self, p: *mut u8, lay: Layout) {
        update(p as usize, 0, 0);
        unsafe { System.dealloc(p, lay) }
    }
    unsafe fn realloc(&self, p: *mut u8, lay: Layout, size: usize) -> *mut u8 {
        let new = unsafe { System.realloc(p, lay, size) };
        if !new.is_null() {
            update(p as usize, new as usize, size);
        }
        new
    }
}
fn measure() {
    LEDGER.with(|l| assert!(l.replace(Some(Ledger::default())).is_none()));
}
fn counts() -> Counts {
    LEDGER.with(|l| l.borrow().as_ref().unwrap().counts)
}
fn stop() -> Counts {
    LEDGER.with(|l| l.replace(None).unwrap().counts)
}
fn owner(value: &str) -> Option<Owner> {
    LEDGER.with(|l| {
        l.borrow().as_ref().and_then(|l| {
            l.slots
                .iter()
                .find(|s| s.ptr == value.as_ptr() as usize)
                .copied()
        })
    })
}

#[derive(Clone, Copy, Debug)]
enum Reply {
    Blob(usize, usize),
    Metadata,
    Done,
    Fail,
}
struct Probe {
    calls: AtomicUsize,
    produced: Mutex<Owner>,
    reply: Reply,
}
fn blob() -> StorageBlobRef {
    StorageBlobRef {
        sha256: "ab".repeat(32),
        bytes: ((N / 4) * 3) as u64,
    }
}
fn payload(n: usize, cap: usize) -> String {
    let mut b = Vec::with_capacity(cap);
    b.resize(n, b'A');
    let s = String::from_utf8(b).unwrap();
    assert_eq!(s.capacity(), cap);
    s
}
impl SessionStorageModule for Probe {
    fn supports_display_projection(&self) -> bool {
        true
    }
    fn execute(&self, _: SessionStorageRequest) -> Result<SessionStorageResponse> {
        self.calls.fetch_add(1, Ordering::SeqCst);
        let remember = |s: &str| {
            if let Some(id) = owner(s) {
                *self.produced.lock().unwrap() = id;
            }
        };
        match self.reply {
            Reply::Blob(n, cap) => {
                let data_base64 = payload(n, cap);
                remember(&data_base64);
                Ok(SessionStorageResponse::BlobData {
                    blob: blob(),
                    data_base64,
                })
            }
            Reply::Metadata => {
                let data = payload(N, N);
                remember(&data);
                Ok(SessionStorageResponse::Metadata {
                    document: Some(StorageMetadataDocument {
                        etag: "etag".into(),
                        value: Value::String(data),
                    }),
                })
            }
            Reply::Done => Ok(SessionStorageResponse::Done),
            Reply::Fail => bail!("provider failure"),
        }
    }
}
fn export(reply: Reply, negotiated: bool) -> SessionStorageExport<Probe> {
    let binding = ProcessComponentExportInitialize::new(
        "session_storage",
        "test",
        "v2",
        ProcessModuleComposition::SelectOne,
        Value::Null,
        if negotiated {
            vec![SESSION_STORAGE_DISPLAY_PROJECTION_FEATURE]
        } else {
            vec![]
        },
    );
    SessionStorageExport::new(
        binding,
        Probe {
            calls: AtomicUsize::new(0),
            produced: Mutex::new(Owner::default()),
            reply,
        },
    )
    .unwrap()
}
fn host(transport: Arc<ModuleTransport>) -> HostBridge {
    HostBridge::new(transport, "h:1:1".into(), Arc::new(AtomicBool::new(false)))
}
fn session() -> Value {
    json!({"session_id":ID,"key":"test"})
}
fn params(kind: &str) -> Value {
    let session = session();
    match kind {
        "read_blob" => json!({"operation":kind,"session":session,"blob":blob()}),
        "read_blob_by_hash" => {
            json!({"operation":kind,"session":session,"sha256":blob().sha256,"max_bytes":blob().bytes})
        }
        "put_blob" => {
            json!({"operation":kind,"lease":{"session":session,"token":ID,"generation":ID},"operation_id":ID,
            "data_base64":"AAAA","expected":blob()})
        }
        "read_cache" => json!({"operation":kind,"session":session,"key":"test","source":null}),
        "read_metadata" => json!({"operation":kind,"session":session,"key":"test"}),
        "open_display_snapshot" => json!({"operation":kind,"session":session}),
        _ => unreachable!(),
    }
}
#[test]
fn r277_blob_ownership() {
    let h = host(Arc::new(ModuleTransport::new(
        1,
        io::sink(),
        8 * 1024 * 1024,
    )));
    for (op, reply, n, cap, slot) in [
        ("read_blob", Reply::Blob(N, N), N, N, "/data_base64"),
        ("read_blob_by_hash", Reply::Blob(N, N), N, N, "/data_base64"),
        ("read_blob", Reply::Blob(N, N + 1), N, N + 1, "/data_base64"),
        (
            "read_blob_by_hash",
            Reply::Blob(N, 8 * N),
            N,
            8 * N,
            "/data_base64",
        ),
        (
            "read_blob_by_hash",
            Reply::Blob(4, 8 * N),
            4,
            8 * N,
            "/data_base64",
        ),
        ("read_blob", Reply::Blob(0, 8 * N), 0, 8 * N, "/data_base64"),
        ("put_blob", Reply::Blob(N, N), N, N, "/data_base64"),
        ("read_cache", Reply::Blob(N, N), N, N, "/data_base64"),
        ("read_metadata", Reply::Metadata, N, N, "/document/value"),
    ] {
        for held in [1, 4] {
            let e = export(reply, false);
            let todo = (0..held).map(|_| params(op)).collect::<Vec<_>>();
            let donated = IS_CANDIDATE && op.starts_with("read_blob") && n == cap;
            let mut results: [Option<Value>; 4] = std::array::from_fn(|_| None);
            measure();
            for (i, param) in todo.into_iter().enumerate() {
                let value = e
                    .invoke(PROCESS_SESSION_STORAGE_EXECUTE_METHOD, param, &h)
                    .unwrap();
                let data = value.pointer(slot).unwrap().as_str().unwrap();
                assert_eq!(data.len(), n);
                let input = *e.storage.produced.lock().unwrap();
                assert_eq!(input.size, cap);
                let output = owner(data);
                if n >= FLOOR {
                    let output = output.unwrap();
                    assert_eq!(output.size, n);
                    assert_eq!(input.generation == output.generation, donated);
                    if donated {
                        assert_eq!(input, output);
                    }
                } else {
                    assert!(output.is_none());
                }
                results[i] = Some(value);
            }
            let c = counts();
            let copies = usize::from(n >= FLOOR && !donated);
            let retained = if n >= FLOOR { n * held } else { 0 };
            assert_eq!(c.calls, held * (1 + copies));
            assert_eq!(c.requested, held * (cap + copies * n));
            assert_eq!(c.live, retained);
            assert_eq!(
                c.peak,
                if copies > 0 {
                    (held - 1) * n + cap + n
                } else {
                    (held - 1) * (if n >= FLOOR { n } else { 0 }) + cap
                }
            );
            assert_eq!(e.storage.calls.load(Ordering::SeqCst), held);
            drop(results);
            assert_eq!(stop().live, 0);
            println!(
                "R277_OWN {op} n={n} cap={cap} held={held} calls={} requested={} live={} peak={} donated={donated}",
                c.calls, c.requested, c.live, c.peak
            );
        }
    }
}

#[test]
fn r277_blob_exact_values_and_existing_errors() {
    let h = host(Arc::new(ModuleTransport::new(
        1,
        io::sink(),
        8 * 1024 * 1024,
    )));
    for op in ["read_blob", "read_blob_by_hash", "put_blob", "read_cache"] {
        for (n, cap) in [(0, 0), (4, 4), (8, 9), (N, N)] {
            let e = export(Reply::Blob(n, cap), false);
            let value = e.invoke("execute", params(op), &h).unwrap();
            let reference = serde_json::to_value(SessionStorageResponse::BlobData {
                blob: blob(),
                data_base64: payload(n, n),
            })
            .unwrap();
            assert_eq!(
                serde_json::to_vec(&value).unwrap(),
                serde_json::to_vec(&reference).unwrap()
            );
            if op.starts_with("read_blob") {
                let request: SessionStorageRequest = serde_json::from_value(params(op)).unwrap();
                let response: SessionStorageResponse = serde_json::from_value(value).unwrap();
                request.validate_response(&response).unwrap();
            }
            assert_eq!(e.storage.calls.load(Ordering::SeqCst), 1);
        }
    }
    let mut bad = params("read_blob_by_hash");
    bad["sha256"] = json!("bad");
    let e = export(Reply::Done, false);
    for (method, v, expect) in [
        ("unknown", Value::Null, "unsupported session storage method"),
        ("execute", Value::Null, "invalid type"),
        ("execute", bad, "invalid storage blob digest"),
        (
            "execute",
            params("open_display_snapshot"),
            "display projection was not negotiated",
        ),
    ] {
        assert!(
            e.invoke(method, v, &h)
                .unwrap_err()
                .to_string()
                .contains(expect)
        );
    }
    assert_eq!(e.storage.calls.load(Ordering::SeqCst), 0);
    let v = e.invoke("execute", params("read_blob"), &h).unwrap();
    assert_eq!(
        v,
        serde_json::to_value(SessionStorageResponse::Done).unwrap(),
        "do not add response validation"
    );
    assert_eq!(e.storage.calls.load(Ordering::SeqCst), 1);
    let e = export(Reply::Fail, false);
    assert_eq!(
        e.invoke("execute", params("read_blob_by_hash"), &h)
            .unwrap_err()
            .to_string(),
        "provider failure"
    );
    assert_eq!(e.storage.calls.load(Ordering::SeqCst), 1);
}

struct PausedFlush {
    observed: std::sync::mpsc::SyncSender<Counts>,
    resume: std::sync::mpsc::Receiver<()>,
}
impl Write for PausedFlush {
    fn write(&mut self, p: &[u8]) -> io::Result<usize> {
        Ok(p.len())
    }
    fn flush(&mut self) -> io::Result<()> {
        self.observed.send(counts()).unwrap();
        self.resume.recv_timeout(Duration::from_secs(5)).unwrap();
        Ok(())
    }
}
#[test]
fn r277_blob_transport_flush_remains_compact() {
    let (send, receive) = sync_channel(0);
    let (unblock, blocked) = sync_channel(0);
    let t = thread::spawn(move || {
        let transport = Arc::new(ModuleTransport::new(
            1,
            PausedFlush {
                observed: send,
                resume: blocked,
            },
            8 * 1024 * 1024,
        ));
        let h = host(transport.clone());
        let e = export(Reply::Blob(N, N), false);
        let request = params("read_blob");
        measure();
        let result = e.invoke("execute", request, &h).unwrap();
        let expected = counts();
        transport.write(&result).unwrap();
        assert_eq!(
            counts(),
            expected,
            "count, write and flush allocate no secondary payload"
        );
        assert_eq!(e.storage.calls.load(Ordering::SeqCst), 1);
        drop(result);
        assert_eq!(stop().live, 0);
    });
    let paused = receive.recv_timeout(Duration::from_secs(5)).unwrap();
    unblock.send(()).unwrap();
    t.join().unwrap();
    assert_eq!(paused.live, N);
    assert_eq!(paused.peak, if IS_CANDIDATE { N } else { 2 * N });
    assert_eq!(paused.calls, if IS_CANDIDATE { 1 } else { 2 });
    println!(
        "R277_PAUSED calls={} peak={} held={}",
        paused.calls, paused.peak, paused.live
    );
}
