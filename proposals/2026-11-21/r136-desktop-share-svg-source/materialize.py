"""Stage exact Node/tree/XML modules and selected safe protocol/image method bodies."""
from pathlib import Path
import hashlib
import shutil
import sys

source, out, packet, settings = map(Path, sys.argv[1:])
src = out / "src"
d = src / "declarative"
d.mkdir(parents=True)
scope = packet / "scope.txt"
for item in scope.read_text().splitlines():
    input_file=source/item
    raw=out/"product"/item
    raw.parent.mkdir(parents=True,exist_ok=True)
    if item=="crates/diff":
        shutil.copytree(input_file,out/item,symlinks=True)
        continue
    shutil.copyfile(input_file,raw)
    if item=="LICENSE-GPL":
        shutil.copyfile(input_file,out/item)

D=source/"src/declarative"
for name in ("widget","control","graph","tree","list","lanes","presentation","icons","svg"):
    shutil.copyfile(D/(name+".rs"),d/(name+".rs"))
(d/"widget").mkdir()
shutil.copyfile(D/"widget/tests.rs",d/"widget/tests.rs")
for name,target in (("harness.toml","Cargo.toml"),("harness.lock","Cargo.lock"),
                    ("probe.rs","src/lib.rs"),("counter.rs","src/counter.rs")):
    shutil.copyfile(packet/name,out/target)
(src/"app_protocol").mkdir()
shutil.copyfile(settings,src/"app_protocol/settings.rs")

hash=lambda x:hashlib.sha256(x.encode()).hexdigest()
def cut(text, a, b):
    assert text.count(a)==1, a
    tail=text.split(a,1)[1]
    assert b in tail,b
    return a+tail.split(b,1)[0]

protocol=(D/"protocol.rs").read_text()
imports="use std::"+protocol.split("use std::",1)[1].split("\npub const PROTOCOL",1)[0]
incoming=cut(protocol,'#[derive(Clone, Debug, Deserialize, PartialEq)]\n#[serde(tag = "type", rename_all = "snake_case", deny_unknown_fields)]\npub enum Incoming {',"\n/// View id of a surface")
(d/"protocol.rs").write_text(imports+incoming+"\n")

u=source/"src/ui/extensions/declarative"
images=(u/"images.rs").read_text()
prod=images.split("\n#[cfg(test)]\nmod tests {",1)[0]
assert "\nimpl Drop for Images" in prod
(src/"images.rs").write_text(prod+"\n\n#[cfg(test)]\nmod proofs;\n")
child=src/"images"
child.mkdir()
for name in ("budget","cache"):
    shutil.copyfile(u/("images/"+name+".rs"),child/(name+".rs"))
shutil.copyfile(packet/"cases.rs",child/"proofs.rs")
raster=(u/"images/raster.rs").read_text()
head=raster.split("    /// Explicit canvases use",1)[0]
tail=cut(raster,"    fn failed(&self) -> bool {","\n#[cfg(test)]")
(child/"raster.rs").write_text(head+tail)
widget=(D/"widget.rs").read_text()
shared="pub struct SvgSource" in widget
(child/"mode.inc.rs").write_text("const SHARED: bool = " + str(shared).lower() + ";\n")
if shared:
    assert "let mut used = HashSet::new();" in prod
    assert "source.clone(),\n                                Asset" in prod
    assert "Arc::from(source.as_str())" not in prod
else:
    assert "Arc::from(source.as_str())" in prod
# Narrow invariant spans. Same-tier native widget + assets/leases modules not
# executed; guard equality is proved for those unchanged source sections.
ctx={
    "svg-validator":(D/"svg.rs").read_text(),
    "svg-node-validation":cut(widget,"            Node::Svg {","            Node::Code {"),
    "incoming":incoming,
    "asset-raster-budget":(u/"images/budget.rs").read_text(),
    "asset-lru-budget":(u/"images/cache.rs").read_text(),
    "asset-native-raster-lifetime":raster,
    "native-pixel-scene-lease":(source/"src/ui/render_image.rs").read_text(),
    "native-inline-use":(u/"view/inline.rs").read_text(),
    "native-retained-view":(u/"view.rs").read_text(),
    "native-svg-render-arm":cut((u/"render.rs").read_text(),"            Node::Svg {","            Node::RichText"),
}
for name, text in sorted(ctx.items()):
    print(f"{hash(text)}  {name}")
