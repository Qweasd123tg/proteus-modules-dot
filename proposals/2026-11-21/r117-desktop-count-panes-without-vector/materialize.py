"""Keep the exact tabs crate and lift the real tab-bar closeability expression."""
from pathlib import Path
import shutil
import sys

source, dst, packet = map(Path, sys.argv[1:])
src = dst / "src"
src.mkdir(parents=True)
shutil.copytree(source / "crates/tabs", dst / "crates/tabs", symlinks=True)
shutil.copyfile(source / "LICENSE-GPL", dst / "LICENSE-GPL")
for old, new in (("harness.toml", "Cargo.toml"), ("harness.lock", "Cargo.lock"),
                 ("probe.rs", "src/lib.rs"), ("counter.rs", "src/counter.rs")):
    shutil.copyfile(packet / old, dst / new)
controls = source / "src/ui/tabs/controls.rs"
shutil.copyfile(controls, src / "product_controls.rs")
body = controls.read_text()
id_line = "        let id = pane.id;\n"
query = "        let closable = layout.can_close(id);\n"
assert body.count(id_line) == body.count(query) == 1
assert ".right_click_menu(move |popup, _, _| pane_menu(popup, id, closable, locked, &workspace))" in body
(src / "lifted.rs").write_text("fn render_controls_closeable(pane: &Pane, layout: &TabLayout) -> bool {\n"
                               + id_line + query + "        closable\n}\n")
