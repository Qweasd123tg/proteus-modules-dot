#!/usr/bin/env python3
"""Replay and verify the exact Rust 1.95 telemetry cache eviction patch."""

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tempfile


PATH = "crates/proteus-core/src/app_server/context_map/telemetry/cache.rs"
BASE_BLOB = "ce9696b19acb3fbd3c0a9e77cd887cd7c6a1592e"
BASE_SHA = "9d2367826cf9aea7500ddab3a65281e2d3af92649e4293fd80956f92af350a05"
AFTER_BLOB = "4c3430aa0b7065d80a713f2e93b04ceaaeaa0375"
AFTER_SHA = "01c58a28e76f15a8f561749fbef6fda6d9365336b21929a0e8c1c4f1676064f9"
PATCH_SHA = "cc3071f5b90f7d1b9cb045884d2304c63dab1c393a7baf2d8430669099fcbd3d"


def check(condition, label):
    if not condition:
        raise ValueError(label)


def identity(source, blob, digest):
    check(hashlib.sha256(source).hexdigest() == digest, "SHA256")
    git_bytes = b"blob " + str(len(source)).encode() + b"\0" + source
    check(hashlib.sha1(git_bytes).hexdigest() == blob, "Git blob")


def replay(src, patch, reverse=False):
    lines = src.splitlines(keepends=True)
    expected_header = (
        f"diff --git a/{PATH} b/{PATH}\n"
        f"index {BASE_BLOB}..{AFTER_BLOB} 100644\n"
        f"--- a/{PATH}\n+++ b/{PATH}\n"
    ).encode()
    check(patch.startswith(expected_header), "patch header")
    hunks = patch[len(expected_header):].splitlines(keepends=True)
    used = 0
    target = []
    index = 0
    count = 0
    while index < len(hunks):
        match = re.fullmatch(rb"@@ -(\d+),(\d+) \+(\d+),(\d+) @@\n", hunks[index])
        check(match is not None, "patch hunk")
        before, before_count, after, after_count = map(int, match.groups())
        index += 1
        count += 1
        before_lines, after_lines = [], []
        while index < len(hunks) and not hunks[index].startswith(b"@@ "):
            line = hunks[index]
            check(line[:1] in (b" ", b"+", b"-"), "patch hunk body")
            if line[:1] != b"+":
                before_lines.append(line[1:])
            if line[:1] != b"-":
                after_lines.append(line[1:])
            index += 1
        check((len(before_lines), len(after_lines)) == (before_count, after_count),
              "patch counts")
        if reverse:
            before, after = after, before
            before_lines, after_lines = after_lines, before_lines
        at = before - 1
        check(used <= at and lines[at:at + len(before_lines)] == before_lines, "patch preimage")
        target.extend(lines[used:at])
        check(len(target) == after - 1, "patch coordinates")
        target.extend(after_lines)
        used = at + len(before_lines)
    check(count == 1, "expected one eviction hunk")
    return b"".join(target + lines[used:])


def section(source, first, end):
    at = source.index(first)
    return source[at:source.index(end, at + len(first))]


RUSTC_SHA = "bff349e72704ff70bc08a234a3847338e797065bbedde5e556808bc87b7bf7c6"
RUSTC_VERSION = "rustc 1.95.0 (59807616e 2026-04-14)"
TRIM = "    while cache.entries.len() > MAX_ENTRIES"
END = "\n}\n\nstruct Budget(usize);"


def make_arm(name, source):
    # Keep the entire file. Imports of Telemetry/SessionId resolve to test types;
    # Serde output is replaced at its existing call boundary, not in Budget.
    return (
        f"#[allow(dead_code)]\nmod {name} {{\nuse crate::serde_json;\n"
        + source + r'''
    fn locked() -> bool { cache().try_lock().is_err() }
    pub(crate) fn reset() {
        let old = {
            let mut guard = cache().lock().unwrap();
            std::mem::take(&mut *guard)
        };
        drop(old);
    }
    pub(crate) fn put(path: &Path, id: u64, stamp: u64, payload: u64, bytes: usize,
                      fail: bool, log: crate::DropLog) {
        let key = Key::new(path, Some(id), Some(Path::new("/private/inert/session")));
        let source = SourceStamp { identity: [stamp; 7] };
        let telemetry = Arc::new(Telemetry { payload, bytes, fail, log, locked });
        insert(key, source, telemetry);
    }
    pub(crate) fn access(path: &Path, id: u64, stamp: u64) -> Option<Arc<Telemetry>> {
        let key = Key::new(path, Some(id), Some(Path::new("/private/inert/session")));
        get(&key, &SourceStamp { identity: [stamp; 7] })
    }
    pub(crate) fn snapshot() -> crate::Snapshot {
        let guard = cache().lock().unwrap();
        let rows = guard.entries.iter().map(|entry| {
            (entry.key.path.clone(), entry.key.session_id.unwrap(),
             entry.source.identity[0], entry.telemetry.payload, entry.bytes)
        }).collect();
        (guard.bytes, rows)
    }
}
'''
    )


def make_trim(name, source, candidate, instrument):
    block = section(source, TRIM, END)
    if instrument and candidate:
        a = "        let mut logs = BTreeSet::new();"
        b = "            .position(|entry| {"
        check(block.count(a) == block.count(b) == 1, "new metric seams")
        block = block.replace(a, "        work.sets += 1;\n" + a)
        block = block.replace(b, b + "\n                work.visits += 1;")
    if instrument and not candidate:
        a = "        || cache\n"
        b = "            > MAX_LOGS\n"
        c = "            .map(|entry| &entry.key.path)"
        check(block.count(a) == block.count(b) == block.count(c) == 1, "old metric seams")
        block = block.replace(a, "        || {\n            work.sets += 1;\n            cache\n")
        block = block.replace(b, b + "        }\n")
        block = block.replace(c, "            .inspect(|_| work.visits += 1)\n" + c)
    work = ", work: &mut Work" if instrument else ""
    return (
        "#[allow(non_snake_case)]\n"
        f"fn {name}(cache: &mut TinyCache, limits: Limits{work}) {{\n"
        "    let (MAX_ENTRIES, MAX_BYTES, MAX_LOGS) = limits;\n"
        + block + "\n}\n"
    )


TESTS = r'''
use std::collections::{BTreeSet, VecDeque};
use std::ffi::OsString;
use std::os::unix::ffi::OsStringExt;
use std::path::{Path, PathBuf};
use std::sync::{Arc, Mutex};

mod domain { pub(crate) type SessionId = u64; }

type DropLog = Arc<Mutex<Vec<(u64, bool)>>>;
type Snapshot = (usize, Vec<(PathBuf, u64, u64, u64, usize)>);
struct Telemetry {
    payload: u64, bytes: usize, fail: bool, log: DropLog, locked: fn() -> bool,
}
impl Drop for Telemetry {
    fn drop(&mut self) {
        self.log.lock().unwrap().push((self.payload, (self.locked)()));
    }
}
mod serde_json {
    use std::io::{self, Write};
    use crate::Telemetry;

    pub(super) fn to_writer(mut writer: impl Write, projection: &Telemetry) -> io::Result<()> {
        let mut left = projection.bytes;
        let block = [0u8; 4096];
        while left > 0 {
            let take = left.min(block.len());
            writer.write_all(&block[..take])?;
            left -= take;
        }
        if projection.fail { Err(io::Error::other("synthetic serializer error")) } else { Ok(()) }
    }
}

struct Arm {
    reset: fn(),
    put: fn(&Path, u64, u64, u64, usize, bool, DropLog),
    get: fn(&Path, u64, u64) -> Option<Arc<Telemetry>>,
    snapshot: fn() -> Snapshot,
    log: DropLog,
}
impl Arm {
    fn new(candidate_arm: bool) -> Self {
        let log = DropLog::default();
        let arm = if candidate_arm {
            Self { reset: candidate::reset, put: candidate::put, get: candidate::access,
                   snapshot: candidate::snapshot, log }
        } else {
            Self { reset: stock::reset, put: stock::put, get: stock::access,
                   snapshot: stock::snapshot, log }
        };
        (arm.reset)();
        arm
    }
    fn put(&self, path: &Path, key: u64, payload: u64, bytes: usize) {
        (self.put)(path, key, 1, payload, bytes, false, self.log.clone());
    }
    fn drops(&self) -> Vec<(u64, bool)> { self.log.lock().unwrap().clone() }
}
impl Drop for Arm { fn drop(&mut self) { (self.reset)(); } }

#[derive(Debug, Clone, PartialEq, Eq)]
struct TinyCache { entries: VecDeque<TinyEntry>, bytes: usize }
#[derive(Debug, Clone, PartialEq, Eq)]
struct TinyEntry { key: TinyKey, id: usize, bytes: usize }
#[derive(Debug, Clone, PartialEq, Eq)]
struct TinyKey { path: PathBuf }
type Limits = (usize, usize, usize);
const LIMITS: Limits = (128, 8 * 1024 * 1024, 16);
#[derive(Debug, Default, PartialEq, Eq)]
struct Work { sets: usize, visits: usize }
fn tiny(rows: impl IntoIterator<Item=(PathBuf, usize)>) -> TinyCache {
    let entries: VecDeque<_> = rows.into_iter().enumerate().map(|(id, (path, bytes))| {
        TinyEntry { key: TinyKey { path }, id, bytes }
    }).collect();
    TinyCache { bytes: entries.iter().map(|entry| entry.bytes).sum(), entries }
}
fn pressure() -> TinyCache {
    tiny((0..112).map(|i| (PathBuf::from("/project/shared/log"), 4096 + i))
        .chain((0..16).map(|j| (PathBuf::from(format!("/project/log{j}")), 8192 + j))))
}
fn oracle(cache: &TinyCache, (entries, bytes, logs): Limits) -> usize {
    for n in 0..=cache.entries.len() {
        let mut total = 0;
        let mut paths: Vec<&Path> = Vec::new();
        for e in cache.entries.iter().skip(n) {
            total += e.bytes;
            let path = e.key.path.as_path();
            if !paths.contains(&path) { paths.push(path); }
        }
        if cache.entries.len() - n <= entries && total <= bytes && paths.len() <= logs {
            return n;
        }
    }
    unreachable!("empty suffix qualifies");
}
fn verify(cache: TinyCache, limits: Limits) {
    let mut old = cache.clone();
    let mut new = cache.clone();
    trim_stock(&mut old, limits);
    trim_candidate(&mut new, limits);
    assert_eq!(old, new);
    let discard = oracle(&cache, limits);
    assert!(new.entries.iter().eq(cache.entries.iter().skip(discard)));
    assert_eq!(new.bytes, new.entries.iter().map(|e| e.bytes).sum::<usize>());
}

#[test]
fn production_pressure_preserves_suffix_and_locked_drop_order() {
    let rows = pressure().entries;
    let run = |candidate_arm| {
        let arm = Arm::new(candidate_arm);
        for e in rows.iter().take(rows.len() - 1) {
            arm.put(&e.key.path, e.id as u64, e.id as u64, e.bytes);
        }
        assert_eq!((arm.snapshot)().0, 587_953);
        assert!(arm.drops().is_empty());
        let last = rows.back().unwrap();
        arm.put(&last.key.path, last.id as u64, last.id as u64, last.bytes);
        ((arm.snapshot)(), arm.drops())
    };
    let old = run(false);
    let new = run(true);
    assert_eq!(old, new);
    assert_eq!(new.0.0, 131_192);
    assert_eq!(new.0.1.len(), 16);
    assert_eq!(new.0.1.iter().map(|r| r.1).collect::<Vec<_>>(), (112..128).collect::<Vec<_>>());
    assert_eq!(new.1, (0..112).map(|i| (i, true)).collect::<Vec<_>>());
}

#[test]
fn production_get_alias_stamps_and_eviction_of_stale_key() {
    let run = |candidate_arm| {
        let arm = Arm::new(candidate_arm);
        let first = Path::new("/project//./log");
        let alias = Path::new("/project/log");
        let raw = PathBuf::from(OsString::from_vec(b"/project/\xff".to_vec()));
        arm.put(first, 1, 10, 100);
        arm.put(&raw, 1, 11, 200);
        arm.put(alias, 2, 12, 300);
        let held = (arm.get)(alias, 1, 1).unwrap();
        assert_eq!(held.payload, 10);
        assert_eq!((arm.snapshot)().1.iter().map(|r| r.3).collect::<Vec<_>>(), [11, 12, 10]);
        assert!((arm.get)(alias, 1, 2).is_none());
        assert_eq!((arm.snapshot)().0, 500);
        assert!(arm.drops().is_empty());
        drop(held); // A caller with an Arc may release the stale payload outside the lock.
        assert_eq!(arm.drops(), [(10, false)]);
        (arm.put)(alias, 2, 2, 13, 222, false, arm.log.clone());
        assert_eq!(arm.drops(), [(10, false), (12, true)]);
        assert_eq!((arm.get)(alias, 2, 2).unwrap().payload, 13);
        assert!((arm.get)(&raw, 99, 1).is_none());
        ((arm.snapshot)(), arm.drops())
    };
    assert_eq!(run(false), run(true));
}

#[test]
fn production_count_and_byte_limits_remain_independent() {
    let run = |candidate_arm| {
        let arm = Arm::new(candidate_arm);
        let path = Path::new("/single/shared");
        for i in 0..129 {
            arm.put(path, i, i, 1);
        }
        assert_eq!((arm.snapshot)().0, 128);
        assert_eq!((arm.snapshot)().1.len(), 128);
        assert_eq!(arm.drops(), [(0, true)]);
        (arm.reset)();
        arm.log.lock().unwrap().clear();
        for i in 0..9 {
            arm.put(path, i, 500 + i, 1024 * 1024);
        }
        assert_eq!((arm.snapshot)().0, 8 * 1024 * 1024);
        assert_eq!((arm.snapshot)().1.len(), 8);
        assert_eq!(arm.drops(), [(500, true)]);
        ((arm.snapshot)(), arm.drops())
    };
    assert_eq!(run(false), run(true));
}

#[test]
fn production_oversized_or_failed_serialization_keeps_existing_entry() {
    let run = |candidate_arm| {
        let arm = Arm::new(candidate_arm);
        let path = Path::new("/single/shared");
        arm.put(path, 1, 10, 1024 * 1024);
        let before = (arm.snapshot)();
        (arm.put)(path, 1, 2, 11, 1024 * 1024 + 1, false, arm.log.clone());
        (arm.put)(path, 1, 2, 12, 17, true, arm.log.clone());
        assert_eq!((arm.snapshot)(), before);
        assert_eq!(arm.drops(), [(11, false), (12, false)]);
        assert_eq!((arm.get)(path, 1, 1).unwrap().payload, 10);
        ((arm.snapshot)(), arm.drops())
    };
    assert_eq!(run(false), run(true));
}

#[test]
fn exact_trim_handles_wrapped_storage_and_path_aliases() {
    let mut cache = tiny((0..128).map(|i| (PathBuf::from(format!("/d/{}", i % 21)), i + 1)));
    cache.entries.rotate_left(61);
    // Force noncontiguous slices without relying on rotate_left's choice of layout.
    for i in 0..17 {
        let mut old = cache.entries.pop_front().unwrap();
        old.id += i + 128;
        cache.entries.push_back(old);
    }
    let (first, second) = cache.entries.as_slices();
    assert!(!first.is_empty() && !second.is_empty());
    for limits in [LIMITS, (127, 2048, 16), (127, 8192, 17), (16, 130, 16)] {
        verify(cache.clone(), limits);
    }
    let raw = |bytes: &[u8]| PathBuf::from(OsString::from_vec(bytes.to_vec()));
    let alias_a = raw(b"/log/\xff");
    let alias_b = raw(b"/log//./\xff");
    assert_eq!(alias_a, alias_b);
    assert_eq!(alias_a.cmp(&alias_b), std::cmp::Ordering::Equal);
    let cache = tiny([(alias_a, 1), (PathBuf::from("/log/../x"), 2),
                      (alias_b, 3), (PathBuf::from("/x"), 4)]);
    assert_ne!(cache.entries[1].key.path, cache.entries[3].key.path);
    for logs in 0..=4 { verify(cache.clone(), (4, 10, logs)); }
}

#[test]
fn generic_boundary_matrix_matches_independent_suffix_oracle() {
    let items = [
        (PathBuf::from("/p/shared"), 1), (PathBuf::from("/p/shared"), 3),
        (PathBuf::from("/p//./shared"), 2), (PathBuf::from("/p/other"), 1),
        (PathBuf::from("/p/third"), 4), (PathBuf::from("/q"), 2),
    ];
    let mut count = 0;
    for length in 0..=4usize {
        for mut choice in 0..items.len().pow(length as u32) {
            let rows = (0..length).map(|_| {
                let row = items[choice % items.len()].clone();
                choice /= items.len();
                row
            });
            let cache = tiny(rows);
            for entries in [0, 1, 2, 3, 6] {
                for bytes in [0, 2, 3, 5, 9, 12] {
                    for logs in [0, 1, 2, 3] {
                        verify(cache.clone(), (entries, bytes, logs));
                        count += 1;
                    }
                }
            }
        }
    }
    assert_eq!(count, 186_600);
}

#[test]
fn instrumented_pressure_counts_path_visits_and_set_builds() {
    let mut old_work = Work::default();
    let mut new_work = Work::default();
    let mut old = pressure();
    let mut new = old.clone();
    assert_eq!(old.bytes, 596_160);
    count_stock(&mut old, LIMITS, &mut old_work);
    count_candidate(&mut new, LIMITS, &mut new_work);
    assert_eq!(old, new);
    assert_eq!((new.entries.len(), new.bytes), (16, 131_192));
    assert_eq!(old_work, Work { sets: 113, visits: 8136 });
    assert_eq!(new_work, Work { sets: 1, visits: 17 });
    println!("R234_WORK {} {} {} {} {} {}", old_work.sets, old_work.visits,
             new_work.sets, new_work.visits, new.entries.len(), new.bytes);
    // The entry cap alone drops the old repeated path and makes log counting non-evicting.
    let mut old = pressure();
    let mut new = old.clone();
    let mut old_entry = Work::default();
    let mut new_entry = Work::default();
    count_stock(&mut old, (16, 8 * 1024 * 1024, 16), &mut old_entry);
    count_candidate(&mut new, (16, 8 * 1024 * 1024, 16), &mut new_entry);
    assert_eq!(old, new);
    assert_eq!(old_entry, Work { sets: 1, visits: 16 });
    assert_eq!(new_entry, old_entry);
}
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("stock", "rustc", "work"):
        parser.add_argument("--" + name, required=True, type=Path)
    args = parser.parse_args()
    raw = args.stock.read_bytes()
    identity(raw, BASE_BLOB, BASE_SHA)
    patch = Path(__file__).with_name("source.patch").read_bytes()
    check(hashlib.sha256(patch).hexdigest() == PATCH_SHA, "patch digest")
    updated = replay(raw, patch)
    identity(updated, AFTER_BLOB, AFTER_SHA)
    check(replay(updated, patch, reverse=True) == raw, "exact rollback")
    old, new = raw.decode(), updated.decode()
    check(old[:old.index(TRIM)] == new[:new.index(TRIM)], "exact pre-trim code")
    check(old[old.index(END):] == new[new.index(END):], "exact tail code")
    caps = "const MAX_LOGS: usize = 16;\nconst MAX_ENTRIES: usize = 128;"
    check(caps in old and "const MAX_BYTES: usize = 8 * 1024 * 1024;" in old
          and "const MAX_ENTRY_BYTES: usize = 1024 * 1024;" in old, "fixture caps")
    rustc = args.rustc.resolve(strict=True)
    check(hashlib.sha256(rustc.read_bytes()).hexdigest() == RUSTC_SHA, "compiler digest")
    with tempfile.TemporaryDirectory(prefix="r234-", dir=args.work.resolve(strict=True)) as temp:
        root = Path(temp)
        env = {"PATH": "/usr/bin:/bin", "HOME": temp, "TMPDIR": temp, "LC_ALL": "C"}
        version = subprocess.check_output([rustc, "--version"], cwd=root, env=env,
                                          text=True, timeout=20).strip()
        check(version == RUSTC_VERSION, "compiler version")
        fixture = root / "lift.rs"
        fixture.write_text(TESTS + "\n" + make_arm("stock", old) + make_arm("candidate", new)
                           + make_trim("trim_stock", old, False, False)
                           + make_trim("trim_candidate", new, True, False)
                           + make_trim("count_stock", old, False, True)
                           + make_trim("count_candidate", new, True, True), encoding="utf-8")
        results = {}
        for mode, flags in [("debug", []), ("optimized", ["-O"])]:
            exe = root / ("test-" + mode)
            subprocess.run([rustc, "--edition=2024", "--test", "-Dwarnings", *flags,
                            fixture, "-o", exe], check=True, cwd=root, env=env, timeout=90)
            run = subprocess.run([exe, "--nocapture", "--test-threads=1"], cwd=root, env=env,
                                 capture_output=True, text=True, timeout=90)
            check(run.returncode == 0, f"{mode} tests:\n{run.stdout}\n{run.stderr}")
            tests = re.search(r"test result: ok\. (\d+) passed; 0 failed;", run.stdout)
            metrics = re.search(r"\bR234_WORK (\d+) (\d+) (\d+) (\d+) (\d+) (\d+)$",
                                run.stdout, re.M)
            check(tests is not None and int(tests[1]) == 7, "test count")
            check(metrics is not None, "pressure receipt")
            sets_old, visits_old, sets_new, visits_new, rows, size = map(int, metrics.groups())
            results[mode] = {
                "tests_passed": int(tests[1]), "generic_pairs": 186600,
                "pressure_stock_set_builds_path_visits": [sets_old, visits_old],
                "pressure_candidate_set_builds_path_visits": [sets_new, visits_new],
                "retained_rows_bytes": [rows, size],
            }
    print(json.dumps({"status": "PASS", "rustc": version, "rustc_sha256": RUSTC_SHA,
                      "exact_forward_and_reverse": True, "results": results,
                      "native_cache_with_inert_serializer_only": True,
                      "real_serde_http_source_stat_or_cargo": False}, indent=2))


if __name__ == "__main__":
    main()
