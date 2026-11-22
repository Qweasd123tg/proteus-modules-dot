"""Lift complete Workspace::new and the exact Preparation receiver gate."""
from pathlib import Path
import shutil
import sys

source, dest, packet = map(Path, sys.argv[1:])
src = dest / "src"
src.mkdir(parents=True)
shutil.copytree(source / "crates/tabs", dest / "crates/tabs", symlinks=True)
shutil.copyfile(source / "LICENSE-GPL", dest / "LICENSE-GPL")
for old, new in (("harness.toml", "Cargo.toml"), ("harness.lock", "Cargo.lock"),
                 ("probe.rs", "src/lib.rs"), ("counter.rs", "src/counter.rs")):
    shutil.copyfile(packet / old, dest / new)
w = source / "src/ui/workspace.rs"
s = source / ("src/ui/" + "workspace/startup.rs")
shutil.copyfile(w, src / "product_workspace.rs")
shutil.copyfile(s, src / "product_startup.rs")

def method(text, head):
    assert text.count(head) == 1, head
    body = head + text.split(head, 1)[1].split("\n    }\n", 1)[0] + "\n    }\n"
    assert body.count("\n    }\n") == 1
    return body

text = w.read_text()
construct = method(text, "    pub fn new(\n        options: LaunchOptions,\n")
empty = method(text, "    fn empty(\n")
assert empty.count("spaces") == 5
assert "        spaces: ChatSpaces,\n" in empty
assert "        let layout = spaces.active_layout().clone();\n" in empty
assert "        windows.register(cx.weak_entity(), spaces.clone());\n" in empty
assert "            spaces,\n" in empty
prepare = method(s.read_text(), "    pub(super) fn for_workspace(\n")
assert prepare.count("async_channel::Receiver") == 1
(src / "construct.inc.rs").write_text("impl Workspace {\n" + construct + "}\n")
(src / "match.inc.rs").write_text("impl Preparation {\n" + prepare + "}\n")

stock = "        let saved = spaces.clone();\n"
candidate = """            let saved = if prepared.is_none() {
                workspace.spaces.clone()
            } else {
                ChatSpaces::default()
            };
"""
assert (stock in construct) != (candidate in construct)
statement = stock if stock in construct else candidate
# Same exact statement outside the model, with prebuilt inputs around the meter.
# Leave the matched-ready (no async branch) zero explicit at call site.
(src / "clone.inc.rs").write_text(
    "fn cloned_layout(spaces: &ChatSpaces, prepared: Option<()>) -> ChatSpaces {\n"
    "    let workspace = BorrowedWorkspace { spaces };\n"
    "    let _ = (&workspace.spaces, &prepared);\n"
    + statement +
    "    saved\n}\n")
