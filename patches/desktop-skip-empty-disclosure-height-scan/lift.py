"""Lift the exact synchronous History, Transcript and disclosure caller; substitute GPUI."""
from pathlib import Path

history = Path("src/ui/chat/history.rs")
prefix = """        if self.expanded.is_empty()
            && self.full_blocks.is_empty()
            && self.open_chains.is_empty()
            && self.tool_diffs.is_empty()
        {
            return Vec::new();
        }
"""
function = "    fn disclosed_height_rows(&self) -> Vec<Range<usize>> {\n"


def read(root, relative):
    return (root / relative).read_text(encoding="utf-8")


def between(source, first, last):
    assert source.count(first) == 1, first
    start = source.index(first)
    return source[start:source.index(last, start)]


def lift(stock, candidate, packet, dest):
    chat = read(stock, "src/ui/chat/mod.rs")
    types = ("expanded: HashSet<u64>", "full_blocks: HashSet<(u64, usize)>",
             "open_chains: HashSet<u64>", "tool_diffs: HashMap<u64, Entity<crate::ui::diff::DiffView>>")
    for line in types:
        assert chat.count(line) == 1, line

    a, b = (read(root, history) for root in (stock, candidate))
    assert a.count(function) == 1 and a.replace(function, function + prefix) == b
    wrapper = read(packet, "interface.rs")
    rust = wrapper.split("// LIFTED CHAT BELOW\n")
    assert len(rust) == 2
    dest.mkdir(parents=True, exist_ok=True)
    t = read(stock, "src/transcript/mod.rs")
    transcript = (
        "use std::{collections::HashMap, sync::{Arc, atomic::{AtomicU64, Ordering}}};\n"
        "use crate::app_protocol::{AppTranscriptMessage, AppTranscriptSubagent, AppTranscriptTool};\n"
        "use crate::domain::{ImageRef, MessageId, ThreadId};\n"
        + between(t, "#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash)]\npub enum Role", "    /// Independent rows in windows")
        .replace("    #[cfg(test)]\n    text_work: text_run::TextWork,\n", "")
        + between(t, "    /// Independent rows in windows", "    pub fn push_user(")
        + between(t, "    fn allocate_key(", "fn delta_keep(")
        + between(t, "/// Whether a row renders the same", "\nmod cache;")
        + "\nmod cache;\nmod chains;\nmod subagent;\n"
        + "pub use cache::window_changes;\npub use chains::affected_rows;\n")
    subdir = dest / "transcript"
    subdir.mkdir()
    (dest / "transcript.rs").write_text(transcript, encoding="utf-8")
    for name in ("cache", "chains", "subagent"):
        source = read(stock, f"src/transcript/{name}.rs")
        (subdir / f"{name}.rs").write_text(source.split("\n#[cfg(test)]\nmod tests")[0], encoding="utf-8")
    protocol = read(stock, "crates/proteus-contracts/src/app_protocol/transcript.rs")
    (dest / "app_protocol.rs").write_text(protocol, encoding="utf-8")
    base = "crates/proteus-contracts/src"
    def extract_type(path, type_decl):
        source = read(stock, f"{base}/{path}")
        end = source.index("\n}", source.index(type_decl)) + len("\n}")
        start = source.rindex("#[derive(", 0, source.index(type_decl))
        return source[start:end] + "\n"

    ids = read(stock, f"{base}/domain/ids.rs")
    (dest / "domain.rs").write_text(
        "use std::path::PathBuf;\nuse serde::{Deserialize, Serialize};\nuse uuid::Uuid;\n"
        + "".join(between(ids, f"pub type {name} = ", "\n") + "\n"
                  for name in ("MessageId", "ThreadId", "SessionId"))
        + extract_type("domain/image.rs", "pub struct ImageRef"), encoding="utf-8")
    (dest / "contracts.rs").write_text(
        "use serde::{Deserialize, Serialize};\nuse uuid::Uuid;\n"
        + extract_type("contracts/tool_terminal.rs", "pub struct ToolTerminalRef"), encoding="utf-8")
    (dest / "model_standard.rs").write_text(
        "use serde::{Deserialize, Serialize};\n"
        + extract_type("model_standard/content_part.rs", "pub enum MessagePhase"), encoding="utf-8")
    fixture = read(stock, "src/ui/chat/history/tests.rs")
    (dest / "fixture.rs").write_text(
        "use crate::{app_protocol::*, transcript::Transcript};\n"
        + between(fixture, "fn rows(", "fn fixture(")
          .replace("fn rows(", "pub fn rows(").replace("fn page(", "pub fn page(")
          .replace("fn cursor(", "pub fn cursor("), encoding="utf-8")

    def variant(src, name):
        decisions = between(src, "const PAGE_ROWS:", "    pub(super) fn seek_history")
        look = "        for (row, entry) in entries.iter().enumerate() {\n"
        assert decisions.count(look) == 1
        # Instrument source visits only; uninstrumented counterparts are also tested.
        if name.endswith("_counted"):
            decisions = decisions.replace(look, look + "            self.visits.set(self.visits.get() + 1);\n")
        return f"mod {name} {{\n" + rust[1] + decisions + "}\n" + read(packet, "scenario.rs") + "}\n"

    (dest / "lib.rs").write_text(
        rust[0] + "".join(variant(s, name) for s, name in
            ((a, "stock"), (b, "candidate"), (a, "stock_counted"), (b, "candidate_counted")))
        + read(packet, "checks.rs"), encoding="utf-8")
