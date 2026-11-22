"""Exact accepted Tree source in a narrow native-effect carrier."""
import hashlib
import re
import shutil
import sys
from pathlib import Path

root, out, packet = map(Path, sys.argv[1:])
dst = out / "src"
schemas = dst / "declarative"
schemas.mkdir(parents=True)
d, ui = root / "src/declarative", root / "src/ui/extensions/declarative"
for name in "widget control graph tree list lanes protocol session presentation icons".split():
    shutil.copyfile(d / (name + ".rs"), schemas / (name + ".rs"))
shutil.copytree(root / "crates/diff", out / "crates/diff", symlinks=True)
for name, target in (("harness.toml","Cargo.toml"), ("harness.lock","Cargo.lock"),
                     ("carrier.rs","src/carrier.rs"), ("probe.rs","src/main.rs"), ("cases.rs","src/cases.rs")):
    shutil.copyfile(packet / name, out / target)

def between(text, start, end):
    offset = text.index(start)
    return text[offset:text.index(end, offset+len(start))]

def digest(text):
    return hashlib.sha256(text.encode()).hexdigest()

tree = (ui / "tree.rs").read_text()
fields = (ui / "fields.rs").read_text()
row = (ui / "tree_row.rs").read_text()
menu = (ui / "menu.rs").read_text()
view = (ui / "view.rs").read_text()
widget = (d / "widget.rs").read_text()
process = (d / "process.rs").read_text()
variant = "rows: Arc<Vec<Row>>" in tree
layout = between(tree, "/// How rows are indented", "impl Tree {")
start = between(tree, "impl Tree {", "    /// Row `index`")
keys = between(tree, "    pub fn focus(", "impl Render for Tree")
fold = between(tree, "/// Rows under the branch", "#[cfg(test)]")
(dst / "tree.inc.rs").write_text(layout + start + keys + fold)
context = between(fields, "/// A retained widget keeps its event sink", "pub(super) enum Text")
arm = between(fields, "            Node::Tree {\n                id,", "            Node::Lanes {\n                id,")
(dst / "fields.inc.rs").write_text(context + """
#[derive(Default)]
struct Fields { trees: HashMap<String, Entity<Tree>> }
#[derive(Default)]
pub(crate) struct DeclarativeView { fields: Fields, embedded: bool }
impl DeclarativeView {
    fn sync_tree(&mut self, root: &Node, cx: &mut Context<Self>) {
        match root {
""" + arm + """
            _ => panic!("non-tree controls are out of scope"),
        }
    }
}
""")
snap = between(row, "        let (items, view) = (row.menu.clone()", "        element\n            .right_click_menu")
assert "super::menu::fill(menu, &items, &view)" in row
# Exact fill/Ask and selected-row snapshot statement; paint/gesture/dialog effects stay modeled.
fill = menu[menu.index("/// Fills a popup menu"):]
ask = between(menu, "/// What a control asks", "/// Sends `action`")
(dst / "menu.inc.rs").write_text(ask + fill + """
impl Tree {
    pub(super) fn observed_menu(&self, n: usize) -> impl Fn() -> PopupMenu + use<> {
        let row = &self.rows[n];
        assert!(!row.menu.is_empty(), "exercise the nonempty menu snapshot");
""" + snap + """
        move || fill(PopupMenu::default(), &items, &view)
    }
}
""")
(dst / "ownership.inc.rs").write_text(
    ("const SHARED: bool = true;\nfn owner(tree: &Tree) -> Option<std::sync::Weak<Vec<Row>>> { Some(Arc::downgrade(&tree.rows)) }\n"
     if variant else "const SHARED: bool = false;\nfn owner(_: &Tree) -> Option<std::sync::Weak<Vec<Row>>> { None }\n"))
validation = between(widget, "            Node::Tree { rows, indent", "            Node::Lanes { columns")
assert validation.count("rows") == 2
validation = validation.replace("rows.iter()", "rows")
prune = between(fields, "            Node::Tree { id, .. }", "            Node::Graph { id, .. }")
guards = {
 "tree-protocol": between((d / "protocol.rs").read_text(), "pub fn parse(", "/// View id of a surface"),
 "tree-row-dto": (d / "tree.rs").read_text(),
 "tree-read-route": between(process, "pub enum Signal", "pub struct Signals"),
 "tree-widget-validation": validation,
 "tree-prune-kind": prune,
 "tree-view-root": between(view, "    pub(super) fn show(", "    /// A previously accepted root"),
 "tree-row-paint-ghost-and-menu": row,
 "menu-fill-send-ask": menu,
 "tree-navigation": keys,
 "tree-animation": fold,
 "tree-reconciliation-after-equality": between(tree, "        self.layout = layout;", "    fn fold_key(").replace(".zip(rows.iter())", ".zip(&rows)"),
}
for label, code in guards.items():
    print(f"{digest(code)}  {label}")
