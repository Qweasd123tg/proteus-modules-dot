#!/usr/bin/env python3
"""Replay the exact source patch and run the Rust 1.95 std-only paired proof."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile


PATH = "crates/proteus-core/src/app_server/http/workspace/git/stats.rs"
BASE_BLOB = "34f8eec790d80d32feecac35a5539393e8fc9761"
BASE_SHA = "a28eadd07267d24ece157f169b99dfe2efb8f54a39817e37031a60f5e7dfd63b"
AFTER_BLOB = "e4cbe0bc28f58a2e68c91af93fc27a9d9acff33b"
AFTER_SHA = "84f8bd4fb628604cbca19aa62fb9f3b276055d7d06b2830d153de644cd537815"
PATCH_SHA = "a4813e4c3331724a6d9267e8c489727cc6de33fc0bba3bd0e9bb6c4bc14a7dc1"


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
    check(count == 2, "expected import and scanner hunks only")
    return b"".join(target + lines[used:])


def make_lift(source, candidate):
    source = source.decode()
    start = source.index("fn count_untracked(")
    exact_tail = source[start:]
    names = ("MAX_UNTRACKED_FILE_BYTES", "MAX_UNTRACKED_TOTAL_BYTES")
    constants = "".join(re.search(r"^const " + name + r": u64 = .*;\n", source, re.M)[0]
                        for name in names)
    alias = re.search(r"^pub\(super\) type LineCounts = .*;\n", source, re.M)[0]
    reader = "    count_text_lines(input.take(MAX_UNTRACKED_FILE_BYTES))\n"
    imports = "ErrorKind, Read" if candidate else "Read"
    if not candidate:
        # Exact stock fragment after a successful open, with only the reader injection seam.
        before = exact_tail[exact_tail.index("    let mut bytes = Vec::new();"):]
        open_chain = "    fs::File::open(path)\n        .ok()?\n"
        check(before.count(open_chain) == 1 and before.endswith("}\n"), "stock injection seam")
        reader = before.replace(open_chain, "    input\n", 1)[:-2]
    return (
        f"use std::{{fs, io::{{{imports}}}, path::Path}};\n" + constants + alias + exact_tail
        + "pub(super) fn file(root: &Path, rel: &str, budget: &mut u64) -> LineCounts {\n"
        + "    count_untracked(root, rel, budget)\n}\n"
        + "pub(super) const CAP: u64 = MAX_UNTRACKED_FILE_BYTES;\n"
        + "pub(super) const BUDGET: u64 = MAX_UNTRACKED_TOTAL_BYTES;\n"
        + "pub(super) fn reader(input: impl Read) -> LineCounts {\n" + reader + "}\n"
    )


TESTS = r'''
use std::collections::VecDeque;
use std::fs;
use std::io::{self, ErrorKind, Read};
use std::path::{Path, PathBuf};

type Counts = Option<(u64, u64)>;
const CAP: usize = stock::CAP as usize;
const BUDGET: u64 = stock::BUDGET;

fn private_dir(name: &str) -> PathBuf {
    let path = PathBuf::from(std::env::var_os("R206_PROOF_ROOT").unwrap()).join(name);
    fs::create_dir(&path).unwrap();
    path
}

fn file_pair(root: &Path, rel: &str, budget: u64, expected: Counts, debited: u64) {
    let mut a = budget;
    let mut b = budget;
    assert_eq!(stock::file(root, rel, &mut a), expected, "stock: {rel}");
    assert_eq!(candidate::file(root, rel, &mut b), expected, "candidate: {rel}");
    assert_eq!((a, b), (budget - debited, budget - debited), "budget: {rel}");
}

#[test]
fn real_untracked_byte_counts_and_chunk_edges() {
    let root = private_dir("byte-files");
    let short: &[(&str, &[u8], Counts)] = &[
        ("empty", b"", Some((0, 0))),
        ("unterminated", b"one", Some((1, 0))),
        ("terminated", b"one\n", Some((1, 0))),
        ("lf", b"\n\n", Some((2, 0))),
        ("crlf", b"one\r\ntwo\r\nthree", Some((3, 0))),
        ("cr-only", b"\r\r", Some((1, 0))),
        ("non-utf8", b"\xff\n\x80", Some((2, 0))),
        ("nul-start", b"\0a\n", None),
        ("nul-end", b"a\n\0", None),
    ];
    for &(name, bytes, expected) in short {
        fs::write(root.join(name), bytes).unwrap();
        file_pair(&root, name, bytes.len() as u64, expected, bytes.len() as u64);
    }
    let mut crossing = vec![b'x'; 8192 + 2];
    crossing[8191] = b'\n';
    fs::write(root.join("lf-chunk-edge"), &crossing).unwrap();
    file_pair(&root, "lf-chunk-edge", BUDGET, Some((2, 0)), crossing.len() as u64);
    crossing[8192] = 0;
    fs::write(root.join("nul-next-chunk"), &crossing).unwrap();
    file_pair(&root, "nul-next-chunk", BUDGET, None, crossing.len() as u64);
    let mut end = vec![b'\n'; CAP];
    fs::write(root.join("full-cap-text"), &end).unwrap();
    file_pair(&root, "full-cap-text", BUDGET, Some((CAP as u64, 0)), CAP as u64);
    end[CAP - 1] = 0;
    fs::write(root.join("full-cap-nul"), &end).unwrap();
    file_pair(&root, "full-cap-nul", BUDGET, None, CAP as u64);
}

#[test]
fn metadata_admission_and_no_debit_for_skips() {
    let root = private_dir("metadata");
    fs::write(root.join("allowed"), b"ok\n").unwrap();
    fs::write(root.join("oversize"), vec![b'x'; CAP + 1]).unwrap();
    fs::create_dir(root.join("directory")).unwrap();
    std::os::unix::fs::symlink("allowed", root.join("link")).unwrap();
    std::os::unix::fs::symlink("missing", root.join("dangling")).unwrap();
    for name in ["oversize", "directory", "link", "dangling", "missing"] {
        file_pair(&root, name, BUDGET, None, 0);
    }
    file_pair(&root, "allowed", 2, None, 0);
    file_pair(&root, "allowed", 3, Some((1, 0)), 3);
}

#[test]
fn exact_shared_budget_including_binary() {
    let root = private_dir("shared-budget");
    assert_eq!((BUDGET, candidate::BUDGET), (4 * 1024 * 1024, 4 * 1024 * 1024));
    assert_eq!((CAP, candidate::CAP), (512 * 1024, 512 * 1024));
    let mut contents = vec![b'x'; CAP];
    contents[CAP - 1] = 0;
    fs::write(root.join("file0"), &contents).unwrap();
    contents[CAP - 1] = b'\n';
    for i in 1..8 {
        fs::write(root.join(format!("file{i}")), &contents).unwrap();
    }
    fs::write(root.join("unfunded"), b"x").unwrap();
    fs::write(root.join("free-empty"), b"").unwrap();
    let mut a = BUDGET;
    let mut b = BUDGET;
    for i in 0..8 {
        let name = format!("file{i}");
        let expected = if i == 0 { None } else { Some((1, 0)) };
        assert_eq!(stock::file(&root, &name, &mut a), expected);
        assert_eq!(candidate::file(&root, &name, &mut b), expected);
        let remain = BUDGET - (i + 1) * CAP as u64;
        assert_eq!((a, b), (remain, remain));
    }
    assert_eq!(stock::file(&root, "unfunded", &mut a), None);
    assert_eq!(candidate::file(&root, "unfunded", &mut b), None);
    assert_eq!(stock::file(&root, "free-empty", &mut a), Some((0, 0)));
    assert_eq!(candidate::file(&root, "free-empty", &mut b), Some((0, 0)));
    assert_eq!((a, b), (0, 0));
}

struct Fragments<'a> {
    bytes: &'a [u8],
    width: usize,
}

impl Read for Fragments<'_> {
    fn read(&mut self, out: &mut [u8]) -> io::Result<usize> {
        let n = out.len().min(self.width);
        self.bytes.read(&mut out[..n])
    }
}

#[test]
fn exhaustive_short_bytes_under_fragmentation() {
    let alphabet = [0, b'\n', b'\r', 0xff, b'a'];
    let mut bytes = [0; 6];
    let mut pairs = 0;
    for len in 0..=6 {
        for mut code in 0..5_usize.pow(len as u32) {
            for byte in &mut bytes[..len] {
                *byte = alphabet[code % 5];
                code /= 5;
            }
            let bytes = &bytes[..len];
            let expected = (!bytes.contains(&0))
                .then(|| (bytes.split_inclusive(|&c| c == b'\n').count() as u64, 0));
            for width in [1, 2, 7] {
                let a = stock::reader(Fragments { bytes, width });
                let b = candidate::reader(Fragments { bytes, width });
                assert_eq!((a, b), (expected, expected), "bytes {bytes:?}, width {width}");
                pairs += 1;
            }
        }
    }
    assert_eq!(pairs, 58_593);
}

#[derive(Clone, Copy)]
enum Event<'a> {
    Bytes(&'a [u8]),
    Interrupt,
    Fail,
    Eof,
}

#[derive(Debug, Default, PartialEq, Eq)]
struct Observed {
    bytes: usize,
    interruptions: usize,
    failures: usize,
    eofs: usize,
}

struct Script<'a> {
    queue: VecDeque<Event<'a>>,
    observed: Observed,
}

impl Read for Script<'_> {
    fn read(&mut self, buf: &mut [u8]) -> io::Result<usize> {
        assert!(!buf.is_empty(), "unexpected zero-length underlying read");
        match self.queue.pop_front().expect("unexpected read past scripted input") {
            Event::Bytes(bytes) => {
                let n = bytes.len().min(buf.len());
                self.observed.bytes += n;
                buf[..n].copy_from_slice(&bytes[..n]);
                if n < bytes.len() {
                    self.queue.push_front(Event::Bytes(&bytes[n..]));
                }
                Ok(n)
            }
            Event::Interrupt => {
                self.observed.interruptions += 1;
                Err(ErrorKind::Interrupted.into())
            }
            Event::Fail => {
                self.observed.failures += 1;
                Err(ErrorKind::BrokenPipe.into())
            }
            Event::Eof => {
                self.observed.eofs += 1;
                Ok(0)
            }
        }
    }
}

fn script_pair(events: &[Event<'_>], expected: Counts, seen: Observed, remain: usize) {
    let mut a = Script { queue: events.to_vec().into(), observed: Observed::default() };
    let mut b = Script { queue: events.to_vec().into(), observed: Observed::default() };
    assert_eq!(stock::reader(&mut a), expected);
    assert_eq!(candidate::reader(&mut b), expected);
    assert_eq!(a.observed, seen);
    assert_eq!(b.observed, seen);
    assert_eq!(a.queue.len(), remain);
    assert_eq!(b.queue.len(), remain);
}

#[test]
fn interrupted_retry_and_ordinary_eof() {
    use Event::*;
    script_pair(&[Interrupt, Interrupt, Bytes(b"a\r"), Interrupt, Bytes(b"\nb"),
                  Eof, Fail], Some((2, 0)),
                Observed { bytes: 4, interruptions: 3, eofs: 1, ..Observed::default() }, 1);
    script_pair(&[Interrupt, Eof, Bytes(b"after-zero")], Some((0, 0)),
                Observed { interruptions: 1, eofs: 1, ..Observed::default() }, 1);
}

#[test]
fn drains_binary_and_observes_late_errors() {
    use Event::*;
    script_pair(&[Bytes(b"\0"), Interrupt, Bytes(b"tail\n"), Eof], None,
                Observed { bytes: 6, interruptions: 1, eofs: 1, ..Observed::default() }, 0);
    script_pair(&[Bytes(b"\0"), Bytes(b"more"), Interrupt, Fail, Eof], None,
                Observed { bytes: 5, interruptions: 1, failures: 1, ..Observed::default() }, 1);
    script_pair(&[Bytes(b"nonbinary\n"), Fail, Eof], None,
                Observed { bytes: 10, failures: 1, ..Observed::default() }, 1);
    script_pair(&[Bytes(b"line\n"), Bytes(b"\0"), Eof], None,
                Observed { bytes: 6, eofs: 1, ..Observed::default() }, 0);
}

#[test]
fn take_never_sees_growth_suffix_or_late_failure() {
    use Event::*;
    let mut too_long = vec![b'x'; CAP + 1];
    too_long[CAP] = 0;
    script_pair(&[Bytes(&too_long), Fail], Some((1, 0)),
                Observed { bytes: CAP, ..Observed::default() }, 2);
    too_long[CAP - 1] = 0;
    script_pair(&[Bytes(&too_long), Fail], None,
                Observed { bytes: CAP, ..Observed::default() }, 2);
    script_pair(&[Bytes(&too_long[..CAP]), Interrupt, Fail], None,
                Observed { bytes: CAP, ..Observed::default() }, 2);
    script_pair(&[Bytes(&too_long[..CAP - 1]), Fail], None,
                Observed { bytes: CAP - 1, failures: 1, ..Observed::default() }, 0);
}
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stock", required=True, type=Path, help="exact unpatched stats.rs")
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
    check(replay(candidate, patch, True) == stock, "reverse patch")
    a, b = (s.split(b"fn count_untracked(", 1)[1] for s in (stock, candidate))
    check(a.split(b"    let mut bytes", 1)[0] ==
          b.split(b"    count_text_lines(fs::File::open(", 1)[0], "metadata and budget unchanged")
    with tempfile.TemporaryDirectory(prefix="r206-proof-", dir=args.work_dir) as directory:
        root = Path(directory).resolve()
        env = {"PATH": "/usr/bin:/bin", "LC_ALL": "C", "HOME": str(root), "TMPDIR": str(root),
               "R206_PROOF_ROOT": str(root)}
        version = subprocess.check_output([args.rustc, "--version", "--verbose"],
                                          cwd=root, env=env, text=True)
        check("release: 1.95.0\n" in version, "expected Rust 1.95.0")
        root.joinpath("proof.rs").write_text(
            "mod stock {\n" + make_lift(stock, False) + "}\nmod candidate {\n"
            + make_lift(candidate, True) + "}\n" + TESTS, encoding="utf-8"
        )
        subprocess.run([args.rustc, "--edition=2024", "--test", "-Dwarnings", "proof.rs",
                        "-o", "proof-bin"], cwd=root, env=env, check=True)
        output = subprocess.check_output([root / "proof-bin", "--test-threads=1"],
                                         cwd=root, env=env, text=True)
        check("7 passed; 0 failed; 0 ignored;" in output, "full proof did not pass")
    print(json.dumps({
        "status": "PASS",
        "rustc": version.splitlines()[0],
        "rustc_binary_sha256": hashlib.sha256(args.rustc.read_bytes()).hexdigest(),
        "candidate_git_blob": AFTER_BLOB,
        "candidate_sha256": AFTER_SHA,
        "patch_sha256": PATCH_SHA,
        "exact_forward_and_reverse_patch": True,
        "native_std_only_tests_passed": 7,
        "paired_real_file_decisions": 30,
        "exhaustive_short_reader_pairs": 58593,
        "paired_fault_script_cases": 10,
        "real_git_http_or_core_build": False,
    }, indent=2))


if __name__ == "__main__":
    main()
