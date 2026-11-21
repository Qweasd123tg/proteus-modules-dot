"""Extract exact Desktop sources into a bounded non-GPUI fixture."""
import hashlib
import sys
import shutil
from pathlib import Path

source, arm, here = map(Path, sys.argv[1:])
d = arm / "src"
chat = d / "ui/chat"
chat.mkdir(parents=True, exist_ok=True)
u = source / "src/ui/chat"

for filename in ("harness.toml", "harness.lock", "probe.rs", "carrier.rs", "ledger.rs"):
    to = dict(zip(
        ("harness.toml", "harness.lock", "probe.rs", "carrier.rs", "ledger.rs"),
        ("Cargo.toml", "Cargo.lock", "src/main.rs", "src/ui/chat/carrier.rs", "src/ledger.rs"),
    ))[filename]
    shutil.copyfile(here / filename, arm / to)

shutil.copytree(source / "src/transcript", d / "transcript")
(d / "agents/codex").mkdir(parents=True, exist_ok=True)
shutil.copyfile(source / "src/agents/codex/types.rs", d / "agents/codex/types.rs")
(d / "agents/codex/mod.rs").write_text("mod types; pub use types::{Item, ItemKind};\n")
(d / "ui/mod.rs").write_text("pub(crate) mod chat;\n")
(chat / "mod.rs").write_text("mod stamp; mod history; mod scroller; mod row_layout; mod carrier;\npub(crate) use carrier::run;\n")

def get(file):
    return file.read_text()

def cut(text, start, stop):
    lo = text.index(start)
    return text[lo:text.index(stop, lo + len(start))]

def insert(text, trigger, new):
    assert text.count(trigger) == 1, trigger
    return text.replace(trigger, trigger + "\n" + new)

def function(text, start, prefix=""):
    pos = text.index(start)
    # The exact target functions have body-closing braces on a clean line.
    end = text.index("\n" + prefix + "}\n", pos) + len(prefix) + 3
    return text[pos:end]

history = get(u / "history.rs").split("\nimpl Chat {", 1)[0]
for unneeded in ("use gpui_kit::*;\n", "use super::Chat;\n", "mod height_key;\n"):
    assert history.count(unneeded) == 1
    history = history.replace(unneeded, "")
(chat / "history.rs").write_text(history + """
pub(super) fn fixture_seek(
    live: &Transcript, history: &mut History, target: ScrollTarget, messages: Vec<AppTranscriptMessage>,
) -> Option<ScrollTarget> {
    history.seek = Some(target);
    let cursor = history.seek_cursor()?;
    let start = cursor.before.checked_sub(messages.len())?;
    let total = history.range(live)?.total;
    let page = AppTranscriptPage { revision: cursor.revision.clone(), start, total, messages, base: None };
    history.accept_seek(live, &cursor, page).map(|(_, target)| target)
}
""")
(chat / "history").mkdir(exist_ok=True)
full_context = get(u / "history/context.rs")
context_impl = cut(full_context, "impl History {", "\nimpl Chat {")
context_src = full_context.split("#[cfg(test)]", 1)[0].split("\nimpl Chat {", 1)[0]
context_src = context_src.replace("CACHE_ROWS, Chat, Direction", "CACHE_ROWS, Direction")
context_src = context_src.replace("use gpui_kit::*;\n", "")
(chat / "history/context.rs").write_text(context_src + context_impl)
shutil.copyfile(u / "row_layout.rs", chat / "row_layout.rs")

scroller = get(u / "scroller/scrollbar.rs")
parts = []
for name in ("HistoryRange", "ScrollTarget"):
    pos = scroller.index(f"pub(crate) struct {name}")
    parts.append(function(scroller, scroller[scroller.rfind("#[derive(", 0, pos):pos] + f"pub(crate) struct {name}"))
(chat / "scroller.rs").write_text("\n".join(parts))

stamp = cut(get(u / "stamp.rs"), "pub(super) fn hidden(", "/// The time of row")
stamp = insert(stamp, "pub(super) fn hidden(entries: &[Entry], entry: &Entry) -> bool {", "    crate::ledger::hidden();")
(chat / "stamp.rs").write_text("use crate::transcript::{Entry, Role};\n" + stamp)

subagent = d / "transcript/subagent.rs"
text = get(subagent)
text = insert(text, "    let child = tool.metadata.get(\"child_thread_id\")?.as_str()?;", "    crate::ledger::link();")
text = insert(text, "    entries.iter().position(|entry| {", "        crate::ledger::peer();")
subagent.write_text(text)

thread = get(u / "thread.rs")
row_head = cut(thread, "        let entries = self\n", "        let image_edge = ")
# Scope ledger to the stamp call and exclude the initial item's visibility test.
start = "        let ending = stamp::turn_end(" if "let ending = stamp::turn_end(" in row_head else "        let time = stamp::time_after("
assert row_head.count(start) == 1
row_head = row_head.replace(start, "        crate::ledger::reset();\n" + start)
tail = function(thread, "    fn complete_stamp_tail(", "    ")
tail = insert(tail, "    fn complete_stamp_tail(&self) -> bool {", "        crate::ledger::tail();")
chains = get(u / "tool_chain.rs")
display = function(get(u / "history.rs"), "    pub(super) fn display_transcript(", "    ")
chain = function(chains, "    pub(super) fn chain_at(", "    ")
open_chain = function(chains, "    pub(super) fn chain_open(", "    ")
running = function(get(u / "session.rs"), "    pub fn running(", "    ")
row_draw = cut(thread, "                    .when(footer && (copyable || time.is_some()),", "                row_id(")
assert ".child(self.turn_footer(key, end_key, time, copyable, cx))," in row_draw
gate = row_draw.split(".when(", 1)[1].split(", |row|", 1)[0]
(chat / "thread.inc.rs").write_text(
    "impl Session {\n" + running + "}\n"
    "impl Chat {\n" + tail + chain + open_chain + display
    + "fn row(&mut self, ix: usize, frame_at: Instant, cx: &mut Cx) -> Option<Row> {\n" + row_head
    + "        let drawn = " + gate + ";\n"
    + "        Some(Row { end, end_key, footer, time, copyable, drawn })\n"
    + "} }\n"
)
# These blocks are non-production footprints; compare unchanged call neighborhoods.
for label, value in (
    ("footer-draw", row_draw), ("history-tail", cut(history, "    pub(super) fn displayed<", "    pub(super) fn apply(")),
    ("tail", tail), ("session-running", running), ("chain-group", chain + open_chain),
    ("initial-row-path", row_head.split("        crate::ledger::reset();", 1)[0]),
    ("copyability", row_head.split("        let end_key", 1)[1]),
    ("same-tier-child-matcher", get(source / "src/transcript/subagent.rs")),
    ("row-context", get(u / "row_layout.rs")), ("unchanged-turn-time-format", cut(get(u / "stamp.rs"), "/// The time of row", "#[cfg(test)]")),
):
    print(f"{hashlib.sha256(value.encode()).hexdigest()}  {label}")
