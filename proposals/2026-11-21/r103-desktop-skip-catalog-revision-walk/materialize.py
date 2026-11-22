"""Admit exact discovery, inventory, and validation over a headless fixture."""
from pathlib import Path
import json
import re
import shutil
import sys

tier, out, packet, packages = map(Path, sys.argv[1:])
src = out / "src"
for name in ("declarative", "catalog/inventory"):
    (src / name).mkdir(parents=True)

def read(path):
    return (tier / "src" / path).read_text()

def write(path, text):
    (src / path).write_text(text)

def cut(text, start, end):
    a = text.index(start)
    return text[a:text.index(end, a+len(start))]

def function(text, signature):
    a = text.index(signature)
    b = text.index("\n}", a) + 2
    return text[a:b] + "\n"

def before(text, target, note):
    assert text.count(target) == 1, target
    indent = " " * (len(target) - len(target.lstrip(" ")))
    return text.replace(target, f"{indent}crate::meter::bump(crate::meter::Hit::{note});\n" + target)

m = read("declarative/manifest.rs")
for target, note in [
    ("    let Ok(entries) = std::fs::read_dir(root) else {", "DiscoveryRoot"),
    ("        match load(&dir) {", "ManifestLoad"),
    ("        let package = dir.canonicalize()?;", "InstructionRoot"),
    ("            let skill_dir = dir", "InstructionDir"),
    ("            let skill_file = skill_dir", "InstructionFile"),
    ("    fn visit(dir: &Path, hash: &mut impl Hasher) {", None),
    ("        let Ok(entries) = std::fs::read_dir(dir) else {", "RevisionDir"),
    ("            if let Ok(metadata) = path.metadata() {", "RevisionMetadata"),
]:
    if note:
        m = before(m,target,note)
m = before(m,"    let mut hash = std::collections::hash_map::DefaultHasher::new();","Revision")
write("declarative/manifest.rs",m)
for name in ("manifest_agent_instructions_tests.rs", "session.rs", "icons.rs"):
    shutil.copyfile(tier/"src/declarative"/name,src/"declarative"/name)
write("declarative/mod.rs","pub mod manifest; pub mod protocol; pub mod icons; pub mod session;\n")
write("declarative/protocol.rs",cut(read("declarative/protocol.rs"), "pub const PROTOCOL:", "/// Visual values"))

prefs = read("preferences.rs")
badge= cut(prefs, "/// Where the compact icon", "/// Which client extensions are on")
write("preferences.rs","use std::path::PathBuf; use serde::{Serialize, Deserialize};\n"+badge+function(prefs,"pub fn config_dir("))
write("backend.rs","use std::path::PathBuf;\n"+function(read("backend.rs"),"pub(crate) fn proteus_binary("))
app_id = next(l for l in read("main.rs").splitlines() if l.startswith("const APP_ID:"))

schema=read("catalog/schema.rs")
write("catalog/schema.rs",
      "use anyhow::{Result,ensure}; use serde::{Serialize,Deserialize}; use std::path::{Component,Path};\n"
      + cut(schema,"#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]","#[derive(Clone, Debug, Deserialize)]")
      + function(schema,"pub fn slug(") + function(schema,"pub fn relative("))
source=read("catalog/mod.rs")
write("catalog/mod.rs","use serde::{Serialize,Deserialize}; pub mod inventory; pub mod open; pub mod schema;\n"
      + cut(source, "#[derive(Clone, Debug, PartialEq, Eq, Hash, Serialize, Deserialize)]", "impl Source"))
shutil.copyfile(tier/"src/catalog/open.rs",src/"catalog/open.rs")
shutil.copyfile(tier/"src/catalog/inventory/tests.rs",src/"catalog/inventory/tests.rs")
write("catalog/inventory.rs", read("catalog/inventory.rs") + """
#[cfg(test)]
impl Inventory {
    pub(crate) fn extension_rows(&self) -> impl Iterator<Item = (&str, &Package)> {
        self.extensions.iter().map(|(id,p)| (id.as_str(),p))
    }
}
""")

# GPUI itself is deliberately absent. Carry only the asset enum spellings used
# by the frozen bundled manifests and the original icon test. The real icons.rs
# still performs its own filename normalization and lookup in this subset.
names = {
    "activity","chart-column","cpu","file-code","file-text","folder-tree",
    "gauge","git-branch","layers","list-checks","shield-check","terminal","workflow"
}
used = {json.loads(p.read_text()).get("icon") for p in packages.glob("*/extension.json")}
assert used == names - {"file-code"}, used
symbols = [(n, "".join(k.capitalize() for k in n.split("-"))) for n in sorted(names)]
icons = "#[derive(Clone,Copy)] pub enum IconName { " + ",".join(v for _,v in symbols) + " }\n"
icons += "impl IconName { pub const ALL: &'static [Self]=&[" + ",".join("Self::"+v for _,v in symbols) + "];\n"
icons += "pub fn path(&self)->&'static str { match self { " + ",".join(f'Self::{v} => "icons/{n}.svg"' for n,v in symbols) + " } } }"
write("lib.rs","""#![cfg(test)]
extern crate self as gpui_kit;
pub mod assets { """+icons+""" }
mod backend;
mod catalog;
mod declarative;
mod preferences;
mod meter;
mod cases;
"""+app_id+"\n")

for a,b in (("harness.toml","Cargo.toml"),("harness.lock","Cargo.lock"),("cases.rs","src/cases.rs"),("meter.rs","src/meter.rs")):
    shutil.copyfile(packet/a,out/b)
