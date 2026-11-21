"""Bind exact production fragments to the deliberately small GPUI carrier."""
import hashlib
import shutil
from pathlib import Path
import sys

root, harness, here = map(Path, sys.argv[1:4])
d = root / "src/declarative"
u = root / "src/ui/extensions/declarative"
m = root / "src/ui/motion"
dst = harness / "src"
dst.mkdir(parents=True, exist_ok=True)
names = "widget control graph tree list lanes protocol session presentation".split()
for name in names:
    (dst / "declarative").mkdir(exist_ok=True)
    shutil.copyfile(d / f"{name}.rs", dst / "declarative" / f"{name}.rs")
shutil.copytree(root / "crates/diff", harness / "crates/diff", symlinks=True)
for name in ("harness",):
    shutil.copyfile(here / f"{name}.toml", harness / "Cargo.toml")
    shutil.copyfile(here / f"{name}.lock", harness / "Cargo.lock")
for name in ["probe", "carrier"]:
    shutil.copyfile(here / f"{name}.rs", dst / f"{'main' if name=='probe' else name}.rs")

def between(content, start, end):
    offset = content.index(start)
    return content[offset:content.index(end, offset + len(start))]

def read(path):
    return path.read_text()

def digest(data):
    return hashlib.sha256(data.encode()).hexdigest()

view = read(u / "view.rs")
badge = read(u / "badge.rs")
popup = read(u / "popup.rs")
runtime = read(u / "runtime.rs")
animation = read(m / "popup.rs")
animate = read(m / "mod.rs")

view_methods = (
    between(view, "    pub(super) fn show_with_revision(", "    pub(super) fn rehost(")
    + between(view, "    pub(super) fn show(", "    /// A previously accepted root")
    + between(view, "    pub(super) fn snapshot(", "    pub(super) fn present(")
    + between(view, "    pub(super) fn act(", "    /// Face of the compact icon")
)
popup_methods = between(popup, "    pub(super) fn toggle_popup(", "    pub(super) fn render_popup(")
popup_policy = between(animation, "fn destination(", "    fn update_anchor(")
incoming = between(runtime, "            Signal::Message(Incoming::View {", "            Signal::Message(Incoming::")
view_action = between(view, "                if !typing\n", "            }))")
view_read = between(view, "        let body = match &self.root {", "        let title = ")
slot = between(badge, "    pub(super) last_popup:", "    pub(super) popup_epoch:")
ease = between(animate, "pub(super) fn ease_enter(", "/// Easing of everything that leaves.")
slow = between(animate, "pub(super) const SLOW:", "/// A held pointer")
(dst / "motion.inc.rs").write_text(slow + ease + popup_policy + "}\n")
(dst / "view.inc.rs").write_text("impl DeclarativeView {\n" + view_methods + "}\n")
(dst / "popup.inc.rs").write_text("mod exact_popup { use super::*; impl DeclarativeBadge {\n" + popup_methods + "} }\n")
(dst / "runtime.inc.rs").write_text(
    "impl Runtime { pub(super) fn handle(&mut self, signal: Signal, cx: &mut Context<Self>) { match signal {\n"
    + incoming + " _ => unreachable!(\"tested View route only\"), } } }\n")
(dst / "view-readers.inc.rs").write_text(
    "impl DeclarativeView { fn observed_render(&mut self, cx: &mut Context<Self>) -> Option<(Node, String)> {\n"
    + view_read + "body\n} }\n"
    "fn observed_key(this: &mut DeclarativeView, chord: Option<String>, typing: bool, cx: &mut Context<DeclarativeView>) {\n"
    + view_action + "}\n")
text = (dst / "carrier.rs").read_text()
assert text.count("    // EXACT SLOT") == 1
(dst / "carrier.rs").write_text(text.replace("    // EXACT SLOT\n", slot))
# These remain full exact bytes (or exact fragments whose production callers are unchanged).
for label, block in (
    ("popup-file", popup), ("runtime-file", runtime),
    ("images-file", read(u / "images.rs")), ("fields-file", read(u / "fields.rs")),
    ("widget-file", read(d / "widget.rs")), ("protocol-file", read(d / "protocol.rs")),
    ("badge-render", badge[badge.index("impl Render for"):]),
    ("view-render", view[view.index("impl Render for"):]),
    ("view-prepare", between(view, "    pub(super) fn prepare(", "\n    /// ")),
    ("popup-close-and-toggle", popup_methods), ("popup-lifecycle", popup_policy),
    ("svg-unexercised", read(d / "svg.rs")), ("icon-unexercised", read(d / "icons.rs")),
    ("typed-action", between(view, "    pub(super) fn act(", "    /// Face of the compact icon")),
    ("runtime-view-arm", incoming),
):
    print(f"{digest(block)}  {label}")
