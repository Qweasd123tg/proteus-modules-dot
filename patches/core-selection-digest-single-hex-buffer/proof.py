#!/usr/bin/env python3
"""Replay the exact source patch and run the Rust 1.95 std-only digest text proof."""

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tempfile


PATH = "crates/proteus-core/src/app_server/session_selection.rs"
BASE_BLOB = "db457b126dac062377e4039edeb874e5732b2ff6"
BASE_SHA = "5c173af2269c51e169550188f5145ba65aa1a886e8e5c4622317410e804df34f"
AFTER_BLOB = "990b82e8006029887f96258f0d3c7097b0980fe4"
AFTER_SHA = "b9c69314f99ecde674b1aa68674d8d6b94b43537dabd3279c51607f72e3ca419"
PATCH_SHA = "ff990d57fb3148a711d918b4519e2f32185338bc00fe7da9ce85c54cb32aae79"


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
    check(count == 1, "expected one digest formatting hunk")
    return b"".join(target + lines[used:])


def section(source, first, end):
    at = source.index(first)
    return source[at:source.index(end, at + len(first))]


def make_lift(stock, candidate):
    old = section(stock, "fn sha256(", "pub(super) fn resolved_path(")
    hash_call = "    digest(&SHA256, bytes)\n        .as_ref()\n"
    check(old.count(hash_call) == 1, "stock digest-only injection point")
    old = old.replace(hash_call, "    bytes\n", 1)
    helper = section(candidate, "fn encode_digest(", "pub(super) fn resolved_path(")
    return (
        "mod stock {\n" + old
        + "pub(super) fn encode(bytes: &[u8]) -> String { sha256(bytes) }\n}\n"
        + "mod candidate {\n" + helper
        + "pub(super) fn encode(bytes: &[u8]) -> String { encode_digest(bytes) }\n}\n"
    )


TESTS = r'''
use std::alloc::{GlobalAlloc, Layout, System};
use std::cell::Cell;
use std::hint::black_box;

fn paired(bytes: &[u8]) -> String {
    let before = stock::encode(bytes);
    let after = candidate::encode(bytes);
    assert_eq!(after.as_bytes(), before.as_bytes(), "{bytes:?}");
    assert_eq!(after.len(), bytes.len() * 2);
    assert!(after.bytes().all(|byte| matches!(byte, b'0'..=b'9' | b'a'..=b'f')));
    after
}

#[test]
fn every_byte_and_every_ordered_pair() {
    for a in 0..=u8::MAX {
        assert_eq!(paired(&[a]), format!("{a:02x}"));
        for b in 0..=u8::MAX {
            assert_eq!(paired(&[a, b]), format!("{a:02x}{b:02x}"));
        }
    }
}

fn next(state: &mut u64) -> u8 {
    *state = state.wrapping_mul(6364136223846793005).wrapping_add(1442695040888963407);
    (*state >> 32) as u8
}

#[test]
fn generated_fixed_width_sha_shaped_digests() {
    let mut state = 225;
    let mut digest = [0; 32];
    for i in 0..12_000 {
        for byte in &mut digest {
            *byte = next(&mut state);
        }
        if i % 7 == 0 {
            digest[i % 32] &= 0x0f;
        }
        assert_eq!(paired(&digest).len(), 64);
    }
}

fn fixture_hex(hex: &str) -> [u8; 32] {
    assert_eq!(hex.len(), 64);
    std::array::from_fn(|i| u8::from_str_radix(&hex[2 * i..2 * i + 2], 16).unwrap())
}

#[test]
fn fixed_known_digest_bytes_and_selection_filename_width() {
    // Public SHA-256 reference byte values; the probe does not invoke or replace ring.
    for hex in [
        "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad",
        "d7a8fbb307d7809469ca9abcb0082e4f8d5651e46d3cdb762d02d0bf37c9e592",
        "0000000000000000000000000000000000000000000000000000000000000000",
        "00f0ff0001000000000000000000000000000000000000000000000000000fe0",
    ] {
        let text = paired(&fixture_hex(hex));
        assert_eq!(text, hex);
        assert_eq!(format!("{text}.json"), format!("{hex}.json"));
    }
}

#[test]
fn empty_and_variable_input_have_exact_widths() {
    assert_eq!(paired(&[]), "");
    assert_eq!(paired(&[0, 1, 15, 16, 255]), "00010f10ff");
    for len in [1, 3, 7, 31, 33, 63, 128, 257, 511] {
        let bytes = vec![0xab; len];
        assert_eq!(paired(&bytes), "ab".repeat(len));
    }
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

fn measured(f: impl FnOnce() -> String) -> (String, usize) {
    ALLOC_EVENTS.with(|count| {
        assert_eq!(count.get(), None);
        count.set(Some(0));
        let value = black_box(f());
        let operations = count.replace(None).unwrap();
        (value, operations)
    })
}

#[test]
fn measure_only_one_formatter_on_fixed_stack_bytes() {
    let input = fixture_hex("ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad");
    let (old, old_ops) = measured(|| stock::encode(black_box(&input)));
    let (new, new_ops) = measured(|| candidate::encode(black_box(&input)));
    assert_eq!(old, new);
    assert!(old_ops >= input.len());
    assert_eq!(new_ops, 1);
    println!("digest format allocation operations: {old_ops} -> {new_ops}");
}
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stock", required=True, type=Path, help="exact unpatched session_selection.rs")
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
    stock, candidate = (source.decode() for source in (stock, candidate))
    check(stock.split("fn sha256(", 1)[0] == candidate.split("fn sha256(", 1)[0],
          "digest imports and earlier source unchanged")
    boundary = "pub(super) fn resolved_path("
    check(stock.split(boundary, 1)[1] == candidate.split(boundary, 1)[1],
          "binding, paths and persistence source unchanged")
    for code in [stock, candidate]:
        check(code.count("digest(&SHA256, bytes)") == 1, "same ring algorithm and input")
    tests = {}
    counters = {}
    with tempfile.TemporaryDirectory(prefix="r225-proof-", dir=args.work_dir) as directory:
        root = Path(directory).resolve()
        env = {"PATH": "/usr/bin:/bin", "LC_ALL": "C", "HOME": str(root), "TMPDIR": str(root)}
        version = subprocess.check_output([args.rustc, "--version", "--verbose"],
                                          cwd=root, env=env, text=True)
        check("release: 1.95.0\n" in version and "host: x86_64-unknown-linux-gnu\n" in version,
              "expected Linux x86-64 Rust 1.95.0")
        root.joinpath("proof.rs").write_text(make_lift(stock, candidate) + TESTS, encoding="utf-8")
        for mode, extra in [("debug", []), ("optimized", ["-O"])]:
            subprocess.run([args.rustc, "--edition=2024", "--test", "-Dwarnings", *extra,
                            "proof.rs", "-o", "proof-bin"], cwd=root, env=env, check=True)
            final = subprocess.run([root / "proof-bin", "--test-threads=1", "--nocapture"],
                                   cwd=root, env=env, text=True, capture_output=True)
            check(final.returncode == 0, f"{mode} proof failed:\n{final.stdout}\n{final.stderr}")
            check("5 passed; 0 failed; 0 ignored;" in final.stdout, f"{mode} expected five tests")
            match = re.search(r"digest format allocation operations: (\d+) -> (\d+)", final.stdout)
            check(match is not None, f"{mode} missing allocator witness")
            tests[mode] = 5
            counters[mode] = list(map(int, match.groups()))
    print(json.dumps({
        "status": "PASS",
        "rustc": version.splitlines()[0],
        "rustc_binary_sha256": hashlib.sha256(args.rustc.read_bytes()).hexdigest(),
        "candidate_git_blob": AFTER_BLOB,
        "candidate_sha256": AFTER_SHA,
        "patch_sha256": PATCH_SHA,
        "exact_forward_and_reverse_patch": True,
        "native_std_only_tests_passed": tests,
        "single_u8_and_ordered_pair_checks_per_mode": 65792,
        "generated_32_byte_inputs_per_mode": 12000,
        "formatter_only_alloc_realloc_zeroed_before_then_after": counters,
        "real_ring_persistence_or_whole_core": False,
    }, indent=2))


if __name__ == "__main__":
    main()
