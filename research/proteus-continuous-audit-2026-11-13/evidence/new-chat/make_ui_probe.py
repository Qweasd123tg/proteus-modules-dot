from pathlib import Path
import hashlib
src=Path('/workspace/scratch/3ba0fff8d310/desktop-behaviour/src/ui/projects.rs').read_text()
start=src.index('    pub(super) fn new_chat_in(')
end=src.index('\n    /// Opens a new session',start)
method=src[start:end]
# Change visibility only because this is a crate-root isolated probe, otherwise verbatim.
method=method.replace('pub(super) fn new_chat_in','pub fn new_chat_in',1)
stubs=r'''
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
'''
tests=r'''
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
      let expected=if project==launch{None}else{Some(source.clone())};
      assert_eq!(ws.requested.unwrap().0,expected);
    }
}
'''
out=Path('/workspace/shared/ui-workflows-round6/evidence');(out/'ui_probe.rs').write_text(stubs+method+tests)
(out/'ui-extraction.txt').write_text(f'projects.rs source sha256={hashlib.sha256(src.encode()).hexdigest()}\nExtracted complete new_chat_in method; visibility changed pub(super) to pub at crate root. GPUI/rendering, active blank chat, and RPC transport stubbed; method selection, source filtering, and canonicalization are actual Desktop source.\n')
