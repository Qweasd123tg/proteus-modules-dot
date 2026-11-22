use super::{history::{self, History}, row_layout, scroller::{HistoryRange, ScrollTarget}, stamp};
use crate::{ledger, transcript::{Role, Transcript, tool_chain}};
use proteus_contracts::app_protocol::{AppTranscriptCursor, AppTranscriptMessage, AppTranscriptSubagent, AppTranscriptTool};
use serde_json::json;
use std::{collections::HashSet, ops::Range, time::Instant};

struct Chat {
    session: Session,
    history: History,
    codex: Option<Binding>,
    open_chains: HashSet<u64>,
}
struct Binding { archive: Option<Transcript> }
struct Session { transcript: Transcript, execution: Execution, external: Option<External> }
struct Execution { active: Option<()> }
struct External { busy: bool }
impl External { fn running(&self) -> bool { self.busy } }

#[derive(Default)]
struct Cx { visual: Visual, moving: bool }
#[derive(Default)]
struct Visual { view: ViewPrefs }
#[derive(Default)]
struct ViewPrefs { compact_tools: bool }
impl Cx { fn entity_id(&self) -> u64 { 1 } }
mod prefs {
    use super::*;
    pub(super) fn visual(cx: &Cx) -> &Visual { &cx.visual }
}
fn chain_reveal_key(_: u64, head: u64) -> u64 { head }
mod motion {
    use super::*;
    pub(super) fn moving_at(_: &u64, _: bool, _: Instant, cx: &Cx) -> bool { cx.moving }
}
struct EmptyElement;
fn div() -> EmptyElement { EmptyElement }
impl EmptyElement { fn into_any_element(self) -> Option<Row> { None } }
#[derive(Debug)]
struct Row { end: usize, end_key: u64, footer: bool, time: Option<i64>, copyable: bool, drawn: bool }
include!("thread.inc.rs");

fn chat(rows: Vec<AppTranscriptMessage>, running: bool) -> Chat {
    let mut history = History::default();
    let mut transcript = Transcript::default();
    history.apply(&mut transcript, rows, None);
    Chat { session: Session { transcript, execution: Execution { active: running.then_some(()) }, external: None },
           history, codex: None, open_chains: HashSet::new() }
}
fn make(n: u128, role: &str, text: &str, timestamp_ms: Option<i64>) -> AppTranscriptMessage {
    AppTranscriptMessage {
        timestamp_ms, message_id: Some(uuid::Uuid::from_u128(n)), phase: None,
        role: role.into(), text: text.into(), images: Vec::new(), tool: None, subagent: None,
        streaming: false,
    }
}
fn user(n: u128) -> AppTranscriptMessage { make(n, "user", "question", None) }
fn assistant(n: u128, text: &str, time: Option<i64>) -> AppTranscriptMessage { make(n, "assistant", text, time) }
fn tool(n: u128, time: Option<i64>) -> AppTranscriptMessage {
    let mut row = make(n, "system", "", time);
    row.tool = Some(AppTranscriptTool {
        terminal: None, call_id: format!("call-{n}"), name: "read_file".into(),
        args: json!({"path":"fixture"}), effective_args: None, status: "done".into(),
        result: None, metadata: json!(null),
    });
    row
}
fn cast_child(id: u128) -> proteus_contracts::app_protocol::AppSubagentSession {
    proteus_contracts::app_protocol::AppSubagentSession {
        session_id: uuid::Uuid::from_u128(id), session_dir: format!("/fixture/child-{id}").into(),
    }
}
fn progress(n: u128, id: &str, child: u128) -> AppTranscriptMessage {
    let mut row = make(n, "system", "", None);
    row.subagent = Some(AppTranscriptSubagent {
        child_thread_id: id.into(), session: Some(cast_child(child)), role: "worker".into(),
        description: None, status: "running".into(), iterations: None, tools: vec![],
    });
    row
}
fn linked(n: u128, id: &str, child: u128) -> AppTranscriptMessage {
    let mut row = tool(n, None);
    row.tool.as_mut().unwrap().metadata = json!({
        "tool": "spawn_agent", "child_thread_id": id, "subagent_session": cast_child(child),
    });
    row
}

struct Expected {
    footer: bool,
    time: Option<i64>,
    copyable: bool,
    drawn: bool,
    hidden: usize,
    links: usize,
    peers: usize,
}
fn yes(time: Option<i64>, hidden: usize) -> Expected {
    Expected { footer: true, time, copyable: true, drawn: true, hidden, links: 0, peers: 0 }
}
fn no(hidden: usize) -> Expected {
    Expected { footer: false, time: None, copyable: false, drawn: false, hidden, links: 0, peers: 0 }
}
fn observe(case: &str, chat: &mut Chat, row: usize, end: usize, state: Expected, cx: &mut Cx, candidate: bool) {
    let data = chat.row(row, Instant::now(), cx).expect("visible row under actual chain and visibility checks");
    assert_eq!(data.end, end, "{case}: represented end");
    assert_eq!(data.end_key, chat.display_transcript().entries()[end-1].key, "{case}: rendered footer key");
    assert_eq!((data.footer,data.time,data.copyable,data.drawn), (state.footer,state.time,state.copyable,state.drawn), "{case}: behavior");
    let calls = if candidate {1} else {2};
    let work = ledger::work();
    assert_eq!(work, ledger::Work { tail: calls, hidden: calls*state.hidden, link: calls*state.links, peer: calls*state.peers }, "{case}: counters");
    println!("PASS {case} end={} key_matches=true footer={} time={:?} copyable={} draws_footer={}", data.end,data.footer,data.time,data.copyable,data.drawn);
    eprintln!("WORK {case} tail={} hidden={} link_lookups={} peer_rows={}",work.tail,work.hidden,work.link,work.peer);
}
fn hidden(case: &str, chat: &mut Chat, row: usize, cx: &mut Cx) {
    ledger::reset();
    assert!(chat.row(row, Instant::now(), cx).is_none(), "{case}: row not drawn");
    assert_eq!(ledger::work().tail, 0, "{case}: no stamp calls for hidden row");
    println!("PASS {case} skipped, turn_end_calls=0");
}
fn archive(rows: Vec<AppTranscriptMessage>) -> Chat {
    let mut chat = chat(Vec::new(), false);
    let mut page: Vec<_> = (0..50-rows.len()).map(|i| user(1000+i as u128)).collect();
    page.extend(rows);
    chat.history.apply(
        &mut chat.session.transcript, vec![user(6001), assistant(6002, "live later", Some(333))],
        Some(AppTranscriptCursor { before:75, revision:"test-r79".into(), base: None }),
    );
    let target = ScrollTarget { row:30, fraction:0. };
    assert_eq!(history::fixture_seek(&chat.session.transcript, &mut chat.history, target, page), Some(target));
    let range = chat.history.range(&chat.session.transcript).unwrap();
    assert_eq!((range.start,range.rows,range.total),(5,50,77));
    assert!(chat.history.archived());
    assert!(!chat.history.at_live_tail(&chat.session.transcript));
    chat
}

pub(crate) fn run(candidate: bool) {
    let mut cx = Cx::default();
    let observe = |case, chat: &mut Chat, row, end, state, cx: &mut Cx| observe(case,chat,row,end,state,cx,candidate);
    observe("normal-earlier-reply", &mut chat(vec![user(1),assistant(2,"answer",Some(101)),user(3)],true),1,2,yes(Some(101),1),&mut cx);
    observe("normal-nonfooter-next-tool", &mut chat(vec![user(1),assistant(2,"answer",Some(101)),tool(3,Some(102)),user(4)],false),1,2,no(1),&mut cx);
    observe("timestamp-less-copy", &mut chat(vec![user(1),assistant(2,"текст",None),user(3)],false),1,2,yes(None,1),&mut cx);
    observe("timestamp-less-empty-no-actions", &mut chat(vec![user(1),assistant(2," \t\n",None),user(3)],false),1,2,
        Expected { footer:true, ..no(1) },&mut cx);
    observe("timestamp-only-no-copy", &mut chat(vec![user(1),assistant(2," \t",Some(101)),user(3)],false),1,2,
        Expected { footer:true,time:Some(101),drawn:true,..no(1) },&mut cx);
    observe("timestamp-fallback-to-previous-reply", &mut chat(vec![user(1),assistant(2,"answer",Some(101)),tool(3,None),user(4)],false),2,3,yes(Some(101),1),&mut cx);
    observe("last-row-time-is-not-max", &mut chat(vec![user(1),assistant(2,"answer",Some(210)),tool(3,Some(105)),user(4)],false),2,3,yes(Some(105),1),&mut cx);
    observe("tool-only-no-time-no-actions-with-user", &mut chat(vec![user(1),tool(2,None)],false),1,2,
        Expected { footer:true,..no(0) }, &mut cx);
    observe("first-turn-no-user-copy-policy", &mut chat(vec![tool(1,None)],false),0,1,yes(None,0),&mut cx);
    observe("current-user", &mut chat(vec![user(1),assistant(2,"answer", Some(101))], false),0,1,no(0),&mut cx);
    let mut streaming = assistant(2,"live",Some(101)); streaming.streaming=true;
    observe("current-streaming", &mut chat(vec![user(1),streaming,user(3)], false),1,2,no(0),&mut cx);

    let mut tail = chat(vec![user(1),assistant(2,"answer",Some(101))],true);
    observe("running-live-tail", &mut tail,1,2,no(0),&mut cx);
    tail.session.execution.active=None;
    observe("settled-live-tail", &mut tail,1,2,yes(Some(101),0),&mut cx);

    let mut skip = chat(vec![user(1),progress(2,"a",41),progress(3,"b",42),assistant(4,"reply",Some(103)),linked(5,"a",41),linked(6,"b",42),user(7)],false);
    observe("two-hidden-links", &mut skip,3,4,Expected {links:2,peers:5,..yes(Some(103),3)},&mut cx);
    hidden("hidden-tool-row", &mut skip,4,&mut cx);
    hidden("missing-row", &mut skip,80,&mut cx);
    // A malformed non-null link is visible, so it cannot accidentally complete the preceding turn.
    let mut bad = linked(5,"a",41);
    bad.tool.as_mut().unwrap().metadata["subagent_session"]["session_dir"] = json!("relative");
    observe("malformed-link-is-visible", &mut chat(vec![user(1),progress(2,"a",41),assistant(3,"reply",Some(103)),bad,user(6)],false),2,3,
        Expected {links:1,..no(1)},&mut cx);
    // Same child ID but different typed session is not a duplicate.
    observe("conflicting-link-is-visible", &mut chat(vec![user(1),progress(2,"a",49),assistant(3,"reply",Some(103)),linked(4,"a",41),user(5)],false),2,3,
        Expected {links:1,peers:5,..no(1)},&mut cx);
    // Old metadata with no durable link may still refer to the same live child.
    let mut legacy = linked(4,"a",41);
    legacy.tool.as_mut().unwrap().metadata.as_object_mut().unwrap().remove("subagent_session");
    observe("legacy-hidden-link-next-user", &mut chat(vec![user(1),progress(2,"a",41),assistant(3,"reply",Some(103)),legacy,user(5)],false),2,3,
        Expected {links:1,peers:2,..yes(Some(103),2)},&mut cx);

    let mut seek = archive(vec![progress(1,"a",41),assistant(2,"reading",Some(105)),linked(3,"a",41)]);
    observe("real-seek-hidden-tail-incomplete", &mut seek,48,49,Expected {links:1,peers:48,..no(1)},&mut cx);
    let entries = seek.display_transcript().entries();
    let context = row_layout::row_context(entries,false,seek.history.range(&seek.session.transcript));
    assert_eq!(context.missing(48),Some(history::Direction::Newer));
    assert_eq!(context.missing(49),Some(history::Direction::Newer));
    assert_eq!(context.missing(47),None);
    println!("PASS real history clipped footer owner after hidden suffix unresolved");

    let mut seek_earlier = archive(vec![assistant(1,"reading",Some(105)),user(2)]);
    observe("real-seek-earlier-complete-turn", &mut seek_earlier,48,49,yes(Some(105),1),&mut cx);
    // The existing Codex archive branch is authoritative even with active live state.
    seek.session.execution.active = Some(());
    let mut codex = Transcript::default();
    codex.reset(vec![progress(1,"a",41),assistant(2,"archive",Some(211)),linked(3,"a",41)]);
    seek.codex=Some(Binding { archive:Some(codex) });
    observe("codex-archive-complete-hidden-tail", &mut seek,1,2,Expected {links:1,peers:1,..yes(Some(211),1)},&mut cx);
    seek.codex=Some(Binding { archive:None });
    observe("codex-nonarchive-still-incomplete", &mut seek,48,49,Expected {links:1,peers:48,..no(1)},&mut cx);

    let mut chain = chat(vec![user(1),tool(2,Some(101)),tool(3,Some(102)),tool(4,Some(103))],false);
    cx.visual.view.compact_tools=true;
    observe("collapsed-folded-final-footer", &mut chain,1,4,Expected {footer:true,time:Some(103),drawn:true,..no(0)},&mut cx);
    hidden("collapsed-member-skips", &mut chain,2,&mut cx);
    chain.open_chains.insert(chain.display_transcript().entries()[1].key);
    observe("settled-open-head-has-next-tool", &mut chain,1,2,no(1),&mut cx);
    observe("settled-open-member-owns-footer", &mut chain,3,4,Expected {footer:true,time:Some(103),drawn:true,..no(0)},&mut cx);
    cx.moving=true;
    observe("moving-chain-head-owns-footer", &mut chain,1,4,Expected {footer:true,time:Some(103),drawn:true,..no(0)},&mut cx);
    hidden("moving-chain-member-skips", &mut chain,3,&mut cx);
}
