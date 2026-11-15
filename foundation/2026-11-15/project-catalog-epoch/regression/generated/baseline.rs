#![allow(dead_code)]
// Synthetic delivery queue. Only the marked methods/helpers come from source.
// No GPUI, driver process, HTTP, deletion, or creation operation is performed.
use std::{cell::RefCell, collections::{HashMap, HashSet}, marker::PhantomData, path::{Path, PathBuf}};

#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
enum AgentKind { #[default] Proteus, Codex }
impl AgentKind {
    fn for_key(key: &ChatKey) -> Self {
        match key { ChatKey::Proteus(_) => Self::Proteus, ChatKey::Codex(_) => Self::Codex }
    }
}
#[derive(Clone, Debug, PartialEq, Eq)]
enum ChatKey { Proteus(PathBuf), Codex(String) }
#[derive(Clone, Debug, PartialEq, Eq)]
struct ConversationSummary { key: ChatKey, parent: Option<ChatKey>, workspace_path: PathBuf, updated_at_ms: Option<u64> }
#[derive(Clone)]
struct CoreSummary { session_dir: PathBuf, workspace_path: PathBuf }
mod proteus_contracts { pub(crate) mod app_protocol { pub(crate) type AppSessionSummary = crate::CoreSummary; } }
mod conversations {
    use super::*;
    pub(super) fn from_codex(row: &ConversationSummary) -> ConversationSummary { row.clone() }
    pub(super) fn from_proteus(rows: Vec<CoreSummary>) -> Vec<ConversationSummary> {
        rows.into_iter().map(|row| ConversationSummary { key: ChatKey::Proteus(row.session_dir), parent: None, workspace_path: row.workspace_path, updated_at_ms: Some(2) }).collect()
    }
}
#[derive(Clone, Copy)]
struct OpenDocument { preview: bool, focus: bool }
struct Window;
enum HostEvent { ContextChanged }
#[derive(Default)]
struct Context<T> { prefs: Prefs, changes: usize, marker: PhantomData<T> }
impl<T> Context<T> { fn emit(&mut self, _: HostEvent) { self.changes += 1; } }
#[derive(Clone, Default)]
struct Prefs { preferred_agent: AgentKind, recent: Recent }
#[derive(Clone, Default)]
struct Recent;
impl Recent { fn forget(&mut self, _: &Path) {} fn touch(&mut self, _: &Path) {} }
mod prefs {
    use super::*;
    pub(super) fn current<T>(cx: &Context<T>) -> Prefs { cx.prefs.clone() }
    pub(super) fn update<T>(cx: &mut Context<T>, change: impl FnOnce(&mut Prefs)) { change(&mut cx.prefs) }
}
#[derive(Default)]
struct SessionList { collapsed: HashSet<PathBuf> }
struct Api(Vec<CoreSummary>);
impl Api { fn sessions(&self) -> Result<Vec<CoreSummary>, String> { Ok(self.0.clone()) } }
struct Codex { rows: Vec<ConversationSummary>, project: RefCell<Option<PathBuf>> }
impl Codex {
    fn list_until_main(&self, project: &Path) -> Result<Vec<ConversationSummary>, String> {
        *self.project.borrow_mut() = Some(project.to_path_buf());
        Ok(self.rows.clone())
    }
}
type Callback = Box<dyn FnOnce(&mut Workspace, &mut Window, &mut Context<Workspace>)>;
#[derive(Default)]
struct Workspace {
    sessions: Vec<ConversationSummary>, session_projects: HashMap<PathBuf, PathBuf>, session_list: SessionList,
    navigation_generation: u64, session_catalog_epoch: u64, navigation_starts: usize,
    core_snapshot: Vec<CoreSummary>, codex_snapshot: Vec<ConversationSummary>, pending: Vec<Callback>,
    reads: Vec<(AgentKind, Option<PathBuf>)>, selected: Vec<ChatKey>, created: Vec<AgentKind>,
}
impl Workspace {
    fn begin_navigation(&mut self, _: &mut Context<Self>) -> bool {
        self.navigation_generation += 1; self.navigation_starts += 1; true
    }
    fn report(&mut self, message: String, _: &mut Context<Self>) { panic!("unexpected report: {message}") }
    fn open_chat(&mut self, key: ChatKey, _: OpenDocument, _: &mut Window, _: &mut Context<Self>) { self.selected.push(key); }
    fn new_chat_in(&mut self, _: PathBuf, _: &mut Window, _: &mut Context<Self>) { self.created.push(AgentKind::Proteus); }
    fn new_codex(&mut self, _: PathBuf, _: Option<()>, _: &mut Window, _: &mut Context<Self>) { self.created.push(AgentKind::Codex); }
    fn call_in<R: 'static>(&mut self, _: &mut Window, _: &mut Context<Self>, job: impl FnOnce(&Api) -> Result<R, String>, done: impl FnOnce(&mut Self, R, &mut Window, &mut Context<Self>) + 'static) {
        self.reads.push((AgentKind::Proteus, None));
        let value = job(&Api(self.core_snapshot.clone())).unwrap();
        self.pending.push(Box::new(move |this, window, cx| done(this, value, window, cx)));
    }
    fn call_codex_in<R: 'static>(&mut self, _: &mut Window, _: &mut Context<Self>, job: impl FnOnce(&Codex) -> Result<R, String>, done: impl FnOnce(&mut Self, R, &mut Window, &mut Context<Self>) + 'static) {
        let service = Codex { rows: self.codex_snapshot.clone(), project: RefCell::new(None) };
        let value = job(&service).unwrap();
        self.reads.push((AgentKind::Codex, service.project.into_inner()));
        self.pending.push(Box::new(move |this, window, cx| done(this, value, window, cx)));
    }
    fn reply(&mut self, cx: &mut Context<Self>) { let done = self.pending.remove(0); done(self, &mut Window, cx); }
    pub fn open_project(
        &mut self,
        project: PathBuf,
        window: &mut Window,
        cx: &mut Context<Self>,
    ) {
        if !self.begin_navigation(cx) {
            return;
        }
        let navigation = self.navigation_generation;
        let project = match project.canonicalize() {
            Ok(path) if path.is_dir() => path,
            _ => {
                prefs::update(cx, |prefs| prefs.recent.forget(&project));
                return self.report(format!("Папка недоступна: {}", project.display()), cx);
            }
        };
        prefs::update(cx, |prefs| prefs.recent.touch(&project));
        self.session_list.collapsed.remove(&project);
        let agent = prefs::current(cx).preferred_agent;
        if agent == AgentKind::Codex {
            if let Some(key) = latest_main_session(&self.sessions, &project, agent) {
                return self.open_chat(key, project_open(), window, cx);
            }
            let listed_project = project.clone();
            return self.call_codex_in(
                window,
                cx,
                move |service| Ok(service.list_until_main(&listed_project)?),
                move |this, summaries, window, cx| {
                    for summary in summaries {
                        let summary = crate::conversations::from_codex(&summary);
                        this.sessions.retain(|row| row.key != summary.key);
                        this.sessions.push(summary);
                    }
                    this.finish_project_navigation(
                        project,
                        AgentKind::Codex,
                        navigation,
                        window,
                        cx,
                    );
                },
            );
        }
        self.call_in(
            window,
            cx,
            |api| api.sessions(),
            move |this, sessions, window, cx| {
                this.set_sessions(sessions, cx);
                this.finish_project_navigation(project, AgentKind::Proteus, navigation, window, cx);
            },
        );
    }
pub fn finish_project_navigation(
        &mut self,
        project: PathBuf,
        agent: AgentKind,
        navigation: u64,
        window: &mut Window,
        cx: &mut Context<Self>,
    ) {
        if self.navigation_generation != navigation {
            return;
        }
        if let Some(key) = latest_main_session(&self.sessions, &project, agent) {
            self.open_chat(key, project_open(), window, cx);
        } else if agent == AgentKind::Codex {
            self.new_codex(project, None, window, cx);
        } else {
            self.new_chat_in(project, window, cx);
        }
    }
pub fn set_sessions(
        &mut self,
        sessions: Vec<proteus_contracts::app_protocol::AppSessionSummary>,
        cx: &mut Context<Self>,
    ) {
        self.session_projects
            .retain(|dir, _| !sessions.iter().any(|summary| summary.session_dir == *dir));
        self.sessions
            .retain(|summary| matches!(summary.key, ChatKey::Codex(_)));
        self.sessions
            .extend(crate::conversations::from_proteus(sessions));
        cx.emit(HostEvent::ContextChanged);
    }
}
fn latest_main_session(
    sessions: &[ConversationSummary],
    project: &Path,
    agent: AgentKind,
) -> Option<ChatKey> {
    sessions
        .iter()
        .filter(|summary| {
            summary.workspace_path == project
                && summary.parent.is_none()
                && AgentKind::for_key(&summary.key) == agent
        })
        .max_by_key(|summary| summary.updated_at_ms)
        .map(|summary| summary.key.clone())
}
fn project_open() -> OpenDocument {
    OpenDocument {
        preview: false,
        focus: true,
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    fn project() -> PathBuf { Path::new(".").canonicalize().unwrap() }
    fn context(agent: AgentKind) -> Context<Workspace> { Context { prefs: Prefs { preferred_agent: agent, ..Default::default() }, ..Default::default() } }
    fn key(agent: AgentKind, id: &str) -> ChatKey {
        match agent { AgentKind::Proteus => ChatKey::Proteus(PathBuf::from(id)), AgentKind::Codex => ChatKey::Codex(id.into()) }
    }
    fn row(agent: AgentKind, id: &str, time: u64) -> ConversationSummary {
        ConversationSummary { key: key(agent, id), parent: None, workspace_path: project(), updated_at_ms: Some(time) }
    }
    fn snapshot(w: &mut Workspace, agent: AgentKind, id: Option<&str>) {
        w.core_snapshot = id.map(|id| CoreSummary { session_dir: id.into(), workspace_path: project() }).into_iter().collect();
        w.codex_snapshot = id.map(|id| row(agent, id, 2)).into_iter().collect();
    }
    fn start(agent: AgentKind) -> (Workspace, Context<Workspace>) {
        let mut w = Workspace::default(); let mut cx = context(agent);
        snapshot(&mut w, agent, Some("old"));
        w.open_project(project(), &mut Window, &mut cx);
        assert_eq!(w.pending.len(), 1);
        (w, cx)
    }
    #[test]
    fn obsolete_epoch_and_intention_do_not_write_or_retry() {
        for agent in [AgentKind::Proteus, AgentKind::Codex] {
            let (mut w, mut cx) = start(agent);
            w.session_catalog_epoch += 1; w.navigation_generation += 1;
            w.session_projects.insert("old".into(), project());
            w.reply(&mut cx);
            assert!(w.sessions.is_empty()); assert!(w.pending.is_empty());
            assert_eq!(w.session_projects.len(), 1); assert_eq!(cx.changes, 0);
            assert_eq!(w.reads.len(), 1); assert!(w.selected.is_empty()); assert!(w.created.is_empty());
        }
    }
    #[test]
    fn live_intention_retries_same_driver_and_project_without_navigation_restart() {
        for agent in [AgentKind::Proteus, AgentKind::Codex] {
            let (mut w, mut cx) = start(agent); let navigation = w.navigation_generation;
            w.session_catalog_epoch += 1;
            // A retry must read again, not take open_project's cached Codex shortcut.
            w.sessions.push(row(agent, "cached", 1));
            snapshot(&mut w, agent, Some("fresh"));
            cx.prefs.preferred_agent = match agent { AgentKind::Proteus => AgentKind::Codex, AgentKind::Codex => AgentKind::Proteus };
            w.reply(&mut cx);
            assert_eq!(w.sessions, [row(agent, "cached", 1)]);
            assert_eq!(w.navigation_generation, navigation); assert_eq!(w.navigation_starts, 1);
            assert_eq!(w.pending.len(), 1); assert!(w.selected.is_empty()); assert!(w.created.is_empty());
            assert_eq!(w.reads.len(), 2); assert!(w.reads.iter().all(|(driver, _)| *driver == agent));
            if agent == AgentKind::Codex { assert!(w.reads.iter().all(|(_, path)| path.as_ref() == Some(&project()))); }
            w.reply(&mut cx);
            assert_eq!(w.selected, [key(agent, "fresh")]); assert!(w.created.is_empty()); assert!(w.pending.is_empty());
            assert!(!w.sessions.iter().any(|row| row.key == key(agent, "old")));
        }
    }
    #[test]
    fn current_catalog_still_merges_after_newer_navigation_without_selecting() {
        for agent in [AgentKind::Proteus, AgentKind::Codex] {
            let (mut w, mut cx) = start(agent); w.navigation_generation += 1;
            w.reply(&mut cx);
            assert!(w.sessions.iter().any(|row| row.key == key(agent, "old")));
            assert!(w.selected.is_empty()); assert!(w.created.is_empty()); assert!(w.pending.is_empty()); assert_eq!(w.reads.len(), 1);
        }
    }
    #[test]
    fn current_catalog_and_intention_preserve_normal_selection() {
        for agent in [AgentKind::Proteus, AgentKind::Codex] {
            let (mut w, mut cx) = start(agent); w.reply(&mut cx);
            assert_eq!(w.selected, [key(agent, "old")]); assert!(w.created.is_empty()); assert_eq!(w.reads.len(), 1);
        }
    }
    #[test]
    fn repeated_epoch_changes_keep_one_read_pending_until_stable_delivery() {
        for agent in [AgentKind::Proteus, AgentKind::Codex] {
            let (mut w, mut cx) = start(agent);
            for _ in 0..3 {
                w.session_catalog_epoch += 1; w.reply(&mut cx);
                assert_eq!(w.pending.len(), 1); assert!(w.sessions.is_empty()); assert!(w.selected.is_empty()); assert!(w.created.is_empty());
            }
            assert_eq!(w.navigation_starts, 1); assert_eq!(w.reads.len(), 4);
            w.reply(&mut cx); assert_eq!(w.selected, [key(agent, "old")]); assert!(w.pending.is_empty());
        }
    }
    #[test]
    fn empty_retry_result_only_invokes_existing_creation_fallback_once() {
        for agent in [AgentKind::Proteus, AgentKind::Codex] {
            let (mut w, mut cx) = start(agent); w.session_catalog_epoch += 1;
            snapshot(&mut w, agent, None); w.reply(&mut cx);
            assert!(w.created.is_empty()); assert!(w.selected.is_empty()); assert_eq!(w.pending.len(), 1);
            w.reply(&mut cx); assert_eq!(w.created, [agent]); assert!(w.pending.is_empty()); assert_eq!(w.reads.len(), 2);
        }
    }
    #[test]
    fn cached_codex_fast_path_still_does_not_read_catalog() {
        let mut w = Workspace::default(); let mut cx = context(AgentKind::Codex);
        w.sessions.push(row(AgentKind::Codex, "cached", 1));
        w.open_project(project(), &mut Window, &mut cx);
        assert_eq!(w.selected, [key(AgentKind::Codex, "cached")]); assert!(w.reads.is_empty()); assert!(w.pending.is_empty());
    }
}
