use super::*;
use base64::{Engine, engine::general_purpose::STANDARD};
use std::alloc::{GlobalAlloc, Layout, System};
use std::cell::Cell;
use uuid::Uuid;

struct Counting;
#[global_allocator]
static ALLOC: Counting = Counting;
thread_local! {
    static STATS: Cell<Option<(usize, usize)>> = const { Cell::new(None) };
}

fn note(n: usize) {
    let _ = STATS.try_with(|slot| {
        if let Some((calls, bytes)) = slot.get() {
            slot.set(Some((calls + 1, bytes + n)));
        }
    });
}
unsafe impl GlobalAlloc for Counting {
    unsafe fn alloc(&self, layout: Layout) -> *mut u8 {
        note(layout.size());
        unsafe { System.alloc(layout) }
    }
    unsafe fn alloc_zeroed(&self, layout: Layout) -> *mut u8 {
        note(layout.size());
        unsafe { System.alloc_zeroed(layout) }
    }
    unsafe fn realloc(&self, p: *mut u8, layout: Layout, n: usize) -> *mut u8 {
        note(n);
        unsafe { System.realloc(p, layout, n) }
    }
    unsafe fn dealloc(&self, p: *mut u8, layout: Layout) {
        unsafe { System.dealloc(p, layout) }
    }
}

#[test]
fn measure_put_blob_and_check_durable_results() {
    for kind in backends() {
        for size in [0, 64, 16_385, 256 * 1024, 4 * 1024 * 1024] {
            let bytes: Vec<_> = (0..size).map(|i| (i % 251) as u8).collect();
            let blob = StorageBlobRef {
                sha256: crate::io::sha256_hex(&bytes),
                bytes: size as u64,
            };
            for pass in 0..4 {
                let f = Fixture::new(kind);
                let dir = f.descriptor.local_path.as_ref().unwrap();
                let ledger = dir.join(".storage-metadata.json");
                let path = dir.join("images").join(&blob.sha256);
                let mut first_receipt = Vec::new();
                for (name, op) in [("create", 1), ("replay", 1), ("reuse", 2)] {
                    let request = SessionStorageRequest::PutBlob {
                        lease: f.lease.clone(),
                        operation_id: Uuid::from_u128(op),
                        data_base64: STANDARD.encode(&bytes),
                        expected: blob.clone(),
                    };
                    STATS.set(Some((0, 0)));
                    let answer = f.service.execute(request);
                    let (calls, allocated) = STATS.replace(None).unwrap();
                    assert_eq!(
                        answer.unwrap(),
                        SessionStorageResponse::Blob {
                            blob: blob.clone(),
                            local_path: Some(path.clone())
                        }
                    );
                    assert_eq!(std::fs::read(&path).unwrap(), bytes);
                    let receipt = std::fs::read(&ledger).unwrap();
                    match name {
                        "create" => first_receipt = receipt.clone(),
                        "replay" => assert_eq!(first_receipt, receipt),
                        "reuse" => assert_ne!(first_receipt, receipt),
                        _ => unreachable!(),
                    }
                    if pass != 0 {
                        println!(
                            "PUT,{kind:?},{size},{name},{pass},{calls},{allocated},{},{}",
                            blob.sha256,
                            crate::io::sha256_hex(&receipt)
                        );
                    }
                }
                // Persisted payload and expected identity survive closing and reopening the service.
                let session = f.descriptor.session.clone();
                drop(f.service);
                assert_eq!(
                    StorageService::new(kind)
                        .execute(SessionStorageRequest::ReadBlob {
                            session,
                            blob: blob.clone()
                        })
                        .unwrap(),
                    SessionStorageResponse::BlobData {
                        blob: blob.clone(),
                        data_base64: STANDARD.encode(&bytes)
                    }
                );
            }
        }
    }
}

// The full operation above also covers both empty and multi-buffer files.
// Exercise corrupted storage and error precedence against each unmodified service.
#[test]
fn check_bad_put_blob_targets() {
    let f = Fixture::new(BackendKind::Jsonl);
    let dir = f.descriptor.local_path.as_ref().unwrap();
    let ledger = dir.join(".storage-metadata.json");
    let input = b"xyz";
    let blob = StorageBlobRef {
        sha256: crate::io::sha256_hex(input),
        bytes: 3,
    };
    let path = dir.join("images").join(&blob.sha256);
    let put = |op| {
        f.service.execute(SessionStorageRequest::PutBlob {
            lease: f.lease.clone(),
            operation_id: Uuid::from_u128(op),
            data_base64: STANDARD.encode(input),
            expected: blob.clone(),
        })
    };
    put(1).unwrap();
    let receipt = std::fs::read(&ledger).unwrap();
    for (case, content, expect) in [
        ("empty", &b""[..], "content-addressed blob collision"),
        ("short", &b"xy"[..], "content-addressed blob collision"),
        ("different", &b"ayz"[..], "content-addressed blob collision"),
        ("trailing", &b"xyz!"[..], "content-addressed blob collision"),
    ] {
        std::fs::write(&path, content).unwrap();
        assert_eq!(put(2).unwrap_err().to_string(), expect, "{case}");
        assert_eq!(std::fs::read(&ledger).unwrap(), receipt);
    }
    // Sparse file: mismatched content *and* oversized; the size error takes priority.
    std::fs::OpenOptions::new()
        .write(true)
        .open(&path)
        .unwrap()
        .set_len(SESSION_STORAGE_MAX_BLOB_BYTES + 1)
        .unwrap();
    assert_eq!(
        put(2).unwrap_err().to_string(),
        format!(
            "storage object exceeds {} bytes",
            SESSION_STORAGE_MAX_BLOB_BYTES
        )
    );
    assert_eq!(std::fs::read(&ledger).unwrap(), receipt);
    #[cfg(unix)]
    {
        std::fs::remove_file(&path).unwrap();
        std::fs::create_dir(&path).unwrap();
        assert_eq!(
            put(2).unwrap_err().to_string(),
            "storage object must be a regular file"
        );
        assert_eq!(std::fs::read(&ledger).unwrap(), receipt);
    }
}
