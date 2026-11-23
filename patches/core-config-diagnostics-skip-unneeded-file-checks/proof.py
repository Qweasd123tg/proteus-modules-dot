#!/usr/bin/env python3
"""Replay the exact source patch and run the Rust 1.95 std-only config diagnostics proof."""

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tempfile


PATH = "crates/proteus-core/src/core/config/files.rs"
BASE_BLOB = "0410b99e974a9f85bfc0efbc51257755b11cde89"
BASE_SHA = "cee2c395917e42e49e3372f36629b2cc880102008347645e9747659a65317ea0"
AFTER_BLOB = "e224c7e79ed5d5dd3345df10d50e48da689f6525"
AFTER_SHA = "b95daf3ea86ca234d351afd9e571b741a0fd0dfb9988cd490cae1bdf5dedc8ed"
PATCH_SHA = "e744e94efcc9f745f2999755699059d2dda94a84176a859aece0bcfbe21b4734"

REFERENCE_BLOB = "850b17b4f188b8fe71fd9839651c5de978c8a093"
REFERENCE_SHA = "868a7653e3723ae9fab271e2cff520f2f691edb2cca1fae7e3b1c7fe4fa16320"


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
    check(count == 1, "expected one diagnostics hunk")
    return b"".join(target + lines[used:])


def section(source, first, end):
    at = source.index(first)
    return source[at:source.index(end, at + len(first))]


def make_lift(name, source, reference, instrumented=False):
    path_import = re.search(r"^use std::path::\{Path, PathBuf\};\n", reference, re.M)[0]
    helper = section(reference, "const MARKER:", "pub fn config_selection(")
    if instrumented:
        check(source.count("path.is_file()") == 2, "exact predicates to observe")
        source = source.replace("path.is_file()", "super::observed_is_file(&path)")
        helper = (
            "mod reference {\n" + path_import + helper + "}\n"
            "fn physical_config_path(path: &Path) -> PathBuf {\n"
            "    let path = reference::physical_config_path(path);\n"
            "    crate::observe_pointer(&path);\n"
            "    path\n"
            "}\n"
            "fn observed_is_file(path: &Path) -> bool {\n"
            "    crate::observe_file_predicate();\n"
            "    path.is_file()\n"
            "}\n"
        )
    return (
        f"mod {name} {{\n" + path_import + helper
        + "mod product {\n" + source + "}\n"
        + "pub(super) fn list(path: Option<&Path>) -> Vec<PathBuf> {\n"
          "    product::config_files(path)\n"
          "}\n"
          "}\n"
    )


TESTS = r'''
use std::cell::Cell;
use std::ffi::OsStr;
use std::fs;
use std::os::unix::ffi::OsStrExt;
use std::os::unix::fs::symlink;
use std::path::{Path, PathBuf};

fn fixture(name: &str) -> PathBuf {
    let root = PathBuf::from(std::env::var_os("R221_PROOF_ROOT").unwrap()).join(name);
    fs::create_dir(&root).unwrap();
    root
}

fn same_raw(actual: &[PathBuf], expected: &[PathBuf]) {
    let actual: Vec<_> = actual.iter().map(|p| p.as_os_str().as_bytes()).collect();
    let expected: Vec<_> = expected.iter().map(|p| p.as_os_str().as_bytes()).collect();
    assert_eq!(actual, expected);
}

fn pair(path: Option<&Path>, expected: &[PathBuf]) {
    same_raw(&stock::list(path), expected);
    same_raw(&candidate::list(path), expected);
}

#[test]
fn none_missing_explicit_and_lexical_path() {
    pair(None, &[]);
    let root = fixture("paths");
    pair(Some(&root.join("missing.toml")), &[]);
    let explicit = root.join("unrelated.TOML");
    fs::write(&explicit, b"").unwrap();
    pair(Some(&explicit), std::slice::from_ref(&explicit));
    let mut lexical = root.as_os_str().as_bytes().to_vec();
    lexical.extend_from_slice(b"//./unrelated.TOML");
    let lexical = Path::new(OsStr::from_bytes(&lexical));
    pair(Some(lexical), &[lexical.to_path_buf()]);
    let null = root.join(OsStr::from_bytes(b"not\0a-real-path.json"));
    pair(Some(&null), &[]);
}

#[test]
fn physical_config_reference_rules_remain_exact() {
    let root = fixture("markers");
    let explicit = root.join("actual.junk");
    fs::write(&explicit, b"").unwrap();
    for suffix in ["#agent=/role", "#agent=invalid", "#agent=/a#agent=/b"] {
        let selected = root.join(format!("actual.junk{suffix}"));
        pair(Some(&selected), std::slice::from_ref(&explicit));
    }
    let ordinary = root.join("literal#profile.json");
    fs::write(&ordinary, b"").unwrap();
    pair(Some(&ordinary), std::slice::from_ref(&ordinary));
    let opaque = root.join(OsStr::from_bytes(b"opaque-\xff#agent=literal.json"));
    fs::write(&opaque, b"").unwrap();
    pair(Some(&opaque), std::slice::from_ref(&opaque));

    // This is diagnostics only: it strips a valid UTF-8 marker before listing
    // even a directory; the config loader has independent selector validation.
    let config = root.join("profiles");
    fs::create_dir(&config).unwrap();
    fs::write(config.join("accepted.json"), b"").unwrap();
    pair(Some(&root.join("profiles#agent=/anything")), &[config.join("accepted.json")]);
}

#[test]
fn literal_extensions_utf8_boundary_and_sorted_paths() {
    let root = fixture("extensions");
    for name in [
        "z.toml", "b.json", "x.TOML", "a.JSON", ".profile.toml", ".json", "multi.JSON.json",
        "x.json.old", "last-dot.", "trailing..toml", "rootfile",
    ] {
        fs::write(root.join(name), b"").unwrap();
    }
    let accepted_raw = OsStr::from_bytes(b"raw-\xff.json");
    fs::write(root.join(accepted_raw), b"").unwrap();
    fs::write(root.join(OsStr::from_bytes(b"bad.jso\xffn")), b"").unwrap();
    fs::create_dir(root.join("directory.toml")).unwrap();
    fs::create_dir(root.join("other.dir")).unwrap();
    let expected = [
        OsStr::new(".profile.toml"), OsStr::new("b.json"), OsStr::new("multi.JSON.json"),
        accepted_raw, OsStr::new("trailing..toml"), OsStr::new("z.toml"),
    ].map(|n| root.join(n));
    pair(Some(&root), &expected);
}

#[test]
fn metadata_follows_eligible_symlinks_keeps_lexical_aliases() {
    let root = fixture("metadata");
    let scan = root.join("scan");
    fs::create_dir(&scan).unwrap();
    fs::write(root.join("target.txt"), b"").unwrap();
    fs::write(root.join("target.toml"), b"").unwrap();
    fs::create_dir(root.join("directory")).unwrap();
    symlink("../target.txt", scan.join("eligible.toml")).unwrap();
    symlink("../target.toml", scan.join("ineligible.link")).unwrap();
    symlink("../missing", scan.join("broken.json")).unwrap();
    symlink("../directory", scan.join("symlink-dir.toml")).unwrap();
    fs::hard_link(root.join("target.txt"), scan.join("hard.json")).unwrap();
    pair(Some(&scan), &[scan.join("eligible.toml"), scan.join("hard.json")]);
    let explicit_alias = scan.join("ineligible.link");
    pair(Some(&explicit_alias), std::slice::from_ref(&explicit_alias));
    pair(Some(&scan.join("broken.json")), &[]);

    let alias = root.join("alias");
    symlink("scan", &alias).unwrap();
    pair(Some(&alias), &[alias.join("eligible.toml"), alias.join("hard.json")]);
}

#[test]
fn repeated_directory_reads_do_not_cache_previous_outputs() {
    let root = fixture("repeated");
    pair(Some(&root), &[]);
    let one = root.join("one.json");
    let two = root.join("two.toml");
    fs::write(&two, b"").unwrap();
    pair(Some(&root), std::slice::from_ref(&two));
    fs::write(&one, b"").unwrap();
    pair(Some(&root), &[one.clone(), two.clone()]);
    fs::remove_file(&two).unwrap();
    pair(Some(&root), &[one]);
}

thread_local! {
    static FILE_PREDICATES: Cell<usize> = const { Cell::new(0) };
    static PHYSICAL_POINTER: Cell<usize> = const { Cell::new(0) };
}

fn observe_file_predicate() {
    FILE_PREDICATES.with(|counter| counter.set(counter.get() + 1));
}

fn pointer(path: &Path) -> usize {
    path.as_os_str().as_bytes().as_ptr() as usize
}

fn observe_pointer(path: &Path) {
    PHYSICAL_POINTER.with(|observed| observed.set(pointer(path)));
}

fn observe_probe(path: &Path, list: fn(Option<&Path>) -> Vec<PathBuf>) -> (Vec<PathBuf>, usize, usize) {
    FILE_PREDICATES.with(|counter| counter.set(0));
    PHYSICAL_POINTER.with(|observed| observed.set(0));
    let paths = list(Some(path));
    (paths, FILE_PREDICATES.with(Cell::get), PHYSICAL_POINTER.with(Cell::get))
}

#[test]
fn structural_file_predicate_counts_on_1000_ineligible_children() {
    let root = fixture("many");
    for i in 0..1000 {
        fs::write(root.join(format!("{i:04}.fixture")), b"").unwrap();
    }
    let accept = root.join("use.toml");
    fs::write(&accept, b"").unwrap();
    fs::create_dir(root.join("directory.json")).unwrap();
    pair(Some(&root), std::slice::from_ref(&accept));
    let (a, old, _) = observe_probe(&root, observed_stock::list);
    let (b, new, _) = observe_probe(&root, observed_candidate::list);
    same_raw(&a, std::slice::from_ref(&accept));
    same_raw(&b, &[accept]);
    assert_eq!((old, new), (1003, 3));
    println!("diagnostic Path::is_file calls: {old} -> {new}");
}

#[test]
fn owned_path_move_only_witness() {
    let root = fixture("pointer");
    let path = root.join("a-nonempty-explicit.fixture");
    fs::write(&path, b"").unwrap();
    let request = root.join("a-nonempty-explicit.fixture#agent=/r");
    let (a, old_calls, before_copy) = observe_probe(&request, observed_stock::list);
    let (b, new_calls, before_move) = observe_probe(&request, observed_candidate::list);
    same_raw(&a, std::slice::from_ref(&path));
    same_raw(&b, &[path]);
    assert_eq!((old_calls, new_calls), (1, 1));
    assert_ne!(before_copy, pointer(&a[0]));
    assert_eq!(before_move, pointer(&b[0]));
}
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stock", required=True, type=Path, help="exact unpatched files.rs")
    parser.add_argument("--reference", required=True, type=Path, help="exact reference.rs on same commit")
    parser.add_argument("--rustc", required=True, type=Path, help="trusted installed Rust 1.95.0")
    parser.add_argument("--work-dir", required=True, type=Path, help="private writable scratch")
    args = parser.parse_args()
    check(args.rustc.is_absolute(), "use absolute rustc path")
    stock = args.stock.read_bytes()
    identity(stock, BASE_BLOB, BASE_SHA)
    reference = args.reference.read_bytes()
    identity(reference, REFERENCE_BLOB, REFERENCE_SHA)
    patch = Path(__file__).with_name("source.patch").read_bytes()
    check(hashlib.sha256(patch).hexdigest() == PATCH_SHA, "patch SHA256")
    candidate = replay(stock, patch)
    identity(candidate, AFTER_BLOB, AFTER_SHA)
    check(replay(candidate, patch, True) == stock, "exact reverse patch")
    stock, candidate, reference = (source.decode() for source in (stock, candidate, reference))
    tests = {}
    counters = {}
    with tempfile.TemporaryDirectory(prefix="r221-proof-", dir=args.work_dir) as directory:
        root = Path(directory).resolve()
        env = {"PATH": "/usr/bin:/bin", "LC_ALL": "C", "HOME": str(root), "TMPDIR": str(root)}
        version = subprocess.check_output([args.rustc, "--version", "--verbose"],
                                          cwd=root, env=env, text=True)
        check("release: 1.95.0\n" in version and "host: x86_64-unknown-linux-gnu\n" in version,
              "expected Linux x86-64 Rust 1.95.0")
        root.joinpath("proof.rs").write_text(
            make_lift("stock", stock, reference) + make_lift("candidate", candidate, reference)
            + make_lift("observed_stock", stock, reference, True)
            + make_lift("observed_candidate", candidate, reference, True)
            + TESTS, encoding="utf-8"
        )
        for mode, extra in [("debug", []), ("optimized", ["-O"])]:
            private = root / mode
            private.mkdir()
            env["R221_PROOF_ROOT"] = str(private)
            subprocess.run([args.rustc, "--edition=2024", "--test", "-Dwarnings", *extra,
                            "proof.rs", "-o", "proof-bin"], cwd=root, env=env, check=True)
            final = subprocess.run([root / "proof-bin", "--test-threads=1", "--nocapture"],
                                   cwd=root, env=env, text=True, capture_output=True)
            check(final.returncode == 0, f"{mode} proof failed:\n{final.stdout}\n{final.stderr}")
            check("7 passed; 0 failed; 0 ignored;" in final.stdout, f"{mode} expected seven tests")
            match = re.search(r"diagnostic Path::is_file calls: (\d+) -> (\d+)", final.stdout)
            check(match is not None, f"{mode} missing structural evidence")
            tests[mode] = 7
            counters[mode] = list(map(int, match.groups()))
    print(json.dumps({
        "status": "PASS",
        "rustc": version.splitlines()[0],
        "rustc_binary_sha256": hashlib.sha256(args.rustc.read_bytes()).hexdigest(),
        "candidate_git_blob": AFTER_BLOB,
        "candidate_sha256": AFTER_SHA,
        "patch_sha256": PATCH_SHA,
        "unchanged_reference_git_blob": REFERENCE_BLOB,
        "unchanged_reference_sha256": REFERENCE_SHA,
        "exact_forward_and_reverse_patch": True,
        "native_std_only_tests_passed": tests,
        "structural_path_is_file_calls_before_then_after": counters,
        "explicit_path_reuses_buffer_in_instrumented_candidate": True,
        "actual_config_loading_app_startup_or_whole_core": False,
    }, indent=2))


if __name__ == "__main__":
    main()
