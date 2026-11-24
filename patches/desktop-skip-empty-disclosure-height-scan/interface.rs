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
    Bind(Option<u64>),
    Notify,
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
    fn notify(&mut self) { self.calls.push(Call::Notify); }
}
#[derive(Default)]
struct Scroller;
impl Scroller {
    fn update<T>(&mut self, cx: &mut Context<T>, f: impl FnOnce(&mut ScrollState<'_>, &mut ())) {
        cx.calls.push(Call::Update);
        f(&mut ScrollState(&mut cx.calls), &mut ());
    }
}
struct ScrollState<'a>(&'a mut Vec<Call>);
impl ScrollState<'_> {
    fn rebase_history(&mut self, prefix: Option<usize>, _: &mut ()) {
        self.0.push(Call::Rebase(prefix));
    }
    fn exclude_document_disk(&mut self, rows: Range<usize>, total: usize) {
        self.0.push(Call::Exclude(rows, total));
    }
    fn invalidate_history_rows(&mut self, rows: Range<usize>, _: &mut ()) {
        self.0.push(Call::Invalidate(rows));
    }
    fn set_archived(&mut self, archived: bool, _: &mut ()) { self.0.push(Call::Archived(archived)); }
    fn set_history_range(&mut self, range: Option<HistoryRange>, seek: bool, _: &mut ()) {
        self.0.push(Call::Range(range, seek));
    }
    fn bind_height_cache(&mut self, key: Option<u64>, _: &mut ()) { self.0.push(Call::Bind(key)); }
    fn scroll_to_end(&mut self, _: &mut ()) { unreachable!() }
}
mod startup_trace {
    pub fn history_window(_: usize, _: usize, _: impl FnOnce() -> usize, _: usize) {}
}
struct ContextSeek;
impl ContextSeek { fn loaded(&mut self, _: &[transcript::Entry]) { unreachable!() } }

// LIFTED CHAT BELOW
use super::*;
use std::cell::Cell;
use std::collections::{HashMap, HashSet};
mod height_key {
    use super::*;
    pub fn key(_: &Session, _: &AppTranscriptCursor) -> Option<u64> { None }
}
type Entity<T> = PhantomData<T>;
struct DiffView;
#[derive(Default)]
struct Session { transcript: Transcript }
struct Codex { archive: Option<Transcript> }
#[derive(Default)]
pub struct Chat {
    expanded: HashSet<u64>,
    full_blocks: HashSet<(u64, usize)>,
    open_chains: HashSet<u64>,
    tool_diffs: HashMap<u64, Entity<DiffView>>,
    history: History,
    session: Session,
    codex: Option<Codex>,
    scroller: Scroller,
    visits: Cell<usize>,
}
impl History {
    fn context_visible(&self, visible: Range<usize>) -> Range<usize> {
        assert!(self.context_seek.is_none());
        visible
    }
}
impl Chat {
    fn codex_latest(&mut self, _: &mut Context<Self>) { unreachable!() }
    fn apply_change(&mut self, change: Change, cx: &mut Context<Self>) {
        cx.calls.push(Call::Apply(change));
    }
}
