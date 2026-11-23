#!/usr/bin/env python3
"""Replay the exact source patch and run the Rust 1.95 std-only watcher lifetime proof."""

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tempfile


PATH = "crates/proteus-core/src/app_server/profile_watch.rs"
BASE_BLOB = "17faba58c14e467fab04097f6b008d957bc5b2ee"
BASE_SHA = "a1de720ff4a19c0ccd941a662fbad0d9b01e2045f7e02a95acff5abc6f108a05"
AFTER_BLOB = "37dc586c663c80924320296f7ed707549c50caf0"
AFTER_SHA = "ffbffa4068356633115266db727fb2452d4f9b0a57ebe2ed7684c3185501ca9d"
PATCH_SHA = "9cb6ce2517615e183b0e53f353d7db53a19e7a5a9505d724c17bc9453c12de5f"


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
    check(count == 1, "expected one clone-lifetime hunk")
    return b"".join(target + lines[used:])


def section(source, first, end):
    at = source.index(first)
    return source[at:source.index(end, at + len(first))]


OLD_START = "            let current = handle.config.read().await.clone();"
NEW_START = "            let already_published = {"
LOOP_END = "        }\n    }));"
SELECT = """            let result = tokio::select! {
                _ = stop.cancelled() => break,
                result = refresh(&handle,&path,&expected) => result,
            };"""
SELECT_STUB = """            let result = match handle.refresh().await {
                Refresh::Cancelled => break,
                Refresh::Result(result) => result,
            };"""


def make_lift(name, source, start):
    loop = section(source, start, LOOP_END)
    check(loop.count(SELECT) == 1, "exact select adapter seam")
    return (
        f"mod {name} {{\nuse crate::*;\n"
        "pub(super) async fn run(handle: &Handle, expected: Fingerprint, mut applied: Fingerprint)"
        " -> Outcome {\n"
        "    let mut failed = Some(Fingerprint { config: vec![90], packages: vec![90] });\n"
        "    let mut poll = ObservePoll(&handle.trace);\n"
        "    for expected in [expected] {\n"
        + loop.replace(SELECT, SELECT_STUB)
        + "    }\n    (applied, failed)\n}\n}\n"
    )


TESTS = r'''
use std::cell::{Cell, RefCell};
use std::fmt;
use std::future::{Future, poll_fn};
use std::ops::Deref;
use std::pin::Pin;
use std::rc::Rc;
use std::task::{Context, Poll, Waker};

type Outcome = (Fingerprint, Option<Fingerprint>);

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum Event {
    GuardAcquired, Clone, GuardDropped, Serialize, DropClone, RefreshPlanned,
    PendingClear, Cleared, PendingReport, Reported, PendingRefresh, Refreshed, Cancelled,
}

#[derive(Default)]
struct State {
    clones: Cell<usize>,
    guards: Cell<usize>,
    events: RefCell<Vec<Event>>,
    errors: RefCell<Vec<Option<String>>>,
}

#[derive(Clone, Default)]
struct Trace(Rc<State>);

impl Trace {
    fn event(&self, event: Event) {
        self.0.events.borrow_mut().push(event);
    }

    fn snapshot(&self) -> Vec<Event> {
        self.0.events.borrow().clone()
    }
}

struct DropSpy(Trace);

impl Drop for DropSpy {
    fn drop(&mut self) {
        let state = &self.0.0;
        assert_eq!(state.clones.get(), 1);
        state.clones.set(0);
        self.0.event(Event::DropClone);
    }
}

struct AppConfig {
    bytes: Vec<u8>,
    fail_serialization: bool,
    trace: Trace,
    _drop_spy: Option<DropSpy>,
}

impl Clone for AppConfig {
    fn clone(&self) -> Self {
        assert_eq!(self.trace.0.guards.get(), 1);
        assert_eq!(self.trace.0.clones.get(), 0);
        self.trace.0.clones.set(1);
        self.trace.event(Event::Clone);
        Self {
            bytes: self.bytes.clone(),
            fail_serialization: self.fail_serialization,
            trace: self.trace.clone(),
            _drop_spy: Some(DropSpy(self.trace.clone())),
        }
    }
}

struct ConfigCell(AppConfig);
struct ReadGuard<'a>(&'a AppConfig);

impl ConfigCell {
    async fn read(&self) -> ReadGuard<'_> {
        assert_eq!(self.0.trace.0.guards.get(), 0);
        self.0.trace.0.guards.set(1);
        self.0.trace.event(Event::GuardAcquired);
        ReadGuard(&self.0)
    }
}

impl Deref for ReadGuard<'_> {
    type Target = AppConfig;
    fn deref(&self) -> &AppConfig { self.0 }
}

impl Drop for ReadGuard<'_> {
    fn drop(&mut self) {
        assert_eq!(self.0.trace.0.guards.get(), 1);
        self.0.trace.0.guards.set(0);
        self.0.trace.event(Event::GuardDropped);
    }
}

mod serde_json {
    use crate::{AppConfig, Event};

    pub(super) fn to_vec(config: &AppConfig) -> Result<Vec<u8>, ()> {
        assert_eq!(config.trace.0.guards.get(), 0);
        assert_eq!(config.trace.0.clones.get(), 1);
        config.trace.event(Event::Serialize);
        if config.fail_serialization { Err(()) } else { Ok(config.bytes.clone()) }
    }
}

#[derive(Clone, Copy)]
enum Decision { Publish, Decline, Error, Cancel }

struct RefreshError;

impl fmt::Display for RefreshError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter.write_str("synthetic refresh failure")
    }
}

enum Refresh { Cancelled, Result(Result<bool, RefreshError>) }

struct Handle {
    trace: Trace,
    config: ConfigCell,
    decision: Decision,
}

impl Handle {
    fn new(bytes: Vec<u8>, fail_serialization: bool, decision: Decision) -> Self {
        let trace = Trace::default();
        let config = ConfigCell(AppConfig {
            bytes, fail_serialization, trace: trace.clone(), _drop_spy: None,
        });
        Self { trace, config, decision }
    }

    async fn set_profile_error(&self, error: Option<String>) {
        let (waiting, finished) = if error.is_some() {
            (Event::PendingReport, Event::Reported)
        } else {
            (Event::PendingClear, Event::Cleared)
        };
        suspend_once(&self.trace, waiting).await;
        self.trace.0.errors.borrow_mut().push(error);
        self.trace.event(finished);
    }

    async fn refresh(&self) -> Refresh {
        suspend_once(&self.trace, Event::PendingRefresh).await;
        if matches!(self.decision, Decision::Cancel) {
            self.trace.event(Event::Cancelled);
            return Refresh::Cancelled;
        }
        self.trace.event(Event::Refreshed);
        Refresh::Result(match self.decision {
            Decision::Publish => Ok(true),
            Decision::Decline => Ok(false),
            Decision::Error => Err(RefreshError),
            Decision::Cancel => unreachable!(),
        })
    }
}

struct ObservePoll<'a>(&'a Trace);

impl ObservePoll<'_> {
    fn record_refresh(&mut self) {
        self.0.event(Event::RefreshPlanned);
    }
}

async fn suspend_once(trace: &Trace, event: Event) {
    let mut first = true;
    poll_fn(|_| {
        if std::mem::take(&mut first) {
            assert_eq!(trace.0.guards.get(), 0);
            trace.event(event);
            Poll::Pending
        } else {
            Poll::Ready(())
        }
    }).await;
}

fn fingerprint(config: &[u8], packages: &[u8]) -> Fingerprint {
    Fingerprint { config: config.to_vec(), packages: packages.to_vec() }
}

fn poll<T>(future: Pin<&mut dyn Future<Output = T>>) -> Poll<T> {
    future.poll(&mut Context::from_waker(Waker::noop()))
}

fn start(handle: &Handle, expected: Fingerprint, applied: Fingerprint, candidate: bool)
    -> Pin<Box<dyn Future<Output = Outcome> + '_>>
{
    if candidate {
        Box::pin(candidate::run(handle, expected, applied))
    } else {
        Box::pin(stock::run(handle, expected, applied))
    }
}

fn assert_suspended(trace: &Trace, event: Event, candidate: bool) {
    let events = trace.snapshot();
    assert_eq!(events[0..4],
               [Event::GuardAcquired, Event::Clone, Event::GuardDropped, Event::Serialize]);
    assert_eq!(events.iter().filter(|&&e| e == Event::Clone).count(), 1);
    assert_eq!(trace.0.guards.get(), 0);
    assert_eq!(trace.0.clones.get(), usize::from(!candidate));
    let wait = events.iter().position(|&e| e == event).unwrap();
    let drop = events.iter().position(|&e| e == Event::DropClone);
    if candidate {
        assert!(drop.is_some_and(|at| at < wait));
    } else {
        assert_eq!(drop, None);
    }
}

fn assert_finished(trace: &Trace) {
    assert_eq!(trace.0.clones.get(), 0);
    assert_eq!(trace.0.guards.get(), 0);
    let events = trace.snapshot();
    assert_eq!(events.iter().filter(|&&e| e == Event::Clone).count(), 1);
    assert_eq!(events.iter().filter(|&&e| e == Event::DropClone).count(), 1);
}

fn assert_equivalent_traces(old: &Handle, new: &Handle) {
    let stripped = |h: &Handle| h.trace.snapshot().into_iter()
        .filter(|e| *e != Event::DropClone).collect::<Vec<_>>();
    assert_eq!(stripped(old), stripped(new));
    assert_eq!(*old.trace.0.errors.borrow(), *new.trace.0.errors.borrow());
}

fn run_pair(bytes: Vec<u8>, fail: bool, decision: Decision,
            expected: Fingerprint, applied: Fingerprint, path: Event) -> Outcome {
    let old = Handle::new(bytes.clone(), fail, decision);
    let new = Handle::new(bytes, fail, decision);
    let mut a = start(&old, expected.clone(), applied.clone(), false);
    let mut b = start(&new, expected, applied, true);
    assert!(poll(a.as_mut()).is_pending());
    assert!(poll(b.as_mut()).is_pending());
    assert_suspended(&old.trace, path, false);
    assert_suspended(&new.trace, path, true);
    let a = poll(a.as_mut());
    let b = poll(b.as_mut());
    let (Poll::Ready(a), Poll::Ready(b)) = (a, b) else { panic!("unexpected second suspension") };
    assert_eq!(a, b);
    assert_finished(&old.trace);
    assert_finished(&new.trace);
    assert_equivalent_traces(&old, &new);
    a
}

#[test]
fn equal_profile_releases_clone_before_pending_error_clear() {
    let expected = fingerprint(b"profile", b"packages");
    let applied = fingerprint(b"old profile", b"packages");
    let result = run_pair(b"profile".to_vec(), false, Decision::Error,
                          expected.clone(), applied, Event::PendingClear);
    assert_eq!(result, (expected, Some(fingerprint(&[90], &[90]))));
}

#[test]
fn changed_config_releases_clone_before_pending_refresh() {
    let expected = fingerprint(b"new", b"packages");
    let applied = fingerprint(b"old", b"packages");
    let result = run_pair(b"old".to_vec(), false, Decision::Publish,
                          expected.clone(), applied, Event::PendingRefresh);
    assert_eq!(result, (expected, None));
}

#[test]
fn same_config_different_packages_and_declined_refresh() {
    let expected = fingerprint(b"same", b"changed");
    let applied = fingerprint(b"same", b"old packages");
    let result = run_pair(b"same".to_vec(), false, Decision::Decline,
                          expected, applied.clone(), Event::PendingRefresh);
    assert_eq!(result, (applied, Some(fingerprint(&[90], &[90]))));
}

#[test]
fn serialization_failure_still_defaults_before_comparison() {
    let applied = fingerprint(b"old", b"packages");
    for (expected, branch) in [
        (fingerprint(&[], b"packages"), Event::PendingClear),
        (fingerprint(b"profile", b"packages"), Event::PendingRefresh),
    ] {
        let result = run_pair(b"profile".to_vec(), true, Decision::Publish,
                              expected.clone(), applied.clone(), branch);
        let failed = (branch == Event::PendingClear).then(|| fingerprint(&[90], &[90]));
        assert_eq!(result, (expected, failed));
    }
}

#[test]
fn refresh_error_remains_identical_through_second_suspension() {
    let old = Handle::new(b"current".to_vec(), false, Decision::Error);
    let new = Handle::new(b"current".to_vec(), false, Decision::Error);
    let applied = fingerprint(b"current", b"packages");
    let expected = fingerprint(b"changed", b"packages");
    let mut a = start(&old, expected.clone(), applied.clone(), false);
    let mut b = start(&new, expected.clone(), applied.clone(), true);
    for event in [Event::PendingRefresh, Event::PendingReport] {
        assert!(poll(a.as_mut()).is_pending());
        assert!(poll(b.as_mut()).is_pending());
        assert_suspended(&old.trace, event, false);
        assert_suspended(&new.trace, event, true);
    }
    assert_eq!(poll(a.as_mut()), Poll::Ready((applied.clone(), Some(expected.clone()))));
    assert_eq!(poll(b.as_mut()), Poll::Ready((applied, Some(expected))));
    assert_finished(&old.trace);
    assert_finished(&new.trace);
    assert_equivalent_traces(&old, &new);
    assert_eq!(*old.trace.0.errors.borrow(), [Some("synthetic refresh failure".into())]);
}

#[test]
fn cancelled_refresh_breaks_without_committing() {
    let expected = fingerprint(b"changed", b"packages");
    let applied = fingerprint(b"old", b"packages");
    let result = run_pair(b"old".to_vec(), false, Decision::Cancel,
                          expected, applied.clone(), Event::PendingRefresh);
    assert_eq!(result, (applied, Some(fingerprint(&[90], &[90]))));
}

#[test]
fn dropping_either_suspended_future_drops_clone_exactly_once() {
    for (expected, at) in [
        (fingerprint(b"same", b"packages"), Event::PendingClear),
        (fingerprint(b"changed", b"packages"), Event::PendingRefresh),
    ] {
        let old = Handle::new(b"same".to_vec(), false, Decision::Publish);
        let new = Handle::new(b"same".to_vec(), false, Decision::Publish);
        let applied = fingerprint(b"old", b"packages");
        let mut a = start(&old, expected.clone(), applied.clone(), false);
        let mut b = start(&new, expected, applied, true);
        assert!(poll(a.as_mut()).is_pending());
        assert!(poll(b.as_mut()).is_pending());
        assert_suspended(&old.trace, at, false);
        assert_suspended(&new.trace, at, true);
        drop(a);
        drop(b);
        assert_finished(&old.trace);
        assert_finished(&new.trace);
        assert_equivalent_traces(&old, &new);
        assert!(old.trace.0.errors.borrow().is_empty());
    }
}
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stock", required=True, type=Path, help="exact unpatched profile_watch.rs")
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
    check(stock.split(OLD_START, 1)[0] == candidate.split(NEW_START, 1)[0],
          "startup, lock setup, and poll guards unchanged")
    boundary = "                // A UI save has already published this session;"
    check(stock.split(boundary, 1)[1] == candidate.split(boundary, 1)[1],
          "clear, refresh, cancel and publication unchanged")
    dt = section(stock, "struct Fingerprint {", "impl Fingerprint {")
    check(dt == section(candidate, "struct Fingerprint {", "impl Fingerprint {"), "same DTO")
    tests = {}
    with tempfile.TemporaryDirectory(prefix="r228-proof-", dir=args.work_dir) as directory:
        root = Path(directory).resolve()
        env = {"PATH": "/usr/bin:/bin", "LC_ALL": "C", "HOME": str(root), "TMPDIR": str(root)}
        version = subprocess.check_output([args.rustc, "--version", "--verbose"],
                                          cwd=root, env=env, text=True)
        check("release: 1.95.0\n" in version and "host: x86_64-unknown-linux-gnu\n" in version,
              "expected Linux x86-64 Rust 1.95.0")
        root.joinpath("proof.rs").write_text(
            "#[derive(Debug, Clone, PartialEq, Eq)]\n" + dt
            + make_lift("stock", stock, OLD_START) + make_lift("candidate", candidate, NEW_START)
            + TESTS, encoding="utf-8"
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
        "paired_drop_spy": "both arms release the read guard before serialization; stock clone survives pending clear/refresh/error-report; candidate clone drops beforehand",
        "real_tokio_serde_watcher_or_whole_core": False,
    }, indent=2))


if __name__ == "__main__":
    main()
