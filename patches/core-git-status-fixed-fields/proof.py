#!/usr/bin/env python3
"""Replay the exact source patch and run the Rust 1.95 inert porcelain status proof."""

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tempfile


PATH = "crates/proteus-core/src/app_server/http/workspace/git/status.rs"
BASE_BLOB = "0302a0459e1c619b87364fc78b71920e8c3cc411"
BASE_SHA = "65fc294e6a1465ccd8b4f010264eb77b3dc85182ba8e39b134ff307aa35d4c29"
AFTER_BLOB = "138ff1d3895d7853d8f632b0255c26c54626b12f"
AFTER_SHA = "c0fb120d62966c2d215301235bb885fb7e433564baae71fcfcda6d9e1b1483dc"
PATCH_SHA = "eda68b11d177fe87206aba0f3d8de97efa21e0749c29776f49e2ee7d84f33d70"


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
    check(count == 4, "expected three field replacements and one helper hunk")
    return b"".join(target + lines[used:])


def section(source, first, end):
    at = source.index(first)
    return source[at:source.index(end, at + len(first))]


REF = (
    ("git", "60455aaa9ddef9e26061560a6e21738ae8f61ffe",
     "782bc990cbcacd7fa05cb9c9c840967c99977f26cab0ee53c04efa772ee7a8cc"),
    ("revision", "92cd0c47caca51ebfcba73c570d18b24679aa77d",
     "17e02f3359fae15a35f157a2a209ed342151bdebeb0beb6978b6397892056fa2"),
    ("workspace", "acfce1e7bb7e32365abd90e2a4b615be560d0e14",
     "5b8c3ad4e243fa6435523b355112bdadb0b4600ad50387f39a5abc63758f5126"),
)
RUSTC_SHA = "bff349e72704ff70bc08a234a3847338e797065bbedde5e556808bc87b7bf7c6"
RUSTC_VERSION = "rustc 1.95.0 (59807616e 2026-04-14)"


def make_lift(name, source):
    change = section(source, "pub(super) struct Change {", "impl Change {")
    check(change.count("    #[serde(skip)]\n") == 1, "private index annotation")
    change = change.replace("    #[serde(skip)]\n", "", 1)
    scan = section(source, "pub(super) struct Scan {", "pub(crate) fn changes(")
    flags = section(source, "const UNTRACKED: &str", "/// Status of the given")
    parser = source[source.index("pub(super) fn scan("):]
    return (
        f"mod {name} {{\nuse crate::*;\n"
        + change + scan + flags + parser
        + """
pub(super) fn observe(scan: Scan) -> ScanView {
    ScanView {
        head_oid: scan.head_oid, branch: scan.branch, upstream: scan.upstream,
        ahead: scan.ahead, behind: scan.behind, truncated: scan.truncated,
        entries: scan.entries.into_iter().map(|e| ChangeView {
            path: e.path, original: e.original, status: e.status,
            staged: e.staged, unstaged: e.unstaged, added: e.added,
            deleted: e.deleted, revision: e.revision, index: e.index,
        }).collect(),
    }
}
}
"""
    )


TESTS = r'''
use std::alloc::{GlobalAlloc, Layout, System};
use std::cell::{Cell, RefCell};
use std::ffi::OsStr;
use std::fmt::Display;
use std::hint::black_box;
use std::num::ParseIntError;
use std::path::Path;

#[derive(Debug, Eq, PartialEq)]
struct Error { label: String, detail: Option<String> }
impl Error {
    fn new(label: &str) -> Self { Self { label: label.into(), detail: None } }
}
impl From<ParseIntError> for Error {
    fn from(err: ParseIntError) -> Self { Self::new(&err.to_string()) }
}
type Result<T> = std::result::Result<T, Error>;
trait Context<T> { fn context(self, label: &str) -> Result<T>; }
impl<T> Context<T> for Option<T> {
    fn context(self, label: &str) -> Result<T> { self.ok_or_else(|| Error::new(label)) }
}
impl<T, E: Display> Context<T> for std::result::Result<T, E> {
    fn context(self, label: &str) -> Result<T> {
        self.map_err(|e| Error { label: label.into(), detail: Some(e.to_string()) })
    }
}
macro_rules! ensure {
    ($condition:expr, $label:literal) => { if !$condition { return Err(Error::new($label)); } }
}
macro_rules! bail {
    ($label:literal) => { return Err(Error::new($label)) }
}
mod anyhow { pub(super) use crate::bail; }
pub(crate) use bail;

#[derive(Clone, Copy, Debug, Default)]
struct Requests { alloc: usize, realloc: usize, bytes: usize }
thread_local! {
    static ALLOC: Cell<Option<Requests>> = const { Cell::new(None) };
    static ACTIVE: RefCell<Option<(Fixture, Vec<Call>)>> = const { RefCell::new(None) };
}
fn requested(bytes: usize, is_realloc: bool) {
    let _ = ALLOC.try_with(|counts| {
        if let Some(mut requests) = counts.get() {
            requests.bytes += bytes;
            if is_realloc { requests.realloc += 1; } else { requests.alloc += 1; }
            counts.set(Some(requests));
        }
    });
}
struct ObserveAllocator;
unsafe impl GlobalAlloc for ObserveAllocator {
    unsafe fn alloc(&self, layout: Layout) -> *mut u8 {
        requested(layout.size(), false);
        unsafe { System.alloc(layout) }
    }
    unsafe fn alloc_zeroed(&self, layout: Layout) -> *mut u8 {
        requested(layout.size(), false);
        unsafe { System.alloc_zeroed(layout) }
    }
    unsafe fn realloc(&self, ptr: *mut u8, before: Layout, bytes: usize) -> *mut u8 {
        requested(bytes, true);
        unsafe { System.realloc(ptr, before, bytes) }
    }
    unsafe fn dealloc(&self, ptr: *mut u8, layout: Layout) {
        unsafe { System.dealloc(ptr, layout) }
    }
}
#[global_allocator]
static ALLOCATOR: ObserveAllocator = ObserveAllocator;

const ROOT: &str = "/inert/status";
#[derive(Clone)]
struct Output { success: bool, truncated: bool, bytes: Vec<u8> }
#[derive(Clone)]
struct Fixture { prefix: Option<&'static str>, output: Option<Output> }
#[derive(Debug, Eq, PartialEq)]
enum Call { Prefix, Read(usize) }
impl Fixture {
    fn new(bytes: Vec<u8>) -> Self {
        Self { prefix: Some("scope/"), output: Some(Output { success: true, truncated: false, bytes }) }
    }
    fn truncated(mut self) -> Self {
        let output = self.output.as_mut().unwrap();
        output.success = false;
        output.truncated = true;
        self
    }
}
fn prefix(root: &Path) -> Result<String> {
    assert_eq!(root, Path::new(ROOT));
    ACTIVE.with_borrow_mut(|active| {
        let (fixture, calls) = active.as_mut().unwrap();
        calls.push(Call::Prefix);
        fixture.prefix.map(str::to_owned).context("synthetic prefix failure")
    })
}
fn os<'a>(args: &[&'a str]) -> Vec<&'a OsStr> { args.iter().copied().map(OsStr::new).collect() }
fn read(root: &Path, args: &[&OsStr], limit: usize) -> Result<Output> {
    assert_eq!(root, Path::new(ROOT));
    assert!(args.iter().copied().eq([
        "status", "--porcelain=v2", "--branch", "-z", "--untracked-files=all",
        "--ignore-submodules=all", "--", ".", "literal path",
    ].iter().map(OsStr::new)));
    assert_eq!(limit, 512 * 1024);
    ACTIVE.with_borrow_mut(|active| {
        let (fixture, calls) = active.as_mut().unwrap();
        calls.push(Call::Read(limit));
        if let Some(output) = &fixture.output { assert!(output.bytes.len() <= limit); }
        fixture.output.clone().context("synthetic runner failure")
    })
}

#[derive(Debug, Eq, PartialEq)]
struct ScanView {
    head_oid: Option<String>, branch: Option<String>, upstream: Option<String>,
    ahead: u64, behind: u64, entries: Vec<ChangeView>, truncated: bool,
}
#[derive(Debug, Eq, PartialEq)]
struct ChangeView {
    path: String, original: Option<String>, status: &'static str,
    staged: Option<&'static str>, unstaged: Option<&'static str>, added: Option<u64>,
    deleted: Option<u64>, revision: Option<String>, index: String,
}
fn invoke<T>(fixture: &Fixture, scan: impl FnOnce(&Path, &[String]) -> Result<T>,
             measure: bool) -> (Result<T>, Requests, Vec<Call>) {
    ACTIVE.with_borrow_mut(|active| {
        assert!(active.replace((fixture.clone(), Vec::with_capacity(2))).is_none());
    });
    let pathspecs = [".".to_owned(), "literal path".to_owned()];
    if measure { ALLOC.set(Some(Requests::default())); }
    let scan = black_box(scan(black_box(Path::new(ROOT)), black_box(&pathspecs)));
    let counts = ALLOC.replace(None).unwrap_or_default();
    let (_, calls) = ACTIVE.with_borrow_mut(|active| active.take().unwrap());
    (scan, counts, calls)
}
fn compare(fixture: Fixture, measure: bool) -> (Result<ScanView>, Requests, Requests, Vec<Call>) {
    let (s, old, sc) = invoke(&fixture, stock::scan, measure);
    let (c, new, cc) = invoke(&fixture, candidate::scan, measure);
    let s = s.map(stock::observe);
    let c = c.map(candidate::observe);
    assert_eq!(s, c, "exact visible/private status mismatch");
    assert_eq!(sc, cc, "runner call order mismatch");
    (c, old, new, cc)
}
fn paired(fixture: Fixture) -> Result<ScanView> { compare(fixture, false).0 }
fn frames(rows: &[&[u8]]) -> Vec<u8> {
    rows.iter().flat_map(|r| r.iter().copied().chain([0])).collect()
}
fn checked(rows: &[&[u8]]) -> ScanView { paired(Fixture::new(frames(rows))).unwrap() }
fn fails(fixture: Fixture, label: &str) {
    assert_eq!(paired(fixture).unwrap_err().label, label);
}
const ONE: &[u8] = b"1 M. N... 100644 100644 100644 base indexed scope/a path";
const TWO: &[u8] = b"2 .R N... 100644 100755 100755 base renamed R100 scope/new path";
const CONFLICT_ROW: &[u8] = b"u UU N... 100644 000000 100755 100644 blob1 blob2 blob3 scope/conflicted path";
const BAD_XY_RENAME: &[u8] = b"2 M N... 100644 100755 100755 base renamed R100 scope/new path";

#[test]
fn mixed_order_fields_and_private_stage_bytes() {
    let (result, _, _, calls) = compare(Fixture::new(frames(&[
        b"# branch.oid (initial)", b"# branch.head (detached)", b"# branch.oid base",
        b"# branch.head topic", b"# branch.upstream origin/topic", b"# branch.ab +4 -3",
        b"# ignored header", ONE, TWO, b"scope/old path", CONFLICT_ROW, "? scope/雪🧪".as_bytes(),
        b"ignored", b"1 D. N... 100644 000000 000000 base ignored outside/file",
    ])), false);
    assert_eq!(calls, [Call::Prefix, Call::Read(512 * 1024)]);
    let got = result.unwrap();
    assert!(!got.truncated);
    assert_eq!((got.head_oid.as_deref(), got.branch.as_deref(), got.upstream.as_deref()),
               (Some("base"), Some("topic"), Some("origin/topic")));
    assert_eq!((got.ahead, got.behind), (4, 3));
    assert_eq!(got.entries.iter().map(|e| e.path.as_str()).collect::<Vec<_>>(),
               ["a path", "new path", "conflicted path", "雪🧪"]);
    assert_eq!(got.entries.iter().map(|e| e.status).collect::<Vec<_>>(),
               ["modified", "renamed", "conflict", "untracked"]);
    assert_eq!(got.entries[1].original.as_deref(), Some("old path"));
    assert_eq!(got.entries[0].index, "100644 indexed 0\0");
    assert_eq!(got.entries[1].index, "100755 renamed 0\0");
    assert_eq!(got.entries[2].index, "100644 blob1 1\0".to_owned() + "100755 blob3 3\0");
    assert!(got.entries[3].index.is_empty());
    assert!(got.entries.iter().all(|e| e.revision.is_none() && e.added.is_none() && e.deleted.is_none()));
}

#[test]
fn literal_spaces_empty_slots_and_unvalidated_field_spellings() {
    let got = checked(&[
        b"1x M. N... 100644 100644 100644 base indexed scope/ a  b\t ",
        b"1 M.  100644   base indexed scope/",
        b"2 .R N... 100644 000000 100755 base renamed R100 scope/",
        b"outside/was tracked",
        b"u UU N... 000000 000000 000000 100644 blob1 blob2 blob3 scope/last",
    ]);
    assert_eq!(got.entries.iter().map(|x| x.path.as_str()).collect::<Vec<_>>(),
               [" a  b\t ", "", "", "last"]);
    assert_eq!(got.entries[2].original, None);
    assert!(got.entries[2].index.is_empty());
    assert!(got.entries[3].index.is_empty());
    let empty_last = Fixture { prefix: Some(""),
        ..Fixture::new(frames(&[b"1 M. N... 100644 100644 100644 base indexed "]))
    };
    assert_eq!(paired(empty_last).unwrap().entries[0].path, "");
    for row in [b"1 M. N... 100644 100644 100644 base indexed".as_slice(),
                b"2 M", b"u UU N... 100644", b"?"] {
        fails(Fixture::new(frames(&[row, b"\xff"])), "invalid Git status record");
    }
    fails(Fixture::new(frames(&[b"1  N... 100644 100644 100644 base indexed scope/ok"])),
          "invalid Git status code");
}

#[test]
fn rename_consumption_utf8_and_truncation_priority() {
    fails(Fixture::new(frames(&[b"2", b"\xff"])).truncated(), "invalid Git status record");
    fails(Fixture::new(frames(&[BAD_XY_RENAME, b"\xff"])).truncated(), "Git path is not UTF-8");
    fails(Fixture::new(frames(&[BAD_XY_RENAME, b"outside/source"])), "invalid Git status code");
    fails(Fixture::new(frames(&[BAD_XY_RENAME])), "incomplete Git rename record");
    let missing = paired(Fixture::new(frames(&[ONE, BAD_XY_RENAME, b""])).truncated()).unwrap();
    assert!(missing.truncated && missing.entries.len() == 1);
    let mut raw_tail = frames(&[BAD_XY_RENAME]);
    raw_tail.extend_from_slice(b"\xffnot framed");
    fails(Fixture::new(raw_tail.clone()), "incomplete Git rename record");
    assert!(paired(Fixture::new(raw_tail).truncated()).unwrap().entries.is_empty());
    let dropped = checked(&[TWO, b"", b"scope/original", ONE]);
    assert_eq!(dropped.entries[0].original.as_deref(), Some("original"));
    assert_eq!(dropped.entries[1].path, "a path");
    let consumed = checked(&[TWO, b"# branch.head not-a-header-here", ONE]);
    assert!(consumed.branch.is_none() && consumed.entries[0].original.is_none());
    let outside = b"2 .R N... 100644 100755 100755 base renamed R100 outside/new";
    fails(Fixture::new(frames(&[outside, b"\xff"])), "Git path is not UTF-8");
}

#[test]
fn input_and_runner_error_priority() {
    let mut fixture = Fixture::new(frames(&[b"# branch.ab malformed", b"\xff"]));
    fails(fixture.clone(), "invalid Git branch.ab");
    fixture.output.as_mut().unwrap().success = false;
    fails(fixture.clone(), "cannot read Git changes");
    fails(fixture.truncated(), "invalid Git branch.ab");
    fails(Fixture::new(frames(&[b"# branch.\xff", ONE])), "Git status is not UTF-8");
    fails(Fixture::new(frames(&[b"unknown\xff", ONE])), "Git status is not UTF-8");
    let no_prefix = compare(Fixture { prefix: None, output: None }, false);
    assert_eq!(no_prefix.0.unwrap_err().label, "synthetic prefix failure");
    assert_eq!(no_prefix.3, [Call::Prefix]);
    let no_result = compare(Fixture { prefix: Some("scope/"), output: None }, false);
    assert_eq!(no_result.0.unwrap_err().label, "synthetic runner failure");
    assert_eq!(no_result.3, [Call::Prefix, Call::Read(MAX_BYTES)]);
    let mut cap_only = frames(&[ONE, b""]);
    cap_only.resize(MAX_BYTES, 255);
    let capped = paired(Fixture::new(cap_only).truncated()).unwrap();
    assert!(capped.truncated && capped.entries.len() == 1);
    let no_complete = paired(Fixture::new(vec![255; MAX_BYTES])).unwrap();
    assert!(!no_complete.truncated && no_complete.entries.is_empty());
}

#[test]
fn limit_after_eligible_parse_and_header_order() {
    let make = || frames(&vec![b"? scope/existing".as_slice(); MAX_ENTRIES]);
    let mut same = make();
    same.extend(frames(&[b"? outside/miss", b"# branch.head after-cap"]));
    let at_limit = paired(Fixture::new(same.clone())).unwrap();
    assert_eq!(at_limit.entries.len(), MAX_ENTRIES);
    assert!(!at_limit.truncated && at_limit.branch.as_deref() == Some("after-cap"));
    let mut bad = same.clone();
    bad.extend(frames(&[b"\xff", b"? scope/next"]));
    fails(Fixture::new(bad), "Git status is not UTF-8");
    let mut malformed = same.clone();
    malformed.extend(frames(&[b"1 M. N..."]));
    fails(Fixture::new(malformed), "invalid Git status record");
    same.extend(frames(&[b"? scope/next", b"\xff", b"# branch.head not-reached"]));
    let stopped = paired(Fixture::new(same)).unwrap();
    assert!(stopped.truncated && stopped.branch.as_deref() == Some("after-cap"));
    assert_eq!(stopped.entries.len(), MAX_ENTRIES);
}

#[test]
fn deterministic_varied_field_counts_and_framed_bytes() {
    let mut state = 42u32;
    let mut next = || {
        state = state.wrapping_mul(1664525).wrapping_add(1013904223);
        state >> 16
    };
    for row in [ONE, TWO, CONFLICT_ROW] {
        for stop in 0..=row.len() {
            for after in [b"scope/previous".as_slice(), b"\xff", b"", b"# branch.ab +7 -8"] {
                for truncated in [false, true] {
                    let fixture = Fixture::new(frames(&[&row[..stop], after, ONE]));
                    let _ = paired(if truncated { fixture.truncated() } else { fixture });
                }
            }
        }
    }
    for i in 0..4096 {
        let mut row = vec![b"12u?#"[i % 5]];
        for _ in 0..next() % 52 {
            let alphabet = b" a b9.\t\xff";
            row.push(alphabet[next() as usize % alphabet.len()]);
        }
        let mut raw = frames(&[&row, b"scope/previous", ONE]);
        raw.extend([b'x', 255]);
        let fixture = Fixture::new(raw);
        let _ = paired(if i % 2 == 0 { fixture } else { fixture.truncated() });
    }
}

#[test]
fn allocation_requests_thousand_tracked_records() {
    let rows = [
        b"1 M. N... 100644 000000 000000 base indexed scope/one".as_slice(),
        b"2 .R N... 100644 000000 100755 base renamed R100 scope/two",
        b"u UU N... 000000 000000 000000 100644 blob1 blob2 blob3 scope/conflict",
    ];
    let mut data = Vec::new();
    for i in 0..1000 {
        data.extend(frames(&[rows[i % 3]]));
        if i % 3 == 1 { data.extend(frames(&[b"scope/original"])); }
    }
    let (result, old, new, _) = compare(Fixture::new(data), true);
    let result = result.unwrap();
    assert_eq!(result.entries.len(), 1000);
    assert!(result.entries.iter().all(|e| e.index.is_empty()));
    assert!(old.alloc >= new.alloc + 1000);
    assert!(old.bytes >= new.bytes + 1000 * 9 * size_of::<&str>());
    println!("R231_ALLOC {} {} {} {} {} {}", old.alloc, old.realloc, old.bytes,
             new.alloc, new.realloc, new.bytes);
}
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ["stock", "git-ref", "revision-ref", "workspace-ref", "rustc", "work"]:
        parser.add_argument("--" + name, required=True, type=Path)
    args = parser.parse_args()
    stock = args.stock.read_bytes()
    patch = Path(__file__).with_name("source.patch").read_bytes()
    identity(stock, BASE_BLOB, BASE_SHA)
    check(hashlib.sha256(patch).hexdigest() == PATCH_SHA, "patch digest")
    candidate = replay(stock, patch)
    identity(candidate, AFTER_BLOB, AFTER_SHA)
    check(replay(candidate, patch, reverse=True) == stock, "exact rollback")
    refs = {}
    for key, blob, sha in REF:
        ref = getattr(args, key + "_ref").read_bytes()
        identity(ref, blob, sha)
        refs[key] = ref.decode()
    records = section(refs["git"], "fn complete_records(", "\n// Deleted files")
    stage = section(refs["revision"], "pub(super) fn stage(", "\npub(super) fn stages")
    caps = "\n".join(re.findall(r"^const MAX_(?:ENTRIES|BYTES): usize = .+;$",
                                refs["workspace"], re.M))
    check(len(caps.splitlines()) == 2, "exact status command limits")
    rustc = args.rustc.resolve(strict=True)
    check(hashlib.sha256(rustc.read_bytes()).hexdigest() == RUSTC_SHA, "compiler digest")
    with tempfile.TemporaryDirectory(prefix="r231-", dir=args.work.resolve(strict=True)) as temp:
        root = Path(temp)
        env = {"PATH": "/usr/bin:/bin", "HOME": temp, "TMPDIR": temp, "LC_ALL": "C"}
        version = subprocess.check_output([rustc, "--version"], cwd=root, env=env,
                                          text=True, timeout=20).strip()
        check(version == RUSTC_VERSION, "compiler version")
        lift = root / "lift.rs"
        lift.write_text(TESTS + "\n" + caps + "\n" + records
                        + "\nmod revision {\n" + stage + "\n}\n"
                        + make_lift("stock", stock.decode())
                        + make_lift("candidate", candidate.decode()), encoding="utf-8")
        results = {}
        for mode, flags in [("debug", []), ("optimized", ["-O"])]:
            exe = root / ("proof-" + mode)
            subprocess.run([rustc, "--edition=2024", "--test", "-Dwarnings", *flags,
                            lift, "-o", exe], cwd=root, env=env, check=True, timeout=90)
            run = subprocess.run([exe, "--nocapture", "--test-threads=1"], cwd=root,
                                 env=env, check=False, text=True, capture_output=True, timeout=60)
            check(run.returncode == 0, f"{mode} tests:\n{run.stdout}\n{run.stderr}")
            tests = re.search(r"test result: ok\. (\d+) passed; 0 failed;", run.stdout)
            counts = re.search(r"\bR231_ALLOC (\d+) (\d+) (\d+) (\d+) (\d+) (\d+)$",
                               run.stdout, re.M)
            check(tests is not None and int(tests[1]) == 7, "test count")
            check(counts is not None, "allocation receipt")
            c = [int(counts[i]) for i in range(1, 7)]
            results[mode] = {"tests_passed": int(tests[1]),
                             "stock_alloc_realloc_requested_bytes": c[:3],
                             "candidate_alloc_realloc_requested_bytes": c[3:]}
    print(json.dumps({"status": "PASS", "rustc": version, "rustc_sha256": RUSTC_SHA,
                      "exact_forward_and_reverse": True, "results": results,
                      "live_git_http_or_cargo": False}, indent=2))


if __name__ == "__main__":
    main()
