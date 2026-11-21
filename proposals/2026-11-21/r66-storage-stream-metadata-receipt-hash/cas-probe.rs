use super::*;
use std::{
    alloc::{GlobalAlloc, Layout, System},
    cell::Cell,
    hint::black_box,
};

struct ScopedAllocator;
#[global_allocator]
static ALLOCATOR: ScopedAllocator = ScopedAllocator;

thread_local! {
    static COUNTS: Cell<Option<(usize, usize)>> = const { Cell::new(None) };
}

fn count(bytes: usize) {
    // Rust may destroy TLS while the surrounding test thread is winding down.
    let _ = COUNTS.try_with(|counts| {
        if let Some((calls, requested)) = counts.get() {
            counts.set(Some((calls + 1, requested + bytes)));
        }
    });
}

unsafe impl GlobalAlloc for ScopedAllocator {
    unsafe fn alloc(&self, layout: Layout) -> *mut u8 {
        let pointer = unsafe { System.alloc(layout) };
        count(layout.size());
        pointer
    }
    unsafe fn alloc_zeroed(&self, layout: Layout) -> *mut u8 {
        let pointer = unsafe { System.alloc_zeroed(layout) };
        count(layout.size());
        pointer
    }
    unsafe fn dealloc(&self, pointer: *mut u8, layout: Layout) {
        unsafe { System.dealloc(pointer, layout) };
    }
    unsafe fn realloc(&self, pointer: *mut u8, layout: Layout, size: usize) -> *mut u8 {
        let result = unsafe { System.realloc(pointer, layout, size) };
        count(size);
        result
    }
}

fn count_scope<T>(f: impl FnOnce() -> T) -> (T, (usize, usize)) {
    COUNTS.with(|counts| {
        assert!(counts.get().is_none());
        counts.set(Some((0, 0)));
        let result = f();
        (result, counts.replace(None).unwrap())
    })
}

fn files(dir: &Path) -> (Vec<u8>, Vec<(std::ffi::OsString, Vec<u8>)>) {
    let ledger = std::fs::read(dir.join(FILE)).unwrap();
    let mut objects = std::fs::read_dir(dir.join(".metadata-objects"))
        .into_iter()
        .flatten()
        .map(|entry| {
            let entry = entry.unwrap();
            (entry.file_name(), std::fs::read(entry.path()).unwrap())
        })
        .collect::<Vec<_>>();
    objects.sort();
    (ledger, objects)
}

#[test]
fn r66_hash_and_real_cas_allocation_pairs() {
    let configuration = serde_json::json!({
        "model":"test/default",
        "reasoning":{"enabled":true,"effort":"medium"},
        "title":"Résumé / draft\t\u{2223}",
    });
    let entries = (0..128)
        .map(|i| {
            serde_json::json!({
                "id": i,
                "active": i % 5 != 0,
                "text": "Row text, quote: \"; unicode: Ёж 🦀. ".repeat(135)
            })
        })
        .collect::<Vec<_>>();
    let imported = serde_json::json!({"description":"synthetic settings", "entries":entries});
    assert!(serde_json::to_vec(&imported).unwrap().len() <= SESSION_STORAGE_MAX_METADATA_BYTES);
    let key = "settings.imported.json".to_owned();
    let expected: Option<String> = None;
    let mut oracle = None;

    for (label, value) in [
        ("deletion", None),
        ("selection", Some(configuration)),
        ("bulk", Some(imported)),
    ] {
        let request = (&key, &expected, &value);
        let bytes = serde_json::to_vec(&request).unwrap();
        let legacy_receipt = sha256_hex(&bytes);
        let mut samples = [vec![], vec![]];
        oracle.take();
        for old in [true, false, false, true] {
            let (digest, (hash_calls, hash_bytes)) = count_scope(|| {
                let request = black_box(request);
                if old {
                    Ok(sha256_hex(&serde_json::to_vec(&request)?))
                } else {
                    hash_request(&request)
                }
            });
            let hash = digest.unwrap();
            assert_eq!(hash, legacy_receipt);

            let dir = tempfile::tempdir().unwrap();
            let inspect = if old {
                legacy_compare_exchange
            } else {
                compare_exchange
            };
            let op = Uuid::from_u128(789);
            let key_arg = key.clone();
            let value_arg = value.clone();
            let (written, initial) =
                count_scope(|| inspect(dir.path(), op, key_arg, None, value_arg));
            let written = written.unwrap();
            let key_arg = key.clone();
            let value_arg = value.clone();
            let (retried, replay) =
                count_scope(|| inspect(dir.path(), op, key_arg, None, value_arg));
            let retried = retried.unwrap();
            assert_eq!(
                serde_json::to_vec(&written).unwrap(),
                serde_json::to_vec(&retried).unwrap(),
            );

            let state = files(dir.path());
            let ledger: serde_json::Value = serde_json::from_slice(&state.0).unwrap();
            assert_eq!(
                ledger["receipts"][op.to_string()]["request_sha256"],
                legacy_receipt
            );
            let outcome = (state, serde_json::to_vec(&written).unwrap());
            if let Some(saved) = &oracle {
                assert_eq!(&outcome, saved);
            } else {
                oracle = Some(outcome);
            }
            let edge = inspect(
                dir.path(),
                op,
                key.clone(),
                Some("wrong etag".into()),
                value.clone(),
            )
            .unwrap_err();
            assert_eq!(
                edge.to_string(),
                "metadata operation id conflicts with earlier content"
            );
            let edge = inspect(
                dir.path(),
                Uuid::from_u128(890),
                key.clone(),
                Some("wrong etag".into()),
                value.clone(),
            )
            .unwrap_err();
            assert_eq!(edge.to_string(), "metadata etag conflict");
            assert_eq!(files(dir.path()), oracle.as_ref().unwrap().0);

            println!(
                "R66 {label} old={old} tuple_bytes={} hash_calls={} hash_requested={} cas_calls={} cas_requested={} retry_calls={} retry_requested={} receipt={hash}",
                bytes.len(),
                hash_calls,
                hash_bytes,
                initial.0,
                initial.1,
                replay.0,
                replay.1
            );
            samples[usize::from(old)].push((hash_calls, hash_bytes, initial, replay));
        }
        for (new, old) in samples[0].iter().zip(&samples[1]) {
            assert!(new.0 < old.0 && new.1 < old.1);
            assert!(new.2.0 < old.2.0 && new.2.1 < old.2.1);
            assert!(new.3.0 < old.3.0 && new.3.1 < old.3.1);
        }
    }
}
