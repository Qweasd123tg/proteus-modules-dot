#![allow(dead_code, unused_imports)]
use anyhow::{Result, anyhow};
use base64::{Engine as _, engine::general_purpose::STANDARD};
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use std::{
    alloc::{GlobalAlloc, Layout, System},
    cell::Cell,
    fs,
    io::Write,
    path::{Path, PathBuf},
    sync::OnceLock,
};
use uuid::Uuid;
mod candidate;
mod io;
mod model;
mod stock;
mod value_hash;
use model::*;
type SessionId = Uuid;

#[derive(Clone, Copy, Debug, Default, Serialize)]
struct Life {
    ptr: usize,
    bytes: usize,
    freed: bool,
    observer_error: bool,
    live_bytes: usize,
    peak_bytes: usize,
    alloc_calls: usize,
    realloc_calls: usize,
    hash_live_bytes: Option<usize>,
    locator_live_bytes: Option<usize>,
    hash_live: Option<bool>,
    locator_live: Option<bool>,
    len: usize,
    steps: [u8; 8],
    step_count: usize,
    checks: usize,
    fail: usize,
}
thread_local! {
    static LIFE: Cell<Option<Life>> = const { Cell::new(None) };
}
fn edit(f: impl FnOnce(&mut Life)) {
    let _ = LIFE.try_with(|c| {
        if let Some(mut l) = c.get() {
            f(&mut l);
            c.set(Some(l));
        }
    });
}
fn event(code: u8) {
    edit(|l| {
        l.steps[l.step_count] = code;
        l.step_count += 1;
    });
}
fn watch(v: &Vec<u8>) {
    edit(|l| {
        assert_eq!(l.ptr, 0);
        l.ptr = v.as_ptr() as usize;
        l.len = v.len();
        l.bytes = v.capacity();
    });
}
struct Monitor;
#[global_allocator]
static MONITOR: Monitor = Monitor;
fn account(l: &mut Life, old: usize, new: usize) {
    if let Some(rest) = l.live_bytes.checked_sub(old) {
        l.live_bytes = rest + new;
        l.peak_bytes = l.peak_bytes.max(l.live_bytes);
    } else {
        l.observer_error = true;
    }
}
unsafe impl GlobalAlloc for Monitor {
    unsafe fn alloc(&self, l: Layout) -> *mut u8 {
        let p = unsafe { System.alloc(l) };
        if !p.is_null() {
            edit(|w| {
                w.alloc_calls += 1;
                account(w, 0, l.size());
            });
        }
        p
    }
    unsafe fn alloc_zeroed(&self, l: Layout) -> *mut u8 {
        let p = unsafe { System.alloc_zeroed(l) };
        if !p.is_null() {
            edit(|w| {
                w.alloc_calls += 1;
                account(w, 0, l.size());
            });
        }
        p
    }
    unsafe fn dealloc(&self, p: *mut u8, shape: Layout) {
        edit(|l| {
            if l.ptr == p as usize && !l.freed {
                l.observer_error |= l.bytes != shape.size();
                l.freed = true;
            }
            account(l, shape.size(), 0);
        });
        unsafe { System.dealloc(p, shape) };
    }
    unsafe fn realloc(&self, p: *mut u8, l: Layout, n: usize) -> *mut u8 {
        let q = unsafe { System.realloc(p, l, n) };
        if !q.is_null() {
            edit(|w| {
                w.observer_error |= !w.freed && w.ptr == p as usize;
                w.realloc_calls += 1;
                account(w, l.size(), n);
            });
        }
        q
    }
}

static DIR: OnceLock<PathBuf> = OnceLock::new();
fn checked_path(s: &SessionLocator) -> Result<PathBuf> {
    let mut failure = false;
    edit(|l| {
        l.checks += 1;
        failure = l.checks == l.fail;
        if l.checks == 2 {
            l.locator_live = Some(!l.freed);
            l.locator_live_bytes = Some(l.live_bytes);
        }
    });
    event(b'L');
    assert_eq!(*s, locator());
    if failure {
        return Err(anyhow!("injected checked_path rejection"));
    }
    Ok(DIR.get().unwrap().clone())
}
fn storage_value_etag(value: &Value) -> Result<String> {
    event(b'H');
    edit(|l| {
        l.hash_live = Some(!l.freed);
        l.hash_live_bytes = Some(l.live_bytes);
    });
    value_hash::storage_value_etag(value)
}
fn locator() -> SessionLocator {
    SessionLocator {
        session_id: Uuid::from_u128(0x1234),
        key: "fixture-component".into(),
    }
}
fn snapshot() -> StorageSnapshot {
    StorageSnapshot {
        session: locator(),
        snapshot_id: "read-handle".into(),
        revision: StorageRevision {
            session_seq: 44,
            history_revision: 25,
        },
        content_sha256: "a".repeat(64),
    }
}
fn nested(n: usize) -> Value {
    let mut obj = serde_json::Map::new();
    obj.insert("z".into(), json!(["🦀",{"n": 123,"s":"x".repeat(n)}]));
    obj.insert("a".into(), json!({"":"\n\t\u{0}","unicode":"Ё"}));
    Value::Object(obj)
}
fn tool(size: usize) -> Value {
    serde_json::to_value(AppToolState {
        call_id: "call-6".into(),
        name: "big".into(),
        status: "running".into(),
        args: nested(size),
        effective_args: Some(nested(2 * size)),
    })
    .unwrap()
}
fn prefix() -> Value {
    let n = 50_000;
    let mut hist = Vec::new();
    let mut msgs = Vec::new();
    let mut parts = Vec::new();
    for i in 0..n {
        let key = Uuid::from_u128(i as u128).into_bytes();
        let hash = ring::digest::digest(&ring::digest::SHA256, &key);
        hist.extend_from_slice(hash.as_ref());
        msgs.extend_from_slice(&key);
        parts.extend_from_slice(&Uuid::from_u128((n + i) as u128).into_bytes());
        parts.push(1);
    }
    assert_eq!(hist.len(), 32 * n);
    let body = Packed {
        format: 1,
        history: STANDARD.encode(hist),
        turns: String::new(),
        exchanges: String::new(),
        messages: STANDARD.encode(msgs),
        parts: STANDARD.encode(parts),
        calls: Vec::<String>::new(),
    };
    assert_eq!(
        body.history.len() + body.messages.len() + body.parts.len(),
        4_333_340
    );
    serde_json::to_value(body).unwrap()
}
fn response(arm: bool, key: &str, hint: Option<&StorageSnapshot>, fail: usize) -> (Vec<u8>, Life) {
    LIFE.with(|c| {
        assert!(
            c.replace(Some(Life {
                fail,
                ..Life::default()
            }))
            .is_none()
        )
    });
    let result = if arm {
        candidate::read_cache(locator(), key.into(), hint.cloned())
    } else {
        stock::read_cache(locator(), key.into(), hint.cloned())
    };
    // The response crosses the SDK boundary only after read_cache returns.
    // Build its verification wire outside the read scope, then re-enable
    // accounting for release of the owned return value.
    let before = LIFE.with(|c| c.replace(None).unwrap());
    let wire = record(&result);
    LIFE.with(|c| c.set(Some(before)));
    drop(result);
    let life = LIFE.with(|c| c.replace(None).unwrap());
    assert!(
        !life.observer_error && life.live_bytes == 0 && (life.bytes == 0 || life.freed),
        "{life:?}"
    );
    (wire, life)
}
fn record(r: &Result<SessionStorageResponse>) -> Vec<u8> {
    match r {
        Ok(r) => serde_json::to_vec(r).unwrap(),
        Err(e) => serde_json::to_vec(&json!({"error":e.to_string()})).unwrap(),
    }
}
fn assess(
    name: &str,
    key: &str,
    source: Option<&StorageSnapshot>,
    failure: usize,
    trace: &[u8],
    value: Option<&Value>,
) -> Value {
    let (ab, old) = response(false, key, source, failure);
    let (bb, new) = response(true, key, source, failure);
    assert_eq!(ab, bb, "wire parity {name}");
    assert_eq!(&old.steps[..old.step_count], trace, "stock steps {name}");
    assert_eq!(
        &new.steps[..new.step_count],
        trace,
        "candidate steps {name}"
    );
    assert_eq!(old.bytes, new.bytes);
    assert_eq!(old.len, new.len);
    assert_eq!(old.hash_live, trace.contains(&b'H').then_some(true));
    assert_eq!(new.hash_live, trace.contains(&b'H').then_some(false));
    assert_eq!(old.locator_live, (trace == b"LRHL").then_some(true));
    assert_eq!(new.locator_live, (trace == b"LRHL").then_some(false));
    if let (Some(a), Some(b)) = (old.hash_live_bytes, new.hash_live_bytes) {
        assert_eq!(a - b, old.bytes);
    }
    if let (Some(a), Some(b)) = (old.locator_live_bytes, new.locator_live_bytes) {
        assert_eq!(a - b, old.bytes);
    }
    assert_eq!(
        (old.alloc_calls, old.realloc_calls),
        (new.alloc_calls, new.realloc_calls)
    );
    assert!(new.peak_bytes <= old.peak_bytes);
    if failure != 0 {
        assert_eq!(
            serde_json::from_slice::<Value>(&ab).unwrap(),
            json!({"error":"injected checked_path rejection"})
        );
        assert!(value.is_none());
    } else {
        let SessionStorageResponse::Metadata { document } = serde_json::from_slice(&ab).unwrap();
        assert_eq!(document.as_ref().map(|d| &d.value), value);
        if let (Some(d), Some(expected)) = (document, value) {
            // Independently normalize lexically ordered object fields and use Ring.
            fn ordered(v: &Value) -> Value {
                match v {
                    Value::Object(m) => serde_json::to_value(
                        m.iter()
                            .map(|(k, v)| (k, ordered(v)))
                            .collect::<std::collections::BTreeMap<_, _>>(),
                    )
                    .unwrap(),
                    Value::Array(v) => Value::Array(v.iter().map(ordered).collect()),
                    _ => v.clone(),
                }
            }
            let etag = io::sha256_hex(&serde_json::to_vec(&ordered(expected)).unwrap());
            assert_eq!(d.etag, etag);
        }
    }
    json!({
        "trace": String::from_utf8(trace.to_vec()).unwrap(),
        "file_bytes": old.len,
        "raw_vec_capacity_bytes": old.bytes,
        "raw_live_at_hash": [old.hash_live, new.hash_live],
        "raw_live_at_final_locator": [old.locator_live, new.locator_live],
        "scope_peak_bytes": [old.peak_bytes, new.peak_bytes],
        "scope_alloc_calls": [old.alloc_calls, new.alloc_calls],
        "scope_realloc_calls": [old.realloc_calls, new.realloc_calls],
        "hash_entry_live_bytes": [old.hash_live_bytes,new.hash_live_bytes],
        "final_locator_live_bytes": [old.locator_live_bytes,new.locator_live_bytes],
        "wire_bytes":ab.len(), "wire_sha256":io::sha256_hex(&ab),
    })
}
fn main() {
    let dir = PathBuf::from(std::env::args_os().nth(1).unwrap());
    DIR.set(dir.clone()).unwrap();
    let mut out = serde_json::Map::new();
    let source = snapshot();
    let write =
        |key: &str, contents: &[u8]| fs::write(stock::file_path(&dir, key), contents).unwrap();
    let mut test = |name: &str,
                    key: &str,
                    s: Option<&StorageSnapshot>,
                    fault: usize,
                    trace: &[u8],
                    v: Option<&Value>| {
        out.insert(name.into(), assess(name, key, s, fault, trace, v));
    };
    let small = nested(28);
    let normal = stock::envelope(&source, &small);
    assert_eq!(normal, candidate::envelope(&source, &small));
    write("small", &normal);
    test("small-hit", "small", None, 0, b"LRHL", Some(&small));
    test(
        "source-exact",
        "small",
        Some(&source),
        0,
        b"LRHL",
        Some(&small),
    );
    let mut alternate = source.clone();
    alternate.snapshot_id = "different-handle".into();
    test(
        "snapshot-id-ignored",
        "small",
        Some(&alternate),
        0,
        b"LRHL",
        Some(&small),
    );
    let mut older = source.clone();
    older.revision.history_revision -= 1;
    test("revision-miss", "small", Some(&older), 0, b"LR", None);
    let mut foreign_hash = source.clone();
    foreign_hash.content_sha256 = "b".repeat(64);
    test("hash-miss", "small", Some(&foreign_hash), 0, b"LR", None);
    let mut foreign = source.clone();
    foreign.session.session_id = Uuid::from_u128(2);
    write("foreign", &stock::envelope(&foreign, &small));
    test("session-miss", "foreign", None, 0, b"LR", None);
    test("first-locator-failure", "small", None, 1, b"L", None);
    test("second-locator-failure", "small", None, 2, b"LRHL", None);
    test("missing-file", "absent", None, 0, b"LR", None);
    fs::create_dir(stock::file_path(&dir, "directory")).unwrap();
    test("non-regular", "directory", None, 0, b"LR", None);
    write("empty", b"");
    test("empty-file", "empty", None, 0, b"LR", None);
    write("truncated", &normal[..normal.len() - 1]);
    test("truncated-JSON", "truncated", None, 0, b"LR", None);
    let mut bad = normal.clone();
    bad.extend_from_slice(b"{}");
    write("badtrail", &bad);
    test("invalid-trailing-JSON", "badtrail", None, 0, b"LR", None);
    write("badutf", b"{\"source\":\"\xff\"}");
    test("malformed-UTF8", "badutf", None, 0, b"LR", None);
    let mut unknown: Value = serde_json::from_slice(&normal).unwrap();
    unknown["unexpected"] = Value::Null;
    write("unknown", &serde_json::to_vec(&unknown).unwrap());
    test("unknown-envelope-field", "unknown", None, 0, b"LR", None);
    let mut repeated = normal[..normal.len() - 1].to_vec();
    repeated.extend_from_slice(br#","value":false}"#);
    write("duplicate", &repeated);
    test(
        "duplicate-envelope-field",
        "duplicate",
        None,
        0,
        b"LR",
        None,
    );
    let unit = Value::Null;
    write("null", &stock::envelope(&source, &unit));
    test("null-content", "null", None, 0, b"LRHL", Some(&unit));
    let medium = tool(16 * 1024);
    write("medium", &stock::envelope(&source, &medium));
    test(
        "hinted-ordinary-tool",
        "medium",
        None,
        0,
        b"LRHL",
        Some(&medium),
    );
    let large = tool(1 << 20);
    let etag = value_hash::storage_value_etag(&large).unwrap();
    assert_eq!(
        etag,
        "71d6fec7008162511c63419d5f3254190290dd567b4dfe3ac730a7e1140abd17"
    );
    let key = format!("display-data-{etag}");
    assert_eq!(
        stock::file_path(&dir, &key).file_name().unwrap(),
        ".storage-cache-a9018743e70dbfcc5ec140814afb14d4e69a1991955705f31d7193737fd8d2ed.json"
    );
    write(&key, &stock::envelope(&source, &large));
    test("large-typed-tool", &key, None, 0, b"LRHL", Some(&large));
    test("large-final-locator-failure", &key, None, 2, b"LRHL", None);
    let prefix = prefix();
    write("display-view-v1-prefix", &stock::envelope(&source, &prefix));
    test(
        "large-prefix-shaped",
        "display-view-v1-prefix",
        Some(&alternate),
        0,
        b"LRHL",
        Some(&prefix),
    );
    let exact = stock::file_path(&dir, "cap");
    {
        let mut f = fs::File::create(&exact).unwrap();
        f.write_all(&normal).unwrap();
        let padding = 65 * 1024 * 1024 - normal.len();
        let block = [b' '; 64 * 1024];
        for _ in 0..padding / block.len() {
            f.write_all(&block).unwrap();
        }
        f.write_all(&block[..padding % block.len()]).unwrap();
    }
    test(
        "cap-valid-trailing-whitespace",
        "cap",
        None,
        0,
        b"LRHL",
        Some(&small),
    );
    fs::OpenOptions::new()
        .append(true)
        .open(exact)
        .unwrap()
        .write_all(b" ")
        .unwrap();
    test("over-cap-by-one", "cap", None, 0, b"LR", None);
    assert_eq!(out.len(), 23);
    println!("{}", serde_json::to_string(&out).unwrap());
}
