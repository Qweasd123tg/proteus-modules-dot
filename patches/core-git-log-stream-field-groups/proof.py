#!/usr/bin/env python3
"""Replay the exact source patch and run the Rust 1.95 std-only log parser proof."""

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tempfile


PATH = "crates/proteus-core/src/app_server/http/workspace/git/log.rs"
BASE_BLOB = "f71b29877f03850ec3504fdc32052670d9485779"
BASE_SHA = "8920e675de14f0f154bbe6dc472aa392e964a21641753f7b0f6d7018e9cb6c00"
AFTER_BLOB = "067b35a21667839cb3080a6ec71dc98ea6e7c012"
AFTER_SHA = "239c2b6ab2a1c378503994d09b107a51fe30dbc0f87de671ff710ff961aebbc1"
PATCH_SHA = "f98fc29841c3668a079db982c1e68d52a19892e165eac613c45cda982ce9ee8a"


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
    check(count == 1, "expected one decoder hunk")
    return b"".join(target + lines[used:])


def section(source, first, end):
    at = source.index(first)
    return source[at:source.index(end, at + len(first))]


def make_lift(source, is_candidate):
    constant = re.search(r"^const FIELDS: usize = \d+;\n", source, re.M)[0]
    types = section(source, "#[derive(Serialize)]\npub(crate) struct Log", "pub(super) fn head_hash")
    types = types.replace("#[derive(Serialize)]\n", "")
    decoder = source[source.index("    // Stopped at the output cap:"):]
    groups = "log_records(text).collect()"
    if not is_candidate:
        groups = section(decoder, "    let fields: Vec<&str>", "    for [hash,").strip()
        groups += "\n    records.to_vec()"
    return (
        "use crate::View;\n" + constant + types
        + """type TestResult<T> = std::result::Result<T, &'static str>;
trait Context<T> { fn context(self, message: &'static str) -> TestResult<T>; }
impl<T, E> Context<T> for std::result::Result<T, E> {
    fn context(self, message: &'static str) -> TestResult<T> { self.map_err(|_| message) }
}
struct Input<'a> { bytes: &'a [u8], truncated: bool }
struct Query { limit: usize }
fn parse_lift(output: Input<'_>, query: Query) -> TestResult<Log> {
    let mut result = Log { head: Some("fixture-head".into()), entries: Vec::new(), has_more: false };
"""
        + decoder
        + """pub(super) fn parse(bytes: &[u8], truncated: bool, limit: usize) -> TestResult<View> {
    let log = parse_lift(Input { bytes, truncated }, Query { limit })?;
    let entries = log.entries.into_iter().map(|e| (
        e.hash, e.short, e.parents, e.summary, e.author, e.email, e.time,
        e.refs.into_iter().map(|r| (r.name, r.kind)).collect()
    )).collect();
    Ok((log.head, entries, log.has_more))
}
pub(super) fn groups(text: &str) -> Vec<[&str; FIELDS]> {
"""
        + groups + "\n}\n"
    )


TESTS = r'''
type Entry = (String, String, Vec<String>, String, String, String, i64, Vec<(String, &'static str)>);
type View = (Option<String>, Vec<Entry>, bool);

fn parse_pair(bytes: &[u8], truncated: bool, limit: usize) -> Result<View, &'static str> {
    let a = stock::parse(bytes, truncated, limit);
    let b = candidate::parse(bytes, truncated, limit);
    assert_eq!(a, b, "limit {limit}, truncated {truncated}, input bytes {}", bytes.len());
    a
}

fn record(index: usize, time: &str, summary: &str) -> String {
    [
        format!("commit-{index:04}"), format!("short-{index:04}"), "parent-a  parent-b".into(),
        "Майя".into(), "fixture@example.invalid".into(), time.into(),
        "HEAD -> refs/heads/main, tag: refs/tags/r0, refs/remotes/fixture/main, unknown".into(),
        summary.into(),
    ].join("\0")
}

#[test]
fn exact_rows_refs_time_and_lossy_bytes() {
    let mut bytes = record(3, "-83", "中文🙂").into_bytes();
    bytes.push(0xff);
    bytes.push(0);
    let (head, rows, more) = parse_pair(&bytes, false, 50).unwrap();
    assert_eq!(head.as_deref(), Some("fixture-head"));
    assert!(!more);
    assert_eq!(rows, vec![(
        "commit-0003".into(), "short-0003".into(), vec!["parent-a".into(), "parent-b".into()],
        "中文🙂�".into(), "Майя".into(), "fixture@example.invalid".into(), -83,
        vec![("HEAD".into(), "head"), ("main".into(), "branch"), ("r0".into(), "tag"),
             ("fixture/main".into(), "remote")],
    )]);
}

#[test]
fn terminal_empty_and_partial_summary_are_still_fields() {
    for suffix in ["", "\0"] {
        for summary in ["", "incomplete summary wording"] {
            let payload = format!("{}{suffix}", record(0, "2", summary));
            let (_, rows, more) = parse_pair(payload.as_bytes(), false, 1).unwrap();
            assert_eq!(rows.len(), 1);
            assert_eq!(rows[0].3, summary);
            assert!(!more);
        }
    }
    assert!(stock::groups("").is_empty());
    assert!(candidate::groups("").is_empty());
    let pure_empty = "\0".repeat(7);
    assert_eq!(stock::groups(&pure_empty), vec![[""; 8]]);
    assert_eq!(candidate::groups(&pure_empty), vec![[""; 8]]);
}

#[test]
fn every_short_tail_and_exact_lookahead() {
    let first = record(0, "0", "first");
    for extra in 0..=8 {
        let payload = first.clone() + &"\0tail".repeat(extra);
        for truncated in [false, true] {
            let (_, rows, more) = parse_pair(payload.as_bytes(), truncated, 1).unwrap();
            assert_eq!(rows.len(), 1);
            assert_eq!(more, truncated || extra == 8);
        }
    }
    assert_eq!(parse_pair(&[], false, 1).unwrap().1.len(), 0);
    assert!(!parse_pair(&[], false, 1).unwrap().2);
    assert!(parse_pair(&[], true, 1).unwrap().2);
}

#[test]
fn invalid_time_priority_at_and_after_page_limit() {
    let valid = record(0, "0", "first");
    let bad = record(1, "bad-timestamp", "do not return");
    let over = record(2, "9223372036854775808", "overflow");
    let payload = [valid.as_str(), bad.as_str(), over.as_str()].join("\0");
    for truncated in [false, true] {
        let (_, rows, more) = parse_pair(payload.as_bytes(), truncated, 1).unwrap();
        assert_eq!(rows.len(), 1);
        assert!(more);
        assert_eq!(parse_pair(payload.as_bytes(), truncated, 2), Err("invalid Git commit time"));
        assert_eq!(parse_pair(over.as_bytes(), truncated, 2), Err("invalid Git commit time"));
        assert_eq!(parse_pair(bad.as_bytes(), truncated, 1), Err("invalid Git commit time"));
    }
}

#[test]
fn typical_and_bounded_max_pages_keep_order() {
    fn page(rows: usize) -> String {
        let mut text = (0..rows).map(|i| record(i, &i.to_string(), "summary"))
            .collect::<Vec<_>>().join("\0");
        text.push('\0');
        text
    }
    for limit in [50, 500] {
        for rows in [limit - 1, limit, limit + 1] {
            let text = page(rows);
            let (_, entries, more) = parse_pair(text.as_bytes(), false, limit).unwrap();
            assert_eq!(entries.len(), limit.min(rows));
            assert_eq!(more, rows > limit);
            for (i, row) in entries.iter().enumerate() {
                assert_eq!(row.0, format!("commit-{i:04}"));
                assert_eq!(row.6, i as i64);
            }
            assert_eq!(candidate::groups(&text).len(), rows);
        }
    }
    assert_eq!(page(501).split('\0').count(), 4_009);
    assert_eq!(std::mem::size_of::<&str>() * 4_009, 64_144);
    assert_eq!(std::mem::size_of::<[&str; 8]>(), 128);
}

#[test]
fn exhaustive_nuls_and_lossy_short_field_groups() {
    let palette = [0, b'x', 0xff];
    let mut raw = [0; 9];
    let mut pairs = 0;
    for len in 0..=raw.len() {
        for mut code in 0..3_usize.pow(len as u32) {
            for byte in &mut raw[..len] {
                *byte = palette[code % palette.len()];
                code /= palette.len();
            }
            let text = String::from_utf8_lossy(&raw[..len]);
            assert_eq!(stock::groups(&text), candidate::groups(&text));
            pairs += 1;
        }
    }
    assert_eq!(pairs, 29_524);
}

#[test]
fn every_byte_boundary_in_mixed_page() {
    let valid = record(0, "-1", "first 🙂");
    let bad = record(1, "bad", "invalid in page");
    let third = record(2, "42", "");
    let payload = [valid, bad, third].join("\0");
    assert_eq!(payload.len(), 499);
    for end in 0..=payload.len() {
        for limit in [1, 2, 5] {
            for truncated in [false, true] {
                let _ = parse_pair(&payload.as_bytes()[..end], truncated, limit);
            }
        }
    }
}
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stock", required=True, type=Path, help="exact unpatched log.rs")
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
    for boundary, before in (("    // Stopped at the output cap:", True), ("/// `%D` with", False)):
        arm = [s.split(boundary, 1)[0 if before else 1] for s in (stock, candidate)]
        check(arm[0] == arm[1], "no Git, page guard or decorations source changes")
    tests = {}
    with tempfile.TemporaryDirectory(prefix="r217-proof-", dir=args.work_dir) as directory:
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
            final = subprocess.run([root / "proof-bin", "--test-threads=1"],
                                   cwd=root, env=env, text=True, capture_output=True)
            check(final.returncode == 0, f"{mode} proof failed:\n{final.stdout}\n{final.stderr}")
            check("7 passed; 0 failed; 0 ignored;" in final.stdout, f"{mode} expected seven tests")
            tests[mode] = 7
    print(json.dumps({
        "status": "PASS",
        "rustc": version.splitlines()[0],
        "rustc_binary_sha256": hashlib.sha256(args.rustc.read_bytes()).hexdigest(),
        "candidate_git_blob": AFTER_BLOB,
        "candidate_sha256": AFTER_SHA,
        "patch_sha256": PATCH_SHA,
        "exact_forward_and_reverse_patch": True,
        "native_std_only_tests_passed": tests,
        "exhaustive_raw_field_group_pairs_per_mode": 29524,
        "mixed_decode_cut_limit_pairs_per_mode": 3000,
        "fixture_501_record_reference_payload_bytes": 64144,
        "one_group_reference_payload_bytes": 128,
        "real_git_http_or_whole_core": False,
    }, indent=2))


if __name__ == "__main__":
    main()
