#![allow(dead_code)]
use std::{path::{Path,PathBuf},collections::{HashMap,HashSet},marker::PhantomData};
use proteus_tabs as tabs;
use tabs::{ChatKey,TabLayout,ChatSpaces};
use conversations::{AgentKind,ConversationSummary};
#[derive(Clone,Copy,Debug)] struct OpenDocument {preview:bool,focus:bool}
struct Window;
#[derive(Default)] struct Context<T> { prefs:Prefs,focused_chat:std::cell::Cell<bool>,_type:PhantomData<T> }
impl<T> Context<T> {fn emit(&mut self,_:HostEvent){} fn notify(&mut self){} }
#[derive(Default,Clone)]struct Prefs {preferred_agent:AgentKind,recent:Recent}
#[derive(Default,Clone)]struct Recent;
impl Recent {fn forget(&mut self,_:&Path){} fn touch(&mut self,_:&Path){} }
mod prefs {use super::*;pub(super)fn current<T>(cx:&Context<T>)->Prefs{cx.prefs.clone()} pub(super)fn update<T>(cx:&mut Context<T>,f:impl FnOnce(&mut Prefs)){f(&mut cx.prefs)}}
enum HostEvent{ContextChanged}
mod proteus_contracts {pub mod app_protocol {use std::path::PathBuf;#[derive(Clone)]pub struct AppSessionSummary {pub session_dir:PathBuf,pub workspace_path:PathBuf}}}
mod conversations {
 use super::*;
 #[derive(Clone,Copy,Debug,Default,PartialEq)]pub enum AgentKind{#[default]Proteus,Codex}
 impl AgentKind {pub fn for_key(k:&ChatKey)->Self{match k{ChatKey::Proteus(_)=>Self::Proteus,ChatKey::Codex(_)=>Self::Codex}}}
 #[derive(Clone,Debug)]pub struct ConversationSummary {pub key:ChatKey,pub parent:Option<ChatKey>,pub workspace_path:PathBuf,pub updated_at_ms:Option<u64>}
 pub fn from_codex(s:&ConversationSummary)->ConversationSummary{s.clone()}
 pub fn from_proteus(s:Vec<proteus_contracts::app_protocol::AppSessionSummary>)->Vec<ConversationSummary>{s.into_iter().map(|s|ConversationSummary{key:ChatKey::Proteus(s.session_dir),parent:None,workspace_path:s.workspace_path,updated_at_ms:Some(1)}).collect()}
}
struct Api(Vec<proteus_contracts::app_protocol::AppSessionSummary>);
impl Api {fn sessions(&self)->Result<Vec<proteus_contracts::app_protocol::AppSessionSummary>,String>{Ok(self.0.clone())}}
struct Codex(Vec<ConversationSummary>);
impl Codex{fn list_until_main(&self,_:&Path)->Result<Vec<ConversationSummary>,String>{Ok(self.0.clone())}}
#[derive(Default)]struct SessionList{collapsed:HashSet<PathBuf>}
type Callback=Box<dyn FnOnce(&mut Workspace,&mut Window,&mut Context<Workspace>)>;
#[derive(Default)]struct Workspace {
 layout:TabLayout,spaces:ChatSpaces,chats:HashMap<String,()>,sessions:Vec<ConversationSummary>,
 session_projects:HashMap<PathBuf,PathBuf>,session_list:SessionList,navigation_generation:u64,session_catalog_epoch:u64,
 deleting_sessions:HashSet<ChatKey>,opening:HashMap<String,()>,settings:Option<()>,creating_chat:Option<()>,
 core_snapshot:Vec<proteus_contracts::app_protocol::AppSessionSummary>,codex_snapshot:Vec<ConversationSummary>,
 pending:Vec<Callback>,focus_calls:Vec<String>,resumed:Vec<(ChatKey,Option<OpenDocument>)>,opened:Vec<ChatKey>,
}
impl Workspace {
 fn call_in<R:'static>(&mut self,_:&mut Window,_:&mut Context<Self>,job:impl FnOnce(&Api)->Result<R,String>,done:impl FnOnce(&mut Self,R,&mut Window,&mut Context<Self>)+'static){let r=job(&Api(self.core_snapshot.clone())).unwrap();self.pending.push(Box::new(move |w,win,cx|done(w,r,win,cx)))}
 fn call_codex_in<R:'static>(&mut self,_:&mut Window,_:&mut Context<Self>,job:impl FnOnce(&Codex)->Result<R,String>,done:impl FnOnce(&mut Self,R,&mut Window,&mut Context<Self>)+'static){let r=job(&Codex(self.codex_snapshot.clone())).unwrap();self.pending.push(Box::new(move |w,win,cx|done(w,r,win,cx)))}
 fn reply(&mut self,cx:&mut Context<Self>){let f=self.pending.remove(0);f(self,&mut Window,cx)}
 fn begin_navigation(&mut self,_:&mut Context<Self>)->bool {self.invalidate_navigation();true}
 fn report(&mut self,msg:String,_:&mut Context<Self>){panic!("unexpected report: {msg}")}
 fn new_codex(&mut self,_:PathBuf,_:Option<()>,_:&mut Window,_:&mut Context<Self>){panic!("not exercised")}
 fn new_chat_in(&mut self,_:PathBuf,_:&mut Window,_:&mut Context<Self>){panic!("not exercised")}
 fn open_catalog_subagent(&mut self,_:&ChatKey,_:&mut Window,_:&mut Context<Self>)->bool{false}
 fn show_external_tab(&mut self,_:&str,_:&mut Context<Self>)->bool{false}
 fn select_chat_space(&mut self,key:&ChatKey,_:&mut Context<Self>)->bool{let root=key.tab_id();let changed=self.spaces.active_root()!=Some(root.as_str());self.spaces.save_active(self.layout.clone());self.spaces.select(&root);self.layout=self.spaces.active_layout().clone();changed}
 fn ensure_chat(&mut self,key:ChatKey,_:&mut Window,_:&mut Context<Self>){self.resumed.push((key,None))}
 fn resume_key(&mut self,key:ChatKey,open:Option<OpenDocument>,_:&mut Window,_:&mut Context<Self>){self.resumed.push((key,open))}
 fn show_tab(&mut self,id:&str,open:OpenDocument,_:&mut Window,_:&mut Context<Self>){if open.preview{self.layout.open_preview(id, |_|false)}else{self.layout.open(id, |_|false)};if open.focus{self.focus_calls.push(id.into())}}
 fn focus_active(&mut self,_:&mut Window,_:&mut Context<Self>){if let Some(id)=self.layout.active(self.layout.focused){if !tabs::is_chat(id)||self.chats.contains_key(id){self.focus_calls.push(id.into())}}}
 fn sync_chats(&mut self,_:&TabLayout,_:&mut Context<Self>){}
 fn focus_active_chat(&self,_:&mut Window,cx:&mut Context<Self>){cx.focused_chat.set(true)}
 fn tab_layout(&self,_:&Context<Self>)->TabLayout{self.layout.clone()}
 fn remove_space_chats(&mut self,ids:&HashSet<String>,_:&mut Context<Self>){self.spaces.remove_chats(ids.iter().map(String::as_str));self.chats.retain(|id,_|!ids.contains(id));self.layout=self.spaces.active_layout().clone()}
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
pub fn invalidate_navigation(&mut self) {
        self.navigation_generation = self.navigation_generation.wrapping_add(1);
        self.creating_chat = None;
    }
pub fn open_chat(
        &mut self,
        key: ChatKey,
        open: OpenDocument,
        window: &mut Window,
        cx: &mut Context<Self>,
    ) {
        if !self.begin_navigation(cx) {
            return;
        }
        if self.deleting_sessions.contains(&key) {
            return;
        }
        if self.open_catalog_subagent(&key, window, cx) {
            return;
        }
        self.creating_chat = None;
        let id = key.tab_id();
        if self.show_external_tab(&id, cx) {
            return;
        }
        let switched = self.select_chat_space(&key, cx);
        if let Some(root) = self.spaces.active_root().and_then(tabs::chat_key)
            && root != key
            && !self.chats.contains_key(&root.tab_id())
        {
            self.ensure_chat(root, window, cx);
        }
        // Re-entering an area restores its document/pane focus. A click on
        // the already displayed root still returns directly to that chat.
        if switched && self.spaces.active_root() == Some(id.as_str()) {
            if !self.layout.contains(&id) {
                self.show_tab(
                    &id,
                    OpenDocument {
                        preview: false,
                        focus: open.focus,
                    },
                    window,
                    cx,
                );
            }
            if !self.chats.contains_key(&id) {
                self.resume_key(key, None, window, cx);
            }
            self.focus_active(window, cx);
            return;
        }
        if self.chats.contains_key(&id) {
            self.show_tab(&id, open, window, cx);
            return;
        }
        // Selection belongs to the click, never to the order of RPC replies.
        // The shared pane already renders an unloaded chat as a loading page.
        self.show_tab(&id, open, window, cx);
        self.resume_key(key, Some(open), window, cx);
    }
pub fn select_session(
        &mut self,
        key: ChatKey,
        clicks: usize,
        window: &mut Window,
        cx: &mut Context<Self>,
    ) {
        let keep = clicks > 1;
        let open = OpenDocument {
            preview: !keep,
            focus: keep,
        };
        self.open_chat(key, open, window, cx);
    }
fn finish_chat_resume(
        &mut self,
        id: &str,
        open: Option<OpenDocument>,
        window: &mut Window,
        cx: &mut Context<Self>,
    ) {
        let layout = self.tab_layout(cx);
        self.sync_chats(&layout, cx);
        cx.emit(HostEvent::ContextChanged);
        if pending::may_focus(
            &layout,
            id,
            self.settings.is_some(),
            open.is_none_or(|open| open.focus),
        ) {
            self.focus_active_chat(window, cx);
        }
        cx.notify();
    }
pub fn forget_chats(
        &mut self,
        keys: &std::collections::HashSet<ChatKey>,
        window: &mut Window,
        cx: &mut Context<Self>,
    ) {
        self.session_catalog_epoch = self.session_catalog_epoch.wrapping_add(1);
        self.deleting_sessions.retain(|key| !keys.contains(key));
        let layout = self.tab_layout(cx);
        let was_active = self
            .spaces
            .active_root()
            .and_then(tabs::chat_key)
            .is_some_and(|key| keys.contains(&key))
            || layout
                .active(layout.focused)
                .and_then(tabs::chat_key)
                .is_some_and(|key| keys.contains(&key));
        self.sessions.retain(|summary| !keys.contains(&summary.key));
        self.opening
            .retain(|id, _| tabs::chat_key(id).is_none_or(|key| !keys.contains(&key)));
        let ids = keys.iter().map(ChatKey::tab_id).collect();
        self.remove_space_chats(&ids, cx);
        if was_active && self.settings.is_none() {
            self.focus_active(window, cx);
        }
        cx.notify();
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
mod pending { use super::*; pub fn may_focus(
    layout: &TabLayout,
    id: &str,
    settings_open: bool,
    requested: bool,
) -> bool {
    requested && !settings_open && layout.active(layout.focused) == Some(id)
}
}
#[cfg(test)]mod audit {
 use super::*;
 fn project()->PathBuf {PathBuf::from(env!("CARGO_MANIFEST_DIR")).canonicalize().unwrap()}
 fn row(key:ChatKey)->ConversationSummary{ConversationSummary{key,parent:None,workspace_path:project(),updated_at_ms:Some(1)}}
 fn ctx(agent:AgentKind)->Context<Workspace>{Context{prefs:Prefs{preferred_agent:agent,..Default::default()},focused_chat:Default::default(),_type:PhantomData}}
 fn race(agent:AgentKind)->Workspace{
  let mut w=Workspace::default();let mut cx=ctx(agent);
  let key=match agent{AgentKind::Proteus=>ChatKey::Proteus("/synthetic/deleted".into()),AgentKind::Codex=>ChatKey::Codex("deleted".into())};
  w.core_snapshot.push(proteus_contracts::app_protocol::AppSessionSummary{session_dir:"/synthetic/deleted".into(),workspace_path:project()});w.codex_snapshot.push(row(key.clone()));
  // Capture the old successful read, holding only its UI completion.
  w.open_project(project(),&mut Window,&mut cx);assert_eq!(w.pending.len(),1);
  // A later explicit destination invalidates selection. Successful deletion
  // reaches the actual production acknowledgement cleanup in this window.
  w.invalidate_navigation();w.forget_chats(&HashSet::from([key.clone()]),&mut Window,&mut cx);
  // The fresh post-delete catalog has already arrived before the delayed callback.
  w.set_sessions(Vec::new(),&mut cx);assert!(w.sessions.is_empty());let epoch=w.session_catalog_epoch;
  w.reply(&mut cx);assert_eq!(w.session_catalog_epoch,epoch);
  assert!(w.resumed.is_empty(),"selection guard correctly rejects stale navigation");w
 }
 #[test]fn observe_core_old_project_catalog_resurrects_deleted_row(){let w=race(AgentKind::Proteus);assert_eq!(w.sessions.len(),1);assert_eq!(w.sessions[0].key,ChatKey::Proteus("/synthetic/deleted".into()));}
 #[test]fn observe_codex_old_project_catalog_resurrects_deleted_row(){let w=race(AgentKind::Codex);assert_eq!(w.sessions.len(),1);assert_eq!(w.sessions[0].key,ChatKey::Codex("deleted".into()));}
 #[test]#[ignore]fn regression_core_deleted_row_must_stay_absent(){assert!(race(AgentKind::Proteus).sessions.is_empty())}
 #[test]#[ignore]fn regression_codex_deleted_row_must_stay_absent(){assert!(race(AgentKind::Codex).sessions.is_empty())}
 fn focus_fixture()->Workspace{
  let mut w=Workspace::default();w.spaces.select("codex:target");let mut target=w.spaces.active_layout().clone();target.open("files:README.md", |_|false);w.spaces.save_active(target);
  w.spaces.select("codex:current");w.layout=w.spaces.active_layout().clone();w.chats.insert("codex:target".into(),());w.chats.insert("codex:current".into(),());w
 }
 #[test]fn observe_single_click_other_area_requests_document_focus(){let mut w=focus_fixture();w.select_session(ChatKey::Codex("target".into()),1,&mut Window,&mut ctx(AgentKind::Codex));assert_eq!(w.focus_calls,["files:README.md"])}
 #[test]fn control_single_click_same_area_does_not_request_focus(){let mut w=focus_fixture();w.select_session(ChatKey::Codex("current".into()),1,&mut Window,&mut ctx(AgentKind::Codex));assert!(w.focus_calls.is_empty())}
 #[test]fn control_double_click_other_area_does_request_focus(){let mut w=focus_fixture();w.select_session(ChatKey::Codex("target".into()),2,&mut Window,&mut ctx(AgentKind::Codex));assert_eq!(w.focus_calls,["files:README.md"])}
 fn delayed_focus()->bool {
  let mut w=Workspace::default();w.spaces.select("codex:current");w.layout=w.spaces.active_layout().clone();let mut cx=ctx(AgentKind::Codex);
  w.select_session(ChatKey::Codex("unloaded".into()),1,&mut Window,&mut cx);assert_eq!(w.resumed.len(),1);let (key,open)=w.resumed.remove(0);w.chats.insert(key.tab_id(),());
  w.finish_chat_resume(&key.tab_id(),open,&mut Window,&mut cx);cx.focused_chat.get()
 }
 #[test]fn observe_unloaded_single_click_defaults_resume_to_focus(){assert!(delayed_focus())}
 #[test]#[ignore]fn regression_unloaded_single_click_must_retain_list_focus(){assert!(!delayed_focus())}
 #[test]#[ignore]fn regression_single_click_other_area_must_retain_list_focus(){let mut w=focus_fixture();w.select_session(ChatKey::Codex("target".into()),1,&mut Window,&mut ctx(AgentKind::Codex));assert!(w.focus_calls.is_empty())}
}
