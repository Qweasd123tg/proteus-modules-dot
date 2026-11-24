#![allow(dead_code, unused_imports)]
extern crate self as proteus_contracts;
mod app_protocol;
mod transcript;
mod fixture;
mod domain;
mod contracts;
mod model_standard;

use std::ops::Range;
use app_protocol::*;
use transcript::{Change, Transcript, window_changes};

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
struct HistoryRange { start: usize, rows: usize, total: usize }
#[derive(Clone, Copy)]
struct ScrollTarget { row: usize, fraction: f32 }

#[derive(Debug, PartialEq, Eq)]
enum Call {
    Update,
    Rebase(Option<usize>),
    Exclude(Range<usize>, usize),
    Invalidate(Range<usize>),
    Archived(bool),
    Apply(Change),
    Range(Option<HistoryRange>, bool),
    Bind(Option<Key>),
    Notify,
    Config,
    Context,
    Cancel,
    Entry(Change),
    State,
    Settled,
}

use std::marker::PhantomData;
type Context<T> = ContextState<T>;
struct ContextState<T> {
    calls: Vec<Call>,
    phantom: PhantomData<T>,
}
impl<T> Default for ContextState<T> {
    fn default() -> Self { Self { calls: Vec::new(), phantom: PhantomData } }
}
impl<T> ContextState<T> {
    fn emit(&mut self, e: ChatEvent) { self.calls.push(match e { ChatEvent::RunSettled=>Call::Settled,ChatEvent::State=>Call::State,ChatEvent::Entries(c)=>Call::Entry(c)}); }
    fn notify(&mut self) { self.calls.push(Call::Notify); }
}
#[derive(Default)]
struct Scroller { state: Option<ScrollState> }
impl Scroller {
    fn update<T>(&mut self, cx: &mut Context<T>, f: impl FnOnce(&mut ScrollState, &mut ())) {
        cx.calls.push(Call::Update);
        let s = self.state.get_or_insert_with(Default::default);
        f(s, &mut ());
        cx.calls.append(&mut s.calls);
    }
    fn telemetry(&self) -> (usize,usize,usize,usize,bool,Option<usize>) {
        self.state.as_ref().expect("bound scroller").bar.telemetry()
    }
}
#[derive(Default)]
struct ScrollState {
    calls: Vec<Call>,
    height_key: Option<Key>,
    bar: scroller::HistoryScrollbar,
    refreshes: usize,
}
impl ScrollState {
    fn rebase_history(&mut self, prefix: Option<usize>, _: &mut ()) { self.calls.push(Call::Rebase(prefix)); }
    fn exclude_document_disk(&mut self, rows: Range<usize>, total: usize) { self.calls.push(Call::Exclude(rows, total)); }
    fn invalidate_history_rows(&mut self, rows: Range<usize>, _: &mut ()) { self.calls.push(Call::Invalidate(rows)); }
    fn set_archived(&mut self, archived: bool, _: &mut ()) { self.calls.push(Call::Archived(archived)); }
    fn set_history_range(&mut self, range: Option<HistoryRange>, seek: bool, _: &mut ()) {
        self.calls.push(Call::Range(range, seek));
        self.bar.set_range(range,seek);
    }
    fn refresh_height_binding(&mut self, _: &mut ()) { self.refreshes += 1; self.calls.push(Call::Bind(self.height_key.clone())); }
    fn history_cancelled(&mut self, _: &mut ()) { self.calls.push(Call::Cancel); }
    fn scroll_to_end(&mut self, _: &mut ()) { unreachable!() }
    fn append(&mut self, count: usize, _: &mut ()) { assert_eq!(count,1); self.calls.push(Call::Apply(Change::Pushed)); }
    fn remeasure_items(&mut self, _: Range<usize>, _: &mut ()) {}
    fn splice(&mut self, range: Range<usize>, inserted: usize, _: &mut ()) { self.calls.push(Call::Apply(Change::Spliced{start:range.start,removed:range.len(),inserted})); }
}
mod startup_trace {
    pub fn first(_: &str) {}
    pub fn history_window(_: usize, _: usize, _: impl FnOnce() -> usize, _: usize) {}
}
struct ContextSeek;
impl ContextSeek { fn loaded(&mut self, _: &[transcript::Entry]) { unreachable!() } }

use std::collections::{HashMap, HashSet};
use std::path::PathBuf;
use uuid::Uuid;
use domain::SessionId;
use feedback::Feedback;
use crate::tabs::ChatKey;
use sync::SessionCursor;
use history::History;
use scroller::HeightCacheKey as Key;
pub(crate) mod ui { pub(crate) mod chat { pub(crate) use crate::{Session,history,scroller}; } }
pub(crate) struct Session {
    key: ChatKey, cursor: SessionCursor, snapshot_identity: Option<(Uuid, String)>,
    root_thread: Option<Uuid>, feedback: Feedback, execution: AppExecutionState, transcript: Transcript,
}
impl Session {
    fn running(&self)->bool {self.execution.active.is_some()}
    fn new(dir: PathBuf) -> Self {
        Self { key: ChatKey::Proteus(dir), cursor: Default::default(), snapshot_identity: None,
              root_thread: None, feedback: Default::default(), execution: Default::default(), transcript: Default::default() }
    }
}
struct Codex { archive: Option<Transcript> }
struct DiffView;
struct Chat {
    expanded: HashSet<u64>, full_blocks: HashSet<(u64, usize)>, open_chains: HashSet<u64>,
    tool_diffs: HashMap<u64, PhantomData<DiffView>>, history: History, session: Session,
    codex: Option<Codex>, scroller: Scroller,
    sent_images: SentImages, replies: Replies, fresh_rows: Fresh,
}
#[derive(Default)] struct Replies(HashSet<u64>);
impl Replies { fn is_empty(&self)->bool {self.0.is_empty()} fn retain(&mut self,k:&HashSet<u64>) {self.0.retain(|x| k.contains(x));} }
#[derive(Default)] struct Fresh;
impl Fresh {fn mark(&mut self,_:u64){}}
enum ChatEvent { RunSettled, State, Entries(Change) }
impl ChatEvent {
    fn entries_changed(c: Change) -> Self { Self::Entries(c) }
    fn state_changed() -> Self { Self::State }
}
impl Chat {
    fn new(dir: PathBuf) -> Self {
        Self { expanded: Default::default(), full_blocks: Default::default(), open_chains: Default::default(),
               tool_diffs: Default::default(), history: Default::default(), session: Session::new(dir),
               codex: None, scroller: Default::default(), sent_images: Default::default(), replies: Default::default(), fresh_rows: Default::default() }
    }
    fn codex_latest(&mut self, _: &mut Context<Self>) { unreachable!() }
    fn load_context(&self, cx: &mut Context<Self>) { cx.calls.push(Call::Context); }
    fn sync_cancel_notice(&self, _: &mut Context<Self>) {}
    fn show_error(&self, _: String, _: &mut Context<Self>) { unreachable!() }
    fn invalidate_archived_live_heights(&self, _: &mut Context<Self>) { unreachable!() }
}
#[cfg(test)]
mod meter;
