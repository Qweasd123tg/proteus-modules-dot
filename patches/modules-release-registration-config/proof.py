#!/usr/bin/env python3
"""Verify exact shared worker registration config release with an inert native Rust harness."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tempfile


BASE = "components/module-runtime/src"
SOURCES = {
    "lib": ("cb6daa80ab2f2beb5578bc47d7ff2f68111a7763",
            "0eec4294e202bbc16c94e8bf03aacd34efaebda1d7b8837e2d0a3c3d44a1abb2",
            "55c76e6110f9876219e58432dac73fc4aa5dc65d",
            "ded021aef25e39d3a8c61d0728c5685fdcc68d66e88fd52db4c148408082f8a7"),
    "registry": ("b6d7ba941aa4cd23b72937730ae2d928c294f7f8",
                 "dc189520b7edad22545116733fdef467b6d8c4c28c2850a95307dd6184bd5052",
                 "bc9ffdb14cc09bdfa8dc72079ae85625b339c30b",
                 "10d2a7322d06c68accd8c3f8ff67b116dbb62afca914fc438a1a645782c3a938"),
}
REFS = {
    "exports": ("db1018b286e811764eb612bfad3d38408c516917",
                "2654886befb9aae2b5867ffc6ae77bb4b29cb78324460b5038d95699fe3a2b7b"),
    "sdk": ("81926d05039949d3e5eacc3843c8f825788b9e2e",
            "6a323d6d8ffadb6708b0e40a629daf78a486f74f3b7660b2c4bfab722573464d"),
    "binding": ("f234d0fd2b67435fc1647629d0b5f1fb993262c7",
                "2d92245d87535b434d6b85db801c3aa5a7089768b2c804c65be000406a8bc128"),
    "schema": ("5c1cb74d5d7afc957c05165c1b916019529a5129",
               "ce317c273720520db832488dec8945f4ecf911224df4377b8ae85df614f8506f"),
    "lock": ("ae7035fc5900b0afc480e55d2408c8234c88dd17",
             "0b4717cd37ba4b5848068f64c52e863000d8d7ea6d90464f4a134689e45bef54"),
}
PATCH_SHA = "6c4d97b8dbcd6f25012bf23a3bcb4eac3964180a1939c2447bf808f0f698cb3f"
RUSTC_SHA = "bff349e72704ff70bc08a234a3847338e797065bbedde5e556808bc87b7bf7c6"
RUSTC_VERSION = "rustc 1.95.0 (59807616e 2026-04-14)"
LOCKED_CORE = "0c1b7572313230e5d123e95c722e1258a2e9ecd6"


def check(ok, label):
    if not ok:
        raise ValueError(label)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def identity(raw, blob, sha):
    check(digest(raw) == sha, "SHA256")
    check(hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest() == blob,
          "Git blob")


def replay(name, raw, patch, reverse=False):
    path = f"{BASE}/{name}.rs"
    old, _, new, _ = SOURCES[name]
    head = (f"diff --git a/{path} b/{path}\nindex {old}..{new} 100644\n"
            f"--- a/{path}\n+++ b/{path}\n").encode()
    check(patch.startswith(head), "patch header")
    hunk, *body = patch[len(head):].splitlines(keepends=True)
    m = re.fullmatch(rb"@@ -(\d+),(\d+) \+(\d+),(\d+) @@\n", hunk)
    check(m is not None, "single hunk header")
    a, al, b, bl = map(int, m.groups())
    pre, post = [], []
    for line in body:
        check(line[:1] in (b" ", b"+", b"-"), "patch line")
        if line[:1] != b"+":
            pre.append(line[1:])
        if line[:1] != b"-":
            post.append(line[1:])
    check(len(pre) == al and len(post) == bl and a == b, "hunk lengths")
    if reverse:
        pre, post = post, pre
    source = raw.splitlines(keepends=True)
    start = a - 1
    check(source[start:start + len(pre)] == pre, "hunk preimage")
    return b"".join(source[:start] + post + source[start + len(pre):])


def section(text, start, stop):
    a = text.index(start)
    return text[a:text.index(stop, a + len(start))]


def de_serde(text):
    return re.sub(r"^#\[serde\(.+\)\]\n", "", text, flags=re.M).replace(
        ", Serialize, Deserialize", "")


def shared(refs):
    sdk = refs["sdk"]
    aliases = re.findall(r"^pub type (\w+ModuleObject) = Box<dyn (\w+Module)>;$", sdk, re.M)
    check(len(aliases) == 7, "locked trait-owned alias set")
    trait = sdk[sdk.index("pub trait ModuleRegistry {"):]
    check(trait.count("fn module_config(&self) -> &serde_json::Value;") == 1
          and trait.rstrip().endswith("}"), "locked registry API")
    shape = "".join(
        f"pub trait {point} {{ fn name(&self) -> &str; }}\n"
        f"pub type {alias} = Box<dyn {point}>;\n"
        f"impl {point} for FixtureModule {{ fn name(&self) -> &str {{ &self.0 }} }}\n"
        for alias, point in aliases
    )
    binding = refs["binding"]
    mode = section(binding, "#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq)]",
                   "\n/// Стабильная identity")
    export_init = section(binding, "#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]\n"
                                  "#[serde(deny_unknown_fields)]\npub struct ProcessComponentExportInitialize",
                          "\n/// Параметры первого JSON-RPC")
    schema = section(refs["schema"], "#[derive(Debug, Clone, Default, Serialize, Deserialize, PartialEq, Eq)]",
                     "\n#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]")
    return ("mod process_module {\nuse crate::FixtureModule;\npub use crate::{ProcessModuleError, ProcessModuleResult};\n" + shape + trait + "\n}\n"
            + de_serde(mode + export_init)
            + "\nmod domain {\nuse crate::ConfigField;\n" + de_serde(schema) + "\n}\n")


def lift(name, src, refs):
    lib, registry = src["lib"], src["registry"]
    check(registry.count("use serde_json::{Value, json};") == 1, "serde import seam")
    registry = registry.replace("use serde_json::{Value, json};", "use serde_json::Value;")
    body = section(lib, "        proteus_module_sdk::run(|binding| {", "\n    })();")
    body = body.replace("        proteus_module_sdk::run(|binding| {",
                        "        inert_sdk(binding, |binding| {", 1)
    exports = refs["exports"]
    runtime = section(exports, "pub struct ModuleExport {", "    pub(crate) fn manifest(")
    check(exports.count("self.binding.module_config.clone()") == 6
          and ".modules.module_config()" not in exports, "original runtime-source reads")
    return (f"mod {name} {{\nuse crate::*;\n"
            + "#[allow(dead_code)]\nmod registry {\n" + registry + "\n}\n"
            + "pub(super) use registry::CollectedModules;\n"
            + runtime + r'''
    pub(super) fn observe(&self) -> ExportView<'_> {
        ExportView {
            binding: &self.binding,
            registry: self.modules.module_config(),
            model: self.modules.models.get(&self.binding.module_id).map(|v| v.name()),
            auxiliary: [
                self.modules.policies.get(&self.binding.module_id).map(|v| v.name()),
                self.modules.context_providers.get(&self.binding.module_id).map(|v| v.name()),
                self.modules.contexts.get(&self.binding.module_id).map(|v| v.name()),
                self.modules.hooks.get(&self.binding.module_id).map(|v| v.name()),
                self.modules.workflows.get(&self.binding.module_id).map(|v| v.name()),
            ],
            tool_names: &self.tool_catalog.names,
            schema: self.config_schema.as_ref(),
        }
    }
    pub(super) fn invocation_config(&self) -> Value {
        self.binding.module_config.clone()
    }
}
pub(super) fn install(
    name: &str, exports: BTreeMap<String,Vec<String>>, binding: ProcessComponentExportInitialize,
    register: impl Fn(&mut dyn ModuleRegistry, &ProcessComponentExportInitialize) -> Result<()>,
    schema: impl Fn(&ProcessComponentExportInitialize) -> Option<ModuleConfigSchema>,
) -> Result<Box<ModuleExport>> {
''' + body + "\n}\n}\n")


TESTS = r'''
extern crate self as proteus_contracts;
extern crate self as serde_json;

use std::{collections::BTreeMap, sync::{
    Arc, Mutex, atomic::{AtomicUsize, Ordering::SeqCst},
}};
use domain::ModuleConfigSchema;
use process_module::ModuleRegistry;

type Result<T> = std::result::Result<T, String>;
#[macro_export]
macro_rules! json { ({}) => { $crate::Value::Object(std::collections::BTreeMap::new()) }; }
macro_rules! bail { ($($args:tt)*) => { return Err(format!($($args)*)) }; }

#[derive(Debug)]
enum Event {
    Clone(usize), Drop(usize), Register, Schema, Serve, Invoke,
}
#[derive(Debug, Default)]
struct History {
    next: AtomicUsize, live_bytes: AtomicUsize, events: Mutex<Vec<Event>>,
}
impl History {
    fn push(&self, event: Event) { self.events.lock().unwrap().push(event); }
    fn timeline(&self) -> Vec<String> {
        self.events.lock().unwrap().iter().map(|event| match event {
            Event::Clone(id) => format!("clone{id}"),
            Event::Drop(id) => format!("drop{id}"),
            Event::Register => "register".into(),
            Event::Schema => "schema".into(),
            Event::Serve => "serve".into(),
            Event::Invoke => "invoke".into(),
        }).collect()
    }
}
#[derive(Debug)]
pub struct ProbeText { text: String, id: usize, history: Arc<History> }
impl ProbeText {
    fn new(chars: usize, history: Arc<History>) -> Self {
        let text = "β".repeat(chars);
        history.live_bytes.fetch_add(text.len(),SeqCst);
        Self { text, id: 0, history }
    }
}
impl Clone for ProbeText {
    fn clone(&self) -> Self {
        let id = self.history.next.fetch_add(1,SeqCst) + 1;
        self.history.live_bytes.fetch_add(self.text.len(),SeqCst);
        self.history.push(Event::Clone(id));
        Self { text: self.text.clone(), id, history: self.history.clone() }
    }
}
impl PartialEq for ProbeText { fn eq(&self, x: &Self) -> bool { self.text == x.text } }
impl Eq for ProbeText {}
impl Drop for ProbeText {
    fn drop(&mut self) {
        self.history.live_bytes.fetch_sub(self.text.len(),SeqCst);
        self.history.push(Event::Drop(self.id));
    }
}
#[derive(Clone, Debug, PartialEq, Eq)]
pub enum Value { Null, Object(BTreeMap<String,Value>), Array(Vec<Value>), Text(ProbeText) }
fn config(history: Arc<History>, chars: usize) -> Value {
    Value::Object(BTreeMap::from([("nested".into(), Value::Array(vec![
        Value::Object(BTreeMap::from([("schema".into(), Value::Text(ProbeText::new(chars,history)))])),
    ]))]))
}
fn payload(value: &Value) -> &ProbeText {
    let Value::Object(root) = value else { panic!("root shape"); };
    let Value::Array(child) = &root["nested"] else { panic!("child shape"); };
    let Value::Object(fields) = &child[0] else { panic!("fields shape"); };
    let Value::Text(payload) = &fields["schema"] else { panic!("payload shape"); };
    payload
}
#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct ConfigField { key: String, label: String, witness_bytes: usize }
#[derive(Debug, Eq, PartialEq)]
pub struct ProcessModuleError(String);
impl ProcessModuleError { fn new(message: impl Into<String>) -> Self { Self(message.into()) } }
impl From<ProcessModuleError> for String { fn from(value: ProcessModuleError) -> Self { value.0 } }
pub type ProcessModuleResult<T> = std::result::Result<T, ProcessModuleError>;
struct FixtureModule(String);

#[derive(Default)]
struct ToolCatalog { names: Vec<String> }
impl ToolCatalog {
    fn new(tools: &[process_module::ToolModuleObject]) -> Self {
        Self { names: tools.iter().map(|tool| tool.name().to_owned()).collect() }
    }
}
struct ExportView<'a> {
    binding: &'a ProcessComponentExportInitialize, registry: &'a Value,
    model: Option<&'a str>, auxiliary: [Option<&'a str>;5], tool_names: &'a [String], schema: Option<&'a ModuleConfigSchema>,
}
fn inert_sdk<T>(binding: ProcessComponentExportInitialize,
               setup: impl FnOnce(ProcessComponentExportInitialize) -> Result<Box<T>>) -> Result<Box<T>> {
    setup(binding)
}
enum Export { Old(Box<stock::ModuleExport>), New(Box<candidate::ModuleExport>) }
impl Export {
    fn install(new: bool, exports: BTreeMap<String,Vec<String>>, binding: ProcessComponentExportInitialize,
               register: impl Fn(&mut dyn ModuleRegistry, &ProcessComponentExportInitialize) -> Result<()>,
               schema: impl Fn(&ProcessComponentExportInitialize) -> Option<ModuleConfigSchema>)
        -> Result<Self>
    {
        if new { candidate::install("fixture-worker",exports,binding,register,schema).map(Self::New) }
        else { stock::install("fixture-worker",exports,binding,register,schema).map(Self::Old) }
    }
    fn observe(&self) -> ExportView<'_> {
        match self { Self::Old(e) => e.observe(), Self::New(e) => e.observe() }
    }
    fn invocation_config(&self) -> Value {
        match self { Self::Old(e) => e.invocation_config(), Self::New(e) => e.invocation_config() }
    }
}
fn bind(slot: &str, id: &str, value: Value) -> ProcessComponentExportInitialize {
    ProcessComponentExportInitialize::new(slot,id,"fixture-version",
        ProcessModuleComposition::SelectOne,value,["fixture-feature"])
}
fn permit(slot: &str, id: &str) -> BTreeMap<String,Vec<String>> {
    BTreeMap::from([(slot.into(),vec![id.into()])])
}

#[test]
fn release_occurs_after_schema_and_before_serving() {
    let chars = 524_288;
    let bytes = chars * 2;
    for new in [false,true] {
        let history = Arc::new(History::default());
        let b = bind("model","synthetic-model",config(history.clone(),chars));
        let original_ptr = payload(&b.module_config).text.as_ptr();
        let result = Export::install(new,permit("model","*"),b,
            |registry, original| {
                history.push(Event::Register);
                assert_eq!(registry.module_config(), &original.module_config);
                assert_eq!(history.live_bytes.load(SeqCst), 2 * bytes);
                assert_eq!(payload(registry.module_config()).id, 1);
                assert_eq!(payload(&original.module_config).id, 0);
                registry.register_model(original.module_id.clone(),
                    Box::new(FixtureModule(format!("owned model {}",payload(registry.module_config()).text.len()))))?;
                registry.register_policy(original.module_id.clone(), Box::new(FixtureModule("policy".into())))?;
                registry.register_context_provider(original.module_id.clone(), Box::new(FixtureModule("provider".into())))?;
                registry.register_context(original.module_id.clone(), Box::new(FixtureModule("context".into())))?;
                registry.register_hook(original.module_id.clone(), Box::new(FixtureModule("hook".into())))?;
                registry.register_workflow(original.module_id.clone(), Box::new(FixtureModule("workflow".into())))?;
                Ok(())
            },
            |original| {
                history.push(Event::Schema);
                assert_eq!(history.live_bytes.load(SeqCst), 2 * bytes);
                assert_eq!(payload(&original.module_config).text.as_ptr(), original_ptr);
                Some(ModuleConfigSchema { fields: vec![ConfigField {
                    key: "schema".into(), label: "fixture".into(), witness_bytes: bytes,
                }] })
            }).unwrap();
        history.push(Event::Serve);
        let state = result.observe();
        assert_eq!(history.live_bytes.load(SeqCst), if new { bytes } else { 2 * bytes });
        assert_eq!(state.registry == &Value::Null,new);
        assert_eq!(state.binding.module_id,"synthetic-model");
        assert_eq!(state.binding.host_features,["fixture-feature"]);
        assert_eq!(payload(&state.binding.module_config).text.as_ptr(), original_ptr);
        assert_eq!(state.schema.unwrap().fields[0].witness_bytes,bytes);
        assert_eq!(state.model,Some(format!("owned model {bytes}").as_str()));
        assert_eq!(state.auxiliary,[Some("policy"),Some("provider"),Some("context"),Some("hook"),Some("workflow")]);
        assert_eq!(history.timeline(), if new {
            vec!["clone1","register","schema","drop1","serve"]
        } else { vec!["clone1","register","schema","serve"] });
        history.push(Event::Invoke);
        let runtime = result.invocation_config();
        assert_eq!(payload(&runtime).id,2);
        assert_eq!(runtime,state.binding.module_config);
        drop(runtime);
        drop(result);
        assert_eq!(history.live_bytes.load(SeqCst),0);
        let log=history.timeline();
        for id in 0..3 {
            assert_eq!(log.iter().filter(|e| **e==format!("drop{id}")).count(),1);
        }
        println!("R241_LIVE {} {}", if new { "candidate" } else {"stock"}, if new {bytes} else {2*bytes});
    }
}

#[test]
fn rejection_precedes_clone_and_callbacks_for_wrong_slot_or_id() {
    for new in [false,true] {
        for (slot,id) in [("missing","listed"),("model","not-listed")] {
            let history=Arc::new(History::default());
            let attempt=Export::install(new,permit("model","listed"),bind(slot,id,config(history.clone(),4)),
                |_,_| panic!("unadmitted register"),
                |_| panic!("unadmitted schema"));
            assert_eq!(attempt.err().unwrap(), format!("fixture-worker has no {slot} module {id:?}"));
            assert_eq!(history.timeline(), ["drop0"]);
            assert_eq!(history.live_bytes.load(SeqCst),0);
        }
    }
}

#[test]
fn registration_error_blocks_schema_and_serving() {
    for new in [false,true] {
        let history=Arc::new(History::default());
        let attempt = Export::install(new, permit("model","one"),
            bind("model","one",config(history.clone(),2)),
            |reg,binding| {
                history.push(Event::Register);
                assert_eq!(reg.module_config(),&binding.module_config);
                reg.register_model("one".into(),Box::new(FixtureModule("first".into())))?;
                reg.register_model("one".into(),Box::new(FixtureModule("duplicate".into())))?;
                Ok(())
            }, |_| panic!("schema after failed registration"));
        assert_eq!(attempt.err().unwrap(),"duplicate module id: one");
        assert_eq!(history.timeline(), ["clone1","register","drop1","drop0"]);
        assert_eq!(history.live_bytes.load(SeqCst),0);
    }
}

#[test]
fn schema_unwind_keeps_original_cleanup_path_without_serving() {
    for new in [false,true] {
        let history=Arc::new(History::default());
        let attempt=std::panic::catch_unwind(|| {
            let _unused = Export::install(new,permit("model","one"),
                bind("model","one",config(history.clone(),4)),
                |reg,_| {
                    history.push(Event::Register);
                    assert_eq!(payload(reg.module_config()).id,1);
                    Ok(())
                },
                |b| {
                    history.push(Event::Schema);
                    assert_eq!(payload(&b.module_config).id,0);
                    panic!("synthetic unwind");
                });
        });
        assert!(attempt.is_err());
        assert_eq!(history.timeline(), ["clone1","register","schema","drop1","drop0"]);
        assert_eq!(history.live_bytes.load(SeqCst),0);
    }
}

#[test]
fn public_registry_constructors_and_direct_export_are_unchanged() {
    assert_eq!(stock::CollectedModules::default().module_config(), &json!({}));
    assert_eq!(candidate::CollectedModules::default().module_config(), &json!({}));
    for new in [false,true] {
        let h=Arc::new(History::default());
        let b=bind("tool","direct",config(h.clone(),1));
        let value=config(h.clone(),2);
        let e=if new {
            let m=candidate::CollectedModules::with_config(value);
            assert_eq!(payload(m.module_config()).text.len(),4);
            Export::New(Box::new(candidate::ModuleExport::new(b,m,None)))
        } else {
            let m=stock::CollectedModules::with_config(value);
            assert_eq!(payload(m.module_config()).text.len(),4);
            Export::Old(Box::new(stock::ModuleExport::new(b,m,None)))
        };
        assert_eq!(payload(e.observe().registry).text.len(),4);
        assert_eq!(h.live_bytes.load(SeqCst),6);
        assert!(e.observe().schema.is_none());
        drop(e);
        assert_eq!(h.live_bytes.load(SeqCst),0);
    }
}

#[test]
fn tool_registration_and_exact_constructor_keep_order_with_absent_schema() {
    for new in [false,true] {
        let e=Export::install(new,permit("tool","tool"),bind("tool","tool",json!({})),
            |reg,_| {
                assert_eq!(reg.module_config(),&json!({}));
                reg.register_tool(Box::new(FixtureModule("alpha".into())))?;
                reg.register_tool(Box::new(FixtureModule("beta".into())))?;
                Ok(())
            }, |original| {
                assert_eq!(original.module_config,json!({}));
                None
            }).unwrap();
        assert_eq!(e.observe().tool_names,["alpha","beta"]);
        assert!(e.observe().schema.is_none());
        assert_eq!(e.invocation_config(),json!({}));
    }
}
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in (*SOURCES, *REFS, "rustc", "work"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    patch = Path(__file__).with_name("source.patch").read_bytes()
    check(digest(patch) == PATCH_SHA, "patch digest")
    chunks = re.split(rb"(?m)(?=^diff --git)", patch)
    check(len(chunks) == 3 and not chunks[0], "two exact patch sections")
    arms = [{}, {}]
    for (name, (old_blob, old_sha, new_blob, new_sha)), hunk in zip(SOURCES.items(), chunks[1:]):
        raw = getattr(args, name).read_bytes()
        identity(raw, old_blob, old_sha)
        new = replay(name, raw, hunk)
        identity(new, new_blob, new_sha)
        check(replay(name, new, hunk, reverse=True) == raw, "exact rollback")
        arms[0][name], arms[1][name] = raw.decode(), new.decode()
    refs = {}
    for key, (blob, digest_) in REFS.items():
        source = getattr(args, key).read_bytes()
        identity(source, blob, digest_)
        refs[key] = source.decode()
    locked = re.search(r'\[\[package\]\]\nname = "proteus-contracts"\n[^\[]+', refs["lock"])
    check(locked is not None and f"?rev={LOCKED_CORE}#{LOCKED_CORE}" in locked[0], "SDK pin")
    rustc = args.rustc.resolve(strict=True)
    check(digest(rustc.read_bytes()) == RUSTC_SHA, "compiler digest")
    with tempfile.TemporaryDirectory(prefix="r241-", dir=args.work.resolve(strict=True)) as temp:
        root = Path(temp)
        env = {"PATH": "/usr/bin:/bin", "HOME": temp, "TMPDIR": temp, "LC_ALL": "C"}
        version = subprocess.check_output([rustc, "--version"], cwd=root, env=env,
                                          text=True, timeout=20).strip()
        check(version == RUSTC_VERSION, "compiler version")
        unit = root / "lift.rs"
        unit.write_text(TESTS + "\n" + shared(refs) + lift("stock", arms[0], refs)
                        + lift("candidate", arms[1], refs), encoding="utf-8")
        results = {}
        for mode, flags in [("debug", []), ("optimized", ["-O"])]:
            exe = root / ("test-" + mode)
            subprocess.run([rustc, "--edition=2024", "--test", "-Dwarnings", *flags, unit,
                            "-o", exe], cwd=root, env=env, timeout=90, check=True)
            run = subprocess.run([exe, "--test-threads=1", "--nocapture"], cwd=root, env=env,
                                 capture_output=True, text=True, timeout=90)
            check(run.returncode == 0, f"{mode} tests:\n{run.stdout}\n{run.stderr}")
            tests = re.search(r"test result: ok\. (\d+) passed; 0 failed;", run.stdout)
            live = re.findall(r"\bR241_LIVE (stock|candidate) (\d+)$", run.stdout, re.M)
            check(tests is not None and int(tests[1]) == 6, "test count")
            check(len(live) == 2, "retained payload receipt")
            results[mode] = {"tests_passed": int(tests[1]),
                             "live_inert_text_bytes_at_serve": {k:int(v) for k,v in live}}
    print(json.dumps({"status":"PASS","rustc":version,"rustc_sha256":RUSTC_SHA,
                      "exact_forward_reverse":True,"results":results,"locked_core":LOCKED_CORE,
                      "real_serde_worker_cargo_host_or_measurement":False}, indent=2))


if __name__ == "__main__":
    main()
