"""Assemble a focused model test target without linking/compiling the GPUI graph.
Uses pinned modules and function bodies; skips two existing ListState-based tests.
"""
import re
import sys
from pathlib import Path

repo, out, tests = [Path(p).resolve() for p in sys.argv[1:]]
h = repo / "src/ui/chat/history"
source = h.with_suffix(".rs").read_text()
ctx = (h / "context.rs").read_text()
scrollbar = (repo / "src/ui/chat/scroller/scrollbar.rs").read_text()
history = source[source.index("const PAGE_ROWS:"):source.index("\nimpl Chat {")]
ranges = scrollbar[scrollbar.rindex("#[derive", 0, scrollbar.index("pub(crate) struct HistoryRange")):scrollbar.index("#[derive", scrollbar.index("pub(crate) struct ScrollTarget"))]
context_type = ctx[ctx.index("pub(super) struct ContextSeek"):ctx.index("#[derive(Debug, PartialEq)]")]
context_methods = ctx[ctx.index("impl ContextSeek {"):ctx.index("    fn step(")] + "}\n"
visible = ctx[ctx.index("    pub(super) fn context_visible("):ctx.index("\nimpl Chat {")]
testfile = tests.read_text()
testfile = re.sub(r"#\[test\]\nfn (?:overlapping_live_tail_keeps_older_visible_rows_until_the_anchor_reaches_live|returning_to_live_tail_keeps_gpui_logical_anchor_and_unique_row_keys)\(\) \{.*?\n\}\n", "", testfile, flags=re.S)
assert "gpui_kit" not in testfile
path = out / "history_model.rs"
path.write_text("use std::ops::Range;\nuse crate::transcript::{Change, Transcript, window_changes};\nuse proteus_contracts::app_protocol::{AppTranscriptCursor, AppTranscriptMessage, AppTranscriptPage};\n" + ranges + history + context_type + context_methods + "impl History {\n" + visible + "\n#[cfg(test)] mod tests {\n" + testfile + "\n}\n")
(out / "check.rs").write_text(f'''#![allow(dead_code, unused_imports)]
mod agents {{ pub(crate) mod codex {{ include!(r"{repo}/src/agents/codex/types.rs"); }} }}
#[path = r"{repo}/src/transcript/mod.rs"]
mod transcript;
#[path = r"{path}"]
mod history;
''')
