#!/usr/bin/env python3
"""Replay and verify the one-line Rust 1.95 config export ownership move."""

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tempfile


PATH = "crates/proteus-core/src/core/registry.rs"
BASE_BLOB = "0b6f9054633e66ea77c765d8f8c46c1a0c55112c"
BASE_SHA = "203e7a12ab450ba98dd0f5d8bc71c3a88179424fae8130055b6e8d68c793b5e5"
AFTER_BLOB = "0b610833bf032129700ebd67e6e4e185397b3e3d"
AFTER_SHA = "27ee1516a0de7256f2bb354e83ca7a282c1c116df5e43a7176db9aefe5c675f1"
PATCH_SHA = "cf0b5714bc5dc491789e7d64ef93975b791f96de2e01ed371c9a9125180fd6e2"


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
    check(count == 1, "expected one owned config-export move")
    return b"".join(target + lines[used:])


def section(source, first, end):
    at = source.index(first)
    return source[at:source.index(end, at + len(first))]


RUSTC_SHA = "bff349e72704ff70bc08a234a3847338e797065bbedde5e556808bc87b7bf7c6"
RUSTC_VERSION = "rustc 1.95.0 (59807616e 2026-04-14)"
REFS = {
    "catalog": ("193f0c59603086dda57fd6dc8724641b75a50181",
                "c1e9f5bf00259e14d42b99cacab601943890ce5eb368f2814f3755ce2d7fdf53"),
    "exports": ("d0449b28e04d139d287fabe82634780dbbeab2a8",
                "f496cad0e1cebff3d0fb87a9ccadcfa9bb8e96e01c4617e3e0d53447147cd666"),
    "binding": ("08a96a9b26bd318473b3d3c611f8b8f008d17ac3",
                "07d202d227ed10e7004be376ea90f09ae0d45c71802cbd8f19e4ed21f17be99c"),
}
CHANGE = "            config_exports: catalog.config_exports.clone(),"
TAIL = "        let policy_ctx = PolicyBuildContext { cwd };"
TAIL_END = "\n\n    pub fn execution_context("
LOOKUP = "        let Some(export) = self\n            .config_exports"
LOOKUP_END = "        let cwd = self.cwd.clone();"


def shared(refs):
    catalog = refs["catalog"]
    check("pub(crate) config_exports: Vec<ProcessExportConfig>," in catalog
          and "impl Drop for ModuleCatalog" not in catalog, "catalog owned field shape")
    binding = section(refs["binding"], "#[derive(Debug, Clone, PartialEq)]\npub struct ProcessExportBinding",
                      "\nimpl ProcessExportBinding")
    exports = section(refs["exports"], "#[derive(Debug, Clone)]\npub(crate) struct ProcessExportConfig",
                      "    pub(crate) fn connect(&self, workspace:")
    return binding + exports + "}\n"


def lift(name, code):
    tail = section(code, TAIL, TAIL_END)
    lookup = section(code, LOOKUP, LOOKUP_END)
    start = "        plan.ensure_valid()?;"
    check(code.count(start) == 1, "plan validation before tail")
    return (f"mod {name} {{\nuse crate::*;\n"
            + r'''
#[allow(dead_code)]
#[derive(Clone)]
pub(super) struct RuntimeRegistry {
    config_exports: Vec<ProcessExportConfig>,
    session_storage: Option<Arc<dyn SessionStorage>>,
    hooks: u8,
    cwd: PathBuf,
    model_config: u8,
    runtime_config: RuntimeConfig,
    instructions: u8,
    model_service: u8,
    context: u8,
    tools: u8,
    tool_allowlist: u8,
    tool_inventory: u8,
    process_tool_specs: Vec<String>,
    policy: Arc<dyn ApprovalPolicy>,
    agent_control: u8,
    workflow: Arc<dyn Workflow>,
    context_providers: u8,
    mcp_servers: Vec<String>,
    plugins: Vec<String>,
}
impl RuntimeRegistry {
    pub(super) fn complete(plan: &AssemblyPlan, catalog: ModuleCatalog,
                          storage: Option<Arc<dyn SessionStorage>>) -> Result<Self> {
''' + start + r'''
        let config = &plan.config;
        let cwd = plan.cwd.as_path();
        let build_ctx = ModuleBuildContext { cwd };
        let (hooks, model_config, model_service, context, tools, tool_allowlist,
             tool_inventory, agent_control, context_providers) = (1,2,3,4,5,6,7,8,9);
        let surface = FixtureSurface {
            process_tool_specs: vec!["discovery only".into()],
            mcp_servers: vec!["synthetic mcp".into()],
        };
        let addons = FixtureAddons { plugins: vec!["synthetic plugin".into()] };
''' + tail + r'''
    pub(super) fn select_export(&self, provider: &str) -> Result<Option<ProcessExportConfig>> {
''' + lookup + r'''
        Ok(Some(export))
    }
    pub(super) fn observe(&self) -> View<'_> {
        View {
            entries: &self.config_exports,
            policy: self.policy.id(), workflow: self.workflow.id(),
            session_storage: self.session_storage.as_ref().map(|storage| storage.id()),
            process_tool_specs: &self.process_tool_specs,
            mcp_servers: &self.mcp_servers, plugins: &self.plugins, cwd: &self.cwd,
        }
    }
}
}
''')


TESTS = r'''
use std::{
    alloc::{GlobalAlloc, Layout, System}, cell::Cell, collections::BTreeMap, hint::black_box,
    path::{Path, PathBuf}, sync::{Arc, Mutex, Weak}, time::Duration,
};
type Result<T> = std::result::Result<T, String>;
macro_rules! bail { ($($args:tt)*) => { return Err(format!($($args)*)) } }

#[derive(Debug, PartialEq, Eq)]
pub enum Value { Object(BTreeMap<String,Value>), Array(Vec<Value>), Text(String), Number(u64) }
thread_local! { static VALUE_CLONES: Cell<usize> = const { Cell::new(0) }; }
impl Clone for Value {
    fn clone(&self) -> Self {
        VALUE_CLONES.set(VALUE_CLONES.get() + 1);
        match self {
            Self::Object(x) => Self::Object(x.clone()),
            Self::Array(x) => Self::Array(x.clone()),
            Self::Text(x) => Self::Text(x.clone()),
            Self::Number(x) => Self::Number(*x),
        }
    }
}

#[derive(Debug)]
struct LauncherConfig { description: Option<String> }
impl LauncherConfig {
    fn description(&self) -> Option<&str> { self.description.as_deref() }
}
#[derive(Debug)]
struct ProcessComponentLauncher {
    component_id: String,
    config: LauncherConfig,
    drops: Arc<Mutex<Vec<&'static str>>>,
}
impl Drop for ProcessComponentLauncher {
    fn drop(&mut self) { self.drops.lock().unwrap().push("launcher dropped"); }
}

mod domain {
    #[derive(Clone, Copy)]
    pub(super) enum ModuleKind { Policy, Workflow, SessionStorage }
}

trait ApprovalPolicy { fn id(&self) -> u8; }
trait Workflow { fn id(&self) -> u8; }
trait SessionStorage { fn id(&self) -> u8; }
struct FixturePolicy;
struct FixtureWorkflow;
struct FixtureStorage(u8);
struct DenyAllPolicy;
struct NoWorkflow;
impl ApprovalPolicy for FixturePolicy { fn id(&self) -> u8 { 11 } }
impl Workflow for FixtureWorkflow { fn id(&self) -> u8 { 12 } }
impl SessionStorage for FixtureStorage { fn id(&self) -> u8 { self.0 } }
impl ApprovalPolicy for DenyAllPolicy { fn id(&self) -> u8 { 1 } }
impl Workflow for NoWorkflow { fn id(&self) -> u8 { 2 } }

#[derive(Clone)]
struct RuntimeConfig;
struct Config { runtime: RuntimeConfig }
impl Config { fn instruction_blocks(&self) -> u8 { 10 } }
struct FixtureSurface { process_tool_specs: Vec<String>, mcp_servers: Vec<String> }
struct FixtureAddons { plugins: Vec<String> }
struct ModuleBuildContext<'a> { cwd: &'a Path }
struct PolicyBuildContext<'a> { cwd: &'a Path }
type Trace = Arc<Mutex<Vec<&'static str>>>;

struct ModuleCatalog {
    config_exports: Vec<ProcessExportConfig>,
    fail: Option<&'static str>,
    trace: Trace,
}
impl ModuleCatalog {
    fn checked(&self, stage: &'static str, id: &str, cwd: &Path) -> Result<()> {
        assert_eq!(stage, id);
        assert_eq!(cwd, Path::new("/private/inert"));
        self.trace.lock().unwrap().push(stage);
        assert!(self.config_exports.iter().all(|export| !export.binding().module_id.is_empty()));
        assert_eq!(VALUE_CLONES.get(), 0); // no export clone on the way to any fallible branch
        if self.fail == Some(stage) { Err(format!("synthetic {stage} failure")) } else { Ok(()) }
    }
    fn build_policy(&self, id: &str, ctx: &PolicyBuildContext<'_>) -> Result<Arc<dyn ApprovalPolicy>> {
        self.checked("policy", id, ctx.cwd)?;
        Ok(Arc::new(FixturePolicy))
    }
    fn build_workflow(&self, id: &str, ctx: &ModuleBuildContext<'_>) -> Result<Arc<dyn Workflow>> {
        self.checked("workflow", id, ctx.cwd)?;
        Ok(Arc::new(FixtureWorkflow))
    }
    fn build_session_storage(&self, id: &str, ctx: &ModuleBuildContext<'_>) -> Result<Arc<dyn SessionStorage>> {
        self.checked("storage", id, ctx.cwd)?;
        Ok(Arc::new(FixtureStorage(13)))
    }
}

struct AssemblyPlan {
    select: bool, invalid: bool, trace: Trace, cwd: PathBuf, config: Config,
}
impl AssemblyPlan {
    fn fixture(trace: Trace) -> Self {
        Self { select: true, invalid: false, trace, cwd: "/private/inert".into(),
               config: Config { runtime: RuntimeConfig } }
    }
    fn ensure_valid(&self) -> Result<()> {
        self.trace.lock().unwrap().push("plan");
        if self.invalid { Err("synthetic plan failure".into()) } else { Ok(()) }
    }
    fn module_id(&self, kind: domain::ModuleKind) -> Option<&str> {
        self.select.then_some(match kind {
            domain::ModuleKind::Policy => "policy",
            domain::ModuleKind::Workflow => "workflow",
            domain::ModuleKind::SessionStorage => "storage",
        })
    }
}
struct View<'a> {
    entries: &'a Vec<ProcessExportConfig>,
    policy: u8, workflow: u8, session_storage: Option<u8>,
    process_tool_specs: &'a [String], mcp_servers: &'a [String],
    plugins: &'a [String], cwd: &'a Path,
}

enum Registry { Stock(stock::RuntimeRegistry), Candidate(candidate::RuntimeRegistry) }
impl Registry {
    fn complete(new: bool, plan: &AssemblyPlan, catalog: ModuleCatalog,
                storage: Option<Arc<dyn SessionStorage>>) -> Result<Self> {
        if new { Ok(Self::Candidate(candidate::RuntimeRegistry::complete(plan, catalog, storage)?)) }
        else { Ok(Self::Stock(stock::RuntimeRegistry::complete(plan, catalog, storage)?)) }
    }
    fn view(&self) -> View<'_> {
        match self { Self::Stock(r) => r.observe(), Self::Candidate(r) => r.observe() }
    }
    fn select(&self, name: &str) -> Result<Option<ProcessExportConfig>> {
        match self { Self::Stock(r) => r.select_export(name), Self::Candidate(r) => r.select_export(name) }
    }
}
fn one_export(launcher: &Arc<ProcessComponentLauncher>, slot: &str, name: &str, priority: u64,
              payload_size: usize) -> ProcessExportConfig {
    let binding = ProcessExportBinding {
        slot: slot.to_owned(), module_id: name.to_owned(), contract_version: "fixture-version".into(),
        module_config: Value::Object(BTreeMap::from([
            ("schema".to_owned(), Value::Object(BTreeMap::from([
                ("priority".to_owned(), Value::Number(priority)),
                ("content".to_owned(), Value::Text("α".repeat(payload_size))),
            ]))),
            ("list".to_owned(), Value::Array(vec![Value::Number(priority),Value::Text("inert".into())])),
        ])),
    };
    ProcessExportConfig {
        launcher: Arc::clone(launcher), binding, timeout_ms: (priority != 0).then_some(priority),
        description: (priority != 0).then(|| format!("export {priority}")),
    }
}
fn catalog(trace: Trace, capacity: usize, rows: usize, payload_size: usize)
    -> (ModuleCatalog, Weak<ProcessComponentLauncher>)
{
    let launcher = Arc::new(ProcessComponentLauncher {
        component_id: "fixture-component".into(),
        config: LauncherConfig { description: Some("fixture description".into()) },
        drops: trace.clone(),
    });
    let mut exports = Vec::with_capacity(capacity);
    for i in 0..rows {
        let slot = if i % 3 == 0 { "workflow" } else { "model" };
        let id = if i < 2 { "same".to_owned() } else { format!("export-{i}") };
        exports.push(one_export(&launcher, slot, &id, i as u64, payload_size));
    }
    (ModuleCatalog { config_exports: exports, fail: None, trace }, Arc::downgrade(&launcher))
}
fn content_ptr(export: &ProcessExportConfig) -> *const u8 {
    let Value::Object(config) = &export.binding().module_config else { panic!("config fixture"); };
    let Value::Object(schema) = &config["schema"] else { panic!("schema fixture"); };
    let Value::Text(content) = &schema["content"] else { panic!("payload fixture"); };
    content.as_ptr()
}
fn trace(trace: &Trace) -> Vec<&'static str> { trace.lock().unwrap().clone() }

#[test]
fn full_owned_move_retains_vec_and_nested_bytes_without_losing_launcher() {
    for new in [false, true] {
        let events = Trace::default();
        let (catalog, weak) = catalog(events.clone(), 32, 3, 9000);
        let original_vec = catalog.config_exports.as_ptr();
        let original_content = content_ptr(&catalog.config_exports[1]);
        let original_count = weak.strong_count();
        let old_capacity = catalog.config_exports.capacity();
        assert_eq!(old_capacity, 32);
        assert_eq!(original_count, 3);
        VALUE_CLONES.set(0);
        let plan = AssemblyPlan::fixture(events.clone());
        let result = Registry::complete(new, &plan, catalog, None).unwrap();
        let result_entries = result.view().entries;
        assert_eq!(trace(&events), ["plan","policy","workflow","storage"]);
        assert_eq!(weak.strong_count(), original_count);
        assert_eq!(result_entries.as_ptr() == original_vec, new);
        assert_eq!(content_ptr(&result_entries[1]) == original_content, new);
        assert_eq!(VALUE_CLONES.get() == 0, new);
        assert_eq!(result_entries.capacity(), if new { 32 } else { 3 });
        assert!(result_entries.iter().all(|e| Weak::ptr_eq(&Arc::downgrade(&e.launcher), &weak)));
        drop(result);
        assert!(weak.upgrade().is_none());
        assert_eq!(trace(&events), ["plan","policy","workflow","storage","launcher dropped"]);
    }
}

#[test]
fn exact_slot_and_schema_association_survives_moving_catalog() {
    let run = |new| {
        let events = Trace::default();
        let (catalog, weak) = catalog(events.clone(), 8, 5, 33);
        VALUE_CLONES.set(0);
        let plan = AssemblyPlan::fixture(events.clone());
        let result = Registry::complete(new, &plan, catalog, None).unwrap();
        let view = result.view();
        assert_eq!((view.policy, view.workflow, view.session_storage), (11,12,Some(13)));
        assert_eq!(view.cwd, Path::new("/private/inert"));
        assert_eq!(view.process_tool_specs, ["discovery only"]);
        assert_eq!(view.mcp_servers, ["synthetic mcp"]);
        assert_eq!(view.plugins, ["synthetic plugin"]);
        assert!(result.select("absent").unwrap().is_none());
        assert!(result.select("Same").unwrap().is_none());
        let selected = result.select("same").unwrap().unwrap();
        assert_eq!(selected.slot(), "model");
        assert_eq!(selected.module_id(), "same");
        assert_eq!(selected.binding().contract_version, "fixture-version");
        assert_eq!(selected.binding(), view.entries[1].binding());
        assert!(Weak::ptr_eq(&Arc::downgrade(&selected.launcher), &weak));
        assert_eq!(selected.component_id(), "fixture-component");
        assert_eq!(selected.timeout(5000).as_millis(), 1);
        assert_eq!(selected.description(), Some("export 1"));
        assert!(selected.validate_for("model", 0).is_ok());
        assert!(selected.validate_for("workflow", 100).is_err());
        assert_eq!(view.entries[0].description(), Some("fixture description"));
        assert!(view.entries[0].validate_for("workflow", 0).is_err());
        assert_eq!(view.entries[0].timeout(50).as_millis(), 50);
        let association = view.entries.iter().map(|e| e.binding().clone()).collect::<Vec<_>>();
        drop(result);
        assert!(weak.upgrade().is_some()); // independent later selection clone survived
        drop(selected);
        assert!(weak.upgrade().is_none());
        association
    };
    assert_eq!(run(false),run(true));
}

#[test]
fn all_prior_failures_leave_export_move_unreached_and_drop_once() {
    for new in [false, true] {
        for (stage, expected) in [("plan",vec!["plan","launcher dropped"]),
            ("policy",vec!["plan","policy","launcher dropped"]),
            ("workflow",vec!["plan","policy","workflow","launcher dropped"]),
            ("storage",vec!["plan","policy","workflow","storage","launcher dropped"])] {
            let events = Trace::default();
            let (mut catalog, weak) = catalog(events.clone(), 4, 3, 32);
            let mut plan = AssemblyPlan::fixture(events.clone());
            plan.invalid = stage == "plan";
            catalog.fail = Some(stage);
            VALUE_CLONES.set(0);
            let Err(error) = Registry::complete(new, &plan, catalog, None) else { panic!("no failure"); };
            assert_eq!(error, format!("synthetic {stage} failure"));
            assert_eq!(VALUE_CLONES.get(), 0);
            assert_eq!(trace(&events), expected);
            assert!(weak.upgrade().is_none());
        }
    }
}

#[test]
fn supplied_storage_and_default_policy_workflow_have_same_owned_results() {
    for new in [false, true] {
        let events = Trace::default();
        let (mut catalog, weak) = catalog(events.clone(), 3, 3, 1);
        catalog.fail = Some("storage");
        let plan = AssemblyPlan::fixture(events.clone());
        VALUE_CLONES.set(0);
        let result = Registry::complete(new, &plan, catalog, Some(Arc::new(FixtureStorage(127)))).unwrap();
        assert_eq!(result.view().session_storage, Some(127));
        assert_eq!(trace(&events), ["plan","policy","workflow"]);
        drop(result);
        assert!(weak.upgrade().is_none());

        let events = Trace::default();
        let (catalog, _) = self::catalog(events.clone(), 4, 0, 0);
        let mut plan = AssemblyPlan::fixture(events.clone());
        plan.select = false;
        VALUE_CLONES.set(0);
        let result = Registry::complete(new, &plan, catalog, None).unwrap();
        let view = result.view();
        assert!(view.entries.is_empty());
        assert_eq!((view.policy,view.workflow,view.session_storage), (1,2,None));
        assert_eq!(trace(&events), ["launcher dropped","plan"]);
    }
}

#[derive(Clone, Copy, Debug, Default)]
struct Requests { alloc: usize, realloc: usize, bytes: usize }
thread_local! { static METER: Cell<Option<Requests>> = const { Cell::new(None) }; }
fn requested(bytes: usize, re: bool) {
    let _ = METER.try_with(|meter| {
        if let Some(mut sums) = meter.get() {
            sums.bytes += bytes;
            if re { sums.realloc += 1; } else { sums.alloc += 1; }
            meter.set(Some(sums));
        }
    });
}
struct Allocator;
unsafe impl GlobalAlloc for Allocator {
    unsafe fn alloc(&self, a: Layout) -> *mut u8 { requested(a.size(), false); unsafe { System.alloc(a) } }
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
fn allocation_scope_compares_sixteen_prepared_exports_with_nested_payloads() {
    let run = |new| {
        let events = Trace::default();
        let (catalog, _) = catalog(events.clone(), 16, 16, 32768);
        let plan = AssemblyPlan::fixture(events);
        VALUE_CLONES.set(0);
        METER.set(Some(Requests::default()));
        let joined = black_box(Registry::complete(new, &plan, black_box(catalog), None)).unwrap();
        let requests = METER.take().unwrap();
        let clones = VALUE_CLONES.get();
        assert_eq!(joined.view().entries.len(), 16);
        assert_eq!(joined.view().entries.capacity(), 16);
        (requests, clones)
    };
    let (old, old_clones) = run(false);
    let (new, new_clones) = run(true);
    assert_eq!(old_clones, 16 * 7);
    assert_eq!(new_clones, 0);
    assert!(old.alloc > new.alloc && old.bytes >= new.bytes + 1024 * 1024);
    println!("R240_ALLOC {} {} {} {} {} {} {} {}", old.alloc, old.realloc, old.bytes,
             new.alloc, new.realloc, new.bytes, old_clones, new_clones);
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
    check(old.count(CHANGE) == 1 and old.replace(CHANGE,
        "            config_exports: catalog.config_exports,", 1) == new, "only one-line move")
    refs = {}
    for key, (blob, digest) in REFS.items():
        ref = getattr(args, key).read_bytes()
        identity(ref, blob, digest)
        refs[key] = ref.decode()
    rustc = args.rustc.resolve(strict=True)
    check(hashlib.sha256(rustc.read_bytes()).hexdigest() == RUSTC_SHA, "compiler digest")
    with tempfile.TemporaryDirectory(prefix="r240-", dir=args.work.resolve(strict=True)) as temp:
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
            counts = re.search(r"\bR240_ALLOC ((?:\d+ ){7}\d+)$", run.stdout, re.M)
            check(tests is not None and int(tests[1]) == 5, "test count")
            check(counts is not None, "allocation receipt")
            c = list(map(int, counts[1].split()))
            results[mode] = {"tests_passed": int(tests[1]),
                             "stock_alloc_realloc_requested_bytes": c[:3],
                             "candidate_alloc_realloc_requested_bytes": c[3:6],
                             "inert_value_clone_calls": c[6:]}
    print(json.dumps({"status": "PASS", "rustc": version, "rustc_sha256": RUSTC_SHA,
                      "exact_forward_and_reverse": True, "results": results,
                      "allocation_fixture_exports": 16,
                      "inert_nested_text_bytes_per_export": 65536,
                      "stock_vs_owned_capacity_on_three_from_reserve_32": [3,32],
                      "actual_worker_authority_serde_or_cargo": False}, indent=2))


if __name__ == "__main__":
    main()
