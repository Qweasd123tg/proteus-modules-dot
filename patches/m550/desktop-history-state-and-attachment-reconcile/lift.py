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
        t[t.index("use std::"):t.index("use proteus_contracts")]
        +
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
            Error { message:String }, Shutdown, Runtime { envelope: Envelope }, Other,
            ExecutionUpdated { execution: AppExecutionState },
            ModulesReloaded { },
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
    execution = between(pump, "            AppServerEvent::ExecutionUpdated { execution } =>", "            AppServerEvent::Runtime { envelope } => {\n                if matches!")
    tail = between(pump, "        shown |= !matches!(change, Change::None);", "    /// Hidden live rows")
    route = ("impl Chat { fn apply_event(&mut self, event: AppServerEvent, cx: &mut Context<Self>) -> bool {\n"
             + gate + execution + '            _ => unreachable!("unexercised dispatch"),\n        };\n'
             + tail
             + between(pump,"    pub(super) fn apply_change(","\n}\n").replace("pub(super) fn apply_change","fn apply_change",1)
             + "\n}\n")
    row = read(stock, "src/ui/chat/row_layout.rs") if (stock/"src/ui/chat/row_layout.rs").exists() else None
    assert row is not None
    (dest/"row_layout.rs").write_text("use super::*; use crate::transcript::{Entry,affected_rows};\n" + between(row,"#[derive(Debug, PartialEq, Eq)]\npub(super) struct RowLayout","\n#[cfg(test)]"))
    images = read(stock, "src/ui/chat/images.rs")
    retained = between(images,"    pub(super) fn retain(","    pub(super) fn missing(")
    (dest/"images.rs").write_text(read(packet,"image_boundary.rs")+"\nimpl SentImages {\n"+retained+"}\n")
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
        + between(scroller, "pub(super) fn height_hash(", "pub(super) fn invalidate_height_cache")
        + read(packet,"scroll_boundary.rs")
        + between(read(stock,"src/ui/chat/scroller/scrollbar.rs"), "#[derive(Clone, Copy, Default)]\nstruct State", "#[derive(Clone)]\npub(crate) struct HistoryScrollbar")
        + "impl HistoryScrollbar {\n"
        + between(read(stock,"src/ui/chat/scroller/scrollbar.rs"),"    pub fn set_range(","    pub fn take_target(")
        + "}\nimpl ScrollState {\n"
        + between(scroller,"    pub(super) fn bind_height_cache(","    fn refresh_height_binding(").replace("cx: &mut Context<Self>","cx: &mut ()")
        + "}\n")
    t=read(stock,"crates/tabs/src/lib.rs")
    (dest/"tabs").mkdir(exist_ok=True)
    (dest/"tabs.rs").write_text("use std::path::Path;\nmod identity; pub use identity::ChatKey;\n" + between(t,'const CHAT_PREFIX:', '/// Tab id of an extension document.') + between(t,'pub fn chat(session_dir:', 'pub fn is_chat('))
    (dest/"tabs/identity.rs").write_text(read(stock,"crates/tabs/src/identity.rs"))
    fb=read(stock,"src/ui/chat/feedback/mod.rs")
    (dest/"feedback.rs").write_text("use super::*; use crate::domain::MessageId;\n" +
        between(fb, "#[derive(Default)]", "impl Feedback {") +
        "impl Feedback {\n" + between(fb,"    pub fn snapshot(","    /// The caller filters child") +
        between(fb,"    fn prune(", "impl PendingSend {"))
    (dest/"tool_row.rs").write_text(between(read(stock,"src/ui/chat/tool_row.rs"),"pub(super) fn is_running(", "fn line_with_name("))
    (dest/"lib.rs").write_text(read(packet,"interface.rs")+"\nmod sync; mod feedback; mod tool_row; mod row_layout; mod images; mod tabs; use crate::{row_layout::{row_layout,reconciles_rows},images::SentImages}; pub(crate) mod history; pub(crate) mod scroller;\n"
        + "impl Session {\n"+methods+"}\n"+route)
