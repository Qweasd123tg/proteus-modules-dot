from pathlib import Path

def read(root, relative):
    return (root / relative).read_text(encoding="utf-8")


def between(source, first, last):
    assert source.count(first) == 1, first
    start = source.index(first)
    return source[start:source.index(last, start)]


def lift(stock, packet, dest):
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
    subdir.mkdir(exist_ok=True)
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

    live = read(stock, "crates/proteus-contracts/src/app_protocol/live.rs")
    with (dest/"app_protocol.rs").open("a") as f:
        f.write("\nmod live { use super::*; use crate::domain::SessionId; use serde::{Serialize,Deserialize};\n")
        f.write(live[live.index("/// Session subscription baseline"):])
        f.write("\n}\npub use live::*;\n")
        f.write("""pub enum AppServerEvent {
            SessionSnapshot { snapshot: Box<AppSessionSnapshot> }, EventStreamLagged { count:u64 },
            PendingRequestsUpdated {}, SessionActivityUpdated {}, SessionCatalogUpdated,
            Error { message:String }, Shutdown, Runtime { envelope: Envelope }, Other, ExecutionUpdated { },
        }
        pub struct Envelope { pub session_id: crate::domain::SessionId, pub event:RuntimeEvent }
        pub enum RuntimeEvent { TokenUsageUpdated { }, Other }
        """)
    with (dest/"domain.rs").open("a") as f:
        f.write(extract_type("domain/run_options.rs","pub struct RunOptions"))
        f.write(extract_type("domain/tool.rs","pub enum PermissionMode"))
    sync = read(stock, "crates/client-common/src/sync.rs")
    (dest/"sync.rs").write_text(sync[:sync.index("#[cfg(test)]")])
    history = read(stock, "src/ui/chat/history.rs")
    decisions = between(history, "const PAGE_ROWS:", "    pub(super) fn seek_history")
    session = read(stock, "src/ui/chat/session.rs")
    # Exact function bodies kept; visibility/super path adapted to lifted nesting.
    methods = between(session, "    pub(super) fn durable_id", "    pub(super) fn new(")
    methods += between(session, "    pub(super) fn snapshot_settles_run(", "    /// Every original event")
    methods = methods.replace("pub(super) fn ", "fn ").replace("super::tool_row::", "tool_row::")
    pump = read(stock, "src/ui/chat/pump.rs")
    gate = between(pump, "        let session = &mut self.session;\n        if !session.cursor.accept", "            AppServerEvent::ExecutionUpdated { execution } =>")
    tail = between(pump, "        if execution_changed {", "    /// Hidden live rows")
    support = between(pump, "fn settled_error(", "/// Streams the session")
    route = ("impl Chat { fn apply_event(&mut self, event: AppServerEvent, cx: &mut Context<Self>) -> bool {\n"
             + gate + '            _ => unreachable!("snapshot-only route"),\n        };\n'
             + tail + "}\n")
    hist = ("use super::*;\nmod height_key;\n" + decisions + "}\n" +
            "impl History { fn context_visible(&self, visible: Range<usize>) -> Range<usize> { assert!(self.context_seek.is_none()); visible } }\n"
            + "#[cfg(test)] mod exercise;\n")
    (dest/"history").mkdir(exist_ok=True)
    (dest/"history.rs").write_text(hist)
    (dest/"history"/"height_key.rs").write_text(read(stock,"src/ui/chat/history/height_key.rs"))
    (dest/"history"/"exercise.rs").write_text(read(packet,"exercise.rs"))
    (dest/"meter.rs").write_text(read(packet,"meter.rs"))
    if "pub(in super::super) use height_store::Key as HeightCacheKey;" not in read(stock,"src/ui/chat/scroller/scrollbar.rs"):
        raise ValueError("changed scroller key wiring")
    store = read(stock,"src/ui/chat/scroller/scrollbar/height_store.rs")
    scroller = read(stock, "src/ui/chat/scroller.rs")
    key = between(store, "#[derive(Clone, Debug, PartialEq, Eq)]\npub(in super::super::super) struct Key", "/// At most four scalar vectors")
    (dest/"scroller.rs").write_text("use sha2::{Digest,Sha256}; type Hash = [u8;32];\n"+key.replace("pub(in super::super::super) struct Key", "pub(crate) struct HeightCacheKey")
        + between(scroller, "pub(super) fn height_hash(", "pub(super) fn invalidate_height_cache"))
    fb=read(stock,"src/ui/chat/feedback/mod.rs")
    (dest/"feedback.rs").write_text("use super::*; use crate::domain::MessageId;\n" +
        between(fb, "#[derive(Default)]", "impl Feedback {") +
        "impl Feedback {\n" + between(fb,"    pub fn snapshot(","    /// The caller filters child") +
        between(fb,"    fn prune(", "impl PendingSend {"))
    (dest/"tool_row.rs").write_text(between(read(stock,"src/ui/chat/tool_row.rs"),"pub(super) fn is_running(", "fn line_with_name("))
    (dest/"lib.rs").write_text(read(packet,"interface.rs")+"\nmod sync; mod feedback; mod tool_row; pub(crate) mod history; pub(crate) mod scroller;\n"
        + "impl Session {\n"+methods+"}\n"+support+route)
