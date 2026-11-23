#!/usr/bin/env python3
"""Replay and verify the exact Rust 1.95 rg scratch reuse patch."""

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tempfile


PATH = "context_provider/rg-search/src/lib.rs"
BASE_BLOB = "5d5c5a35fa5c19f6824d941c8b8c03b17805b181"
BASE_SHA = "bb26f2ead2c3df2aa47d48ff32c8fa2367793cc97c75bb94a0227cd66b285baa"
AFTER_BLOB = "1b8b95923b6a0c83fc3cecbc5b58b9fadba8ce49"
AFTER_SHA = "f90abf916169121367f72d42e94a1affcb081dc0250c47b49872f37bb058f4d2"
PATCH_SHA = "3010b9ff403fe326eea587c9c9c422922eeeb73b4a235bab597d74067265069e"


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
    check(count == 1, "expected one line reader hunk")
    return b"".join(target + lines[used:])


def section(source, first, end):
    at = source.index(first)
    return source[at:source.index(end, at + len(first))]


RUSTC_SHA = "bff349e72704ff70bc08a234a3847338e797065bbedde5e556808bc87b7bf7c6"
RUSTC_VERSION = "rustc 1.95.0 (59807616e 2026-04-14)"
LOCKED_CORE = "0c1b7572313230e5d123e95c722e1258a2e9ecd6"
START = "fn read_rg_matches("
PARSE = "\nfn parse_rg_match("
END = "\npub fn register_modules("
REFS = {
    "matcher": ("c5c2a9f744e2d3ade6db570732f544da8f97398c",
                "9bd27a320b2d557091cdfb909ea0c7df431647769e67f8e4dcde188c472c7c62"),
    "lock": ("ae7035fc5900b0afc480e55d2408c8234c88dd17",
             "0b4717cd37ba4b5848068f64c52e863000d8d7ea6d90464f4a134689e45bef54"),
    "stdio": ("623c34c6d2910bf5df829e8907d4e2e49880a228",
              "6dc2214a87c8f1b1b90c99f1a447ce76e7dfcf0c762fc46b9432343525491fdf"),
}


def lift(name, source):
    return (
        f"mod {name} {{\nuse crate::*;\n"
        + section(source, START, END)
        + """
pub(super) fn run(reader: impl BufRead, query: &SearchQuery)
    -> std::io::Result<(Vec<ContextChunk>, bool)>
{
    read_rg_matches(reader, query)
}
}
"""
    )


TESTS = r'''
use std::{
    alloc::{GlobalAlloc, Layout, System},
    cell::{Cell, RefCell},
    hint::black_box,
    io::{self, BufRead, BufReader, Cursor, ErrorKind, Read},
    path::PathBuf,
};

#[derive(Debug, Eq, PartialEq)]
struct ContextChunk { source: &'static str, content: String, path: Option<PathBuf>, line: u64 }
impl ContextChunk {
    fn new(source: &'static str, content: String) -> Self {
        Self { source, content, path: None, line: 0 }
    }
    fn with_path(mut self, path: PathBuf) -> Self { self.path = Some(path); self }
    fn with_metadata(mut self, line: u64) -> Self { self.line = line; self }
}
macro_rules! json { ({ "line": $line:ident }) => { $line }; }

#[derive(Clone, Copy)]
enum Value {
    Object(&'static [(&'static str, Value)]),
    String(&'static str),
    U64(u64),
}
impl Value {
    fn get(&self, key: &str) -> Option<&Value> {
        match self {
            Self::Object(pairs) => pairs.iter().find(|(k, _)| *k == key).map(|(_, v)| v),
            _ => None,
        }
    }
    fn as_str(&self) -> Option<&str> { if let Self::String(s) = self { Some(s) } else { None } }
    fn as_u64(&self) -> Option<u64> { if let Self::U64(n) = self { Some(*n) } else { None } }
}
const BEGIN: &str = r#"{"type":"begin"}"#;
const A: &str = r#"{"type":"match","data":{"path":{"text":"./src/α.rs"},"line_number":7,"lines":{"text":"alpha\r\n"}}}"#;
const B: &str = r#"{"type":"match","data":{"path":{"text":"src/β.rs"},"line_number":8,"lines":{"text":"beta"}}}"#;
const OTHER: &str = r#"{"type":"match","data":{"path":{"text":"tests/α.rs"},"line_number":3,"lines":{"text":"test"}}}"#;
const SUFFIX: &str = r#"{"type":"match","data":{"path":{"text":"src/a.md"},"line_number":4,"lines":{"text":"doc"}}}"#;
const NO_TEXT: &str = r#"{"type":"match","data":{"path":{"bytes":"AA=="}}}"#;
const GIANT_START: &str = r#"{"type":"match","padding":""#;
const GIANT_END: &str = r#"","data":{"path":{"text":"src/wide.rs"},"line_number":9,"lines":{"text":"wide"}}}"#;
macro_rules! model {
    ($path:literal,$n:literal,$body:literal) => {
        Value::Object(&[
            ("type", Value::String("match")),
            ("data", Value::Object(&[
                ("path", Value::Object(&[("text", Value::String($path))])),
                ("line_number", Value::U64($n)),
                ("lines", Value::Object(&[("text", Value::String($body))])),
            ])),
        ])
    };
}
thread_local! {
    static PARSES: RefCell<Option<Vec<String>>> = const { RefCell::new(None) };
}
mod serde_json {
    use super::*;
    pub(super) fn from_str(line: &str) -> std::result::Result<Value, ()> {
        PARSES.with_borrow_mut(|trace| {
            if let Some(trace) = trace { trace.push(line.to_owned()); }
        });
        // Inert exact fixture recognizer; production from_str is intentionally not run.
        let fixture = line.trim_end_matches('\r');
        Ok(match fixture {
            BEGIN => Value::Object(&[("type", Value::String("begin"))]),
            A => model!("./src/α.rs", 7, "alpha\r\n"),
            B => model!("src/β.rs", 8, "beta"),
            OTHER => model!("tests/α.rs", 3, "test"),
            SUFFIX => model!("src/a.md", 4, "doc"),
            NO_TEXT => Value::Object(&[
                ("type", Value::String("match")),
                ("data", Value::Object(&[("path", Value::Object(&[]))])),
            ]),
            s if s.strip_prefix(GIANT_START)
                .and_then(|s| s.strip_suffix(GIANT_END))
                .is_some_and(|p| p.len() >= 65536 && p.bytes().all(|b| b == b'x')) =>
                    model!("src/wide.rs", 9, "wide"),
            _ => return Err(()),
        })
    }
}

struct Input<'a> {
    bytes: &'a [u8], offset: usize, fragment: usize,
    fault: Option<(usize, ErrorKind)>, fired: bool,
}
impl Read for Input<'_> {
    fn read(&mut self, dst: &mut [u8]) -> io::Result<usize> {
        let mut end = self.bytes.len();
        if let Some((at, kind)) = self.fault && !self.fired {
            assert!(at <= end && self.offset <= at);
            if at == self.offset {
                self.fired = true;
                return Err(io::Error::new(kind, "injected only"));
            }
            end = at;
        }
        let count = (end - self.offset).min(dst.len()).min(self.fragment);
        dst[..count].copy_from_slice(&self.bytes[self.offset..self.offset + count]);
        self.offset += count;
        Ok(count)
    }
}
#[derive(Debug, Clone, Copy, Eq, PartialEq)]
struct ReadMark { before_capacity: usize, after_capacity: usize, consumed: usize, kind: Option<ErrorKind> }
struct Witness<'a, 'b> {
    inner: BufReader<Input<'a>>,
    calls: &'b mut Vec<ReadMark>,
}
impl Read for Witness<'_, '_> {
    fn read(&mut self, dst: &mut [u8]) -> io::Result<usize> { self.inner.read(dst) }
}
impl BufRead for Witness<'_, '_> {
    fn fill_buf(&mut self) -> io::Result<&[u8]> { self.inner.fill_buf() }
    fn consume(&mut self, n: usize) { self.inner.consume(n); }
    fn read_line(&mut self, text: &mut String) -> io::Result<usize> {
        assert!(text.is_empty(), "read_line must see an empty scratch");
        let before_capacity = text.capacity();
        let result = self.inner.read_line(text);
        self.calls.push(ReadMark {
            before_capacity, after_capacity: text.capacity(),
            consumed: self.inner.get_ref().offset - self.inner.buffer().len(),
            kind: result.as_ref().err().map(io::Error::kind),
        });
        result
    }
}
type Reply = Result<(Vec<ContextChunk>, bool), (ErrorKind, String)>;
struct Outcome { reply: Reply, parses: Vec<String>, reads: Vec<ReadMark> }
fn pair(bytes: &[u8], query: &SearchQuery, frag: usize, fault: Option<(usize, ErrorKind)>)
    -> (Outcome, Outcome)
{
    let run = |new| {
        assert!(PARSES.replace(Some(Vec::new())).is_none());
        let mut reads = Vec::new();
        let input = Input { bytes, offset: 0, fragment: frag, fault, fired: false };
        let reader = Witness { inner: BufReader::with_capacity(frag, input), calls: &mut reads };
        let result = if new { candidate::run(reader, query) } else { stock::run(reader, query) };
        let reply = result.map_err(|e| (e.kind(), e.to_string()));
        Outcome { reply, parses: PARSES.take().unwrap(), reads }
    };
    let old = run(false);
    let new = run(true);
    assert_eq!(old.reply, new.reply);
    assert_eq!(old.parses, new.parses);
    assert_eq!(old.reads.iter().map(|r| (r.consumed, r.kind)).collect::<Vec<_>>(),
               new.reads.iter().map(|r| (r.consumed, r.kind)).collect::<Vec<_>>());
    assert!(old.reads.iter().all(|r| r.before_capacity == 0));
    assert!(new.reads.iter().all(|r| r.before_capacity <= 8 * 1024));
    (old, new)
}
fn q(limit: usize) -> SearchQuery {
    SearchQuery::new("fixture", PathBuf::from("/private/inert"), limit)
        .with_use_case("scratch witness")
        .with_path_filters(["././src/"], [".rs"])
}
fn rows(lines: &[&str]) -> Vec<u8> { (lines.join("\n") + "\n").into_bytes() }

#[test]
fn exact_newline_lf_crlf_bare_cr_and_eof() {
    let data = format!("\n{BEGIN}\n{A}\r\n{BEGIN}\r\r\n{B}\r");
    let got = pair(data.as_bytes(), &q(10), 3, None).1;
    assert_eq!(got.parses, ["", BEGIN, A, &format!("{BEGIN}\r"), &format!("{B}\r")]);
    assert_eq!(got.reads.last().unwrap().consumed, data.len());
    let (chunks, hit) = got.reply.unwrap();
    assert!(!hit);
    assert_eq!(chunks.iter().map(|c| c.content.as_str()).collect::<Vec<_>>(), ["alpha", "beta"]);
    assert_eq!(chunks.iter().map(|c| c.line).collect::<Vec<_>>(), [7, 8]);
}

#[test]
fn real_matcher_filters_before_cap_and_parses_once() {
    let query = q(2);
    assert_eq!(query.text, "fixture");
    assert_eq!(query.cwd, PathBuf::from("/private/inert"));
    assert_eq!(query.use_case.as_deref(), Some("scratch witness"));
    let data = rows(&[BEGIN, OTHER, NO_TEXT, SUFFIX, A, B, A]);
    let got = pair(&data, &query, 16, None).1;
    assert_eq!(got.parses, [BEGIN, OTHER, NO_TEXT, SUFFIX, A, B]);
    let (chunks, hit) = got.reply.unwrap();
    assert!(hit);
    assert_eq!(chunks[0].path.as_deref().unwrap().to_str(), Some("src/α.rs"));
    assert_eq!(chunks[1].path.as_deref().unwrap().to_str(), Some("src/β.rs"));
    assert!(chunks.iter().all(|c| c.source == "rg"));
    assert!(got.reads.last().unwrap().consumed < data.len());
}

#[test]
fn zero_limit_and_io_error_order_before_and_after_accepted_hit() {
    let fault = ErrorKind::PermissionDenied;
    let data = rows(&[OTHER, A, B]);
    let start_a = OTHER.len() + 1;
    let end_a = start_a + A.len() + 1;
    let none = pair(&data, &q(0), 7, Some((0, fault))).1;
    assert!(none.reads.is_empty() && none.parses.is_empty());
    assert_eq!(none.reply.unwrap(), (Vec::new(), false));
    let before = pair(&data, &q(1), 7, Some((start_a + 6, fault))).1;
    assert_eq!(before.reply.unwrap_err().0, fault);
    assert_eq!(before.parses, [OTHER]);
    let after = pair(&data, &q(1), 7, Some((end_a, fault))).1;
    assert!(after.reply.unwrap().1);
    assert_eq!(after.parses, [OTHER, A]);
    let still_needed = pair(&data, &q(2), 7, Some((end_a, fault))).1;
    assert_eq!(still_needed.reply.unwrap_err().0, fault);
    assert_eq!(still_needed.parses, [OTHER, A]);
}

#[test]
fn invalid_utf8_and_interrupted_read_are_std_behavior() {
    let mut data = rows(&[A]);
    data.extend(b"bad\xff\n");
    let complete = pair(&data, &q(1), 2, None).1;
    assert!(complete.reply.unwrap().1);
    let reading = pair(&data, &q(2), 2, None).1;
    assert_eq!(reading.reply.unwrap_err().0, ErrorKind::InvalidData);
    assert_eq!(reading.parses, [A]);
    let early = pair(b"bad\xff\n", &q(1), 8, None).1;
    assert!(early.parses.is_empty());
    assert_eq!(early.reply.unwrap_err().0, ErrorKind::InvalidData);
    let body = rows(&[B]);
    let resumed = pair(&body, &q(1), 3, Some((6, ErrorKind::Interrupted))).1;
    assert!(resumed.reply.unwrap().1);
    assert_eq!(resumed.parses, [B]);
}

#[test]
fn large_valid_line_is_parsed_but_its_buffer_is_not_retained_next_read() {
    let giant = format!("{GIANT_START}{}{GIANT_END}", "x".repeat(65536));
    let data = rows(&[BEGIN, &giant, BEGIN, A]);
    let (_, got) = pair(&data, &q(4), 511, None);
    assert_eq!(got.parses, [BEGIN, &giant, BEGIN, A]);
    assert!(got.reads[1].before_capacity > 0);
    assert!(got.reads[1].after_capacity > 8 * 1024);
    assert_eq!(got.reads[2].before_capacity, 0);
    assert!(got.reads[3].before_capacity > 0);
    let (chunks, capped) = got.reply.unwrap();
    assert!(!capped);
    assert_eq!(chunks.iter().map(|c| c.line).collect::<Vec<_>>(), [9, 7]);
}

#[test]
fn generated_framing_filters_limits_and_failures() {
    let choices = [b"\r".as_slice(), b"\n", b"\r\n", b"\r\r\n", b"\0", b"\xff",
                   "界".as_bytes(), BEGIN.as_bytes(), A.as_bytes(), B.as_bytes(),
                   OTHER.as_bytes(), NO_TEXT.as_bytes(), b"garbage"];
    let mut state = 151u32;
    let mut next = |n: usize| {
        state = state.wrapping_mul(1664525).wrapping_add(1013904223);
        (state >> 16) as usize % n
    };
    for i in 0..4096 {
        let mut body = Vec::new();
        for _ in 0..next(14) { body.extend(choices[next(choices.len())]); }
        let fault = (i % 7 == 0).then(|| (next(body.len() + 1), ErrorKind::BrokenPipe));
        let _ = pair(&body, &q(i % 5), 1 + next(32), fault);
    }
}

#[derive(Clone, Copy, Debug, Default)]
struct Requests { alloc: usize, realloc: usize, bytes: usize }
thread_local! { static METER: Cell<Option<Requests>> = const { Cell::new(None) }; }
fn requested(bytes: usize, realloc: bool) {
    let _ = METER.try_with(|meter| {
        if let Some(mut sums) = meter.get() {
            sums.bytes += bytes;
            if realloc { sums.realloc += 1; } else { sums.alloc += 1; }
            meter.set(Some(sums));
        }
    });
}
struct Allocator;
unsafe impl GlobalAlloc for Allocator {
    unsafe fn alloc(&self, a: Layout) -> *mut u8 {
        requested(a.size(), false); unsafe { System.alloc(a) }
    }
    unsafe fn alloc_zeroed(&self, a: Layout) -> *mut u8 {
        requested(a.size(), false); unsafe { System.alloc_zeroed(a) }
    }
    unsafe fn realloc(&self, p: *mut u8, a: Layout, bytes: usize) -> *mut u8 {
        requested(bytes, true); unsafe { System.realloc(p, a, bytes) }
    }
    unsafe fn dealloc(&self, p: *mut u8, a: Layout) { unsafe { System.dealloc(p, a) } }
}
#[global_allocator]
static ALLOCATOR: Allocator = Allocator;

#[test]
fn bounded_churn_measured_on_4096_nonmatch_lines() {
    let body = rows(&vec![BEGIN; 4096]);
    let query = q(1);
    let run = |new| {
        let read = Cursor::new(black_box(body.as_slice()));
        assert!(PARSES.with_borrow(|p| p.is_none()));
        assert!(METER.replace(Some(Requests::default())).is_none());
        let result = black_box(if new { candidate::run(read, &query) } else { stock::run(read, &query) });
        let counts = METER.take().unwrap();
        assert_eq!(result.unwrap(), (vec![], false));
        counts
    };
    let (old, new) = (run(false), run(true));
    assert_eq!(old.alloc, 4096);
    assert_eq!(new.alloc, 1);
    assert_eq!((old.realloc, new.realloc), (0,0));
    assert!(old.bytes > new.bytes);
    println!("R236_ALLOC {} {} {} {} {} {}", old.alloc, old.realloc, old.bytes,
             new.alloc, new.realloc, new.bytes);
}
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("stock", "matcher", "lock", "stdio", "rustc", "work"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    raw = args.stock.read_bytes()
    identity(raw, BASE_BLOB, BASE_SHA)
    patch = Path(__file__).with_name("source.patch").read_bytes()
    check(hashlib.sha256(patch).hexdigest() == PATCH_SHA, "patch digest")
    updated = replay(raw, patch)
    identity(updated, AFTER_BLOB, AFTER_SHA)
    check(replay(updated, patch, reverse=True) == raw, "exact rollback")
    old, new = raw.decode(), updated.decode()
    check(old[:old.index(START)] == new[:new.index(START)] and
          old[old.index(PARSE):] == new[new.index(PARSE):], "unchanged parser and context")
    refs = {}
    for key, (blob, digest) in REFS.items():
        ref = getattr(args, key).read_bytes()
        identity(ref, blob, digest)
        refs[key] = ref.decode()
    locked = re.search(r'\[\[package\]\]\nname = "proteus-contracts"\n[^\[]+', refs["lock"])
    check(locked is not None and f"?rev={LOCKED_CORE}#{LOCKED_CORE}" in locked[0], "SDK pin")
    std = section(refs["stdio"], "impl<B: BufRead> Iterator for Lines<B>", "\n}\n") + "\n}"
    check(all(fragment in std for fragment in (
        "let mut buf = String::new();", "match self.buf.read_line(&mut buf)",
        "Ok(0) => None", "if buf.ends_with('\\n') {", "if buf.ends_with('\\r') {",
        "Some(Ok(buf))", "Err(e) => Some(Err(e))",
    )), "pinned std Lines semantics")
    matcher = refs["matcher"].split("#[cfg(test)]", 1)[0]
    check(matcher.count("use serde::{Deserialize, Serialize};") == 1
          and matcher.count("#[serde(deny_unknown_fields)]") == 1
          and matcher.count("Debug, Clone, Serialize, Deserialize") == 1, "matcher serde seams")
    matcher = matcher.replace("use serde::{Deserialize, Serialize};", "")
    matcher = matcher.replace("#[serde(deny_unknown_fields)]", "")
    matcher = matcher.replace("Debug, Clone, Serialize, Deserialize", "Debug, Clone")
    matcher = matcher.replace("use std::path::PathBuf;\n", "", 1)
    rustc = args.rustc.resolve(strict=True)
    check(hashlib.sha256(rustc.read_bytes()).hexdigest() == RUSTC_SHA, "compiler digest")
    with tempfile.TemporaryDirectory(prefix="r236-", dir=args.work.resolve(strict=True)) as temp:
        root = Path(temp)
        env = {"PATH": "/usr/bin:/bin", "HOME": temp, "TMPDIR": temp, "LC_ALL": "C"}
        version = subprocess.check_output([rustc, "--version"], cwd=root, env=env,
                                          text=True, timeout=20).strip()
        check(version == RUSTC_VERSION, "compiler version")
        unit = root / "lift.rs"
        unit.write_text(TESTS + "\n" + matcher + lift("stock", old) + lift("candidate", new),
                        encoding="utf-8")
        results = {}
        for mode, flags in [("debug", []), ("optimized", ["-O"])]:
            exe = root / ("test-" + mode)
            subprocess.run([rustc, "--edition=2024", "--test", "-Dwarnings", *flags, unit,
                            "-o", exe], check=True, cwd=root, env=env, timeout=90)
            run = subprocess.run([exe, "--test-threads=1", "--nocapture"], cwd=root, env=env,
                                 capture_output=True, text=True, timeout=90)
            check(run.returncode == 0, f"{mode} tests:\n{run.stdout}\n{run.stderr}")
            tests = re.search(r"test result: ok\. (\d+) passed; 0 failed;", run.stdout)
            counts = re.search(r"\bR236_ALLOC (\d+) (\d+) (\d+) (\d+) (\d+) (\d+)$",
                               run.stdout, re.M)
            check(tests is not None and int(tests[1]) == 7, "test count")
            check(counts is not None, "allocation receipt")
            c = list(map(int, counts.groups()))
            results[mode] = {"tests_passed": int(tests[1]), "generated_pairs": 4096,
                             "stock_alloc_realloc_requested_bytes": c[:3],
                             "candidate_alloc_realloc_requested_bytes": c[3:]}
    print(json.dumps({"status": "PASS", "rustc": version, "rustc_sha256": RUSTC_SHA,
                      "exact_forward_and_reverse": True, "results": results,
                      "locked_matcher": LOCKED_CORE, "real_serde_rg_host_or_cargo": False}, indent=2))


if __name__ == "__main__":
    main()
