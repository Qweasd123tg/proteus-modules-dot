#![allow(dead_code,unused_imports)]
use std::{path::{Path,PathBuf},collections::HashMap,cell::Cell,rc::Rc,marker::PhantomData};
use proteus_tabs as tabs;
use tabs::{ChatSpaces,TabLayout};
#[path="../../source/src/agents/codex/mod.rs"] mod codex;
#[path="../../source/src/ui/chats/pending.rs"] mod pending;
#[derive(Clone,Copy,Debug)] struct OpenDocument{preview:bool,focus:bool}
struct Window;
#[derive(Default)] struct Context<T>{_marker:PhantomData<T>}
impl<T> Context<T>{fn notify(&mut self){} fn entity_id(&self)->usize{0}}
#[derive(Default)]struct WindowGroup;
impl WindowGroup{fn persist(&self,_:usize,_:&ChatSpaces,_:&mut Context<Workspace>) {}}
#[derive(Default)]struct SpaceViews{notice:Option<String>}
type Callback=Box<dyn FnOnce(&mut Workspace,&mut Window,&mut Context<Workspace>)>;
struct Workspace{
 service:codex::CodexService, layout:TabLayout,spaces:ChatSpaces,opening:HashMap<String,Rc<Cell<Option<OpenDocument>>>>,
 chats:HashMap<String,codex::Opened>,codex_models:Vec<codex::Model>,parked_spaces:HashMap<Option<String>,SpaceViews>,
 notice:Option<String>,windows:WindowGroup,callbacks:Vec<Callback>,finished:Vec<String>,failed:Vec<String>,
}
impl Workspace{
 fn fixture(service:codex::CodexService)->Self{let mut spaces=ChatSpaces::default();spaces.select("codex:pending");Self{service,layout:spaces.active_layout().clone(),spaces,opening:HashMap::new(),chats:HashMap::new(),codex_models:vec![],parked_spaces:HashMap::new(),notice:None,windows:WindowGroup,callbacks:vec![],finished:vec![],failed:vec![]}}
 // The transport and CodexService are real. Deliberately hold the typed UI
 // completion while another native-window action runs; no GPUI scheduler mocked as proof.
 fn call_codex_in<R:Send+'static>(&mut self,_:&mut Window,_:&mut Context<Self>,job:impl FnOnce(&codex::CodexService)->anyhow::Result<R>+Send+'static,done:impl FnOnce(&mut Self,R,&mut Window,&mut Context<Self>)+'static){let result=job(&self.service).unwrap();self.callbacks.push(Box::new(move |w,win,cx|done(w,result,win,cx)));}
 fn reply(&mut self){let cb=self.callbacks.remove(0);cb(self,&mut Window,&mut Context{_marker:PhantomData});}
 fn start(&mut self){self.resume_codex("pending".into(),Some(OpenDocument{preview:false,focus:true}),&mut Window,&mut Context{_marker:PhantomData});}
 fn insert_codex_chat(&mut self,opened:codex::Opened,_:bool,_:&mut Window,_:&mut Context<Self>)->String{let id=tabs::codex(opened.handle.thread_id());self.chats.insert(id.clone(),opened);id}
 fn finish_chat_resume(&mut self,id:&str,_:Option<OpenDocument>,_:&mut Window,_:&mut Context<Self>){self.finished.push(id.into())}
 fn sync_chats(&mut self,_:&TabLayout,_:&mut Context<Self>){}
 // This narrow adapter performs the production detach state operations in
 // their order. Window creation/rehost/paint/focus are not executed.
 fn detach_loading(&mut self)->Self{
   let id="codex:pending";
   assert!(self.layout.contains(id));assert!(!self.chats.contains_key(id));
   let mut destination=Self::fixture(self.service.clone());
   self.opening.remove(id);
   self.layout.extract(id);
   self.spaces.save_active(self.layout.clone());
   destination.start(); destination
 }
pub fn resume_codex(
        &mut self,
        thread: String,
        open: Option<OpenDocument>,
        window: &mut Window,
        cx: &mut Context<Self>,
    ) {
        let id = tabs::codex(&thread);
        if let Some(pending) = self.opening.get(&id) {
            if let Some(open) = open {
                let previous = pending.get().unwrap_or(open);
                pending.set(Some(OpenDocument {
                    preview: previous.preview && open.preview,
                    focus: previous.focus || open.focus,
                }));
            }
            return;
        }
        let pending = Rc::new(Cell::new(open));
        self.opening.insert(id.clone(), pending.clone());
        self.call_codex_in(
            window,
            cx,
            move |service| {
                Ok(service
                    .resume(&thread)
                    .and_then(|opened| Ok((opened, service.models()?))))
            },
            move |this, result, window, cx| {
                let Some(open) = pending::take(&mut this.opening, &id, &pending, &this.spaces)
                else {
                    return;
                };
                let (opened, models) = match result {
                    Ok(result) => result,
                    Err(error) => {
                        return this.fail_chat_resume(&id, format!("Codex: {error:#}"), cx);
                    }
                };
                this.codex_models = models;
                let id = this.insert_codex_chat(opened, false, window, cx);
                this.finish_chat_resume(&id, open, window, cx);
            },
        );
    }
pub fn fail_chat_resume(
        &mut self,
        id: &str,
        message: String,
        cx: &mut Context<Self>,
    ) {
        let owner = self.spaces.owner_of_chat(id).map(str::to_owned);
        self.spaces.extract_chat(id);
        self.layout = self.spaces.active_layout().clone();
        let layout = self.layout.clone();
        self.sync_chats(&layout, cx);
        if owner.as_deref() == self.spaces.active_root() {
            self.notice = Some(message.into());
        } else if let Some(parked) = self.parked_spaces.get_mut(&owner) {
            parked.notice = Some(message.into());
        }
        self.windows.persist(cx.entity_id(), &self.spaces, cx);
        cx.notify();
    }
}

#[cfg(test)]mod audit{
 use super::*;
 const PEER:&str=r#"
import json,sys
for line in sys.stdin:
 m=json.loads(line)
 if 'id' not in m: continue
 p=m.get('params',{}); method=m['method']
 if method=='initialize': result={}
 elif method=='thread/resume': result={'thread':{'id':p['threadId'],'cwd':'/synthetic','status':{'type':'idle'}}}
 elif method=='thread/items/list': result={'data':[],'nextCursor':None}
 elif method=='model/list': result={'data':[],'nextCursor':None}
 elif method=='thread/unsubscribe': result={}
 else: raise AssertionError(method)
 print(json.dumps({'id':m['id'],'result':result}),flush=True)
"#;
 fn service()->codex::CodexService{let mut l=proteus_codex_client::Launch::codex(PathBuf::from("python3"),std::env::current_dir().unwrap());l.args=vec!["-u".into(),"-c".into(),PEER.into()];l.limits.request_timeout=std::time::Duration::from_secs(3);codex::CodexService::launch(l).unwrap()}
 fn race()->(Workspace,Workspace){
  let mut source=Workspace::fixture(service());source.start();
  assert_eq!(source.callbacks.len(),1);assert!(source.chats.is_empty());assert!(source.opening.contains_key("codex:pending"));
  let mut dest=source.detach_loading();assert!(!source.spaces.contains("codex:pending"));assert!(dest.spaces.contains("codex:pending"));
  // Deliver the destination's duplicate-route error first, then old success.
  dest.reply();source.reply();
  eprintln!("source loaded={}, destination tab={}, destination loaded={}, notice={:?}",source.chats.len(),dest.spaces.contains("codex:pending"),dest.chats.len(),dest.notice);
  (source,dest)
 }
 #[test]fn observe_detach_pending_codex_drops_both_loading_endpoints(){let (source,dest)=race();assert!(source.chats.is_empty());assert!(dest.chats.is_empty());assert!(!dest.spaces.contains("codex:pending"));assert_eq!(dest.notice.as_deref(),Some("Codex: Codex protocol: Codex thread is already open"));}
 #[test]#[ignore]fn regression_detach_pending_must_finish_at_destination(){let (_,dest)=race();assert!(dest.chats.contains_key("codex:pending"),"accepted detach must retain the one successful resume");}
 #[test]fn control_ordinary_resume_succeeds(){let mut w=Workspace::fixture(service());w.start();w.reply();assert!(w.chats.contains_key("codex:pending"));assert!(w.notice.is_none());}
 #[test]fn control_retry_after_dropped_source_completion_recovers(){let (source,mut dest)=race();drop(source);dest.spaces.select("codex:pending");dest.layout=dest.spaces.active_layout().clone();dest.layout.open("codex:pending", |_|false);dest.spaces.save_active(dest.layout.clone());dest.start();dest.reply();assert!(dest.chats.contains_key("codex:pending"));}
 #[test]fn control_loaded_detach_moves_opened_without_second_resume(){let mut source=Workspace::fixture(service());source.start();source.reply();let mut dest=Workspace::fixture(source.service.clone());dest.chats.insert("codex:pending".into(),source.chats.remove("codex:pending").unwrap());assert!(source.chats.is_empty());assert!(dest.chats.contains_key("codex:pending"));assert!(dest.callbacks.is_empty());}
}

mod core_guard;
mod attention{#[derive(Default)]pub struct Tracker;impl Tracker{pub fn baseline(&self,_:&std::path::Path,_:()) {}}}
mod proteus_contracts{pub mod app_protocol{use std::path::PathBuf;pub struct AppSessionSummary{pub session_dir:PathBuf,pub workspace_path:PathBuf,pub activity:Option<Activity>}pub struct Activity{pub status:()}}}
mod conversations{
 use super::tabs::ChatKey;
 #[derive(Clone,Copy,PartialEq)]pub enum AgentKind{Proteus,Codex}
 impl AgentKind{pub fn for_key(key:&ChatKey)->Self{match key{ChatKey::Proteus(_)=>Self::Proteus,ChatKey::Codex(_)=>Self::Codex}}}
 pub struct ConversationSummary{pub key:ChatKey}
 pub fn from_proteus(rows:Vec<crate::proteus_contracts::app_protocol::AppSessionSummary>)->Vec<ConversationSummary>{rows.into_iter().map(|s|ConversationSummary{key:ChatKey::Proteus(s.session_dir)}).collect()}
}
