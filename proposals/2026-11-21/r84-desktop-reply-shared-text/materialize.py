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
    "carrier.rs":"src/carrier.rs", "lifecycle.rs":"src/ui/chat/lifecycle.rs",
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
shutil.copytree(s/"transcript",d/"transcript")
(d/"agents/codex").mkdir(parents=True,exist_ok=True)
shutil.copyfile(s/"agents/codex/types.rs",d/"agents/codex/types.rs")
(d/"agents/codex/mod.rs").write_text("mod types; pub use types::{Item, ItemKind};\n")

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
source_type = cut(protocol,"/// Reply bodies borrow", "/// Original closed fence") if "pub enum ContentSource" in protocol else ""
put(d/"declarative/protocol.rs",
    "use std::{path::PathBuf,sync::Arc}; use serde::Serialize; use serde_json::Value;\n"
    + cut(protocol,"pub const PROTOCOL:", "/// Visual values")
    + source_type + decl(protocol,"pub struct Content") + decl(protocol,"pub enum SurfaceKind")
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
    "pub(in crate::ui) mod content; pub(in crate::ui) mod runtime_probe;\n"
    "fn build_page() {} fn preview() {} fn build_document() {} fn build_panel() {} mod badge { pub(super) fn build() {} }\n"
    + catalog
    + "pub(in crate::ui) fn rescan_now() { rescan(); }\n"
    "pub(in crate::ui) fn current_manifest(id: &str) -> Option<&'static Installed> { installed(id) }\n"
)
c = get(dec/"content.rs")
selection = cut(c,"/// Enabled contributors", "pub(in crate::ui) struct WillResize;")
set_source=fn(c,"    pub(in crate::ui) fn set_source(","    ")
native_read=cut(c,"                let source =", "                width = Some(").strip()
native_copy=cut(c,"            move |_, _| ", "            Some(toggle").strip().rstrip(",")
assert native_copy.startswith("move |_, _| ")
native_copy=native_copy.removeprefix("move |_, _| ")
put(new_dec/"content.rs",
    "use crate::carrier::*; use crate::declarative::protocol::Content; use std::{rc::Rc,sync::Arc};\n"
    + ("use crate::declarative::protocol::ContentSource;\n" if source_type else "")
    + selection
    + get(here/"content_carrier.rs")
    + "impl ContentView {\n" + set_source.replace("        let mut context =", "        cx.events.borrow_mut().set_source += 1;\n        let mut context =", 1)
    + "pub fn raw(&self) -> SharedString { " + native_read + " source }\n"
    + "pub fn frozen(&self) -> impl Fn() -> SharedString + 'static { let content=Arc::clone(&self.content); move || " + native_copy + " }\n"
    + "}\n"
    + "pub(in crate::ui) fn context(value: &mut serde_json::Value,cx:&App) { populate_context(value,cx); }\n"
)
r = get(dec/"runtime.rs")
runtime = "".join(fn(r,key,"    ") for key in ("    fn render(","    pub(super) fn set_content(","    fn content_finished(","    pub(super) fn send("))
put(new_dec/"runtime_probe.rs",get(here/"runtime_carrier.rs"))
runtimefolder=new_dec/"runtime_probe"
runtimefolder.mkdir()
shutil.copyfile(dec/"runtime/content_queue.rs",runtimefolder/"content_queue.rs")
put(new_dec/"runtime.inc.rs","impl Runtime {\n"+runtime+"}\n")
process=get(s/"declarative/process.rs")
enqueue=fn(process,"    fn enqueue(","    ")
send=fn(process,"    pub fn send(","    ")
# Observe only the ephemeral payload seen by the actual writer entrypoint.
recv="        let result = self.enqueue(message);"
assert send.count(recv)==1
send = send.replace(recv, """        if let Outgoing::Render { content:Some(content), .. }=message {
            let source=content.source.as_str();
            self.state.writer.0.payloads.borrow_mut().push((source.as_ptr() as usize,source.len()));
        }
"""+recv)
put(new_dec/"process.inc.rs","impl Process {\n"+send+enqueue+"}\n")
io=get(s/"declarative/process/io.rs")
put(new_dec/"wire.inc.rs", cut(io,"pub(super) const MAX_FRAME", "\n") + "\n"+io[io.index("struct Count"):])
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
    ("ordered-enablement",outer_registry),
    ("wire-render-layout",outgoing), ("enqueue-admission-and-wire",enqueue),
    ("begin-render-context",runtime.split("            Some(Content {",1)[0]),
    ("finish-render-context",runtime.split("        } else if attached.surface == SurfaceKind::Content",1)[1]),
    ("queue-rules",get(dec/"runtime/content_queue.rs").split("#[cfg(test)]",1)[0]),
    ("raw-shell-except-source",c[c.index("impl Render for ContentView"):c.index("/// Retained full-body content")].replace(native_read,"<SOURCE_READ>").replace(native_copy,"<SOURCE_COPY>")),
):
    print(f"{hashlib.sha256(value.encode()).hexdigest()}  {label}")
