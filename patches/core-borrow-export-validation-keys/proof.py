#!/usr/bin/env python3
"""Replay and verify the Rust 1.95 borrowed duplicate-export key patch."""

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tempfile


PATH = "crates/proteus-core/src/core/module_catalog/components.rs"
BASE_BLOB = "3e6f29cb8e16e8b4e8a2f0f057d8c7009afb79e3"
BASE_SHA = "6f506dccb59c5a687251e6d9e42d2392cead2cfbb7d4ce3efcc88f789be7ad5c"
AFTER_BLOB = "a2128b6b4a7ceec6f6e43d15f90bf462d8947b40"
AFTER_SHA = "556d99244dfce0d6133fec40d2e475ad36bdfc0ea0cd4a7414eb24074e596e90"
PATCH_SHA = "62ead31da5e84cc45ac9b441cb827d57a6294289b33d738d7df34e5179bd152e"


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
    check(count == 1, "expected one duplicate export key hunk")
    return b"".join(target + lines[used:])


def section(source, first, end):
    at = source.index(first)
    return source[at:source.index(end, at + len(first))]


RUSTC_SHA = "bff349e72704ff70bc08a234a3847338e797065bbedde5e556808bc87b7bf7c6"
RUSTC_VERSION = "rustc 1.95.0 (59807616e 2026-04-14)"
REFS = {
    "exports": ("d0449b28e04d139d287fabe82634780dbbeab2a8",
                "f496cad0e1cebff3d0fb87a9ccadcfa9bb8e96e01c4617e3e0d53447147cd666"),
    "sandbox": ("5bae5b6fd40657554455b4fd67cfae75b9e53165",
                "75b3f481a1659cb6fed51fdd3fa257b72e0fc0ca9a69b6d23ca1f4f7e75704c0"),
    "transport": ("8d89b9478c5324ee7314af3a4296588e7d4b0d73",
                  "76ebc392979a6f1b1c7826fa145e388ac6dca53867e856aa49106b93fdfeef8b"),
    "app": ("283ffa7c6637b62f8fcce0dc225865542d0b1fb2",
            "8c7094927c4755ac0acf4e97197160fac97723fa72b6178a26a69e363d3e5d7e"),
}
CHANGE = "            if !exports.insert((slot.to_owned(), module_id.to_owned())) {"
CANDIDATE = "            if !exports.insert((slot, module_id)) {"


def remove_serde(text):
    return re.sub(r"^[ \t]*#\[serde\(.+\)\]\n", "", text, flags=re.M).replace(
        ", Serialize, Deserialize", "")


def shared(refs):
    expo = refs["exports"]
    fields = section(expo, "#[derive(Debug, Clone, Serialize, Deserialize)]",
                      "\nimpl ProcessExportLaunchConfig")
    fields = remove_serde(fields)
    fields = fields.replace("pub struct ProcessComponentConfig", "#[allow(dead_code)]\npub struct ProcessComponentConfig")
    fields = fields.replace("pub struct ProcessExportLaunchConfig", "#[allow(dead_code)]\npub struct ProcessExportLaunchConfig")
    iter_ = section(expo, "    pub fn exports(&self)", "\n    pub(crate) fn remove_export")
    guard = section(expo, "    pub fn validate_for(&self, component_id:", "\n    fn handshake_timeout")
    sandbox = section(refs["sandbox"], "#[derive(Debug, Clone, PartialEq, Eq", "\n#[cfg(test)]")
    trans = refs["transport"]
    transport = section(trans, "pub const COMPONENT_MAX_FRAME_BYTES_ENV:", "\nimpl Default")
    bounds = section(trans, "impl ComponentTransportConfig {", "\n    /// Rust workers")
    exact_app = "    pub components: BTreeMap<String, crate::process_adapters::ProcessComponentConfig>,"
    check(refs["app"].count(exact_app) == 1, "exact components shape")
    return (fields + "\nimpl ProcessComponentConfig {\n" + iter_ + guard + "\n}\n"
            + remove_serde(sandbox + transport + bounds) + "\n}\n"
            + "mod process_adapters {pub use crate::ProcessComponentConfig;}\n"
            + "#[derive(Default, Clone)]\nstruct AppConfig {\n" + exact_app + "\n}\n")


def lift(name, code):
    exact = section(code, "fn validate_component_shapes(", "\nfn ensure_process_id_is_free(")
    return (f"mod {name} {{\nuse crate::*;\n" + exact + r'''
pub(super) fn inspect(config: &AppConfig) -> Result<()> {
    validate_component_shapes(config)
}
}
''')


TESTS = r'''
use std::{
    alloc::{GlobalAlloc,Layout,System}, cell::Cell,
    collections::{BTreeMap,BTreeSet}, hint::black_box,
    path::PathBuf,
};
#[derive(Debug,Eq,PartialEq)]
pub struct Error { outer: Option<String>, message: String }
impl Error {
    fn leaf(message: String) -> Self { Self { outer: None, message } }
    fn rendered(self) -> String {
        match self.outer { Some(c) => format!("{c}: {}", self.message), None => self.message }
    }
}
type Result<T> = std::result::Result<T,Error>;
trait Context<T> { fn with_context(self, context: impl FnOnce()->String) -> Result<T>; }
impl<T> Context<T> for Result<T> {
    fn with_context(self, context: impl FnOnce()->String) -> Result<T> {
        self.map_err(|prior| Error { outer: Some(context()), message: prior.rendered() })
    }
}
macro_rules! bail { ($($args:tt)*) => { return Err(Error::leaf(format!($($args)*))) }; }
macro_rules! ensure { ($cond:expr, $($args:tt)*) => { if !$cond { bail!($($args)*) } }; }

fn component(exports: &[(&str,&str)]) -> ProcessComponentConfig {
    let mut c = ProcessComponentConfig {
        command: "inert-fixture".into(), args: vec![], cwd: None, env_allowlist: vec![],
        env: BTreeMap::new(), sandbox: ProcessSandboxConfig::default(), handshake_timeout_ms: None,
        transport: None, description: None, icon: None, exports: BTreeMap::new(),
    };
    for &(slot,id) in exports {
        c.exports.entry(slot.into()).or_default().insert(id.into(), ProcessExportLaunchConfig::default());
    }
    c
}
fn cfg(items: impl IntoIterator<Item=(&'static str, ProcessComponentConfig)>) -> AppConfig {
    AppConfig { components: items.into_iter().map(|(k,v)| (k.into(),v)).collect() }
}
fn pair(input: &AppConfig) -> Result<()> {
    let a = stock::inspect(input);
    let b = candidate::inspect(input);
    assert_eq!(a,b,"paired guard/error mismatch");
    b
}
fn expects(input: AppConfig, message: &str) {
    assert_eq!(pair(&input).unwrap_err().rendered(), message);
}

#[test]
fn tuple_keys_preserve_exact_text_and_all_allowed_shapes() {
    pair(&AppConfig::default()).unwrap();
    let a = component(&[("model","shared"),("slot","β"),("case","Z"),("a:b","c"),
                        ("slot","é"), ("slot"," id")]);
    let b = component(&[("workflow","shared"),("slot ","β"),("case","z"),("a","b:c"),
                        ("slot","e\u{301}"), ("slot","id")]);
    pair(&cfg([("second",b.clone()),("first",a.clone())])).unwrap();
    let c = component(&[("slot","β")]);
    expects(cfg([("second",b),("first",a),("third",c)]), "duplicate process component export: slot/β");
}

#[test]
fn previous_duplicate_vs_current_full_shape_and_later_fault() {
    let first=component(&[("model","exact")]);
    let duplicate=component(&[("model","exact")]);
    let mut broken=duplicate.clone();
    broken.command=" \t ".into();
    expects(cfg([("z",duplicate.clone()),("b",broken.clone()),("a",first.clone())]),
            "components.b.command must not be empty");
    expects(cfg([("c",broken),("b",duplicate.clone()),("a",first.clone())]),
            "duplicate process component export: model/exact");
    let mut second=component(&[("model","exact"),("workflow","extra")]);
    second.exports.get_mut("workflow").unwrap().get_mut("extra").unwrap().timeout_ms=Some(0);
    expects(cfg([("b",second),("a",first)]),
            "components.b.exports.workflow.extra.timeout_ms must be greater than zero");
}

#[test]
fn actual_per_component_name_export_and_timeout_rules() {
    let ordinary=component(&[("model","one")]);
    expects(cfg([(" \t",ordinary.clone())]),"components. \t component id must not be empty");
    let mut handshake=ordinary;
    handshake.handshake_timeout_ms=Some(0);
    expects(cfg([("a",handshake)]),"components.a.handshake_timeout_ms must be greater than zero");
    expects(cfg([("a",component(&[]))]),"components.a.exports must not be empty");
    expects(cfg([("a",component(&[(" ","id")]))]),"components.a.exports contains an empty slot");
    let mut no_module=component(&[]);
    no_module.exports.insert("model".into(),BTreeMap::new());
    expects(cfg([("a",no_module)]),"components.a.exports.model must not be empty");
    expects(cfg([("a",component(&[("model"," \n")]))]),
            "components.a.exports.model contains an empty module id");
}

fn restricted(empty: bool) -> ProcessSandboxConfig {
    ProcessSandboxConfig::Restricted {
        read_only: vec![if empty { PathBuf::new() } else { "/inert/not-accessed".into() }],
        read_write: vec![], network: false, read_executable: false,
    }
}

#[test]
fn exact_sandbox_host_owned_env_and_transport_frame_guards_stay_in_order() {
    let mut multiple=component(&[("model","one"),("workflow","two")]);
    multiple.sandbox=restricted(true);
    expects(cfg([("a",multiple)]),
            "components.a.sandbox: restricted components require exactly one export; split exports into separate components");
    let mut single=component(&[("model","one")]);
    single.sandbox=restricted(true);
    single.env.insert(COMPONENT_MAX_FRAME_BYTES_ENV.into(),"inert".into());
    single.transport=Some(ComponentTransportConfig { max_frame_bytes: 0 });
    expects(cfg([("a",single.clone())]),"components.a.sandbox: sandbox grant paths must not be empty");
    single.sandbox=restricted(false);
    expects(cfg([("a",single.clone())]),
            "components.a.transport: PROTEUS_MODULE_MAX_FRAME_BYTES is host-owned; configure transport.max_frame_bytes instead");
    single.env.clear();
    for invalid in [0, MAX_COMPONENT_FRAME_BYTES+1] {
        single.transport=Some(ComponentTransportConfig {max_frame_bytes: invalid});
        expects(cfg([("a",single.clone())]), &format!(
            "components.a.transport: component transport max_frame_bytes must be between 1 and {MAX_COMPONENT_FRAME_BYTES}"));
    }
    for valid in [1, MAX_COMPONENT_FRAME_BYTES] {
        single.transport=Some(ComponentTransportConfig {max_frame_bytes: valid});
        pair(&cfg([("a",single.clone())])).unwrap();
    }
}

#[test]
fn generated_ordered_components_preserve_first_exact_failure() {
    let mut state=93u32;
    let mut draw=|n:usize| {
        state=state.wrapping_mul(1664525).wrapping_add(1013904223);
        (state>>16) as usize %n
    };
    let mut accepted=0;
    let mut duplicate=0;
    let mut bad=0;
    for _ in 0..4096 {
        let names=["delta","beta","γ","alpha","kappa"];
        let slots=["model","tool","workflow","hook","ó"];
        let ids=["β","plain","x"," e","é","e\u{301}"];
        let mut input=AppConfig::default();
        for name in names.into_iter().take(draw(names.len()+1)) {
            let mut exports=Vec::new();
            for _ in 0..(draw(4)+1) {
                exports.push((slots[draw(slots.len())],ids[draw(ids.len())]));
            }
            let mut c=component(&exports);
            match draw(13) {
                0 => c.sandbox=restricted(false),
                1 => c.sandbox=restricted(true),
                2 => c.handshake_timeout_ms=Some(0),
                3 => { c.env.insert(COMPONENT_MAX_FRAME_BYTES_ENV.into(),"fixture".into()); }
                4 => c.transport=Some(ComponentTransportConfig{max_frame_bytes:0}),
                _ => {}
            }
            input.components.insert(name.into(),c);
        }
        match pair(&input) {
            Ok(()) => accepted+=1,
            Err(e) if e.message.starts_with("duplicate process component export:") => duplicate+=1,
            Err(_) => bad+=1,
        }
    }
    assert!(accepted>0 && duplicate>0 && bad>0);
    assert_eq!(accepted+duplicate+bad,4096);
}

#[derive(Clone,Copy,Debug,Default)]
struct Requests { alloc:usize, realloc:usize, bytes:usize }
thread_local! { static METER:Cell<Option<Requests>>=const {Cell::new(None)}; }
fn requested(bytes:usize, re:bool) {
    let _=METER.try_with(|meter| {
        if let Some(mut t)=meter.get() {
            t.bytes+=bytes;
            if re {t.realloc+=1;} else {t.alloc+=1;}
            meter.set(Some(t));
        }
    });
}
struct Allocator;
unsafe impl GlobalAlloc for Allocator {
    unsafe fn alloc(&self,a:Layout)->*mut u8 { requested(a.size(),false); unsafe {System.alloc(a)} }
    unsafe fn alloc_zeroed(&self,a:Layout)->*mut u8 {
        requested(a.size(),false); unsafe {System.alloc_zeroed(a)}
    }
    unsafe fn realloc(&self,p:*mut u8,a:Layout,n:usize)->*mut u8 {
        requested(n,true); unsafe {System.realloc(p,a,n)}
    }
    unsafe fn dealloc(&self,p:*mut u8,a:Layout) { unsafe {System.dealloc(p,a)} }
}
#[global_allocator]
static ALLOCATOR:Allocator=Allocator;

#[test]
fn allocation_scope_compares_real_guards_on_128_shape_valid_exports() {
    let mut c=component(&[]);
    for k in 0..8 {
        let slot = format!("slot-{k}");
        let modules = c.exports.entry(slot).or_default();
        for i in 0..16 {
            modules.insert(format!("fixture-module-{i:02}"), ProcessExportLaunchConfig::default());
        }
    }
    assert_eq!(c.exports().count(),128);
    let app=cfg([("prepared",c)]);
    let run=|new| {
        METER.set(Some(Requests::default()));
        let result=black_box(if new { candidate::inspect(black_box(&app)) }
                             else { stock::inspect(black_box(&app)) });
        let counts=METER.take().unwrap();
        result.unwrap();
        counts
    };
    let (old,new)=(run(false),run(true));
    assert!(old.alloc>=new.alloc+256);
    assert!(old.bytes>new.bytes);
    println!("R244_ALLOC {} {} {} {} {} {}",old.alloc,old.realloc,old.bytes,new.alloc,new.realloc,new.bytes);
}
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("stock", "rustc", "work", *REFS):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    raw = args.stock.read_bytes()
    identity(raw, BASE_BLOB, BASE_SHA)
    patch = Path(__file__).with_name("source.patch").read_bytes()
    check(hashlib.sha256(patch).hexdigest() == PATCH_SHA, "patch digest")
    changed = replay(raw, patch)
    identity(changed, AFTER_BLOB, AFTER_SHA)
    check(replay(changed, patch, reverse=True) == raw, "exact rollback")
    old, new = raw.decode(), changed.decode()
    check(old.count(CHANGE) == 1 and old.replace(CHANGE, CANDIDATE, 1) == new,
          "sole source change")
    refs = {}
    for key, (blob, digest) in REFS.items():
        ref = getattr(args, key).read_bytes()
        identity(ref, blob, digest)
        refs[key] = ref.decode()
    rustc = args.rustc.resolve(strict=True)
    check(hashlib.sha256(rustc.read_bytes()).hexdigest() == RUSTC_SHA, "compiler digest")
    with tempfile.TemporaryDirectory(prefix="r244-", dir=args.work.resolve(strict=True)) as temp:
        root = Path(temp)
        env = {"PATH": "/usr/bin:/bin", "HOME": temp, "TMPDIR": temp, "LC_ALL": "C"}
        version = subprocess.check_output([rustc, "--version"], cwd=root, env=env,
                                          text=True, timeout=20).strip()
        check(version == RUSTC_VERSION, "compiler version")
        unit = root / "lift.rs"
        unit.write_text(TESTS + "\n" + shared(refs) + lift("stock", old) + lift("candidate", new),
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
            counts = re.search(r"\bR244_ALLOC (\d+) (\d+) (\d+) (\d+) (\d+) (\d+)$",
                               run.stdout, re.M)
            check(tests is not None and int(tests[1]) == 6, "test count")
            check(counts is not None, "allocation receipt")
            c = list(map(int, counts.groups()))
            results[mode] = {"tests_passed": int(tests[1]), "generated_pairs": 4096,
                             "stock_alloc_realloc_requested_bytes": c[:3],
                             "candidate_alloc_realloc_requested_bytes": c[3:]}
    print(json.dumps({"status": "PASS", "rustc": version, "rustc_sha256": RUSTC_SHA,
                      "exact_forward_and_reverse": True, "results": results,
                      "allocation_fixture_exports": 128,
                      "actual_grants_process_authority_serde_or_cargo": False}, indent=2))


if __name__ == "__main__":
    main()
