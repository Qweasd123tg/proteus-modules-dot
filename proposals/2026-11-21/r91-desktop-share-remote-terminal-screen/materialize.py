"""Copy exact terminal crate and isolate the current production render/cursor seam."""
import hashlib
import re
import shutil
import sys
from pathlib import Path

source, output, packet = map(Path, sys.argv[1:])
term=output/"crates/terminal"
shutil.copytree(source/"crates/terminal",term,symlinks=True)
(output/"vendor").mkdir()
for vendor in ("ghostty-vt","ghostty-vt-sys"):
    shutil.copytree(source/"vendor"/vendor,output/"vendor"/vendor,symlinks=True)
for a,b in (("harness.toml","Cargo.toml"),("harness.lock","Cargo.lock")):
    shutil.copyfile(packet/a,output/b)
for name in ("LICENSE-GPL","LICENSE-APACHE"):
    shutil.copyfile(source/name,output/name)
root=term/"src/display"
(root/"tests.rs").write_text((root/"tests.rs").read_text()+'\n#[path = "r91_fixtures.rs"]\nmod r91_fixtures;\n')
for file in ("r91_fixtures.rs","paint_carrier.rs"):
    shutil.copyfile(packet/file,root/file)
def between(s,a,b):
    i=s.index(a)
    return s[i:s.index(b,i+len(a))]
def read(path):
    return (source/path).read_text()
local=read("src/ui/extensions/declarative/terminal.rs")
remote=read("src/ui/terminal/view.rs")
cells=read("src/ui/terminal/cells.rs")
display=read("crates/terminal/src/display.rs")
snapshot=between(remote,"        let screen = self.display.as_ref().map(", "        let state = if self.finished")
paint=between(remote,"            .children(screen.as_ref().map(", "\n        v_flex()")
paint=paint.removeprefix("            .children(")
assert paint.endswith("));")
paint=paint.removesuffix(");")
local_paint=between(local,"        let rendered = match self.state.terminal()","        // Status occupies its own layout")
draw=between(cells,"fn render_run(", "pub(in crate::ui) fn screen(")+cells[cells.index("pub(in crate::ui) fn screen("):]
draw=draw.replace("pub(in crate::ui) fn screen", "pub(super) fn screen")
helpers=between(cells,"pub(in crate::ui) const PADDING", "pub(in crate::ui) fn cell_size")
helpers=helpers.replace("pub(in crate::ui)", "pub(super)")
(root/"cells_projection.inc.rs").write_text(helpers+draw)
(root/"view_projection.inc.rs").write_text("""impl Remote<'_> {
    fn render_screen(&self, cell: Size<Pixels>, foreground: Hsla, background: Hsla, window: &Window) -> Option<Div> {
"""+snapshot+"        "+paint+"\n    }\n}\n"+
"""impl Local<'_> {
    fn render_screen(&self, cell: Size<Pixels>, foreground: Hsla, background: Hsla, window: &Window) -> Div {
        use cells::rgb_bytes;
        let base = div();
"""+local_paint+"        rendered\n    }\n}\n")
if "screen: Arc<Screen>" in display:
    ownership="""const SHARED: bool = true;
fn weak(frame: &Arc<Screen>) -> Option<std::sync::Weak<Screen>> { Some(Arc::downgrade(frame)) }
"""
else:
    ownership="""const SHARED: bool = false;
fn weak(_: &Screen) -> Option<std::sync::Weak<Screen>> { None }
"""
(root/"ownership.inc.rs").write_text(ownership)
# Normalize only the ownership and per-consumer cursor plumbing to assert every other production statement is unchanged.
contexts={
    "display-engine-and-queues": display.replace("screen: Arc<Screen>,","screen: Screen,")
        .replace("screen: Arc::new(Screen {","screen: Screen {")
        .replace("                    scrolled: 0,\n                }),","                    scrolled: 0,\n                },")
        .replace("snapshot(&self, base: Base) -> Arc<Screen>", "snapshot(&self, base: Base) -> Screen")
        .replace("Arc::clone(&view.screen)","view.screen.clone()")
        .replace("Arc::new(engine.snapshot(base)?)","engine.snapshot(base)?"),
    "remote-rest-of-render": remote.replace(snapshot,"").replace("            .children("+paint+");",""),
    "local-exhaustive-except-pass-through-cursor": local.replace("                    screen.cursor,\n",""),
    "cells-except-explicit-cursor-source": cells.replace("    cursor: Option<(usize, usize)>,\n","").replace("let cursor = cursor.map","let cursor = screen.cursor.map"),
    "actor-engine": read("crates/terminal/src/display/engine.rs"),
    "ghostty-local": read("crates/terminal/src/ghostty.rs"),
    "ghostty-display-engine": read("crates/terminal/src/ghostty/display.rs"),
    "remote-transport-io": read("src/ui/terminal/io.rs"),
    "remote-transport-pending": read("src/ui/terminal/pending.rs"),
}
for label,text in contexts.items():
    print(hashlib.sha256(text.encode()).hexdigest(),label)
