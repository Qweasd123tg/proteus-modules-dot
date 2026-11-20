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
        if let Some((a, b)) = slot.get() {
            slot.set(Some((a + 1, b + n as u64)));
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
    TOTAL.set(Some((0, 0)));
    let value = f();
    (value, TOTAL.replace(None).unwrap())
}

use crate::metadata::compare_exchange;
use crate::types::SESSION_STORAGE_MAX_METADATA_BYTES as MAX;
use serde_json::{Value, json};

#[test]
fn compare_metadata_allocations_and_persisted_bytes() {
    for size in [64, 65536, MAX] {
        for pass in 0..4 {
            let dir = tempfile::tempdir().unwrap();
            let value = Value::String("x".repeat(size - 2));
            let bytes = serde_json::to_vec(&value).unwrap();
            assert_eq!(bytes.len(), size);
            let key = "settings".to_owned();
            let create = Uuid::from_u128(1);
            let op = |id, expected, value| {
                compare_exchange(dir.path(), id, key.clone(), expected, value)
            };
            let input = value.clone();
            let (answer, (a, b)) = sample(|| op(create, None, Some(input)).unwrap().unwrap());
            let mut prefixed = create.as_bytes().to_vec();
            prefixed.extend_from_slice(&bytes);
            assert_eq!(answer.value, value);
            assert_eq!(answer.etag, crate::io::sha256_hex(&prefixed));
            let expected = answer.etag.clone();
            let hash = crate::io::sha256_hex(&bytes);
            let object = dir
                .path()
                .join(".metadata-objects")
                .join(format!("{hash}.json"));
            assert_eq!(std::fs::read(&object).unwrap(), bytes);
            let ledger_path = dir.path().join(".storage-metadata.json");
            let ledger = std::fs::read(&ledger_path).unwrap();
            let digest = crate::io::sha256_hex(&ledger);
            if pass > 0 {
                println!("CAS,create,{size},{pass},{a},{b},{hash},{digest}");
            }
            let input = value.clone();
            let (answer2, (a2, b2)) = sample(|| op(create, None, Some(input)).unwrap().unwrap());
            assert_eq!(answer2, answer);
            assert_eq!(std::fs::read(&ledger_path).unwrap(), ledger);
            if pass > 0 {
                println!("CAS,replay,{size},{pass},{a2},{b2},{hash},{digest}");
            }
            // A new op writing the same bytes checks the on-disk object for a collision.
            let input = value.clone();
            let (answer3, (a3, b3)) = sample(|| {
                op(Uuid::from_u128(2), Some(expected), Some(input))
                    .unwrap()
                    .unwrap()
            });
            assert_eq!(answer3.value, value);
            assert_ne!(answer3.etag, answer.etag);
            let ledger2 = std::fs::read(&ledger_path).unwrap();
            if pass > 0 {
                println!(
                    "CAS,same_object,{size},{pass},{a3},{b3},{hash},{}",
                    crate::io::sha256_hex(&ledger2)
                );
            }
            assert!(op(create, None, Some(json!("different"))).is_err());
            assert!(op(Uuid::from_u128(3), None, None).is_err());
            assert_eq!(std::fs::read(&ledger_path).unwrap(), ledger2);
            assert!(
                op(Uuid::from_u128(3), Some(answer3.etag), None)
                    .unwrap()
                    .is_none()
            );
            // Existing object is no longer referenced by the current document, so this
            // exercises the store collision check, not the hydrate check.
            std::fs::write(&object, "different bytes").unwrap();
            assert!(
                op(Uuid::from_u128(4), None, Some(value))
                    .unwrap_err()
                    .to_string()
                    .contains("metadata object collision")
            );
            assert!(
                op(create, None, Some(Value::String("x".repeat(size - 2))))
                    .unwrap_err()
                    .to_string()
                    .contains("metadata object hash mismatch")
            );
        }
    }
    let dir = tempfile::tempdir().unwrap();
    let e = compare_exchange(
        dir.path(),
        Uuid::from_u128(1),
        "k".into(),
        None,
        Some(Value::String("x".repeat(MAX - 1))),
    )
    .unwrap_err();
    assert!(e.to_string().contains("metadata document exceeds maximum"));
    assert!(dir.path().read_dir().unwrap().next().is_none());
}
