#!/usr/bin/env python3
"""Replay the exact source patch and run the Rust 1.95 std-only scorer proof."""

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tempfile


PATH = "crates/proteus-core/src/app_server/http/workspace/search.rs"
BASE_BLOB = "069326da4bf2f177efc0a4cc68472a5b34dc38e3"
BASE_SHA = "49c5993d30a8bd4c10c1d52c4b8f3d18367c2f66b77dab121f7ea8e5bdcc318a"
AFTER_BLOB = "bc4589dc3b680ca06d14f45fb6a56a1e24391dbe"
AFTER_SHA = "f7a2650792fc7ecc0585007b73666e588853b3c40e29d61dc5f4401741e47437"
PATCH_SHA = "25975bc5f9408948f23050d5a1eb9b2658000a9d90193cbac4c8e83d834a959e"


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
    check(count == 2, "expected the two score-only hunks")
    return b"".join(target + lines[used:])


def section(source, first, end):
    at = source.index(first)
    return source[at:source.index(end, at + len(first))]


def make_lift(source):
    terms = section(source, "fn terms(", "pub(crate) fn search(")
    score_tail = source[source.index("/// Every term must match the path;"):]
    ranks = section(source, "    let mut scored: Vec<(i64, &Candidate)>", "    let mut entries")
    return (
        "use crate::Candidate;\n" + terms + score_tail
        + "pub(super) fn query_terms(query: &str) -> Vec<String> { terms(query) }\n"
        + "pub(super) fn eval(terms: &[String], path: &str) -> Option<i64> { score(terms, path) }\n"
        + "pub(super) fn ranked<'a>(query: &str, candidates: &'a [Candidate]) "
          "-> Vec<(i64, &'a Candidate)> {\n"
        + "    let terms = terms(query);\n" + ranks + "    scored\n}\n"
    )


TESTS = r'''
use std::alloc::{GlobalAlloc, Layout, System};
use std::cell::Cell;
use std::hint::black_box;

fn pair(query: &str, path: &str) -> (Option<i64>, Option<i64>) {
    let terms = stock::query_terms(query);
    assert_eq!(terms, candidate::query_terms(query));
    (stock::eval(&terms, path), candidate::eval(&terms, path))
}

#[test]
fn explicit_unicode_and_ascii_score_paths() {
    for (query, path, expected) in [
        ("tree", "src/tree", Some(3999)),
        ("TREE", "src/TREE", Some(3999)),
        ("tree", "SRC/tree.RS", Some(2999)),
        ("tree", "src/subtree.rs", Some(1999)),
        ("tree", "tree/mod.rs", Some(999)),
        ("tree", "src/t_r_e_e.rs", Some(150)),
        ("tree", "src/main.rs", None),
        ("ος", "src/ΟΣ", Some(3999)),
        ("οσ", "src/ΟΣ", None),
        ("İ", "src/İ", Some(3999)),
        ("🙂", "x/🙂", Some(3999)),
        ("   ", "x/.", Some(-1)), // scorer only; live query rejects whitespace
        ("z", "a/\0\t.Z", Some(1999)), // synthetic scorer, not a live filename
    ] {
        assert_eq!(pair(query, path), (expected, expected), "{query:?} {path:?}");
    }
    for code in 0..=127_u8 {
        let ch = char::from(code);
        let path = format!("src/{ch}file.rs");
        for query in ["file", "src file", "sfr", "missing", " "] {
            let (a, b) = pair(query, &path);
            assert_eq!(a, b, "ASCII {code} {query:?}");
        }
    }
}

#[test]
fn scores_match_on_generated_ascii_and_unicode_matrix() {
    let atoms = ["A", "a", "B", "b", "/", "\\", "_", "-", " ", ".", "İ", "\u{307}",
                 "Σ", "ς", "🙂", "界"];
    let mut paths = Vec::new();
    for a in atoms {
        for b in atoms {
            for c in atoms {
                paths.push(format!("{a}{b}{c}"));
            }
        }
    }
    let mut queries = ["", "files tree", "İ", "ος", "οσ", "Я_Ж", "🙂\0", "\u{2003}A\tB"]
        .map(str::to_owned).to_vec();
    for a in atoms {
        for b in atoms {
            queries.push(format!("{a}{b}"));
        }
    }
    let mut pairs = 0;
    for query in &queries {
        let terms = stock::query_terms(query);
        assert_eq!(candidate::query_terms(query), terms);
        for path in &paths {
            assert_eq!(stock::eval(&terms, path), candidate::eval(&terms, path),
                       "{query:?} {path:?}");
            pairs += 1;
        }
    }
    assert_eq!(pairs, 1_081_344);
}

#[test]
fn actual_ranking_and_stable_raw_path_ties() {
    let paths = [("z/t", false), ("b/t", true), ("b/t", false), ("t", false),
                 ("t/tt", false), ("long/t", false), ("none", false), ("a/T", true)];
    let paths: Vec<_> = paths.into_iter()
        .map(|(path, directory)| Candidate { path: path.into(), directory })
        .collect();
    fn view(rows: Vec<(i64, &Candidate)>) -> Vec<(i64, &str, bool)> {
        rows.into_iter().map(|(score, row)| (score, row.path.as_str(), row.directory)).collect()
    }
    let expected = [(4000, "t", false), (3999, "a/T", true), (3999, "b/t", true),
                    (3999, "b/t", false), (3999, "z/t", false), (3999, "long/t", false),
                    (2999, "t/tt", false)];
    assert_eq!(view(stock::ranked("T", &paths)), expected);
    assert_eq!(view(candidate::ranked("T", &paths)), expected);
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

fn measured<T>(f: impl FnOnce() -> T) -> (T, usize) {
    ALLOC_EVENTS.with(|count| {
        assert_eq!(count.get(), None);
        count.set(Some(0));
        let value = black_box(f());
        let operations = count.replace(None).unwrap();
        (value, operations)
    })
}

#[test]
fn scorer_only_allocation_witness_lowercase_paths() {
    let paths: Vec<_> = (0..50_000).map(|i| {
        let segment = if i % 3 == 0 { "needle" } else { "branch" };
        format!("src/pkg_{:04}/{segment}/leaf_{i:05}.rs", i / 50)
    }).collect();
    let terms = stock::query_terms("needle leaf");
    let observed = |score: fn(&[String], &str) -> Option<i64>| {
        let mut matches = 0;
        let mut sum = 0;
        for path in &paths {
            if let Some(value) = score(black_box(&terms), black_box(path)) {
                matches += 1;
                sum += value;
            }
        }
        (matches, sum)
    };
    // Fixture and query allocations occur outside the scoped scorer measurements.
    let (before, stock_allocs) = measured(|| observed(stock::eval));
    let (after, candidate_allocs) = measured(|| observed(candidate::eval));
    assert_eq!(before, after);
    assert_eq!(before.0, 16_667);
    assert_eq!((stock_allocs, candidate_allocs), (50_000, 0));
    for p in &paths {
        assert_eq!(stock::eval(&terms, p), candidate::eval(&terms, p));
    }
    println!("lowercase scorer allocation operations: {stock_allocs} -> {candidate_allocs}");
}

#[test]
fn cases_forcing_fallback_do_not_take_the_ascii_borrow_path() {
    let terms = stock::query_terms("src needle");
    let upper_at_end = format!("src/{}/needle.Z", "a".repeat(4096));
    let unicode_at_end = format!("src/{}/needle/é", "a".repeat(4096));
    for path in ["SRC/needle.rs", "src/İ/needle.rs", "src/Σ/needle.rs",
                 upper_at_end.as_str(), unicode_at_end.as_str()] {
        let (a, old_count) = measured(|| stock::eval(black_box(&terms), black_box(path)));
        let (b, new_count) = measured(|| candidate::eval(black_box(&terms), black_box(path)));
        assert_eq!(a, b, "{path:?}");
        assert_eq!(old_count, new_count);
        assert!(new_count > 0);
    }
}
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stock", required=True, type=Path, help="exact unpatched search.rs")
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
    for boundary, before in (("fn score(", True), ("/// Scattered match:", False)):
        arm = [s.split(boundary, 1)[0 if before else 1] for s in (stock, candidate)]
        check(arm[0] == arm[1], "no product changes outside score")
    tests = {}
    counters = {}
    with tempfile.TemporaryDirectory(prefix="r215-proof-", dir=args.work_dir) as directory:
        root = Path(directory).resolve()
        env = {"PATH": "/usr/bin:/bin", "LC_ALL": "C", "HOME": str(root), "TMPDIR": str(root)}
        version = subprocess.check_output([args.rustc, "--version", "--verbose"],
                                          cwd=root, env=env, text=True)
        check("release: 1.95.0\n" in version and "host: x86_64-unknown-linux-gnu\n" in version,
              "expected Linux x86-64 Rust 1.95.0")
        root.joinpath("proof.rs").write_text(
            section(stock, "struct Candidate {", "fn candidates(")
            + "mod stock {\n" + make_lift(stock) + "}\nmod candidate {\n"
            + make_lift(candidate) + "}\n" + TESTS, encoding="utf-8"
        )
        for mode, extra in [("debug", []), ("optimized", ["-O"])]:
            subprocess.run([args.rustc, "--edition=2024", "--test", "-Dwarnings", *extra,
                            "proof.rs", "-o", "proof-bin"], cwd=root, env=env, check=True)
            output = subprocess.check_output(
                [root / "proof-bin", "--test-threads=1", "--nocapture"],
                cwd=root, env=env, text=True,
            )
            check("11 passed; 0 failed; 0 ignored;" in output, f"{mode} proof did not pass")
            match = re.search(r"lowercase scorer allocation operations: (\d+) -> (\d+)", output)
            check(match is not None, f"{mode} missing allocation evidence")
            tests[mode] = 11
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
        "generated_score_pairs_per_mode": 1081344,
        "prebuilt_lowercase_path_pairs_per_mode": 50000,
        "scorer_only_alloc_realloc_zeroed_before_then_after": counters,
        "real_filesystem_search_git_http_or_whole_core": False,
    }, indent=2))


if __name__ == "__main__":
    main()
