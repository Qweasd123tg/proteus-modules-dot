#!/usr/bin/env python3
"""Replay the exact source patch and run the Rust 1.95 std-only display proof."""

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tempfile


PATH = "crates/proteus-core/src/core/session_store/context_summary.rs"
BASE_BLOB = "5eed456f2ceca5d9d631cc54f2f3309227e392a7"
BASE_SHA = "20e0efa411b092fb74c856cbbef6b328c903192609d241cec10769980b13243a"
AFTER_BLOB = "1e54f93328a4ae8d0d8ec32c55c7d4fda0dab263"
AFTER_SHA = "70bd938b8dfcce6e1e6141d4acc5dc99793a70067ba7e79988de2bb2d51e8bf1"
PATCH_SHA = "450b726d3f9a2c4c950c45a18a7e84b0bbdcb5908657187cf06c561eb04e9f9d"


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
    check(count == 2, "expected helper and display call-site hunks only")
    return b"".join(target + lines[used:])


def make_lift(source, candidate):
    source = source.decode()
    start = source.index("pub(crate) fn summarize_context_history(")
    counter = source[source.index("fn path_display_bytes("):start] if candidate else ""
    display = "path_display_bytes(path)" if candidate else "path.display().to_string().len()"
    check(source.count(display) == 2, "exact two display sizing expressions")
    # Only the imports and serde byte seam are adapted. The summary and token functions
    # and the candidate formatter are copied verbatim from the authenticated inputs.
    return (
        "use crate::shape::*;\nuse std::path::Path;\n"
        + ("use std::fmt;\n" if candidate else "")
        + "fn json_bytes(value: &JsonBytes) -> usize { value.0 }\n"
        + counter + source[start:]
        + f"pub(super) fn display(path: &Path) -> usize {{ {display} }}\n"
        + "pub(super) fn estimate(bytes: usize) -> u32 { estimate_tokens_from_bytes(bytes) }\n"
    )


TESTS = r'''
mod shape {
    use std::path::PathBuf;

    #[derive(Debug, Default, PartialEq, Eq)]
    pub struct AppContextHistorySummary {
        pub messages: usize,
        pub user_messages: usize,
        pub assistant_messages: usize,
        pub system_messages: usize,
        pub tool_results: usize,
        pub estimated_tokens: u32,
    }

    // This is the precomputed size of a synthetic JSON value, not a serializer.
    pub struct JsonBytes(pub usize);
    pub struct CanonicalMessage {
        pub metadata: JsonBytes,
        pub role: MessageRole,
        pub parts: Vec<Part>,
    }
    pub enum MessageRole { User, Assistant, System, Developer, Tool, Other }
    pub struct Part { pub payload: ContentPart }
    pub struct Chunk {
        pub source: String,
        pub path: Option<PathBuf>,
        pub content: String,
        pub metadata: JsonBytes,
    }
    pub struct Call { pub name: String, pub args: JsonBytes }
    pub struct ResultData {
        pub output: String,
        pub error: Option<String>,
        pub metadata: JsonBytes,
        pub content: Vec<JsonBytes>,
    }
    pub struct PatchData { pub content: String }
    pub enum ContentPart {
        Text { text: String },
        ReasoningSummary { text: String },
        Reasoning { text: String },
        Context { chunk: Chunk },
        FileRef { path: PathBuf, content: Option<String> },
        ToolCall { call: Call },
        ToolResult { result: ResultData },
        Patch { patch: PatchData },
        HostedToolActivity { activity: JsonBytes },
        Citation { citation: JsonBytes },
        Other,
    }
}

use std::alloc::{GlobalAlloc, Layout, System};
use std::cell::Cell;
use std::ffi::OsStr;
use std::hint::black_box;
use std::os::unix::ffi::OsStrExt;
use std::path::Path;
use shape::*;

fn path(raw: &[u8]) -> &Path {
    Path::new(OsStr::from_bytes(raw))
}

#[test]
fn display_replacements_and_literal_separators() {
    let fixtures: &[(&[u8], &str)] = &[
        (b"", ""),
        (b"/x/.././y", "/x/.././y"),
        (b"a\\b \t\0\"'", "a\\b \t\0\"'"),
        ("рус/策略/🙂".as_bytes(), "рус/策略/🙂"),
        (b"\xFF", "�"),
        (b"\xE2\x82", "�"),
        (b"a\xF0\x90\x80/b", "a�/b"),
        (b"\xED\xA0\x80", "���"),
        (b"\xFF\xFE\x80", "���"),
        (b"\xC2\x80\0", "\u{80}\0"),
        (b"\xC0\xAF", "��"),
        (b"\xF4\x90\x80\x80", "����"),
    ];
    for &(raw, expected) in fixtures {
        assert_eq!(path(raw).display().to_string(), expected);
        assert_eq!((stock::display(path(raw)), candidate::display(path(raw))),
                   (expected.len(), expected.len()));
    }
}

#[test]
fn exhaustive_short_opaque_paths() {
    let palette = [0, b'/', b'\\', b'\t', b'A', b' ', 0x7f, 0x80, 0xbf, 0xc0,
                   0xc2, 0xe2, 0xed, 0xf0, 0xf4, 0xff];
    let mut raw = [0; 4];
    let mut pairs = 0;
    for len in 0..=4 {
        for mut value in 0..palette.len().pow(len as u32) {
            for byte in &mut raw[..len] {
                *byte = palette[value % palette.len()];
                value /= palette.len();
            }
            let p = path(&raw[..len]);
            assert_eq!(candidate::display(p), stock::display(p));
            pairs += 1;
        }
    }
    assert_eq!(pairs, 69_905);
}

fn next(state: &mut u64) -> u64 {
    *state = state.wrapping_mul(6364136223846793005).wrapping_add(1442695040888963407);
    *state
}

fn large_path() -> Vec<u8> {
    let pattern = b"/x\0\xff\xe2\x82/\xf0\x9f\x99\x82\t\xed\xa0\x80";
    pattern.iter().copied().cycle().take(1024 * 1024).collect()
}

#[test]
fn generated_byte_paths_and_one_mib_mixed_path() {
    let mut state = 211;
    let mut raw = [0; 97];
    for _ in 0..25_000 {
        let len = (next(&mut state) >> 32) as usize % (raw.len() + 1);
        for byte in &mut raw[..len] {
            *byte = (next(&mut state) >> 32) as u8;
        }
        let raw = &raw[..len];
        let expected = String::from_utf8_lossy(raw).len();
        assert_eq!((stock::display(path(raw)), candidate::display(path(raw))),
                   (expected, expected));
    }
    let large = large_path();
    let p = path(&large);
    assert_eq!(candidate::display(p), stock::display(p));
}

thread_local! {
    static ALLOC_EVENTS: Cell<Option<usize>> = const { Cell::new(None) };
}

fn record_allocation() {
    let _ = ALLOC_EVENTS.try_with(|count| {
        if let Some(n) = count.get() {
            count.set(Some(n.saturating_add(1)));
        }
    });
}

struct CountingAllocator;
unsafe impl GlobalAlloc for CountingAllocator {
    unsafe fn alloc(&self, layout: Layout) -> *mut u8 {
        record_allocation();
        unsafe { System.alloc(layout) }
    }
    unsafe fn alloc_zeroed(&self, layout: Layout) -> *mut u8 {
        record_allocation();
        unsafe { System.alloc_zeroed(layout) }
    }
    unsafe fn realloc(&self, ptr: *mut u8, layout: Layout, size: usize) -> *mut u8 {
        record_allocation();
        unsafe { System.realloc(ptr, layout, size) }
    }
    unsafe fn dealloc(&self, ptr: *mut u8, layout: Layout) {
        unsafe { System.dealloc(ptr, layout) }
    }
}
#[global_allocator]
static ALLOCATOR: CountingAllocator = CountingAllocator;

fn measured(f: impl FnOnce() -> usize) -> (usize, usize) {
    ALLOC_EVENTS.with(|count| {
        assert_eq!(count.get(), None);
        count.set(Some(0));
        let value = black_box(f());
        let operations = count.replace(None).unwrap();
        (value, operations)
    })
}

#[test]
fn allocation_witness_only_around_lifted_display_helpers() {
    let large = large_path();
    let ascii = vec![b'x'; 8192];
    for raw in [&ascii[..], &b"x/\xF0\x90\x80../\xff"[..], "策略/🙂".as_bytes(), &large[..]] {
        let p = path(raw);
        let expected = String::from_utf8_lossy(raw).len();
        let (old, old_allocs) = measured(|| stock::display(black_box(p)));
        let (new, new_allocs) = measured(|| candidate::display(black_box(p)));
        assert_eq!((old, new), (expected, expected));
        assert!(old_allocs > 0);
        assert_eq!(new_allocs, 0);
    }
}

fn message(role: MessageRole, metadata: usize, parts: Vec<ContentPart>) -> CanonicalMessage {
    CanonicalMessage {
        role,
        metadata: JsonBytes(metadata),
        parts: parts.into_iter().map(|payload| Part { payload }).collect(),
    }
}

fn summarize_pair(messages: &[CanonicalMessage], expected: AppContextHistorySummary) {
    assert_eq!(stock::summarize_context_history(messages), expected);
    assert_eq!(candidate::summarize_context_history(messages), expected);
}

#[test]
fn exact_summary_functions_with_precomputed_json_lengths() {
    use ContentPart::*;
    let p = path(b"x\xF0\x90\x80/").to_owned();
    let messages = [
        message(MessageRole::User, 3, vec![
            FileRef { path: p.clone(), content: Some("ok".into()) },
            Context { chunk: Chunk { source: "策略".into(), path: Some(p), content: "abc".into(),
                                     metadata: JsonBytes(2) } },
            Context { chunk: Chunk { source: String::new(), path: None, content: "x".into(),
                                     metadata: JsonBytes(4) } },
            Text { text: "🙂".into() },
        ]),
        message(MessageRole::Assistant, 1, vec![
            ToolCall { call: Call { name: "do".into(), args: JsonBytes(5) } },
            ToolResult { result: ResultData { output: "ok".into(), error: Some("error".into()),
                           metadata: JsonBytes(6), content: vec![JsonBytes(3), JsonBytes(1)] } },
            Patch { patch: PatchData { content: "ok".into() } },
            HostedToolActivity { activity: JsonBytes(8) },
            Citation { citation: JsonBytes(9) },
            ReasoningSummary { text: "why".into() },
            Reasoning { text: "reason".into() },
        ]),
        message(MessageRole::System, 0, vec![]),
        message(MessageRole::Developer, 0, vec![]),
        message(MessageRole::Tool, 0, vec![]),
        message(MessageRole::Other, 0, vec![Other]),
    ];
    summarize_pair(&messages, AppContextHistorySummary {
        messages: 6, user_messages: 1, assistant_messages: 1, system_messages: 2,
        tool_results: 1, estimated_tokens: 28,
    });
    summarize_pair(&[], AppContextHistorySummary::default());
}

#[test]
fn both_path_part_branches_at_floor_boundaries_and_u32_clamp() {
    use ContentPart::*;
    let mut state = 211;
    let mut raw = [0; 24];
    for i in 0..4096 {
        for byte in &mut raw[..i % 24] {
            *byte = (next(&mut state) >> 32) as u8;
        }
        let bytes = &raw[..i % 24];
        let plain = String::from_utf8_lossy(bytes).len();
        let fixture = match i % 2 {
            0 => Context { chunk: Chunk { source: String::new(), path: Some(path(bytes).to_owned()),
                                          content: "x".repeat(i % 4), metadata: JsonBytes(0) } },
            _ => FileRef { path: path(bytes).to_owned(), content: Some("x".repeat(i % 4)) },
        };
        summarize_pair(&[message(MessageRole::User, 0, vec![fixture])],
                       AppContextHistorySummary { messages: 1, user_messages: 1,
                           estimated_tokens: ((4 + plain + i % 4) / 4) as u32,
                           ..AppContextHistorySummary::default() });
    }
    let mut cases = vec![(0,0), (1,1), (3,1), (4,1), (7,1), (8,2), (11,2), (12,3)];
    if let Ok(top) = usize::try_from(u64::from(u32::MAX) * 4 + 4) {
        cases.extend([(top - 5, u32::MAX - 1), (top - 4, u32::MAX),
                      (top - 1, u32::MAX), (top, u32::MAX), (usize::MAX, u32::MAX)]);
    }
    for (bytes, expected) in cases {
        assert_eq!((stock::estimate(bytes), candidate::estimate(bytes)), (expected, expected));
    }
}
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stock", required=True, type=Path, help="exact unpatched context_summary.rs")
    parser.add_argument("--rustc", required=True, type=Path, help="trusted installed Rust 1.95.0")
    parser.add_argument("--work-dir", required=True, type=Path, help="private writable scratch")
    args = parser.parse_args()
    check(args.rustc.is_absolute(), "use absolute rustc path")
    stock = args.stock.read_bytes()
    identity(stock, BASE_BLOB, BASE_SHA)
    patch = Path(__file__).with_name("source.patch").read_bytes()
    check(hashlib.sha256(patch).hexdigest() == PATCH_SHA, "patch SHA256")
    candidate = replay(stock, patch)
    identity(candidate, AFTER_BLOB, AFTER_SHA)
    check(replay(candidate, patch, True) == stock, "exact reverse patch")
    for name in (b"fn json_bytes", b"fn estimate_tokens_from_bytes"):
        chunks = [code.split(name, 1)[1].split(b"\n}\n", 1)[0] for code in (stock, candidate)]
        check(chunks[0] == chunks[1], "unchanged JSON and token arithmetic")
    passed = {}
    with tempfile.TemporaryDirectory(prefix="r211-proof-", dir=args.work_dir) as directory:
        root = Path(directory).resolve()
        env = {"PATH": "/usr/bin:/bin", "LC_ALL": "C", "HOME": str(root), "TMPDIR": str(root)}
        version = subprocess.check_output([args.rustc, "--version", "--verbose"],
                                          cwd=root, env=env, text=True)
        check("release: 1.95.0\n" in version and "host: x86_64-unknown-linux-gnu\n" in version,
              "expected Linux x86-64 Rust 1.95.0")
        root.joinpath("proof.rs").write_text(
            "mod stock {\n" + make_lift(stock, False) + "}\nmod candidate {\n"
            + make_lift(candidate, True) + "}\n" + TESTS, encoding="utf-8"
        )
        for mode, extra in [("debug", []), ("optimized", ["-O"])]:
            subprocess.run([args.rustc, "--edition=2024", "--test", "-Dwarnings", *extra,
                            "proof.rs", "-o", "proof-bin"], cwd=root, env=env, check=True)
            output = subprocess.check_output([root / "proof-bin", "--test-threads=1"],
                                             cwd=root, env=env, text=True)
            check("6 passed; 0 failed; 0 ignored;" in output, f"{mode} proof did not pass")
            passed[mode] = 6
    print(json.dumps({
        "status": "PASS",
        "rustc": version.splitlines()[0],
        "rustc_binary_sha256": hashlib.sha256(args.rustc.read_bytes()).hexdigest(),
        "candidate_git_blob": AFTER_BLOB,
        "candidate_sha256": AFTER_SHA,
        "patch_sha256": PATCH_SHA,
        "exact_forward_and_reverse_patch": True,
        "native_std_only_tests_passed": passed,
        "exhaustive_short_path_pairs_per_mode": 69905,
        "generated_raw_path_pairs_per_mode": 25000,
        "generated_path_part_pairs_per_mode": 4096,
        "long_path_bytes": 1048576,
        "allocation_witness": "four nonempty Linux path fixtures per mode: stock >0; candidate 0 (alloc/realloc/alloc_zeroed within display helper only)",
        "real_serializer_or_whole_core": False,
    }, indent=2))


if __name__ == "__main__":
    main()
