#![allow(dead_code)]
use std::path::{Path,PathBuf};
use std::marker::PhantomData;
use proteus_tabs::{TabLayout,ChatKey,Edge,PaneId};
struct Window;
struct Context<T>(PhantomData<T>);
#[derive(Clone,Copy,PartialEq)] enum AgentKind { Proteus,Codex }
impl AgentKind { fn for_key(key:&ChatKey)->Self {match key{ChatKey::Proteus(_)=>Self::Proteus,ChatKey::Codex(_)=>Self::Codex}} }
struct ConversationSummary { key:ChatKey, parent:Option<ChatKey>,workspace_path:PathBuf,updated_at_ms:Option<u64> }
#[derive(Default)] struct Workspace {
 layout:TabLayout,settings:Option<()>,navigation_generation:u64,creating_chat:Option<()>,sessions:Vec<ConversationSummary>,opened:Vec<ChatKey>, focused:Option<String>
}
fn project_open() {}
impl Workspace {
 fn update_tabs(&mut self,_:&mut Context<Self>,change:impl FnOnce(&mut TabLayout)){change(&mut self.layout)}
 fn focus_tab(&mut self,id:&str,_:&mut Window,_:&mut Context<Self>){self.focused=Some(id.into())}
 fn open_chat(&mut self,key:ChatKey,_:(),_:&mut Window,_:&mut Context<Self>){self.layout.open(&key.tab_id(), |_|false);self.opened.push(key)}
 fn new_codex(&mut self,_:PathBuf,_:Option<()>,_:&mut Window,_:&mut Context<Self>){panic!("fixture must choose existing target")}
 fn new_chat_in(&mut self,_:PathBuf,_:&mut Window,_:&mut Context<Self>){panic!("fixture must choose existing target")}
pub fn step_tab(&mut self, offset: isize, window: &mut Window, cx: &mut Context<Self>) {
        if self.settings.is_some() {
            return;
        }
        let mut next = None;
        self.update_tabs(cx, |tabs| next = tabs.step(offset));
        if let Some(id) = next {
            self.focus_tab(&id, window, cx);
        }
    }
pub fn focus_neighbor(
        &mut self,
        edge: Edge,
        window: &mut Window,
        cx: &mut Context<Self>,
    ) {
        if self.settings.is_some() {
            return;
        }
        let mut next = None;
        self.update_tabs(cx, |tabs| next = tabs.focus_neighbor(edge));
        if let Some(id) = next {
            self.focus_tab(&id, window, cx);
        }
    }
pub fn focus_pane(&mut self, pane: PaneId, cx: &mut Context<Self>) {
        if self.layout.focused != pane {
            self.update_tabs(cx, |tabs| tabs.focus(pane));
        }
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
pub fn invalidate_navigation(&mut self) {
        self.navigation_generation = self.navigation_generation.wrapping_add(1);
        self.creating_chat = None;
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
#[cfg(test)] mod audit {
 use super::*;
 fn fixture(split:bool)->Workspace {
  let mut w=Workspace::default();
  w.layout.open("codex:a", |_|false);w.layout.open("codex:b", |_|false);
  if split {w.layout.split("codex:b",w.layout.pane_of("codex:a").unwrap(),Edge::Right)}
  let p=w.layout.pane_of("codex:a").unwrap(); w.layout.activate(p,"codex:a");
  w.sessions.push(ConversationSummary{key:ChatKey::Codex("delayed-project".into()),parent:None,workspace_path:"/pending-project".into(),updated_at_ms:Some(1)});
  w.navigation_generation=5;w
 }
 fn late(w:&mut Workspace,generation:u64){w.finish_project_navigation("/pending-project".into(),AgentKind::Codex,generation,&mut Window,&mut Context(PhantomData))}
 #[test]fn late_project_must_not_override_keyboard_tab_switch(){
  let mut w=fixture(false);let generation=w.navigation_generation;
  w.step_tab(1,&mut Window,&mut Context(PhantomData));
  assert_eq!(w.layout.active(w.layout.focused),Some("codex:b"));late(&mut w,generation);
  assert!(w.opened.is_empty(),"late callback accepted after tab switch: {:?}",w.opened);
 }
 #[test]fn late_project_must_not_override_keyboard_pane_switch(){
  let mut w=fixture(true);let generation=w.navigation_generation;
  w.focus_neighbor(Edge::Right,&mut Window,&mut Context(PhantomData));
  assert_eq!(w.layout.active(w.layout.focused),Some("codex:b"));late(&mut w,generation);
  assert!(w.opened.is_empty(),"late callback accepted after pane switch: {:?}",w.opened);
 }
 #[test]fn late_project_must_not_override_mouse_pane_switch(){
  let mut w=fixture(true);let generation=w.navigation_generation;
  w.focus_pane(w.layout.pane_of("codex:b").unwrap(),&mut Context(PhantomData));
  assert_eq!(w.layout.active(w.layout.focused),Some("codex:b"));late(&mut w,generation);
  assert!(w.opened.is_empty(),"late callback accepted after pane click: {:?}",w.opened);
 }
 #[test]fn explicit_invalidation_control_rejects_late_callback(){
  let mut w=fixture(false);let generation=w.navigation_generation;
  w.invalidate_navigation();late(&mut w,generation);assert!(w.opened.is_empty());
 }
}
