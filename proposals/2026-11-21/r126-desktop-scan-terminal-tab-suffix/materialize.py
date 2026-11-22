"""Bind exact real tabs and three product methods; model only inert UI boundaries."""
from pathlib import Path
import shutil
import sys

source, baseline, dest, packet = map(Path, sys.argv[1:])
src = dest / "src"
src.mkdir(parents=True)
shutil.copytree(source / "crates/tabs", dest / "crates/tabs", symlinks=True)
shutil.copyfile(source / "LICENSE-GPL", dest / "LICENSE-GPL")
for old,new in (("harness.toml","Cargo.toml"),("harness.lock","Cargo.lock"),
                ("probe.rs","src/lib.rs"),("counter.rs","src/counter.rs")):
    shutil.copyfile(packet / old, dest / new)
windows = "src/ui/" + "workspace/windows.rs"
extensions = "src/ui/extensions/mod.rs"
actions = "src/ui/tabs/mod.rs"
paths = {"product_windows.rs": windows, "product_extensions.rs": extensions, "product_tabs.rs": actions}
for destname, origin in paths.items():
    shutil.copyfile(source / origin, src / destname)

def cut(text, start, end):
    assert text.count(start) == 1, start
    body = start + text.split(start, 1)[1].split(end, 1)[0]
    assert body
    return body

old = (baseline / windows).read_text()
current = (source / windows).read_text()
module = (source / extensions).read_text()
tabs = (source / actions).read_text()
old_head = "    pub(in crate::ui) fn all_tabs("
new_head = "    pub(in crate::ui) fn max_tab_suffix("
def method(text, name):
    return cut(text, name, "\n    }\n") + "\n    }\n"

all_tabs = method(old, old_head)
save = method(old, "    fn saved_layout(")
assert save == method(current, "    fn saved_layout(")
window_method = method(current, new_head) if new_head in current else method(current, old_head)
(src/"window.inc.rs").write_text("impl WindowGroup {\n" + window_method + "}\n")
# The identical baseline method is an independent observer in both arms.
(src/"oracle.inc.rs").write_text("impl Group {\n" + save + "}\n" +
    "impl WindowGroup {\n" + all_tabs.replace(old_head,"    fn baseline_all_tabs(") + "}\n")
selected = cut(module, "pub(super) fn next_document(", "\nimpl DocumentSurface") + "\n"
(src/"extensions.inc.rs").write_text(selected)
action = method(tabs, "    pub(super) fn open_terminal(")
dispatch = cut(action, "        let Some(id) = ", " else {").strip()
expr = dispatch.removeprefix("let Some(id) = ").strip()
assert expr in {
    'extensions::next_document("terminal.new", &self.windows.all_tabs(), cx)',
    '''extensions::next_document(
            "terminal.new",
            |prefix| self.windows.max_tab_suffix(prefix),
            cx,
        )''',
}, repr(expr)
# Only the surrounding wrapper is test-specific; the call expression is exact.
(src/"action.inc.rs").write_text("impl Workspace {\n" + action +
    "    fn resolve_terminal(&self, cx: &App) -> Option<String> {\n        " + expr + "\n    }\n}\n")
