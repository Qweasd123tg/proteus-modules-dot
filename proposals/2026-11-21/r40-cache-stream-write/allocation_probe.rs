use super::*;
use serde_json::{Value, json};
use std::{
    alloc::{GlobalAlloc, Layout, System},
    cell::Cell,
    time::Instant,
};

struct Counting;
#[global_allocator]
static ALLOC: Counting = Counting;
#[derive(Clone, Copy, Default)]
struct Counts {
    calls: usize,
    requested: usize,
    live_delta: isize,
    peak_delta: isize,
}
thread_local! { static COUNTS: Cell<Option<Counts>> = const {Cell::new(None)}; }
fn note(old: usize, new: usize, request: bool) {
    let _ = COUNTS.try_with(|s| {
        if let Some(mut c) = s.get() {
            c.calls += usize::from(request);
            c.requested += new;
            c.live_delta += new as isize - old as isize;
            c.peak_delta = c.peak_delta.max(c.live_delta);
            s.set(Some(c));
        }
    });
}
unsafe impl GlobalAlloc for Counting {
    unsafe fn alloc(&self, l: Layout) -> *mut u8 {
        note(0, l.size(), true);
        unsafe { System.alloc(l) }
    }
    unsafe fn alloc_zeroed(&self, l: Layout) -> *mut u8 {
        note(0, l.size(), true);
        unsafe { System.alloc_zeroed(l) }
    }
    unsafe fn realloc(&self, p: *mut u8, l: Layout, n: usize) -> *mut u8 {
        note(l.size(), n, true);
        unsafe { System.realloc(p, l, n) }
    }
    unsafe fn dealloc(&self, p: *mut u8, l: Layout) {
        note(l.size(), 0, false);
        unsafe { System.dealloc(p, l) }
    }
}
fn fixture(name: &str) -> Value {
    match name {
        "tiny" => json!({"label":"short"}),
        "256KiB" => json!({"body":"x".repeat(256*1024)}),
        "4MiB" => json!({"body":"x".repeat(4*1024*1024)}),
        "structured" => json!(
            (0..4096)
                .map(|i| json!({"seq":i,"text":"Привет\n\"","tags":[null,true,2.5]}))
                .collect::<Vec<_>>()
        ),
        _ => unreachable!(),
    }
}
#[test]
fn measure_write_cache() {
    let key = "display.v1";
    for kind in backends() {
        let mut f = Fixture::new(kind);
        f.append(vec![text("persistent source")]);
        let source = f.snapshot();
        let dir = f.descriptor.local_path.as_ref().unwrap();
        let path = dir.join(format!(
            ".storage-cache-{}.json",
            crate::io::sha256_hex(key.as_bytes())
        ));
        for name in ["tiny", "256KiB", "structured", "4MiB"] {
            let value = fixture(name);
            let etag = storage_value_etag(&value).unwrap();
            let expected = format!(
                r#"{{"source":{},"value":{}}}"#,
                serde_json::to_string(&source).unwrap(),
                value
            );
            for run in 0..4 {
                let request = SessionStorageRequest::WriteCache {
                    session: source.session.clone(),
                    key: key.into(),
                    source: source.clone(),
                    value: value.clone(),
                };
                let start = Instant::now();
                COUNTS.set(Some(Counts::default()));
                let answer = f.service.execute(request);
                let c = COUNTS.replace(None).unwrap();
                let micros = start.elapsed().as_micros();
                assert_eq!(
                    answer.unwrap(),
                    SessionStorageResponse::CacheWritten {
                        etag: Some(etag.clone())
                    }
                );
                assert_eq!(std::fs::read(&path).unwrap(), expected.as_bytes());
                if run > 0 {
                    println!(
                        "CACHE,{kind:?},{name},{run},{},{},{},{},{micros},{etag}",
                        expected.len(),
                        c.calls,
                        c.requested,
                        c.peak_delta
                    );
                }
            }
            assert_eq!(
                StorageService::new(kind)
                    .execute(SessionStorageRequest::ReadCache {
                        session: source.session.clone(),
                        source: Some(source.clone()),
                        key: key.into()
                    })
                    .unwrap(),
                SessionStorageResponse::Metadata {
                    document: Some(StorageMetadataDocument { value, etag })
                }
            );
        }
    }
}
#[test]
fn reject_oversized_escaped_envelope_before_touching_file() {
    for kind in backends() {
        let mut f = Fixture::new(kind);
        f.append(vec![text("previous cache")]);
        let mut source = f.snapshot();
        let key = "size-case";
        let value = json!({"v": 1});
        let req = |source: StorageSnapshot| SessionStorageRequest::WriteCache {
            session: source.session.clone(),
            source,
            key: key.into(),
            value: value.clone(),
        };
        f.service.execute(req(source.clone())).unwrap();
        let dir = f.descriptor.local_path.as_ref().unwrap();
        let path = dir.join(format!(
            ".storage-cache-{}.json",
            crate::io::sha256_hex(key.as_bytes())
        ));
        let previous = std::fs::read(&path).unwrap();
        // Each U+0000 becomes six JSON bytes; validation accepts nonblank opaque IDs.
        source.snapshot_id = "\0".repeat((65 * 1024 * 1024) / 6 + 1);
        assert_eq!(
            f.service.execute(req(source)).unwrap_err().to_string(),
            "cache value exceeds maximum"
        );
        assert_eq!(std::fs::read(&path).unwrap(), previous);
        assert!(
            !std::fs::read_dir(dir).unwrap().any(|e| e
                .unwrap()
                .file_name()
                .to_string_lossy()
                .ends_with(".tmp"))
        );
    }
}
