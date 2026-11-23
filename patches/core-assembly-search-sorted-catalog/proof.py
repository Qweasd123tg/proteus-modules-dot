#!/usr/bin/env python3
"""Replay the exact source patch and verify the Rust 1.95 assembly lookup."""

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tempfile


PATH = "crates/proteus-core/src/core/assembly/mod.rs"
BASE_BLOB = "04dd96a38d071d0be9378b3931ecec21b5dd7e72"
BASE_SHA = "938550c7126780a3dd0dd01d3bb5cd1b718a3b66056a08c133b5b17bbd02e7c4"
AFTER_BLOB = "c71aeb982b8250998d162a551bdd0064718eb87e"
AFTER_SHA = "4aa49f012ef5924a456793b295f3a603c33cb1447d8e9d745f932f87f9a4c437"
PATCH_SHA = "2addc68ecfe3a1c0dd0c191a8ccc8ac22e11d70c9d5ff9813f4b4fefffd97fcb"


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
    check(count == 4, "expected source lookup hunks only")
    return b"".join(target + lines[used:])


def section(source, first, end):
    at = source.index(first)
    return source[at:source.index(end, at + len(first))]


RUSTC_SHA = "bff349e72704ff70bc08a234a3847338e797065bbedde5e556808bc87b7bf7c6"
RUSTC_VERSION = "rustc 1.95.0 (59807616e 2026-04-14)"
REFS = {
    "catalog": ("193f0c59603086dda57fd6dc8724641b75a50181",
                "c1e9f5bf00259e14d42b99cacab601943890ce5eb368f2814f3755ce2d7fdf53"),
    "types": ("15a3b55e40ef7f648fc3b8a9b212f221a544f3e3",
              "9aa290d69dc568abcf6cd0b521190722d02a409880326d2e718715d5747a8c70"),
    "exports": ("d0449b28e04d139d287fabe82634780dbbeab2a8",
                "f496cad0e1cebff3d0fb87a9ccadcfa9bb8e96e01c4617e3e0d53447147cd666"),
    "manifest": ("35aae7fa00b5e46772278fbce12113f58269d508",
                 "c6a08604d9ac8c9f9e19351bd71047573a8beb6831ec0cffcb847a4459bae3ed"),
    "slots": ("268b6cf3396774ca48468966bbc5f70043f3e570",
              "8c9bb70e19d1e0fcad109d807f10c96a4080e9a9b4e686917d497de86ea424e9"),
}
START = "        let mut active_modules = BTreeMap::new();"
END = "        check_duplicate_requested_tools(&config, &mut checks);"
STOCK_INDEX = "        let known = catalog_entries\n"
STOCK_INDEX_END = "        let export_components ="
NEW_PROBE = "fn known_catalog_entry<'a>("
EXPORTS = "fn configured_export_components("
EXPORTS_END = "\nfn build_components("
KIND = "pub enum ModuleKind {"
KIND_IMPL = "impl ModuleKind {"
SOURCE = "pub(crate) fn catalog_module_source("


def remove_serde(source):
    return re.sub(r"^\s*#\[serde\(.+\)\]\n", "", source, flags=re.M).replace(
        ", Serialize, Deserialize", "").replace(", serde::Serialize", "").replace(", Serialize", "")


def shared(refs):
    catalog = refs["catalog"]
    summary = section(catalog, "pub struct ModuleCatalogEntrySummary {",
                      "\npub struct ModuleBuildContext")
    producer = section(catalog, "    pub fn entry_summaries(", "\n    pub(crate) fn")
    # Use the exact single method even if another public method precedes the next marker.
    producer = producer[:producer.index("\n    }") + len("\n    }")]
    check("left.slot" in producer and ".then_with(|| left.id.cmp(&right.id))" in producer,
          "sorted catalog producer")
    check("entries: HashMap<(SlotId, String), ModuleEntry>," in catalog, "actual key type")
    manifest = refs["manifest"]
    choices = section(manifest, KIND, "\nimpl ModuleManifest")
    kind = section(manifest, KIND_IMPL, "\n#[cfg(test)]")
    manifest_fields = section(manifest, "pub struct ModuleManifest {",
                              "\n#[derive(Debug, Clone, Copy")
    slot_id = re.search(r"^pub type SlotId = .+;$", manifest, re.M)
    check(slot_id is not None and slot_id[0] == "pub type SlotId = Cow<'static, str>;",
          "slot id value equality")
    types = refs["types"]
    slots_mark = "#[derive(Debug, Clone, Serialize, PartialEq, Eq)]\npub struct AssemblyModelPlan"
    slots_end = "#[derive(Debug, Clone, Serialize, PartialEq, Eq)]\npub struct AssemblyComponentPlan"
    decisions = "#[derive(Debug, Clone, Serialize, PartialEq, Eq)]\npub struct AssemblyCheck"
    export = section(refs["exports"], "    pub fn exports(&self)", "\n    pub(crate) fn remove_export")
    check("exports: BTreeMap<String, BTreeMap<String, ProcessExportLaunchConfig>>," in
          refs["exports"], "actual export map shape")
    return ("#[derive(Debug, Clone, PartialEq, Eq)]\n" + summary
            + "\nimpl ModuleCatalog {\n" + producer + "\n}\n"
            + "#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Hash)]\n" + choices
            + kind + "\n#[derive(Debug, Clone, PartialEq, Eq)]\n" + manifest_fields
            + slot_id[0] + "\n"
            + remove_serde(section(types, slots_mark, slots_end) + types[types.index(decisions):])
            + "\nmod core_slots {\n" + refs["slots"] + "\n}\n"
            + "impl ProcessComponentConfig {\n" + export + "\n}\n")


def lift(name, source, revised):
    branch = section(source, START, END)
    exports = section(source, EXPORTS, EXPORTS_END)
    classify = section(source, SOURCE, "\n#[cfg(test)]")
    if revised:
        helper = section(source, NEW_PROBE, EXPORTS)
        probe = "    known_catalog_entry(catalog_entries, slot, id)\n"
    else:
        helper = ""
        probe = section(source, STOCK_INDEX, STOCK_INDEX_END)
        probe += "    known.get(&(slot.to_owned(), id.to_owned())).copied()\n"
    return (f"mod {name} {{\nuse crate::*;\n"
            + """pub(super) fn resolve(catalog_entries: Vec<ModuleCatalogEntrySummary>, config: AppConfig,
        model: Option<AssemblyModelPlan>) -> Outcome {
    let mut checks = Vec::new();
"""
            + branch + "    (catalog_entries, slots, checks, active_modules)\n}\n"
            + helper + exports + classify
            + """pub(super) fn by_tuple<'a>(catalog_entries: &'a [ModuleCatalogEntrySummary],
        slot: &str, id: &str) -> Option<&'a ModuleCatalogEntrySummary> {
""" + probe + "}\n}\n")


TESTS = r'''
use std::{
    alloc::{GlobalAlloc, Layout, System},
    borrow::Cow,
    cell::Cell,
    collections::{BTreeMap, HashMap},
    hint::black_box,
};
use core_slots::CORE_SLOT_DESCRIPTORS;
mod domain { pub(crate) use crate::ModuleKind; }

struct ModuleCatalog { entries: HashMap<(SlotId, String), ModuleEntry> }
struct ModuleEntry { manifest: ModuleManifest }
impl ModuleCatalog {
    fn new() -> Self { Self { entries: HashMap::new() } }
    fn insert(&mut self, slot: SlotId, id: &str, kind: ModuleKind, flags: &[&str]) {
        let manifest = ModuleManifest {
            id: id.into(), kind, version: "stand-in".into(), api_version: "inert".into(),
            capabilities: flags.iter().map(|flag| (*flag).to_owned()).collect(),
            description: None,
        };
        self.entries.insert((slot, id.to_owned()), ModuleEntry { manifest });
    }
}
#[derive(Default, Clone)]
struct ProcessExportLaunchConfig;
#[derive(Default, Clone)]
struct ProcessComponentConfig { exports: BTreeMap<String, BTreeMap<String, ProcessExportLaunchConfig>> }
#[derive(Default, Clone)]
struct Modules {
    selected: Vec<(ModuleKind, String)>,
    hooks: Vec<String>,
    bad_hooks: bool,
}
impl Modules {
    fn iter(&self) -> impl Iterator<Item=(ModuleKind, &str)> {
        self.selected.iter().map(|(kind,id)| (*kind,id.as_str()))
    }
    fn validate_hooks(&self) -> Result<(), &'static str> {
        if self.bad_hooks { Err("synthetic hook failure") } else { Ok(()) }
    }
}
#[derive(Default, Clone)]
struct AppConfig {
    modules: Modules, components: BTreeMap<String, ProcessComponentConfig>, bad_commands: bool,
}
impl AppConfig {
    fn validate_commands(&self) -> Result<(), &'static str> {
        if self.bad_commands { Err("synthetic command failure") } else { Ok(()) }
    }
}
type Outcome = (Vec<ModuleCatalogEntrySummary>, Vec<AssemblySlotPlan>, Vec<AssemblyCheck>,
    BTreeMap<String,String>);
fn model(provider: &str) -> AssemblyModelPlan {
    AssemblyModelPlan { profile_id: "fixture".to_owned(), provider: provider.to_owned(),
        name: "synthetic".to_owned(), stream: false }
}
fn pair(catalog: &ModuleCatalog, config: AppConfig, model: Option<AssemblyModelPlan>) -> Outcome {
    let input = catalog.entry_summaries();
    let a = stock::resolve(input.clone(), config.clone(), model.clone());
    let b = candidate::resolve(input, config, model);
    assert_eq!(a,b);
    b
}
fn key(e: &ModuleCatalogEntrySummary) -> (&str, &str) { (e.slot.as_str(), e.id.as_str()) }

#[test]
fn real_producer_sorts_and_cow_identity_is_by_text() {
    use ModuleKind::*;
    let mut catalog = ModuleCatalog::new();
    catalog.insert(Cow::Borrowed("workflow"), "same", Workflow, &["process"]);
    catalog.insert(Cow::Borrowed("hook"), "same", Hook, &["process"]);
    catalog.insert(Cow::Owned("hook".to_owned()), "same", Hook, &["config_defined"]);
    catalog.insert(Cow::Borrowed("hook"), "ά", Hook, &[]);
    catalog.insert(Cow::Borrowed("hook"), "Z", Hook, &[]);
    catalog.insert(Cow::Borrowed("hook"), "", Hook, &[]);
    let rows = catalog.entry_summaries();
    assert_eq!(rows.iter().map(key).collect::<Vec<_>>(),
               [("hook",""),("hook","Z"),("hook","same"),("hook","ά"),("workflow","same")]);
    let expected = &rows[2];
    assert_eq!(expected.manifest.capabilities, ["config_defined"]);
    assert!(std::ptr::eq(stock::by_tuple(&rows,"hook","same").unwrap(), expected));
    assert!(std::ptr::eq(candidate::by_tuple(&rows,"hook","same").unwrap(), expected));
    assert!(candidate::by_tuple(&rows,"hook","provider\0id").is_none());
    assert!(candidate::by_tuple(&rows,"","").is_none());
    assert!(candidate::by_tuple(&rows,"z","zzz").is_none());
}

#[test]
fn exact_selection_and_diagnostic_order_keeps_owned_outputs() {
    use AssemblyModuleSource::*;
    use ModuleKind::*;
    let mut catalog = ModuleCatalog::new();
    catalog.insert(Workflow.slot_id(), "loop", Workflow, &["config_defined", "process"]);
    catalog.insert(Policy.slot_id(), "guard", Policy, &["config_defined"]);
    catalog.insert(Hook.slot_id(), "known", Hook, &["process"]);
    catalog.insert(Model.slot_id(), "model-a", Model, &[]);
    catalog.insert(Tool.slot_id(), "missing-context", Tool, &["process"]);
    let mut config = AppConfig::default();
    config.modules.selected = vec![(Workflow, "loop".into()), (Context, "missing-context".into()),
                                   (Policy, "guard".into())];
    config.modules.hooks = ["known", "missing-b", "missing-a"].into_iter().map(String::from).collect();
    config.modules.bad_hooks = true;
    config.bad_commands = true;
    config.components.insert("fixture-component".to_owned(), ProcessComponentConfig {
        exports: BTreeMap::from([("workflow".into(), BTreeMap::from([
            ("loop".into(), ProcessExportLaunchConfig)
        ]))]),
    });
    let (entries, slots, checks, active) = pair(&catalog, config, Some(model("model-a")));
    assert_eq!(entries.len(), 5);
    assert_eq!(slots.iter().map(|s| s.id.as_str()).collect::<Vec<_>>(),
               ["session_storage","hook","workflow","context","model","policy"]);
    assert_eq!(slots.iter().map(|s| s.source).collect::<Vec<_>>(),
               [None,None,Some(Process),Some(Unknown),Some(Builtin),Some(Config)]);
    assert_eq!(slots[2].component_id.as_deref(), Some("fixture-component"));
    assert_eq!(active.get("context").map(String::as_str), Some("missing-context"));
    assert_eq!(checks.iter().map(|c| (c.code.as_str(),c.message.as_str())).collect::<Vec<_>>(),
               [("module_not_registered","active module is not registered: context/missing-context"),
                ("invalid_hooks","synthetic hook failure"),("invalid_commands","synthetic command failure"),
                ("hook_not_registered","active hook is not registered: hook/missing-b"),
                ("hook_not_registered","active hook is not registered: hook/missing-a")]);
    assert!(checks.iter().all(|c| c.severity == AssemblyCheckSeverity::Error));
}

#[test]
fn synthetic_duplicate_tuple_chooses_last_exact_borrow() {
    use ModuleKind::*;
    let mut catalog = ModuleCatalog::new();
    catalog.insert(Hook.slot_id(), "a", Hook, &[]);
    catalog.insert(Hook.slot_id(), "b", Hook, &[]);
    catalog.insert(Hook.slot_id(), "c", Hook, &[]);
    let mut rows = catalog.entry_summaries();
    let mut duplicate = rows[1].clone();
    duplicate.manifest.description = Some("earlier occurrence".into());
    rows.insert(1, duplicate);
    assert!(rows.windows(2).all(|p| key(&p[0]) <= key(&p[1])));
    for (slot,id,expected) in [("hook","a",Some(&rows[0])),("hook","b",Some(&rows[2])),
                              ("hook","c",Some(&rows[3])),("hook","b0",None),
                              ("model","a",None),("","",None),("zz","zzz",None)] {
        let addr = |value: Option<&ModuleCatalogEntrySummary>| value.map(std::ptr::from_ref);
        assert_eq!(addr(stock::by_tuple(&rows,slot,id)), addr(expected));
        assert_eq!(addr(candidate::by_tuple(&rows,slot,id)), addr(expected));
    }
    assert!(candidate::by_tuple(&[], "hook", "a").is_none());
}

#[test]
fn generated_sorted_entries_and_probe_matrix() {
    use ModuleKind::*;
    let words = ["", "A", "A\0x", "a", "e\u{301}", "é", "界", "🧪"];
    let names = ["context", "hook", "model", "policy", "workflow"];
    let mut state = 113u32;
    let mut draw = |n: usize| {
        state = state.wrapping_mul(1664525).wrapping_add(1013904223);
        (state >> 16) as usize % n
    };
    for _ in 0..128 {
        let mut catalog = ModuleCatalog::new();
        for _ in 0..draw(40) {
            catalog.insert(Cow::Borrowed(names[draw(names.len())]), words[draw(words.len())],
                           [Context, Hook, Model, Policy, Workflow][draw(5)], &[]);
        }
        let rows = catalog.entry_summaries();
        for slot in names {
            for id in words {
                let oracle = rows.iter().rev().find(|e| key(e) == (slot,id)).map(std::ptr::from_ref);
                assert_eq!(stock::by_tuple(&rows,slot,id).map(std::ptr::from_ref), oracle);
                assert_eq!(candidate::by_tuple(&rows,slot,id).map(std::ptr::from_ref), oracle);
            }
        }
    }
}

#[test]
fn generated_plan_choices_and_diagnostics_keep_same_projection() {
    use ModuleKind::*;
    let names = ["A", "alpha", "á", "beta", "last", "x", "fallback", "🧪"];
    let variants = [Context, Hook, Model, Policy, SessionStorage, Workflow];
    let mut state = 511u32;
    let mut draw = |n: usize| {
        state = state.wrapping_mul(1664525).wrapping_add(1013904223);
        (state >> 16) as usize % n
    };
    for i in 0..1024 {
        let mut catalog = ModuleCatalog::new();
        let mut config = AppConfig::default();
        for k in variants {
            for _ in 0..draw(4) {
                catalog.insert(k.slot_id(), names[draw(names.len())], k,
                               [vec![], vec!["process"], vec!["config_defined"]][draw(3)].as_slice());
            }
            if k != Hook && k != Model && draw(3) != 0 {
                config.modules.selected.push((k, names[draw(names.len())].into()));
            }
        }
        config.modules.hooks = (0..draw(5)).map(|_| names[draw(names.len())].to_owned()).collect();
        config.modules.bad_hooks = i % 35 == 0;
        config.bad_commands = i % 7 == 0;
        let chosen = (i % 3 != 0).then(|| model(names[draw(names.len())]));
        let (_,_,checks,_) = pair(&catalog, config, chosen);
        if i % 7 == 0 { assert!(checks.iter().any(|c| c.code == "invalid_commands")); }
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
fn scoped_allocator_compares_exact_resolution_on_128_prepared_entries() {
    use ModuleKind::*;
    let mut catalog = ModuleCatalog::new();
    for i in 0..128 {
        let k = [Context, Hook, Model, Policy, SessionStorage, Workflow, Tool][i % 7];
        catalog.insert(k.slot_id(), &format!("candidate-{i:03}"), k, &[]);
    }
    let rows = catalog.entry_summaries();
    let mut config = AppConfig::default();
    config.modules.selected = vec![(Context, "candidate-000".into()), (Workflow, "candidate-005".into()),
                                   (Policy, "candidate-003".into()), (SessionStorage, "candidate-004".into())];
    config.modules.hooks = vec!["candidate-001".into(), "candidate-008".into()];
    let run = |new| {
        let input = rows.clone();
        let configured = config.clone();
        let selected = Some(model("candidate-002"));
        assert!(METER.replace(Some(Requests::default())).is_none());
        let outcome = black_box(if new {
            candidate::resolve(black_box(input), configured, selected)
        } else {
            stock::resolve(black_box(input), configured, selected)
        });
        let counts = METER.take().unwrap();
        (outcome, counts)
    };
    let (stock, old) = run(false);
    let (candidate, new) = run(true);
    assert_eq!(stock, candidate);
    assert_eq!(candidate.0.len(), 128);
    assert!(candidate.2.is_empty());
    assert!(old.alloc >= new.alloc + 270 && old.bytes > new.bytes);
    println!("R238_ALLOC {} {} {} {} {} {}", old.alloc, old.realloc, old.bytes,
             new.alloc, new.realloc, new.bytes);
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
    check(section(old, EXPORTS, EXPORTS_END) == section(new, EXPORTS, EXPORTS_END),
          "unchanged export diagnostics")
    refs = {}
    for key, (blob, digest) in REFS.items():
        ref = getattr(args, key).read_bytes()
        identity(ref, blob, digest)
        refs[key] = ref.decode()
    rustc = args.rustc.resolve(strict=True)
    check(hashlib.sha256(rustc.read_bytes()).hexdigest() == RUSTC_SHA, "compiler digest")
    with tempfile.TemporaryDirectory(prefix="r238-", dir=args.work.resolve(strict=True)) as temp:
        root = Path(temp)
        env = {"PATH": "/usr/bin:/bin", "HOME": temp, "TMPDIR": temp, "LC_ALL": "C"}
        version = subprocess.check_output([rustc, "--version"], cwd=root, env=env,
                                          text=True, timeout=20).strip()
        check(version == RUSTC_VERSION, "compiler version")
        unit = root / "lift.rs"
        unit.write_text(TESTS + "\n" + shared(refs) + lift("stock", old, False)
                        + lift("candidate", new, True), encoding="utf-8")
        results = {}
        for mode, flags in [("debug", []), ("optimized", ["-O"])]:
            exe = root / ("test-" + mode)
            subprocess.run([rustc, "--edition=2024", "--test", "-Dwarnings", *flags, unit,
                            "-o", exe], check=True, cwd=root, env=env, timeout=90)
            run = subprocess.run([exe, "--test-threads=1", "--nocapture"], cwd=root, env=env,
                                 capture_output=True, text=True, timeout=90)
            check(run.returncode == 0, f"{mode} tests:\n{run.stdout}\n{run.stderr}")
            tests = re.search(r"test result: ok\. (\d+) passed; 0 failed;", run.stdout)
            counts = re.search(r"\bR238_ALLOC (\d+) (\d+) (\d+) (\d+) (\d+) (\d+)$",
                               run.stdout, re.M)
            check(tests is not None and int(tests[1]) == 7, "test count")
            check(counts is not None, "allocation receipt")
            c = list(map(int, counts.groups()))
            results[mode] = {"tests_passed": int(tests[1]), "generated_lookup_pairs": 5120,
                             "generated_plan_pairs": 1024,
                             "stock_alloc_realloc_requested_bytes": c[:3],
                             "candidate_alloc_realloc_requested_bytes": c[3:]}
    print(json.dumps({"status": "PASS", "rustc": version, "rustc_sha256": RUSTC_SHA,
                      "exact_forward_and_reverse": True, "results": results,
                      "allocation_fixture_catalog_entries": 128,
                      "real_runtime_authority_serde_or_cargo": False}, indent=2))


if __name__ == "__main__":
    main()
