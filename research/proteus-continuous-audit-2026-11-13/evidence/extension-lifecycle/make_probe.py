#!/usr/bin/env python3
"""Compile exact lifecycle methods with inert GPUI entities, no process/UI/network."""
import hashlib,json,pathlib,subprocess,sys
root=pathlib.Path(sys.argv[1]).resolve(); here=pathlib.Path(__file__).resolve().parent
sha=subprocess.check_output(['git','-C',str(root),'rev-parse','HEAD'],text=True).strip()
records=[]
def extract(path,marker):
 s=subprocess.check_output(['git','-C',str(root),'show','HEAD:'+path],text=True)
 start=s.index(marker); end=s.index('{',start)+1; level=1
 while level:
  level+=(s[end]=='{')-(s[end]=='}'); end+=1
 code=s[start:end]
 records.append(dict(path=path,start_line=s[:start].count('\n')+1,end_line=s[:end].count('\n')+1,sha256=hashlib.sha256(code.encode()).hexdigest()))
 return code
host=extract('src/ui/extensions/host.rs','    pub(in crate::ui) fn subscribe_session')
p='src/ui/extensions/declarative/runtime/scopes.rs'
ensure=extract(p,'    pub(super) fn ensure_scope(')
event=extract(p,'    fn scope_event(')
update=extract(p,'fn workspace_update(')
shim=r'''
#![allow(dead_code,unused_variables)]
use std::{cell::RefCell,collections::HashMap,marker::PhantomData,ops::Deref,path::PathBuf,rc::Rc};
#[derive(Default)]struct App;
struct Context<T>{app:App,subscriptions:usize,callbacks:Vec<Box<dyn FnMut(&mut T,&dyn std::any::Any,&mut Context<T>)>>,_t:PhantomData<T>}
impl<T> Default for Context<T>{fn default()->Self{Self{app:App,subscriptions:0,callbacks:Vec::new(),_t:PhantomData}}}
impl<T> Deref for Context<T>{type Target=App;fn deref(&self)->&App{&self.app}}
impl<T:'static> Context<T>{
 fn subscribe<U:'static,E:'static>(&mut self,_:&Entity<U>,mut callback:impl FnMut(&mut T,Entity<U>,&E,&mut Context<T>)+'static)->Subscription{self.subscriptions+=1;self.callbacks.push(Box::new(move |this,event,cx|{if let Some(event)=event.downcast_ref::<E>(){callback(this,Entity(PhantomData),event,cx)}}));Subscription}
 fn emit(&mut self,this:&mut T,event:impl std::any::Any){let mut callbacks=std::mem::take(&mut self.callbacks);for callback in &mut callbacks{callback(this,&event,self)}self.callbacks=callbacks;}
}
struct Subscription;
struct Entity<T>(PhantomData<T>);
struct WeakEntity<T>(PhantomData<T>);
impl<T> Clone for WeakEntity<T>{fn clone(&self)->Self{Self(PhantomData)}}
impl<T> WeakEntity<T>{fn upgrade(&self)->Option<Entity<T>>{Some(Entity(PhantomData))}}
#[derive(Clone,Copy)]struct AnyWindowHandle;
#[derive(Clone,Copy,Debug,PartialEq)]enum Lifetime{Workspace,Preview}
impl Lifetime{fn session(self)->bool{self==Self::Workspace}}
#[derive(Clone)]struct RuntimeScope{lifetime:Lifetime}
#[derive(Clone,Copy,Debug,PartialEq)]enum HostEvent{ContextChanged,SessionOpened,RunSettled,NavigationChanged}
#[derive(Clone,Copy,Debug,PartialEq)]enum HostEventKind{SessionOpened,RunSettled,NavigationChanged}
#[derive(Clone,Debug)]enum Outgoing{
 Context{context:String,workspace:PathBuf,session_dir:Option<PathBuf>},
 Event{context:String,event:HostEventKind,session_dir:Option<PathBuf>,document:Option<String>},
 SessionUpdate{context:String,session_dir:PathBuf,update:()},
}
struct Chat;struct Workspace;
#[derive(Default)]struct Queue;
impl Queue{fn reset(&mut self){}}
struct Attached{context:String,queue:Queue}
struct Manifest;
impl Manifest{fn accepts_session_update(&self,_:&())->bool{true}}
struct Installed{manifest:Manifest}
#[derive(Default)]struct EventCursor;
impl EventCursor{fn admit(&mut self,_:u64)->bool{true}}
mod tabs{pub type ChatKey=String;}
mod ui{pub mod extensions{
 use super::super::*;
 pub mod session{use super::*;pub struct SessionChanged{pub event_id:u64,pub session_dir:PathBuf,pub update:()}}
 pub mod host{
  use super::*;
  #[derive(Clone)]pub struct Host{
   runtime_scope:RuntimeScope,workspace:WeakEntity<Workspace>,
   session:Rc<RefCell<Option<PathBuf>>>,folder:Rc<RefCell<Option<PathBuf>>>,context:String,
  }
  impl Host{
   fn session_dir(&self,_:&App)->Option<PathBuf>{self.session.borrow().clone()}
   fn supports_core(&self,cx:&App)->bool{self.session_dir(cx).is_some()}
   fn scope(&self)->String{self.context.clone()}
   fn workspace_path(&self,_:&App)->Option<PathBuf>{self.folder.borrow().clone()}
   fn active_document(&self,_:&App)->Option<String>{None}
   fn session_source(&self,_:&App)->Option<(WeakEntity<Chat>,crate::tabs::ChatKey)>{None}
   fn inherit(&mut self,_:Option<(WeakEntity<Chat>,crate::tabs::ChatKey)>){ }
   fn subscribe<T:'static>(&self,cx:&mut Context<T>,_:impl FnMut(&mut T,HostEvent,&mut Context<T>)+'static)->Option<Subscription>{cx.subscriptions+=1;Some(Subscription)}
'''
mid=r'''
  }
  pub fn host(session:Option<&str>,folder:Option<&str>)->Host{
   Host{runtime_scope:RuntimeScope{lifetime:Lifetime::Workspace},workspace:WeakEntity(PhantomData),session:Rc::new(RefCell::new(session.map(Into::into))),folder:Rc::new(RefCell::new(folder.map(Into::into))),context:"window:command".into()}
  }
  pub fn set_session(host:&Host,value:Option<&str>){*host.session.borrow_mut()=value.map(Into::into)}
  pub fn set_folder(host:&Host,value:Option<&str>){*host.folder.borrow_mut()=value.map(Into::into)}
 }
 pub mod declarative{pub mod runtime{
  use super::super::super::super::*;
  use crate::ui::extensions::host::{self,Host};
  struct Scope{host:Host,window:AnyWindowHandle,popup_closed:u64,source:Option<(WeakEntity<Chat>,crate::tabs::ChatKey)>,session:Option<PathBuf>,workspace:PathBuf,announced:bool,_events:Option<Subscription>,_session_events:Option<Subscription>}
  struct Runtime{lifetime:Lifetime,scopes:HashMap<String,Scope>,extension:Installed,session_events:EventCursor,process:Option<()>,error:Option<String>,views:HashMap<String,Attached>,starts:usize,sent:RefCell<Vec<Outgoing>>}
  impl Default for Runtime{fn default()->Self{Self{lifetime:Lifetime::Workspace,scopes:HashMap::new(),extension:Installed{manifest:Manifest},session_events:EventCursor,process:None,error:None,views:HashMap::new(),starts:0,sent:RefCell::default()}}}
'''
methods='\n'+update+'\nimpl Runtime{\n'+ensure+'\n'+event
end=r'''
   fn send(&self,message:&Outgoing){self.sent.borrow_mut().push(message.clone())}
   // Counters only: no simulated successful process or scheduler.
   fn start(&mut self,_:&mut Context<Self>){self.starts+=1}
   fn announce_scope(&mut self,context:&str,cx:&App){let s=self.scopes.get_mut(context).unwrap();s.announced=true;s.session=s.host.session_dir(cx);s.workspace=s.host.workspace_path(cx).unwrap_or_default()}
   fn render(&mut self,_:&str,_:&App){}
  }
  #[cfg(test)]mod tests{
   use super::*;
   fn setup(session:Option<&str>,folder:Option<&str>)->(Runtime,Context<Runtime>,Host){
    let mut rt=Runtime::default();let mut cx=Context::default();let h=host::host(session,folder);
    rt.ensure_scope(h.clone(),AnyWindowHandle,&mut cx);(rt,cx,h)
   }
   #[test]fn observed_no_session_at_attach_never_gains_session_subscription(){
    let(mut rt,mut cx,h)=setup(None,Some("/project"));
    assert!(rt.scopes["window:command"]._events.is_some());
    assert!(rt.scopes["window:command"]._session_events.is_none());
    host::set_session(&h,Some("/sessions/new"));
    rt.scope_event("window:command",HostEvent::SessionOpened,&mut cx);
    rt.process=Some(()); // Explicit fixture: eventual launch succeeds.
    rt.ensure_scope(h.clone(),AnyWindowHandle,&mut cx);
    rt.scope_event("window:command",HostEvent::NavigationChanged,&mut cx);
    rt.scope_event("window:command",HostEvent::ContextChanged,&mut cx);
    assert!(rt.scopes["window:command"]._session_events.is_none());assert_eq!(cx.subscriptions,1);
    rt.sent.borrow_mut().clear();
    cx.emit(&mut rt,crate::ui::extensions::session::SessionChanged{event_id:1,session_dir:"/sessions/new".into(),update:()});
    assert!(rt.sent.borrow().is_empty());
    println!("empty scope -> Core session -> render/host events: session subscription remains absent; emitted SessionChanged is not forwarded");
   }
   #[test]fn control_scope_created_with_session_has_two_subscriptions(){
    let(mut rt,mut cx,_)=setup(Some("/sessions/ready"),Some("/project"));
    assert!(rt.scopes["window:command"]._session_events.is_some());assert_eq!(cx.subscriptions,2);
    cx.emit(&mut rt,crate::ui::extensions::session::SessionChanged{event_id:1,session_dir:"/sessions/ready".into(),update:()});
    assert_eq!(rt.sent.borrow().len(),1);assert!(matches!(rt.sent.borrow()[0],Outgoing::SessionUpdate{..}));
    rt.sent.borrow_mut().clear();cx.emit(&mut rt,crate::ui::extensions::session::SessionChanged{event_id:2,session_dir:"/sessions/other".into(),update:()});
    assert!(rt.sent.borrow().is_empty());
    println!("control: scope created with ready session forwards matching SessionChanged and rejects another session");
   }
   #[test]fn control_recreate_scope_after_session_appears_restores_subscription(){
    let(mut rt,mut cx,h)=setup(None,Some("/project"));
    host::set_session(&h,Some("/sessions/new"));rt.scopes.clear();let before=cx.subscriptions;
    rt.ensure_scope(h,AnyWindowHandle,&mut cx);
    assert!(rt.scopes["window:command"]._session_events.is_some());assert_eq!(cx.subscriptions,before+2);
   }
   #[test]fn observed_late_workspace_context_cannot_retry_initial_start(){
    let(mut rt,mut cx,h)=setup(Some("/sessions/late"),None);
    // Initial launch has no required workspace and therefore no process.
    assert!(h.workspace_path(&cx).is_none());rt.start(&mut cx);assert_eq!(rt.starts,1);
    host::set_folder(&h,Some("/project/late"));
    rt.scope_event("window:command",HostEvent::ContextChanged,&mut cx);
    assert_eq!(rt.starts,1);assert!(rt.sent.borrow().is_empty());
    println!("initial start withheld for missing workspace -> metadata available + ContextChanged: no retry and no message");
    rt.scope_event("window:command",HostEvent::NavigationChanged,&mut cx);
    assert_eq!(rt.starts,2);println!("control: later NavigationChanged admits retry");
   }
   #[test]fn control_running_context_metadata_is_forwarded_without_new_start(){
    let(mut rt,mut cx,h)=setup(Some("/sessions/late"),Some("/old"));
    rt.process=Some(());rt.announce_scope("window:command",&cx);
    host::set_folder(&h,Some("/new"));rt.scope_event("window:command",HostEvent::ContextChanged,&mut cx);
    assert_eq!(rt.starts,0);assert_eq!(rt.sent.borrow().len(),2);
   }
   #[test]fn control_failed_runtime_does_not_automatically_restart_on_metadata(){
    let(mut rt,mut cx,h)=setup(Some("/sessions/late"),None);rt.error=Some("fixture failure".into());
    host::set_folder(&h,Some("/new"));rt.scope_event("window:command",HostEvent::ContextChanged,&mut cx);
    assert_eq!(rt.starts,0);
   }
   #[test]fn control_preview_scope_does_not_subscribe_to_production_session(){
    let mut rt=Runtime::default();rt.lifetime=Lifetime::Preview;let mut cx=Context::default();
    rt.ensure_scope(host::host(Some("/synthetic"),Some("/project")),AnyWindowHandle,&mut cx);
    assert!(rt.scopes["window:command"]._session_events.is_none());assert_eq!(cx.subscriptions,0);
   }
   #[test]#[ignore]fn required_session_subscription_follows_first_session_open(){
    let(mut rt,mut cx,h)=setup(None,Some("/project"));host::set_session(&h,Some("/sessions/new"));
    rt.scope_event("window:command",HostEvent::SessionOpened,&mut cx);
    assert!(rt.scopes["window:command"]._session_events.is_some(),"live session has no update subscription");
    rt.sent.borrow_mut().clear();cx.emit(&mut rt,crate::ui::extensions::session::SessionChanged{event_id:1,session_dir:"/sessions/new".into(),update:()});
    assert_eq!(rt.sent.borrow().len(),1);assert!(matches!(rt.sent.borrow()[0],Outgoing::SessionUpdate{..}));
   }
   #[test]#[ignore]fn required_metadata_ready_retries_waiting_launch(){
    let(mut rt,mut cx,h)=setup(Some("/sessions/late"),None);rt.start(&mut cx);
    host::set_folder(&h,Some("/new"));rt.scope_event("window:command",HostEvent::ContextChanged,&mut cx);
    assert_eq!(rt.starts,2,"metadata became ready but start was not retried");
   }
  }
 } }
}}
'''
# Rust privacy scope is real; source methods are unchanged; all shim helper methods
# accessible within parent modules for the source-driven probe.
shim=shim.replace('fn session_dir','pub(in crate::ui::extensions) fn session_dir').replace('fn supports_core','pub(in crate::ui::extensions) fn supports_core').replace('fn scope(','pub(in crate::ui::extensions) fn scope(').replace('fn workspace_path','pub(in crate::ui::extensions) fn workspace_path').replace('fn active_document','pub(in crate::ui::extensions) fn active_document').replace('fn session_source','pub(in crate::ui::extensions) fn session_source').replace('fn inherit','pub(in crate::ui::extensions) fn inherit').replace('fn subscribe<','pub(in crate::ui::extensions) fn subscribe<')
# Context is crate-level, so avoid accidental restricted visibility replacement.
shim=shim.replace('pub(in crate::ui::extensions) fn subscribe<U','fn subscribe<U')
code=shim+host+mid+methods+end
(here/'lifecycle_probe.rs').write_text(code)
candidate=code.replace('!self.runtime_scope.lifetime.session() || !self.supports_core(cx)','!self.runtime_scope.lifetime.session()').replace('if !scope.announced || self.process.is_none() {\n                return;\n            }','if self.process.is_none() { if self.error.is_none() { self.start(cx); } return; }\n            if !scope.announced { return; }')
(here/'candidate_probe.rs').write_text(candidate)
(here/'source-extractions.json').write_text(json.dumps({'desktop_sha':sha,'method':'unchanged git show HEAD methods in inert typed GPUI shell; no native window/subprocess','extractions':records},indent=2)+'\n')
import difflib
patch=[]
for file in ['src/ui/extensions/host.rs','src/ui/extensions/declarative/runtime/scopes.rs']:
 old=subprocess.check_output(['git','-C',str(root),'show','HEAD:'+file],text=True)
 if file.endswith('/host.rs'):
  # Restrict substitution to subscribe_session, not other guards in Host.
  new=old.replace(host,host.replace('!self.runtime_scope.lifetime.session() || !self.supports_core(cx)','!self.runtime_scope.lifetime.session()'))
 else:
  new=old.replace('            if !scope.announced || self.process.is_none() {\n                return;\n            }','            if self.process.is_none() {\n                if self.error.is_none() {\n                    self.start(cx);\n                }\n                return;\n            }\n            if !scope.announced {\n                return;\n            }')
 patch.extend(difflib.unified_diff(old.splitlines(True),new.splitlines(True),fromfile='a/'+file,tofile='b/'+file))
(here/'candidate-late-context.patch').write_text(''.join(patch))
print(here/'lifecycle_probe.rs')
