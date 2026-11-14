
#![allow(dead_code)]
use std::path::{Path,PathBuf};
use std::marker::PhantomData;
struct Window;
struct Context<T>(PhantomData<T>);
#[derive(Copy,Clone,PartialEq)] enum AgentKind {Proteus,Codex}
#[derive(Clone)] enum ChatKey {Proteus(PathBuf),Codex}
impl ChatKey {fn proteus_dir(&self)->Option<&Path>{match self{Self::Proteus(p)=>Some(p),_=>None}}}
impl AgentKind {fn for_key(k:&ChatKey)->Self {match k{ChatKey::Proteus(_)=>Self::Proteus,_=>Self::Codex}}}
struct Chat;
impl Chat {fn is_blank(&self,_:&Context<Workspace>)->bool{false}}
struct Entity(Chat);
impl Entity {fn read(&self,_:&Context<Workspace>)->&Chat{&self.0} fn entity_id(&self)->u64{0}}
struct Summary {workspace_path:PathBuf,parent:Option<ChatKey>,key:ChatKey,updated_at_ms:Option<u64>}
struct Recent;
impl Recent {fn forget(&mut self,_:&Path){} fn touch(&mut self,_:&Path){}}
struct Prefs{recent:Recent,preferred_agent:AgentKind}
mod prefs {use super::*;pub fn current(_:&Context<Workspace>)->Prefs{Prefs{recent:Recent,preferred_agent:AgentKind::Proteus}} pub fn update(cx:&mut Context<Workspace>,f:impl FnOnce(&mut Prefs)){f(&mut current(cx));}}
struct Workspace {workspace_path:PathBuf,sessions:Vec<Summary>,requested:Option<(Option<PathBuf>,Option<PathBuf>)>}
impl Workspace {
fn begin_navigation(&mut self,_:&mut Context<Self>)->bool{true}
fn active_chat_view(&self)->Option<&Entity>{None}
fn active_chat_key(&self)->Option<ChatKey>{None}
fn chat_project(&self,_:u64)->PathBuf{panic!("no active blank chat")}
fn report(&self,msg:String,_:&mut Context<Self>){panic!("{msg}")}
fn focus_active_chat(&self,_:&mut Window,_:&mut Context<Self>){panic!("no active blank chat")}
fn new_codex(&self,_:PathBuf,_:Option<()>,_:&mut Window,_:&mut Context<Self>){panic!("Proteus only")}
fn start_chat(&mut self,source:Option<PathBuf>,workspace:Option<PathBuf>,_:&mut Window,_:&mut Context<Self>){self.requested=Some((source,workspace));}
    pub fn new_chat_in(
        &mut self,
        project: PathBuf,
        window: &mut Window,
        cx: &mut Context<Self>,
    ) {
        if !self.begin_navigation(cx) {
            return;
        }
        let project = match project.canonicalize() {
            Ok(path) if path.is_dir() => path,
            _ => {
                prefs::update(cx, |prefs| prefs.recent.forget(&project));
                let message = format!("Папка недоступна: {}", project.display());
                return self.report(message, cx);
            }
        };
        prefs::update(cx, |prefs| prefs.recent.touch(&project));
        let agent = prefs::current(cx).preferred_agent;
        let blank = self.active_chat_view().and_then(|chat| {
            let key = self.active_chat_key()?;
            (AgentKind::for_key(&key) == agent && chat.read(cx).is_blank(cx))
                .then(|| (chat.entity_id(), key))
        });
        if let Some((chat, _)) = &blank
            && self.chat_project(*chat) == project
        {
            return self.focus_active_chat(window, cx);
        }
        if agent == AgentKind::Codex {
            return self.new_codex(project, None, window, cx);
        }
        if project == self.workspace_path {
            return self.start_chat(None, None, window, cx);
        }
        let source = self
            .sessions
            .iter()
            .filter(|summary| {
                summary.workspace_path == project
                    && summary.parent.is_none()
                    && matches!(summary.key, ChatKey::Proteus(_))
            })
            .max_by_key(|summary| summary.updated_at_ms)
            .and_then(|summary| summary.key.proteus_dir().map(Path::to_path_buf));
        self.start_chat(source, Some(project), window, cx)
    }

}
#[test]
fn actual_desktop_method_omits_latest_source_only_in_launch_project(){
    let base=PathBuf::from(env!("CARGO_MANIFEST_DIR"));
    let launch=base.join("fixtures/launch");
    let other=base.join("fixtures/other");
    std::fs::create_dir_all(&launch).unwrap();std::fs::create_dir_all(&other).unwrap();
    let launch=launch.canonicalize().unwrap();let other=other.canonicalize().unwrap();
    let source=PathBuf::from("/synthetic/last-session");
    for project in [launch.clone(),other.clone()] {
      let mut ws=Workspace{workspace_path:launch.clone(),sessions:vec![Summary{workspace_path:project.clone(),parent:None,key:ChatKey::Proteus(source.clone()),updated_at_ms:Some(100)}],requested:None};
      ws.new_chat_in(project.clone(),&mut Window,&mut Context(PhantomData));
      println!("project={} source={:?}",project.display(),ws.requested.as_ref().unwrap().0);
      let expected=Some(source.clone());
      assert_eq!(ws.requested.unwrap().0,expected);
    }
}
