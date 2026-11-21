"""Project exact Desktop RichText/source methods over a native-effect model."""
import hashlib
import shutil
import sys
from pathlib import Path

source, out, packet = map(Path, sys.argv[1:])
dst = out/"src"
schemas = dst/"declarative"
schemas.mkdir(parents=True)
d, ui = source/"src/declarative", source/"src/ui/extensions/declarative"
for name in "widget control graph tree list lanes protocol session presentation icons".split():
    shutil.copyfile(d/(name+".rs"), schemas/(name+".rs"))
shutil.copytree(source/"crates/diff",out/"crates/diff",symlinks=True)
for a,b in (("harness.toml","Cargo.toml"),("harness.lock","Cargo.lock"),("carrier.rs","src/carrier.rs"),
            ("probe.rs","src/main.rs"),("cases.rs","src/cases.rs")):
    shutil.copyfile(packet/a,out/b)

def between(text,start,end):
    x=text.index(start)
    return text[x:text.index(end,x+len(start))]
widget=(d/"widget.rs").read_text()
proto=(d/"protocol.rs").read_text()
rich=(ui/"rich_text.rs").read_text()
fields=(ui/"fields.rs").read_text()
view=(ui/"view.rs").read_text()
rich_impl=between(rich,"pub(super) struct RichText {","pub(super) struct Content {")
prepare=between(rich,"    pub(super) fn prepare_rich_text(","    pub(super) fn prepare_content(")
prep_arm=between(fields,"            Node::RichText { id, html, inlines }","            Node::Content {")
ready=between(view,"    /// A previously accepted root","    /// Prepare an accepted tree")
(dst/"rich.inc.rs").write_text(rich_impl+"impl DeclarativeView {\n"+prepare+ready+
"""    fn prepare_root(&mut self, window: &mut Window, cx: &mut Context<Self>) {
        let root = self.root.clone().unwrap();
        match root.as_ref() {
"""+prep_arm+"""
            _ => panic!("only RichText preparation is executed"),
        }
    }
}
""")
is_shared="html: Arc<String>" in rich_impl
(dst/"owner.inc.rs").write_text("""const SHARED: bool = true;
fn weak_memo(text: &RichText) -> Option<std::sync::Weak<String>> {
    Some(Arc::downgrade(&text.html))
}
""" if is_shared else """const SHARED: bool = false;
fn weak_memo(_: &RichText) -> Option<std::sync::Weak<String>> { None }
""")
scopes={
    "rich-wire-validation": between(widget,"            Node::RichText { inlines, .. }","            Node::Svg {"),
    "wire-parse-dispatch": between(proto,"pub fn parse(","/// View id of a surface"),
    "unchanged-dispatch-and-fields": fields,
    "rich-app-prepare": prepare.replace("html: &Arc<String>","html: &str"),
    "visual-ready-and-pending": ready,
    "element-selection": between(rich_impl,"    pub(super) fn element(","\n}\n"),
    "root-acceptance": between(view,"    pub(super) fn show(","    pub(super) fn fail("),
    "inline-implementation": (ui/"inline_content.rs").read_text(),
    "content-shell": (ui/"content.rs").read_text(),
    "vendor-state": (source/"vendor/gpui-base/src/text/state.rs").read_text(),
    "vendor-element": (source/"vendor/gpui-base/src/text/text_view.rs").read_text(),
}
# Prior Tree field ownership changes this unrelated full source; preserve exact bytes within each tier.
for label,content in scopes.items():
    print(hashlib.sha256(content.encode()).hexdigest(),label)
