from pathlib import Path
import hashlib,json
root=Path(__file__).resolve().parents[1]
records=[]
def extract(path,name):
 text=(root/path).read_text(); start=text.index('fn '+name+'('); start=text.rfind('\n',0,start)+1
 brace=text.index('{',start); depth=1; i=brace+1
 while depth:
  depth += (text[i]=='{') - (text[i]=='}');i+=1
 code=text[start:i].strip()
 records.append(dict(file=path,function=name,start_line=text[:start].count('\n')+1,end_line=text[:i].count('\n')+1,sha256=hashlib.sha256(code.encode()).hexdigest()))
 return code.replace('pub(super) ', 'pub ').replace('pub(in crate::ui) ', 'pub ')
methods='\n'.join(extract(path,name)for path,name in [
 ('src/ui/tabs/mod.rs','step_tab'),('src/ui/tabs/mod.rs','focus_neighbor'),('src/ui/tabs/mod.rs','focus_pane'),
 ('src/ui/projects.rs','finish_project_navigation'),('src/ui/actions.rs','invalidate_navigation')])
helper=extract('src/ui/projects.rs','latest_main_session')
header='''#![allow(dead_code)]
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
'''
footer='''
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
'''
(root/'audit-round5/probe/src/lib.rs').write_text(header+methods+'\n}\n'+helper+footer)
(root/'audit-round5/navigation-extraction.json').write_text(json.dumps(records,indent=2)+'\n')
