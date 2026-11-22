"""Lift exact terminal key/guards and exact workspace ownership predicates."""
from pathlib import Path
import shutil
import sys

source, dest, packet = map(Path, sys.argv[1:])
src = dest / "src"
src.mkdir(parents=True)
shutil.copytree(source / "crates/tabs", dest / "crates/tabs", symlinks=True)
shutil.copyfile(source / "LICENSE-GPL", dest / "LICENSE-GPL")
for a, b in (("harness.toml", "Cargo.toml"), ("harness.lock", "Cargo.lock"),
             ("probe.rs", "src/lib.rs"), ("cases.rs", "src/cases.rs"), ("counter.rs", "src/counter.rs")):
    shutil.copyfile(packet/a, dest/b)

paths = {
    "product_terminal.rs": "src/ui/terminal/mod.rs",
    "product_view.rs": "src/ui/terminal/view.rs",
    "product_spaces.rs": "src/ui/" + "workspace/spaces.rs",
    "product_subagent.rs": "src/ui/chats/subagent.rs",
}
for destname, origin in paths.items():
    shutil.copyfile(source / origin, src / destname)
terminal, view, spaces, subagent = [(source / path).read_text() for path in paths.values()]
def slurp(text, start, end):
    assert text.count(start) == 1, start
    return start + text.split(start, 1)[1].split(end, 1)[0]

target = slurp(terminal, 'const PREFIX: &str = "agent-terminal:";', "pub(super) struct Remote")
fields = slurp(terminal, "    target: Target,\n", "    api: Api,")
ctor = slurp(view, "            target,\n", "            api,")
guard = slurp(terminal, "    fn current(&self, entity: EntityId, cx: &App) -> bool {\n", "\n}")
if "target_id: OnceCell<String>" in fields:
    helper = slurp(terminal, "    fn target_id(&self)", "    fn current")
    assert "target_id: Default::default()" in ctor
    assert guard.count("self.target_id()") == 2
    cache = "self.target_id.get()"
else:
    assert guard.count("&self.target.id()") == 2
    helper, cache = "", "None"
rehost = slurp(terminal, "                        view.workspace = workspace;\n", "                        cx.notify();")
assert rehost.strip() == "view.workspace = workspace;"
lifted = ("use super::*;\n" + target
          + "pub(super) struct Remote {\n" + fields + "    api: Api,\n    workspace: WeakHandle,\n}\n"
          + "impl Remote {\n    pub(super) fn new(target: Target, api: Api, workspace: WeakHandle) -> Self {\n"
          + "        Self {\n" + ctor + "            api,\n            workspace,\n        }\n    }\n"
          + helper + guard + """
    pub(super) fn check_current(&self, entity: EntityId) -> bool { self.current(entity, &App) }
    pub(super) fn check_visible(&self, entity: EntityId) -> bool { self.visible(entity, &App) }
    pub(super) fn memo(&self) -> Option<&String> { """ + cache + """ }
    pub(super) fn rehost(&mut self, workspace: WeakHandle) {
        let view = self;
""" + rehost + """
    }
}
pub(super) fn original_id(target: &Target) -> String { target.id() }
""")
(src / "guard.rs").write_text(lifted)
anchor = "    fn id(&self) -> String {\n"
assert lifted.count(anchor) == 1
(src / "observed.rs").write_text(lifted.replace(anchor, anchor + "        note_id();\n"))
def method(text, name):
    start = f"    pub(in crate::ui) fn {name}(&self, id: &str, entity: EntityId) -> bool {{\n"
    return slurp(text, start, "\n    }\n") + "\n    }\n"
current = method(spaces, "document_current")
visible = method(subagent, "document_visible")
membership = visible.split("self.settings.is_none()\n            && ", 1)[1].split("\n", 1)[0]
assert membership in {"self.layout.visible().any(|visible| visible == id)", "self.layout.is_visible(id)"}
assert visible == """    pub(in crate::ui) fn document_visible(&self, id: &str, entity: EntityId) -> bool {
        self.settings.is_none()
            && MEMBERSHIP
            && self
                .documents
                .get(id)
                .is_some_and(|surface| surface.view.entity_id() == entity)
    }
""".replace("MEMBERSHIP", membership)
(src / "workspace.inc.rs").write_text("impl Workspace {\n" + current + " }\n")
(src / "active.inc.rs").write_text("impl Workspace {\n" + visible + " }\n")
