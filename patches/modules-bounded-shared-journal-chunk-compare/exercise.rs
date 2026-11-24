#![allow(dead_code)]
mod candidate;
mod io;
mod read_fault;
mod stock;
mod types;
mod diagnostics {
    pub(crate) fn decoded() {}
}

use anyhow::Result;
use serde_json::{Value, json};
use std::{
    alloc::{GlobalAlloc, Layout, System},
    cell::{Cell, RefCell},
    collections::{BTreeMap, BTreeSet},
    fs::{self, File, OpenOptions},
    io::{Error, ErrorKind, Read},
    os::unix::fs::symlink,
    path::Path,
    sync::atomic::{AtomicU64, Ordering::Relaxed},
};
use types::*;

#[derive(Clone, Copy, Debug, Default)]
struct Meter {
    live: usize,
    peak: usize,
    allocs: usize,
    reallocs: usize,
    regular_opens: usize,
    seen: usize,
}
thread_local! {
    static METER: Cell<Option<Meter>> = const { Cell::new(None) };
    static SAMPLES: RefCell<Vec<Meter>> = const { RefCell::new(Vec::new()) };
    static MUTATION: Cell<u8> = const { Cell::new(0) };
}
fn update(f: impl FnOnce(&mut Meter)) {
    let _ = METER.try_with(|m| {
        if let Some(mut r) = m.get() {
            f(&mut r);
            m.set(Some(r));
        }
    });
}
fn delta(sub: usize, add: usize, re: bool) {
    update(|m| {
        m.live = m.live.checked_sub(sub).unwrap() + add;
        m.peak = m.peak.max(m.live);
        if re {
            m.reallocs += 1;
        } else if sub == 0 {
            m.allocs += 1;
        }
    });
}
struct Count;
unsafe impl GlobalAlloc for Count {
    unsafe fn alloc(&self, l: Layout) -> *mut u8 {
        let p = unsafe { System.alloc(l) };
        if !p.is_null() {
            delta(0, l.size(), false);
        }
        p
    }
    unsafe fn alloc_zeroed(&self, l: Layout) -> *mut u8 {
        let p = unsafe { System.alloc_zeroed(l) };
        if !p.is_null() {
            delta(0, l.size(), false);
        }
        p
    }
    unsafe fn dealloc(&self, p: *mut u8, l: Layout) {
        delta(l.size(), 0, false);
        unsafe { System.dealloc(p, l) };
    }
    unsafe fn realloc(&self, p: *mut u8, l: Layout, s: usize) -> *mut u8 {
        let q = unsafe { System.realloc(p, l, s) };
        if !q.is_null() {
            delta(l.size(), s, true);
        }
        q
    }
}
#[global_allocator]
static ALLOC: Count = Count;

// Only affects temporary names for the fsync + rename path. The UUID never persists.
pub(crate) fn temp_uuid() -> uuid::Uuid {
    static NEXT: AtomicU64 = AtomicU64::new(1);
    uuid::Uuid::from_u128((0x7280_u128 << 112) | NEXT.fetch_add(1, Relaxed) as u128)
}
pub(crate) fn observe_open(path: &Path, _file: &File) {
    if METER.with(|m| m.get().is_none()) {
        return;
    }
    update(|s| s.regular_opens += 1);
    match MUTATION.with(|m| m.replace(0)) {
        0 => {}
        1 => fs::rename(path.with_extension("replacement"), path).unwrap(),
        2 => {
            let f = OpenOptions::new().write(true).open(path).unwrap();
            f.set_len(65_537).unwrap();
        }
        3 => {
            let f = OpenOptions::new().write(true).open(path).unwrap();
            f.set_len(20_356).unwrap();
        }
        _ => unreachable!(),
    }
}
fn start_meter() {
    assert!(METER.with(|m| m.replace(Some(Meter::default())).is_none()));
}
fn stop_meter() -> Meter {
    METER.with(|m| m.replace(None).unwrap())
}
fn put_meter(m: Meter) {
    SAMPLES.with(|s| s.borrow_mut().push(m));
}
fn sample() -> Vec<Meter> {
    SAMPLES.with(|s| s.take())
}
pub(crate) fn stock_read(path: &Path, max: usize, expected: &[u8]) -> Result<bool> {
    start_meter();
    let result = io::bounded_read(path, max);
    let output = match result {
        Ok(bytes) => {
            update(|s| s.seen = bytes.capacity());
            Ok(bytes == expected)
        }
        Err(e) => Err(e),
    };
    put_meter(stop_meter());
    output
}
pub(crate) fn candidate_eq(path: &Path, expected: &[u8], max: usize) -> Result<bool> {
    start_meter();
    let output = io::bounded_file_eq(path, expected, max);
    put_meter(stop_meter());
    output
}

const FIRST_HIT: &str = "63a22e93b51ac665f726035ea712e61115428cd6e84ece3554ee2b706012897a";
const ORDERED: bool = cfg!(feature = "preserve_order");
fn want_hash(n: usize) -> &'static str {
    match (ORDERED, n) {
        (false, 0) => "4778a7109e0d68b81ed73aa2c583f65a58d128d33d50f2230c435324f94130f4",
        (false, 1) => "92e9793fe6624d582b914dddc1f36224924572f2dfc3a3cbe3ed36f526ceb0f5",
        (true, 0) => "2bb60b5f8239ae079a30e9580131a82872811c5db82724da12d4696cbf3010c5",
        (true, 1) => "0f4fd905cd57d7832564c8bc7ed83f352f574e836f892e18d17c4d53baa452dc",
        _ => unreachable!(),
    }
}
fn id(n: u128) -> uuid::Uuid {
    uuid::Uuid::from_u128(0x00000000000040008000000000000000 | n)
}
fn payload(seed: u64) -> String {
    let mut state = seed;
    (0..1024 * 1024)
        .map(|_| {
            state ^= state << 13;
            state ^= state >> 7;
            state ^= state << 17;
            char::from(b'a' + (state % 26) as u8)
        })
        .collect()
}
fn records() -> (JournalRecord, JournalRecord) {
    let t = payload(7);
    (
        record(0, t.clone()),
        record(1, "new prefix".to_owned() + &t),
    )
}
fn record(n: u64, text: String) -> JournalRecord {
    JournalRecord {
        schema_version: JOURNAL_SCHEMA_VERSION,
        record_id: id(100 + n as u128),
        session_id: id(90),
        session_seq: n + 1,
        timestamp_ms: (10 + n) as i64,
        execution_id: None,
        thread_id: Some(id(91)),
        turn_id: None,
        entry: JournalEntry::HistoryMutated(HistoryMutated {
            previous_revision: n,
            new_revision: n + 1,
            mutation: HistoryMutationKind::Append,
            messages: vec![CanonicalMessage {
                id: id(1 + 2 * n as u128),
                role: MessageRole::User,
                phase: None,
                name: None,
                tool_call_id: None,
                metadata: Value::Null,
                parts: vec![CanonicalPart {
                    part_id: id(2 + 2 * n as u128),
                    provenance: PartProvenance::User,
                    scope: PartScope::Conversation,
                    payload: ContentPart::Text { text },
                }],
            }],
            compaction: None,
            tool_results: vec![],
        }),
    }
}
#[derive(Debug, PartialEq, Eq)]
struct DiskNode {
    kind: &'static str,
    bytes_or_link: Vec<u8>,
}
fn collect(root: &Path) -> BTreeMap<String, DiskNode> {
    fn recurse(root: &Path, path: &Path, result: &mut BTreeMap<String, DiskNode>) {
        for ent in fs::read_dir(path).unwrap() {
            let ent = ent.unwrap();
            let p = ent.path();
            let typ = ent.file_type().unwrap();
            let key = p.strip_prefix(root).unwrap().to_str().unwrap().to_owned();
            let (kind, bytes_or_link) = if typ.is_symlink() {
                (
                    "symlink",
                    fs::read_link(&p)
                        .unwrap()
                        .as_os_str()
                        .as_encoded_bytes()
                        .to_owned(),
                )
            } else if typ.is_dir() {
                recurse(root, &p, result);
                ("dir", vec![])
            } else {
                assert!(typ.is_file());
                ("file", fs::read(&p).unwrap())
            };
            result.insert(
                key,
                DiskNode {
                    kind,
                    bytes_or_link,
                },
            );
        }
    }
    let mut all = BTreeMap::new();
    recurse(root, root, &mut all);
    all
}
fn manifest(root: &Path, n: usize) -> (Value, Vec<u8>) {
    let raw = fs::read(root.join("blobs").join(format!("{}.json", want_hash(n)))).unwrap();
    let body = raw.strip_prefix(b"PROTEUS-SHARED-BLOB-1\n").unwrap();
    let m: Value = serde_json::from_slice(body).unwrap();
    assert_eq!(m["sha256"], want_hash(n));
    assert_eq!(m["bytes"], 1_048_941 + 10 * n);
    assert_eq!(m["chunks"].as_array().unwrap().len(), 30);
    (m, raw)
}
fn hashes(m: &Value) -> Vec<(&str, usize)> {
    m["chunks"]
        .as_array()
        .unwrap()
        .iter()
        .map(|v| {
            (
                v["sha256"].as_str().unwrap(),
                v["bytes"].as_u64().unwrap() as usize,
            )
        })
        .collect()
}
fn reconstruction(root: &Path, m: &Value) {
    let mut full = Vec::new();
    for (h, len) in hashes(m) {
        let b = fs::read(root.join("blobs/shared").join(format!("{h}.bin"))).unwrap();
        assert_eq!(b.len(), len);
        assert_eq!(io::sha256_hex(&b), h);
        full.extend_from_slice(&b);
    }
    assert_eq!(io::sha256_hex(&full), m["sha256"].as_str().unwrap());
}

#[derive(Clone, Copy)]
enum Side {
    Stock,
    Candidate,
}
struct Step {
    extent: u64,
    bytes: Vec<u8>,
    blobs: Vec<std::path::PathBuf>,
}
fn append(side: Side, root: &Path, record: &JournalRecord) -> Result<Step> {
    match side {
        Side::Stock => {
            let mut writer = stock::Jsonl::new();
            writer.recover(root, record.session_id)?;
            let a = writer.append(root, record)?;
            Ok(Step {
                extent: a.extent,
                bytes: a.bytes,
                blobs: a.blobs,
            })
        }
        Side::Candidate => {
            let mut writer = candidate::Jsonl::new();
            writer.recover(root, record.session_id)?;
            let a = writer.append(root, record)?;
            Ok(Step {
                extent: a.extent,
                bytes: a.bytes,
                blobs: a.blobs,
            })
        }
    }
}
fn decode(side: Side, root: &Path, expected: &JournalRecord, bytes: &[u8], external: bool) {
    let (actual, observed_external) = match side {
        Side::Stock => stock::codec::decode(root, expected.session_id, bytes),
        Side::Candidate => candidate::codec::decode(root, expected.session_id, bytes),
    }
    .unwrap();
    assert_eq!(expected, &actual);
    assert_eq!(external, observed_external);
}
fn refs_for(m: &Value, n: usize) -> Vec<std::path::PathBuf> {
    let mut list: Vec<_> = hashes(m)
        .into_iter()
        .map(|(h, _)| format!("shared/{h}.bin").into())
        .collect();
    list.push(format!("{}.json", want_hash(n)).into());
    list
}

struct Case {
    changed: &'static str,
    error: Option<&'static str>,
}
const COLLISION: &str = "shared blob collision";
const LIMIT: &str = "storage object exceeds 65536 bytes";
const NOTREGULAR: &str = "storage object must be a regular file";
const CASES: &[Case] = &[
    Case {
        changed: "equal",
        error: None,
    },
    Case {
        changed: "first",
        error: Some(COLLISION),
    },
    Case {
        changed: "middle",
        error: Some(COLLISION),
    },
    Case {
        changed: "last",
        error: Some(COLLISION),
    },
    Case {
        changed: "empty",
        error: Some(COLLISION),
    },
    Case {
        changed: "short-prefix",
        error: Some(COLLISION),
    },
    Case {
        changed: "long-prefix",
        error: Some(COLLISION),
    },
    Case {
        changed: "size-maximum-mismatch",
        error: Some(COLLISION),
    },
    Case {
        changed: "max-plus-one",
        error: Some(LIMIT),
    },
    Case {
        changed: "much-larger-mismatch",
        error: Some(LIMIT),
    },
    Case {
        changed: "directory",
        error: Some(NOTREGULAR),
    },
    Case {
        changed: "absent-is-new",
        error: None,
    },
    Case {
        changed: "regular-symlink",
        error: None,
    },
    Case {
        changed: "dangling-is-new",
        error: None,
    },
    Case {
        changed: "in-place-growth-after-open",
        error: Some(LIMIT),
    },
    Case {
        changed: "in-place-truncation-after-open",
        error: Some(COLLISION),
    },
    Case {
        changed: "pathname-replaced-after-open",
        error: None,
    },
];
fn alter(root: &Path, case: &str) -> u8 {
    let hit = root.join(format!("blobs/shared/{FIRST_HIT}.bin"));
    let mut b = fs::read(&hit).unwrap();
    let n = b.len();
    assert_eq!(n, 20_357);
    match case {
        "equal" => return 0,
        "first" => b[0] ^= 1,
        "middle" => b[n / 2] ^= 1,
        "last" => b[n - 1] ^= 1,
        "empty" => b.clear(),
        "short-prefix" => b.truncate(n - 1),
        "long-prefix" => b.push(0),
        "size-maximum-mismatch" => {
            b.resize(65_536, 0);
            b[0] ^= 1;
        }
        "max-plus-one" => b.resize(65_537, 0),
        "much-larger-mismatch" => {
            b.resize(190_000, 0);
            b[0] ^= 1;
        }
        "directory" => {
            fs::remove_file(&hit).unwrap();
            fs::create_dir(&hit).unwrap();
            return 0;
        }
        "absent-is-new" => {
            fs::remove_file(&hit).unwrap();
            return 0;
        }
        "regular-symlink" => {
            fs::rename(&hit, hit.with_file_name("original")).unwrap();
            symlink("original", &hit).unwrap();
            return 0;
        }
        "dangling-is-new" => {
            fs::remove_file(&hit).unwrap();
            symlink("absent", &hit).unwrap();
            return 0;
        }
        "in-place-growth-after-open" => return 2,
        "in-place-truncation-after-open" => return 3,
        "pathname-replaced-after-open" => {
            b[0] ^= 1;
            fs::write(hit.with_extension("replacement"), b).unwrap();
            return 1;
        }
        _ => unreachable!(),
    }
    fs::write(hit, b).unwrap();
    0
}
fn totals(samples: &[Meter]) -> Value {
    json!({
        "comparisons": samples.len(),
        "regular_opens": samples.iter().map(|s|s.regular_opens).sum::<usize>(),
        "allocs": samples.iter().map(|s|s.allocs).sum::<usize>(),
        "reallocs": samples.iter().map(|s|s.reallocs).sum::<usize>(),
        "max_requested_live": samples.iter().map(|s|s.peak).max().unwrap_or(0),
        "max_terminal_vec_capacity": samples.iter().map(|s|s.seen).max().unwrap_or(0),
        "sum_terminal_vec_capacity_not_simultaneous": samples.iter().map(|s|s.seen).sum::<usize>()
    })
}
fn exercise(
    side: Side,
    root: &Path,
    case: &Case,
    a: &JournalRecord,
    b: &JournalRecord,
) -> (BTreeMap<String, DiskNode>, Value) {
    fs::create_dir(root).unwrap();
    let first = append(side, root, a).unwrap();
    assert!(sample().is_empty()); // all first chunks are new
    let before = fs::read(root.join("journal.jsonl")).unwrap();
    assert_eq!(first.extent as usize, before.len());
    assert_eq!(first.bytes, before);
    let (m0, raw0) = manifest(root, 0);
    assert_eq!(first.blobs, refs_for(&m0, 0));
    reconstruction(root, &m0);
    decode(side, root, a, &first.bytes, true);
    MUTATION.with(|m| m.set(alter(root, case.changed)));
    let second = append(side, root, b);
    let measured = sample();
    assert_eq!(MUTATION.with(Cell::get), 0);
    let mtr = totals(&measured);
    if let Some(error) = case.error {
        let err = second.err().unwrap();
        assert_eq!(err.to_string(), error, "{}", case.changed);
        assert_eq!(measured.len(), 1);
        assert_eq!(
            measured[0].regular_opens,
            usize::from(case.changed != "directory")
        );
        assert_eq!(fs::read(root.join("journal.jsonl")).unwrap(), before);
        assert!(!root.join(format!("blobs/{}.json", want_hash(1))).exists());
        // The earlier non-shared chunk is written before comparison failure and remains.
        let all = collect(root);
        let original: BTreeSet<_> = hashes(&m0).into_iter().map(|(h, _)| h).collect();
        let orphans: Vec<_> = all
            .iter()
            .filter_map(|(path, node)| {
                let h = path.strip_prefix("blobs/shared/")?.strip_suffix(".bin")?;
                if original.contains(h) {
                    return None;
                }
                assert_eq!(node.kind, "file");
                assert_eq!(io::sha256_hex(&node.bytes_or_link), h);
                Some(node.bytes_or_link.len())
            })
            .collect();
        assert_eq!(orphans, vec![if ORDERED { 26_402 } else { 26_319 }]);
        return (
            all,
            json!({"error":error,"comparison_scope":mtr,"orphan_bytes":orphans[0]}),
        );
    }
    let second = second.unwrap();
    assert_eq!(second.extent as usize, before.len() + second.bytes.len());
    let (m1, raw) = manifest(root, 1);
    assert_eq!(second.blobs, refs_for(&m1, 1));
    let previous: BTreeSet<_> = hashes(&m0).into_iter().map(|(h, _)| h).collect();
    let overlap: Vec<_> = hashes(&m1)
        .into_iter()
        .filter(|(h, _)| previous.contains(h))
        .collect();
    assert_eq!(
        (overlap.len(), overlap.iter().map(|(_, n)| n).sum::<usize>()),
        if ORDERED {
            (29, 1_022_549)
        } else {
            (28, 988_882)
        }
    );
    if case.changed == "equal" {
        assert_eq!(measured.len(), overlap.len());
        assert!(measured.iter().all(|s| s.regular_opens == 1 && s.live == 0));
        assert_eq!(overlap.iter().map(|(_, n)| *n).max(), Some(65_536));
        match side {
            Side::Stock => {
                assert!(
                    measured
                        .iter()
                        .zip(&overlap)
                        .all(|(s, (_, n))| s.seen >= *n && s.peak >= s.seen && s.allocs > 0)
                );
                assert!(measured.iter().any(|s| s.seen >= 65_536));
            }
            Side::Candidate => assert!(
                measured
                    .iter()
                    .all(|s| s.allocs == 0 && s.reallocs == 0 && s.peak == 0)
            ),
        }
    }
    let mut joined = before;
    joined.extend_from_slice(&second.bytes);
    assert_eq!(fs::read(root.join("journal.jsonl")).unwrap(), joined);
    if case.changed != "pathname-replaced-after-open" {
        reconstruction(root, &m1);
        decode(side, root, b, &second.bytes, true);
        if case.changed == "equal" {
            let mut duplicate = b.clone();
            duplicate.record_id = id(107);
            duplicate.session_seq = 3;
            let third = append(side, root, &duplicate).unwrap();
            assert_eq!(third.blobs, second.blobs);
            assert!(
                sample().is_empty(),
                "exact whole payload bypasses chunk packing"
            );
            decode(side, root, &duplicate, &third.bytes, true);
        }
    } else {
        // Open file descriptor got original bytes, subsequent payload decode uses pathname again.
        let error = match side {
            Side::Stock => stock::codec::decode(root, b.session_id, &second.bytes),
            Side::Candidate => candidate::codec::decode(root, b.session_id, &second.bytes),
        }
        .unwrap_err();
        assert_eq!(error.to_string(), "shared blob chunk hash mismatch");
    }
    (
        collect(root),
        json!({"comparison_scope":mtr,"first_manifest_sha256":io::sha256_hex(&raw0),"manifest_sha256":io::sha256_hex(&raw),"line_sha256":io::sha256_hex(&second.bytes)}),
    )
}

struct FaultReader<'a> {
    meter: &'a Cell<(usize, usize)>,
    length: usize,
    failure_offset: Option<usize>,
    interrupted_at: Option<usize>,
}
impl Read for FaultReader<'_> {
    fn read(&mut self, b: &mut [u8]) -> std::io::Result<usize> {
        let (offset, calls) = self.meter.get();
        self.meter.set((offset, calls + 1));
        if self.interrupted_at == Some(offset) {
            self.interrupted_at = None;
            return Err(ErrorKind::Interrupted.into());
        }
        if self.failure_offset == Some(offset) {
            return Err(Error::other("late bounded test error"));
        }
        let n = b
            .len()
            .min(17)
            .min(self.length - offset)
            .min(self.failure_offset.map_or(usize::MAX, |at| at - offset))
            .min(self.interrupted_at.map_or(usize::MAX, |at| at - offset));
        b[..n].fill(1);
        self.meter.set((offset + n, calls + 1));
        Ok(n)
    }
}
fn reader_cases() -> Value {
    let mut r = BTreeMap::new();
    for (name, length, failure_offset, interrupted_at, max, pattern, want, consumed) in [
        (
            "late-fault-after-mismatch",
            71,
            Some(17),
            Some(0),
            100,
            vec![2; 71],
            "late bounded test error",
            17,
        ),
        (
            "fault-at-exact-limit",
            108,
            Some(100),
            Some(51),
            100,
            vec![2; 100],
            "late bounded test error",
            100,
        ),
        (
            "bound-wins-before-further-fault",
            108,
            Some(101),
            Some(51),
            100,
            vec![2; 100],
            "storage object exceeds 100 bytes",
            101,
        ),
        (
            "interrupted-after-mismatch",
            101,
            None,
            Some(17),
            100,
            vec![2; 101],
            "storage object exceeds 100 bytes",
            101,
        ),
        ("exact", 100, None, Some(0), 100, vec![1; 100], "true", 100),
        ("short", 100, None, Some(0), 100, vec![1; 101], "false", 100),
        ("zero", 0, None, Some(0), 0, vec![], "true", 0),
        (
            "zero-overflow",
            1,
            None,
            Some(0),
            0,
            vec![],
            "storage object exceeds 0 bytes",
            1,
        ),
    ] {
        let s = Cell::new((0, 0));
        let c = Cell::new((0, 0));
        let ptr = |meter| FaultReader {
            meter,
            length,
            failure_offset,
            interrupted_at,
        };
        let as_text = |r: Result<bool>| match r {
            Ok(b) => b.to_string(),
            Err(e) => e.to_string(),
        };
        let old = as_text(read_fault::read_bounded(ptr(&s), max, 0).map(|b| b == pattern));
        let new = as_text(read_fault::bounded_file_eq(ptr(&c), &pattern, max));
        assert_eq!(old, want, "{name}");
        assert_eq!(old, new, "{name}");
        assert_eq!(s.get().0, consumed);
        assert_eq!(c.get().0, consumed);
        r.insert(name, json!({ "result":new, "bytes_consumed": consumed }));
    }
    json!(r)
}
fn control_paths(side: Side, root: &Path) -> BTreeMap<String, DiskNode> {
    fs::create_dir(root).unwrap();
    let inline = record(0, "tiny".to_owned());
    let out = append(side, root, &inline).unwrap();
    assert!(out.blobs.is_empty() && sample().is_empty());
    decode(side, root, &inline, &out.bytes, false);
    // Exact production codec option: force a short external object without chunk manifests.
    let (line, blobs) = match side {
        Side::Stock => stock::codec::encode(root, &inline, 0),
        Side::Candidate => candidate::codec::encode(root, &inline, 0),
    }
    .unwrap();
    assert_eq!(blobs.len(), 1);
    assert!(sample().is_empty());
    assert!(!root.join("blobs/shared").exists());
    decode(side, root, &inline, &line, true);
    collect(root)
}
fn main() {
    let root = std::path::PathBuf::from(std::env::args_os().nth(1).unwrap());
    let (a, b) = records();
    let mut results = BTreeMap::new();
    for case in CASES {
        let (x, s) = exercise(
            Side::Stock,
            &root.join(format!("{}-stock", case.changed)),
            case,
            &a,
            &b,
        );
        let (y, c) = exercise(
            Side::Candidate,
            &root.join(format!("{}-candidate", case.changed)),
            case,
            &a,
            &b,
        );
        assert!(x == y, "paired disk inventory differs: {}", case.changed);
        for key in [
            "error",
            "first_manifest_sha256",
            "manifest_sha256",
            "line_sha256",
            "orphan_bytes",
        ] {
            assert_eq!(s[key], c[key]);
        }
        results.insert(case.changed, json!({"stock":s,"candidate":c}));
    }
    assert!(
        control_paths(Side::Stock, &root.join("controls-stock"))
            == control_paths(Side::Candidate, &root.join("controls-candidate"))
    );
    println!(
        "{}",
        json!({"real_append_cases":results,"nonpacked_controls":2,"scripted_read":reader_cases()})
    );
}
