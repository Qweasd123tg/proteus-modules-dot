from pathlib import Path
import json,hashlib
root=Path(__file__).resolve().parent/"source";out=Path(__file__).resolve().parent;rec=[]
def block(s,a):
 b=s.index('{',a);d=1;e=b+1
 while d:d+=(s[e]=='{')-(s[e]=='}');e+=1
 return b,e

def extract(path,name):
 s=(root/path).read_text();a=s.index('fn '+name+'(');a=s.rfind('\n',0,a)+1;b,e=block(s,a);raw=s[a:e].strip();record(path,name,s,a,e,raw);return raw.replace('pub(super) ','pub ').replace('pub(in crate::ui) ','pub ')
def record(path,name,s,a,e,raw):rec.append(dict(path=path,name=name,start=s[:a].count('\n')+1,end=s[:e].count('\n')+1,sha256=hashlib.sha256(raw.encode()).hexdigest()))
def callback(path,fn,start):
 s=(root/path).read_text();a=s.index(start,s.index('fn '+fn));b,e=block(s,a);raw=s[b+1:e-1];record(path,fn+' UI result callback',s,b+1,e-1,raw);return raw
call=callback('src/ui/workspace.rs','call<','this.update(cx, |this, cx| {')
call_in=callback('src/ui/workspace.rs','call_in<','this.update_in(cx, |this, window, cx| {')
stop=callback('src/ui/workspace/windows.rs','server_stopped','view.update(cx, |this, cx| {')
methods='\n'.join(extract(p,n) for p,n in [('src/ui/chats.rs','resume_chat'),('src/ui/chats.rs','refresh_sessions'),('src/ui/chats.rs','set_sessions'),('src/ui/workspace/drivers.rs','fail_openings')])
header=r'''
use super::{OpenDocument,Window};
use std::{cell::{Cell,RefCell},rc::Rc,path::{Path,PathBuf},collections::{HashMap,HashSet},time::Instant,marker::PhantomData};
use proteus_tabs as tabs;
use tabs::{TabLayout,ChatSpaces,ChatKey};
use crate::{pending,conversations,proteus_contracts};
use conversations::AgentKind;
#[derive(Clone,Copy,Debug,PartialEq)]enum Status{Ready}
#[derive(Default)]struct Context<T>{_marker:PhantomData<T>}
impl<T> Context<T>{fn notify(&mut self){}fn emit(&mut self,_:HostEvent){}fn default_global<U:Default>(&self)->U{U::default()}}
enum HostEvent{ContextChanged}
#[derive(Clone)]struct Api {id:u64,calls:Rc<Cell<usize>>}
impl Api{fn connection_id(&self)->u64{self.id}fn resume(&self,dir:&Path)->anyhow::Result<Opened>{self.calls.set(self.calls.get()+1);Ok(Opened{session_dir:dir.into(),workspace_path:"/project".into()})}fn sessions(&self)->anyhow::Result<Vec<crate::proteus_contracts::app_protocol::AppSessionSummary>>{self.calls.set(self.calls.get()+1);Ok(vec![])}}
struct Opened{session_dir:PathBuf,workspace_path:PathBuf}
#[derive(Clone)]struct Group{current:Rc<Cell<Option<u64>>>}
impl Group{fn has_core_connection(&self,id:u64)->bool{self.current.get()==Some(id)}fn watch_backend(&self,_:u64,_:(),_:&mut Context<Workspace>) {}}
type Callback=Box<dyn FnOnce(&mut Workspace,&mut Window,&mut Context<Workspace>)>;
struct Workspace{
 api:Option<Api>,windows:Group,status:Status,notice:Option<String>,opening:HashMap<String,Rc<Cell<Option<OpenDocument>>>>,
 spaces:ChatSpaces,layout:TabLayout,chats:HashMap<String,()>,session_projects:HashMap<PathBuf,PathBuf>,
 deleting_sessions:HashSet<ChatKey>,session_catalog_epoch:u64,sessions_loading:bool,sessions_stale:bool,sessions_arrived:Option<Instant>,
 sessions:Vec<conversations::ConversationSummary>,callbacks:Vec<Callback>,calls:Rc<Cell<usize>>,
}
impl Workspace{
 fn fixture()->Self{let mut spaces=ChatSpaces::default();spaces.select("chat:/synthetic/a");let calls=Rc::new(Cell::new(0));Self{api:Some(Api{id:1,calls:calls.clone()}),windows:Group{current:Rc::new(Cell::new(Some(1)))},status:Status::Ready,notice:None,opening:HashMap::new(),layout:spaces.active_layout().clone(),spaces,chats:HashMap::new(),session_projects:HashMap::new(),deleting_sessions:HashSet::new(),session_catalog_epoch:0,sessions_loading:false,sessions_stale:false,sessions_arrived:None,sessions:vec![],callbacks:vec![],calls}}
 fn api(&self)->Option<Api>{self.api.clone()}
 fn reply(&mut self){let cb=self.callbacks.remove(0);cb(self,&mut Window,&mut Context{_marker:PhantomData});}
 fn insert_chat(&mut self,dir:PathBuf,_:&mut Window,_:&mut Context<Self>)->String{let id=tabs::chat(&dir);self.chats.insert(id.clone(),());id}
 fn finish_chat_resume(&mut self,_:&str,_:Option<OpenDocument>,_:&mut Window,_:&mut Context<Self>){}
 fn fail_chat_resume(&mut self,id:&str,msg:String,_:&mut Context<Self>){self.spaces.extract_chat(id);self.layout=self.spaces.active_layout().clone();self.notice=Some(msg)}
 fn report(&mut self,msg:String,_:&mut Context<Self>){self.notice=Some(msg)}
 fn update_tabs(&mut self,_:&mut Context<Self>,change:impl FnOnce(&mut TabLayout)){change(&mut self.layout);self.spaces.save_active(self.layout.clone());}
 fn reconnect(&mut self){self.windows.current.set(Some(2));self.api=Some(Api{id:2,calls:self.calls.clone()});}
 fn stop(&mut self){
  // This models the real shared-slot retirement just above the production
  // per-workspace closure. No real backend is started or terminated.
  let connection=1;let report="synthetic exit";self.windows.current.set(None);
  let this=self;let cx=&mut Context::<Workspace>{_marker:PhantomData};
'''
wrappers='''\n}\nfn call<R:Send+'static>(&mut self,_:&mut Context<Self>,job:impl FnOnce(&Api)->anyhow::Result<R>+Send+'static,done:impl FnOnce(&mut Self,R,&mut Context<Self>)+'static){
 let api=self.api.clone().unwrap();let value=job(&api);let exited:Option<()>=None;
 self.callbacks.push(Box::new(move |this,_window,cx|{let result: anyhow::Result<_>=Ok((api,exited,value));
'''+call+'''}));
}
fn call_in<R:Send+'static>(&mut self,_:&mut Window,_:&mut Context<Self>,job:impl FnOnce(&Api)->anyhow::Result<R>+Send+'static,done:impl FnOnce(&mut Self,R,&mut Window,&mut Context<Self>)+'static){
 let api=self.api.clone().unwrap();let value=job(&api);let exited:Option<()>=None;
 self.callbacks.push(Box::new(move |this,window,cx|{let result:anyhow::Result<_>=Ok((api,exited,value));
'''+call_in+'''}));
}
'''
tests=r'''
}
#[cfg(test)]mod audit{
 use super::*;
 fn start(w:&mut Workspace){w.resume_chat("/synthetic/a".into(),None,&mut Window,&mut Context{_marker:PhantomData});}
 fn stopped_resume()->Workspace{
  let mut w=Workspace::fixture();start(&mut w);assert_eq!(w.calls.get(),1);assert_eq!(w.callbacks.len(),1);
  w.stop();assert!(w.api.is_none());w.reply();assert!(w.callbacks.is_empty());assert!(w.chats.is_empty());
  w.reconnect();for _ in 0..5 {start(&mut w)}
  eprintln!("Core retired completion: opening={}, chats={}, attempted resume requests={}, queued={}",w.opening.len(),w.chats.len(),w.calls.get(),w.callbacks.len());w
 }
 #[test]fn observe_retired_core_resume_leaves_unretriable_opening(){let w=stopped_resume();assert!(w.opening.contains_key("chat:/synthetic/a"));assert_eq!(w.calls.get(),1);assert!(w.chats.is_empty());assert!(w.callbacks.is_empty());}
 #[test]#[ignore]fn regression_retired_core_resume_must_allow_retry(){let w=stopped_resume();assert!(w.calls.get()>1,"new connection must not reuse an unconsumable old opening ticket");}
 fn stopped_catalog()->Workspace{
  let mut w=Workspace::fixture();w.refresh_sessions(&mut Context{_marker:PhantomData});assert!(w.sessions_loading);assert_eq!(w.calls.get(),1);w.stop();w.reply();w.reconnect();for _ in 0..5{w.refresh_sessions(&mut Context{_marker:PhantomData});}
  eprintln!("Core retired catalog: loading={}, stale={}, requests={}, queued={}",w.sessions_loading,w.sessions_stale,w.calls.get(),w.callbacks.len());w
 }
 #[test]fn observe_retired_core_catalog_never_releases_loading(){let w=stopped_catalog();assert!(w.sessions_loading&&w.sessions_stale);assert_eq!(w.calls.get(),1);assert!(w.callbacks.is_empty());}
 #[test]#[ignore]fn regression_retired_catalog_must_allow_refresh(){let w=stopped_catalog();assert!(w.calls.get()>1,"new connection cannot keep coalescing into an abandoned old catalog request");}
 #[test]fn control_live_core_reply_resumes_and_releases_ticket(){let mut w=Workspace::fixture();start(&mut w);w.reply();assert!(w.chats.contains_key("chat:/synthetic/a"));assert!(w.opening.is_empty());}
 #[test]fn control_live_catalog_reply_allows_next_refresh(){let mut w=Workspace::fixture();w.refresh_sessions(&mut Context{_marker:PhantomData});w.reply();assert!(!w.sessions_loading);w.refresh_sessions(&mut Context{_marker:PhantomData});assert_eq!(w.calls.get(),2);}
 #[test]fn control_explicit_opening_failure_releases_ticket(){let mut w=Workspace::fixture();start(&mut w);w.fail_openings(AgentKind::Proteus,&mut Context{_marker:PhantomData});assert!(w.opening.is_empty());}
}
'''
(out/'probe/src/core_guard.rs').write_text(header+stop+wrappers+methods+tests)
(out/'core-extraction.json').write_text(json.dumps(rec,indent=2)+'\n')
