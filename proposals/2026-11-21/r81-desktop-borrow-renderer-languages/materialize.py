"""Bind the exact catalog, routing, and reply paths to a small UI carrier."""
import hashlib
from pathlib import Path
import shutil
import sys

source, arm, ext, here = map(Path, sys.argv[1:])
s = source / "src"
d = arm / "src"
ui = s / "ui"
ext_ui = ui / "extensions"
dec = ext_ui / "declarative"
new_ext = d / "ui/extensions"
new_dec = new_ext / "declarative"
new_dec.mkdir(parents=True, exist_ok=True)
(d / "ui/chat").mkdir(exist_ok=True)
(d / "declarative").mkdir(exist_ok=True)
for name, out in {
    "harness.toml":"Cargo.toml", "harness.lock":"Cargo.lock", "probe.rs":"src/main.rs",
    "carrier.rs":"src/carrier.rs", "lifecycle.rs":"src/ui/chat/lifecycle.rs", "ledger.rs":"src/ledger.rs",
}.items():
    shutil.copyfile(here / name, arm / out)
for name in ["json-render", "markdown-render", "mermaid-render"]:
    category = arm / "bundled" / name
    category.mkdir(parents=True)
    shutil.copyfile(ext / "packages" / name / "extension.json", category / "extension.json")
    for skill in (ext / "packages" / name / "skills").glob("*/SKILL.md"):
        to = category / "skills" / skill.parent.name
        to.mkdir(parents=True)
        shutil.copyfile(skill,to/"SKILL.md")

def cut(text,a,b):
    start=text.index(a);return text[start:text.index(b,start+len(a))]
def fn(text,a,indent=""):
    start=text.index(a);end=text.index("\n"+indent+"}\n",start)+3+len(indent)
    return text[start:end]
def decl(text,label):
    pos=text.index(label)
    return fn(text,text[text.rindex("#[derive(",0,pos):pos]+label)
def get(p):
    return p.read_text()
def put(p,text):
    p.write_text(text)

manifest = s / "declarative/manifest.rs"
shutil.copyfile(manifest,d/"declarative/manifest.rs")
icons = get(s/"declarative/icons.rs").replace("use gpui_kit::assets::IconName as Lucide;","use crate::carrier::Lucide;")
assert "gpui_kit" not in icons
put(d/"declarative/icons.rs",icons)
put(d/"declarative/mod.rs","pub mod manifest; pub mod protocol; pub mod icons; pub mod session;\n")
shutil.copyfile(s/"declarative/session.rs",d/"declarative/session.rs")
protocol = get(s/"declarative/protocol.rs")
outgoing = cut(protocol,"    Render {", "    /// The surface is gone")
put(d/"declarative/protocol.rs",
    "use std::path::PathBuf; use serde::Serialize; use serde_json::Value;\n"
    + cut(protocol,"pub const PROTOCOL:", "/// Visual values")
    + decl(protocol,"pub struct Content") + decl(protocol,"pub enum SurfaceKind")
    + "#[derive(Clone, Debug, Serialize)]\n#[serde(tag = \"type\", rename_all = \"snake_case\")]\npub enum Outgoing {\n"
    + outgoing + "}\n")

pref = get(s/"preferences.rs")
put(d/"preferences.rs",
    "use std::{collections::BTreeMap,path::PathBuf}; use serde::{Serialize,Deserialize};\n"
    + decl(pref,"pub enum BadgePlace") + fn(pref,"impl BadgePlace {")
    + cut(pref,"/// Which client extensions are on", "\nfn path()")
)
outer = get(ext_ui/"mod.rs")
outer_registry = fn(outer,"pub(super) fn catalog(") + fn(outer,"pub(super) fn is_enabled(") + fn(outer,"pub(super) fn ordered(")
outer_types = fn(outer,"pub(super) struct PanelSurface") + fn(outer,"pub(super) struct DocumentSurface") + fn(outer,"pub(super) struct BadgeSurface") + fn(outer,"pub(super) struct Manifest")
put(new_ext/"mod.rs",
    "use crate::carrier::*; use crate::preferences::BadgePlace; use std::path::Path;\n"
    "pub(super) mod declarative; pub(in crate::ui) use declarative::content; use crate::carrier::prefs;\n"
    + "type BuildFocused = fn(); type BuildView = fn(); type BuildDocument = fn();\n"
    + outer_registry + outer_types
)
registry = get(dec/"mod.rs")
catalog = cut(registry,"/// An installed extension and its catalog entry.", "/// Default runtime selected")
put(new_dec/"mod.rs",
    "use std::{collections::HashMap,path::Path,sync::RwLock};\n"
    "use super::{Manifest, PanelSurface, DocumentSurface, BadgeSurface}; use crate::declarative::manifest::{self,Installed,Problem}; use crate::carrier::Lucide;\n"
    "pub(in crate::ui) mod content; pub(in crate::ui) mod inline_content;\n"
    "fn build_page() {} fn preview() {} fn build_document() {} fn build_panel() {} mod badge { pub(super) fn build() {} }\n"
    + catalog
    + "pub(in crate::ui) fn rescan_now() { rescan(); }\n"
    "pub(in crate::ui) fn current_manifest(id: &str) -> Option<&'static Installed> { installed(id) }\n"
)
c = get(dec/"content.rs")
selection = cut(c,"/// Enabled contributors", "pub(in crate::ui) struct WillResize;")
needle = ".cloned()"
# The language clone, not the unrelated caller context clone, is metered.
if needle in selection.split("pub(in crate::ui) fn language_renderer",1)[0]:
    selection = selection.replace(".iter()\n                        .cloned()", ".iter()\n                        .map(crate::ledger::clone_name)",1)
else:
    selection = selection.replace(".map(move |language| (language.as_str(), manifest.id))",
                                  ".map(move |language| { crate::ledger::yielded(); (language.as_str(), manifest.id) })",1)
set_source=fn(c,"    pub(in crate::ui) fn set_source(","    ")
put(new_dec/"content.rs",
    "use crate::carrier::*; use crate::declarative::protocol::Content; use std::sync::Arc;\n"
    + selection
    + get(here/"content_carrier.rs")
    + "impl ContentView {\n" + set_source.replace("        let mut context =", "        cx.events.borrow_mut().set_source += 1;\n        let mut context =", 1) + "}\n"
    + "pub(in crate::ui) fn context(value: &mut serde_json::Value,cx:&App) { populate_context(value,cx); }\n"
)
inline = get(dec/"inline_content.rs")
inline_prefix = cut(inline,"        let languages = content::languages(cx);","            if let Some(slot)")
put(new_dec/"inline_content.rs",
    "use super::content; use crate::carrier::App; struct Spec { language: String }\n"
    "pub(in crate::ui) fn resolve(query:&[String],cx:&App)->Vec<Option<&'static str>> {\n"
    "let specifications: Vec<_> = query.iter().cloned().map(|language| Spec { language }).collect();\n"
    "let mut out = Vec::new();\n"
    + inline_prefix + "    out.push(renderer); }\nout\n}\n")
reply = get(ui/"chat/replies.rs")
reply_head = cut(reply,"#[derive(Default)]","    pub(super) fn rehost(")
reply_tail = fn(reply,"    pub(super) fn retain(","    ")
put(d/"ui/chat/replies.rs",
    "use crate::carrier::*; use crate::declarative::protocol::Content; use super::super::extensions::content;\n"
    "use std::sync::Arc; use std::collections::{HashSet,HashMap};\n"
    + reply_head + reply_tail + "}\n"
    "impl Replies { pub(in crate::ui) fn remembered(&self,key:u64)->Vec<(&str,&str)> { self.0[&key].languages.iter().map(|(name,id)| (name_view(name),*id)).collect() } }\n"
    "fn name_view(s:&impl AsRef<str>) -> &str { s.as_ref() }\n"
)
put(d/"ui/chat/mod.rs","mod replies; mod lifecycle; pub(crate) use lifecycle::run;\n")
put(d/"ui/mod.rs","mod extensions; mod chat; pub(crate) use chat::run;\n")
for label, value in (
    ("registry-discovery",catalog), ("manifest-schema",get(manifest)),
    ("ordered-enablement",outer_registry), ("suffix-wire-update",set_source),
    ("retained-reply-methods",reply_head[reply_head.index("impl Replies {"):]+reply_tail),
    ("content-view-update-gate",fn(c,"fn updated_content(")), ("wire-content",decl(protocol,"pub struct Content")),
    ("wire-render",outgoing),
):
    print(f"{hashlib.sha256(value.encode()).hexdigest()}  {label}")
