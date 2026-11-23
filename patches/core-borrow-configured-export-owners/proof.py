#!/usr/bin/env python3
"""Verify the exact borrowed export index and two-way #547 composition."""

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
AFTER_BLOB = "e7218d76805468b9526bece8fdd7bf817f2f4f05"
AFTER_SHA = "88dcbf0a86f9dc7579d3d87c7d8924c612fdcf7883860225bbfaebee5c4a87d6"
PATCH_SHA = "aff1304eec44c868db44e07ce23f7d65f94e8503c2299fa311bd2ad7a99252a3"


def check(condition, label):
    if not condition:
        raise ValueError(label)


def identity(source, blob, digest):
    check(hashlib.sha256(source).hexdigest() == digest, "SHA256")
    git_bytes = b"blob " + str(len(source)).encode() + b"\0" + source
    check(hashlib.sha1(git_bytes).hexdigest() == blob, "Git blob")


def replay(src, patch, pre, post, count_expected, reverse=False):
    lines = src.splitlines(keepends=True)
    expected_header = (
        f"diff --git a/{PATH} b/{PATH}\n"
        f"index {pre}..{post} 100644\n"
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
    check(count == count_expected, "expected exact hunk count")
    return b"".join(target + lines[used:])


def section(source, first, end):
    at = source.index(first)
    return source[at:source.index(end, at + len(first))]


RUSTC_SHA = "bff349e72704ff70bc08a234a3847338e797065bbedde5e556808bc87b7bf7c6"
RUSTC_VERSION = "rustc 1.95.0 (59807616e 2026-04-14)"
REFS = {
    "app": ("283ffa7c6637b62f8fcce0dc225865542d0b1fb2",
            "8c7094927c4755ac0acf4e97197160fac97723fa72b6178a26a69e363d3e5d7e"),
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
    check("pub components: BTreeMap<String, crate::process_adapters::ProcessComponentConfig>,"
          in refs["app"], "exact config ownership shape")
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
            + branch + "    (catalog_entries, slots, checks, active_modules, config)\n}\n"
            + helper + exports + classify
            + """pub(super) fn by_tuple<'a>(catalog_entries: &'a [ModuleCatalogEntrySummary],
        slot: &str, id: &str) -> Option<&'a ModuleCatalogEntrySummary> {
""" + probe + "}\n}\n")


PR547_BLOB = "c71aeb982b8250998d162a551bdd0064718eb87e"
PR547_SHA = "4aa49f012ef5924a456793b295f3a603c33cb1447d8e9d745f932f87f9a4c437"
PR547_PATCH_SHA = "2addc68ecfe3a1c0dd0c191a8ccc8ac22e11d70c9d5ff9813f4b4fefffd97fcb"
COMPOSED_BLOB = "4357b97d7673e0a20df89ce63486d2119a8831ff"
COMPOSED_SHA = "c97f8b62642a1ff33bd4f962925ac9c58381d8a8b676cd051e6fbe002b8dbe12"
CARRY_547_SHA = "75f22b9ae326fe6c7630f3755919dcdc2bdd315fb73758c4b304551539dfb43a"


def swap_exact(raw, before, after):
    check(raw.count(before) == 1, "single context-only substitution")
    return raw.replace(before, after, 1)


def index(before, after):
    return f"index {before}..{after} 100644\n".encode()


def compose(stock, r246, p547):
    only246 = replay(stock, r246, BASE_BLOB, AFTER_BLOB, 2)
    identity(only246, AFTER_BLOB, AFTER_SHA)
    check(replay(only246, r246, BASE_BLOB, AFTER_BLOB, 2, True) == stock, "R246 rollback")
    only547 = replay(stock, p547, BASE_BLOB, PR547_BLOB, 4)
    identity(only547, PR547_BLOB, PR547_SHA)
    check(replay(only547, p547, BASE_BLOB, PR547_BLOB, 4, True) == stock, "#547 rollback")

    # #547 changes the earlier prefix lengths by -4 and +10 at these exact
    # R246 hunk starts. Leave every context/removal/addition body byte intact.
    carry246 = swap_exact(r246, index(BASE_BLOB, AFTER_BLOB), index(PR547_BLOB, COMPOSED_BLOB))
    carry246 = swap_exact(carry246, b"@@ -89,6 +89,6 @@\n", b"@@ -85,6 +85,6 @@\n")
    carry246 = swap_exact(carry246, b"@@ -276,12 +276,9 @@\n", b"@@ -286,12 +286,9 @@\n")

    # The actual old #547 edit does not touch the signature, but asks for
    # its old spelling as context. R246 already changed that spelling.
    carry547 = swap_exact(p547, index(BASE_BLOB, PR547_BLOB), index(AFTER_BLOB, COMPOSED_BLOB))
    old_sig = b" fn configured_export_components(config: &AppConfig) -> BTreeMap<(String, String), String> {\n"
    new_sig = b" fn configured_export_components(config: &AppConfig) -> BTreeMap<(&str, &str), &str> {\n"
    check(old_sig in p547 and old_sig[1:] not in only246 and new_sig[1:] in only246,
          "explicit stale context, not a rewritten change line")
    # Header adjustment alone intentionally fails; no fuzzy context bypass.
    try:
        replay(only246, carry547, AFTER_BLOB, COMPOSED_BLOB, 4)
    except ValueError as error:
        check(str(error) == "patch preimage", "exact expected context rejection")
    else:
        raise ValueError("historical signature context unexpectedly matched")
    carry547 = swap_exact(carry547, old_sig, new_sig)
    check(hashlib.sha256(carry547).hexdigest() == CARRY_547_SHA, "independent #547 carry pin")

    left = replay(only547, carry246, PR547_BLOB, COMPOSED_BLOB, 2)
    right = replay(only246, carry547, AFTER_BLOB, COMPOSED_BLOB, 4)
    check(left == right, "commuting exact composition")
    identity(left, COMPOSED_BLOB, COMPOSED_SHA)
    check(replay(left, carry246, PR547_BLOB, COMPOSED_BLOB, 2, True) == only547, "post547 rollback")
    check(replay(right, carry547, AFTER_BLOB, COMPOSED_BLOB, 4, True) == only246, "post246 rollback")
    return (stock, only246, only547, left), {
        "after547-r246.patch": carry246, "after246-547.patch": carry547,
    }


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
#[derive(Default, Clone, Debug, PartialEq, Eq)]
struct ProcessExportLaunchConfig;
#[derive(Default, Clone, Debug, PartialEq, Eq)]
struct ProcessComponentConfig { exports: BTreeMap<String, BTreeMap<String, ProcessExportLaunchConfig>> }
#[derive(Default, Clone, Debug, PartialEq, Eq)]
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
#[derive(Default, Clone, Debug, PartialEq, Eq)]
struct AppConfig {
    modules: Modules, components: BTreeMap<String, ProcessComponentConfig>, bad_commands: bool,
}
impl AppConfig {
    fn validate_commands(&self) -> Result<(), &'static str> {
        if self.bad_commands { Err("synthetic command failure") } else { Ok(()) }
    }
}
type Outcome = (Vec<ModuleCatalogEntrySummary>, Vec<AssemblySlotPlan>, Vec<AssemblyCheck>,
    BTreeMap<String,String>, AppConfig);
fn model(provider: &str) -> AssemblyModelPlan {
    AssemblyModelPlan { profile_id: "fixture".to_owned(), provider: provider.to_owned(),
        name: "synthetic".to_owned(), stream: false }
}
fn pair(catalog: &ModuleCatalog, config: AppConfig, model: Option<AssemblyModelPlan>) -> Outcome {
    let input = catalog.entry_summaries();
    let for_547 = model.clone();
    let a = stock::resolve(input.clone(), config.clone(), model.clone());
    let b = candidate::resolve(input, config, model);
    let c = after547::resolve(b.0.clone(), b.4.clone(), for_547.clone());
    let d = composed::resolve(b.0.clone(), b.4.clone(), for_547);
    assert_eq!(a,b);
    assert_eq!(b,c);
    assert_eq!(c,d);
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
    let (entries, slots, checks, active, retained_config) = pair(&catalog, config, Some(model("model-a")));
    assert_eq!(entries.len(), 5);
    let original_owner = retained_config.components.get_key_value("fixture-component").unwrap().0;
    assert_ne!(slots[2].component_id.as_ref().unwrap().as_ptr(), original_owner.as_ptr());
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
                assert_eq!(after547::by_tuple(&rows,slot,id).map(std::ptr::from_ref), oracle);
                assert_eq!(composed::by_tuple(&rows,slot,id).map(std::ptr::from_ref), oracle);
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
        let (_,_,checks,_,_) = pair(&catalog, config, chosen);
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
fn exact_export_owner_pairs_preserve_last_config_order_and_missing_catalog_behavior() {
    use ModuleKind::*;
    let mut catalog = ModuleCatalog::new();
    catalog.insert(Cow::Borrowed("workflow"), "β", Workflow, &["process"]);
    let config = |entries: &[(&str,&str,&str)]| {
        let mut c=AppConfig::default();
        c.modules.selected=vec![(Workflow,"β".into()),(Context,"same".into()),
                                (Policy,"unowned".into())];
        for (component,slot,module) in entries {
            c.components.entry(component.to_string()).or_default()
                .exports.entry(slot.to_string()).or_default()
                .insert(module.to_string(),ProcessExportLaunchConfig);
        }
        c
    };
    let data=[("z later","workflow","β"),("a first","workflow","β"),
              ("owner for context","context","same"),("z alias","workflow","β "),
              ("other slot","policy","same")];
    let a=pair(&catalog,config(&data),None);
    let rev=data.iter().rev().copied().collect::<Vec<_>>();
    let b=pair(&catalog,config(&rev),None);
    assert_eq!(a,b);
    let find=|out:&Outcome,slot:&str| {
        out.1.iter().find(|s|s.id==slot).unwrap().component_id.clone()
    };
    assert_eq!(find(&a,"workflow").as_deref(),Some("z later"));
    assert_eq!(find(&a,"context").as_deref(),Some("owner for context"));
    assert_eq!(find(&a,"policy"),None);
    assert_eq!(a.2.iter().map(|d|d.message.as_str()).collect::<Vec<_>>(),[
        "active module is not registered: context/same",
        "active module is not registered: policy/unowned"]);
}

#[test]
fn generated_configured_export_ownership_quadrants() {
    let mut state=228u32;
    let mut next=|n:usize| {
        state=state.wrapping_mul(1664525).wrapping_add(1013904223);
        (state>>16) as usize % n
    };
    let kinds=[ModuleKind::Workflow,ModuleKind::Context,ModuleKind::Policy,
               ModuleKind::SessionStorage,ModuleKind::Model];
    let texts=["owner","id","id "," β","é","e\u{301}","A","\0","🧪"];
    for i in 0..4096 {
        let mut cat=ModuleCatalog::new();
        let mut input=AppConfig::default();
        for k in kinds {
            for _ in 0..next(4) { cat.insert(k.slot_id(),texts[next(texts.len())],k,&[]); }
            if k!=ModuleKind::Model && i%3!=0 {
                input.modules.selected.push((k,texts[next(texts.len())].into()));
            }
        }
        for _ in 0..next(21) {
            let name=texts[next(texts.len())];
            let kind=kinds[next(kinds.len())].as_str();
            let id=texts[next(texts.len())];
            input.components.entry(name.into()).or_default()
                .exports.entry(kind.into()).or_default()
                .insert(id.into(),ProcessExportLaunchConfig);
        }
        let selected=(i%4!=0).then(||model(texts[next(texts.len())]));
        let _=pair(&cat,input,selected);
    }
}

#[test]
fn scoped_allocation_of_real_export_inventory_in_both_pairings() {
    let mut catalog=ModuleCatalog::new();
    let mut config=AppConfig::default();
    for i in 0..128 {
        let module=format!("fixture-{i:03}");
        catalog.insert(ModuleKind::Workflow.slot_id(),&module,ModuleKind::Workflow,&[]);
        config.components.entry(format!("fixture-component-{i:03}")).or_default()
            .exports.entry("workflow".into()).or_default()
            .insert(module, ProcessExportLaunchConfig);
    }
    config.modules.selected=vec![(ModuleKind::Workflow,"fixture-002".into())];
    let rows=catalog.entry_summaries();
    let run=|arm:fn(Vec<ModuleCatalogEntrySummary>,AppConfig,Option<AssemblyModelPlan>)->Outcome| {
        let prepped=rows.clone();
        let configured=config.clone();
        METER.set(Some(Requests::default()));
        let outcome=black_box(arm(black_box(prepped),configured,None));
        let count=METER.take().expect("scope");
        assert_eq!(outcome.1[2].component_id.as_deref(),Some("fixture-component-002"));
        assert!(outcome.2.is_empty());
        (outcome,count)
    };
    let (a,base)=run(stock::resolve);
    let (b,alone)=run(candidate::resolve);
    let (c,anchor)=run(after547::resolve);
    let (d,both)=run(composed::resolve);
    assert_eq!(a,b);
    assert_eq!(b,c);
    assert_eq!(c,d);
    assert!(base.alloc>=alone.alloc+384 && base.bytes>alone.bytes);
    assert!(anchor.alloc>=both.alloc+384 && anchor.bytes>both.bytes);
    println!("R246_ALLOC {} {} {} {} {} {} {} {} {} {} {} {}",
        base.alloc,base.realloc,base.bytes,alone.alloc,alone.realloc,alone.bytes,
        anchor.alloc,anchor.realloc,anchor.bytes,both.alloc,both.realloc,both.bytes);
}
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("stock", "rustc", "work", "pr547", *REFS):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--emit-continuations", type=Path,
                        help="optionally create a new directory for the two exact generated patches")
    args = parser.parse_args()
    raw = args.stock.read_bytes()
    identity(raw, BASE_BLOB, BASE_SHA)
    patch = Path(__file__).with_name("source.patch").read_bytes()
    p547 = args.pr547.read_bytes()
    check(hashlib.sha256(patch).hexdigest() == PATCH_SHA, "R246 patch digest")
    check(hashlib.sha256(p547).hexdigest() == PR547_PATCH_SHA, "#547 patch digest")
    arms, carries = compose(raw, patch, p547)
    carry_sums = {name:hashlib.sha256(value).hexdigest() for name,value in carries.items()}
    refs = {}
    for key,(blob,digest) in REFS.items():
        ref=getattr(args,key).read_bytes()
        identity(ref,blob,digest)
        refs[key]=ref.decode()
    rustc=args.rustc.resolve(strict=True)
    check(hashlib.sha256(rustc.read_bytes()).hexdigest()==RUSTC_SHA,"compiler digest")
    with tempfile.TemporaryDirectory(prefix="r246-",dir=args.work.resolve(strict=True)) as temp:
        root=Path(temp)
        env={"PATH":"/usr/bin:/bin","HOME":temp,"TMPDIR":temp,"LC_ALL":"C"}
        version=subprocess.check_output([rustc,"--version"],cwd=root,env=env,
                                        text=True,timeout=20).strip()
        check(version==RUSTC_VERSION,"compiler version")
        unit=root/"lift.rs"
        names=("stock","candidate","after547","composed")
        unit.write_text(TESTS+"\n"+shared(refs)+"".join(
            lift(name, raw.decode(), i>=2) for i,(name,raw) in enumerate(zip(names,arms))),
            encoding="utf-8")
        results={}
        for mode,flags in [("debug",[]),("optimized",["-O"])]:
            exe=root/("test-"+mode)
            subprocess.run([rustc,"--edition=2024","--test","-Dwarnings",*flags,unit,
                            "-o",exe],check=True,cwd=root,env=env,timeout=90)
            run=subprocess.run([exe,"--test-threads=1","--nocapture"],cwd=root,env=env,
                               capture_output=True,text=True,timeout=90)
            check(run.returncode==0,f"{mode} tests:\n{run.stdout}\n{run.stderr}")
            tests=re.search(r"test result: ok\. (\d+) passed; 0 failed;",run.stdout)
            counts=re.search(r"\bR246_ALLOC ((?:\d+ ){11}\d+)$",run.stdout,re.M)
            check(tests is not None and int(tests[1])==9,"test count")
            check(counts is not None,"allocator receipt")
            c=list(map(int,counts[1].split()))
            results[mode]={"tests_passed":int(tests[1]),"generated_export_cases":4096,
                           "stock_alloc_realloc_requested_bytes":c[:3],
                           "r246_alloc_realloc_requested_bytes":c[3:6],
                           "pr547_alloc_realloc_requested_bytes":c[6:9],
                           "composed_alloc_realloc_requested_bytes":c[9:]}
    # Optional output never overwrites source code or an existing directory.
    if args.emit_continuations:
        emit = args.emit_continuations
        emit.mkdir(mode=0o700, exist_ok=False)
        for name,value in carries.items():
            (emit/name).write_bytes(value)
        (emit/"SHA256SUMS").write_text("".join(f"{sha}  {name}\n" for name,sha in carry_sums.items()))
    print(json.dumps({"status":"PASS","rustc":version,"rustc_sha256":RUSTC_SHA,
                      "exact_forward_and_reverse":True,"both_composition_orders_equal":True,
                      "composed_git_blob":COMPOSED_BLOB,"composed_sha256":COMPOSED_SHA,
                      "continuation_sha256":carry_sums,
                      "results":results,"full_runtime_authority_serde_or_cargo":False},indent=2))


if __name__=="__main__":
    main()
