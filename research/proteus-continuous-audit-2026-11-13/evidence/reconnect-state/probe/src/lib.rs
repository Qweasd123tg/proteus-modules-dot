#![allow(dead_code,private_interfaces)]
#[path="../../source/src/api/mod.rs"]mod api;
#[path="../../source/src/backend.rs"]mod backend;
#[path="../../source/src/connection.rs"]mod connection;
mod ui{pub(crate) mod workspace{pub(crate) use crate::Workspace;}}
#[path="../../source/src/ui/chat/context_requests.rs"]mod context_requests;
mod startup_trace{pub fn span(_: &str){}}
mod launch {
 #[derive(Clone)]pub enum Target{Spawn{profile:Option<String>},Attach{origin:String,token:String}}
 pub struct LaunchOptions{pub workspace:std::path::PathBuf,pub target:Target}
}
use std::{cell::RefCell,rc::{Rc,Weak},path::PathBuf,collections::{HashMap,HashSet},sync::{Arc,Mutex},marker::PhantomData};
use anyhow::Result;
use api::Api;
use connection::{BackendGuard,PumpItem};
use launch::LaunchOptions;
use proteus_tabs as tabs;
use tabs::{ChatKey,ChatSpaces,TabLayout};
struct CoreConnection{api:Api,backend:Option<BackendGuard>}
#[derive(Default,Clone)]struct WindowGroup(Rc<RefCell<Group>>);
#[derive(Default)]struct Group{core:Arc<Mutex<Option<CoreConnection>>>,windows:Vec<(WeakEntity<Workspace>,ChatSpaces)>}
#[derive(Debug,PartialEq)]enum Status{Ready}
struct App;
struct Window;
struct Context<T>{_p:PhantomData<T>}
impl<T> Default for Context<T>{fn default()->Self{Self{_p:PhantomData}}}
impl<T> Context<T>{
 fn notify(&mut self){}
 fn emit<E>(&mut self,_:E){}
 fn weak_entity(&self)->WeakEntity<T>{WeakEntity(Weak::new())}
 fn new<U>(&mut self,f:impl FnOnce(&mut Context<U>)->U)->Entity<U>{Entity(Rc::new(RefCell::new(f(&mut Context::default()))))}
}
enum HostEvent{SessionOpened}
struct Entity<T>(Rc<RefCell<T>>);
impl<T> Clone for Entity<T>{fn clone(&self)->Self{Self(self.0.clone())}}
struct WeakEntity<T>(Weak<RefCell<T>>);
impl<T> Clone for WeakEntity<T>{fn clone(&self)->Self{Self(self.0.clone())}}
impl<T> WeakEntity<T>{fn update<R>(&self,_:&mut App,f:impl FnOnce(&mut T,&mut Context<T>)->R)->Result<R>{let e=self.0.upgrade().ok_or_else(||anyhow::anyhow!("dropped"))?;Ok(f(&mut e.borrow_mut(),&mut Context::default()))}}
impl<T> Entity<T>{fn update<R,U>(&self,_:&mut Context<U>,f:impl FnOnce(&mut T,&mut Context<T>)->R)->R{f(&mut self.0.borrow_mut(),&mut Context::default())}}
#[derive(Clone,Copy)]struct OpenDocument{preview:bool,focus:bool}
type ComposerExtras=();
struct Feedback;impl Feedback{fn clear_activity(&mut self){}}
struct ChatEvent;impl ChatEvent{fn state_changed()->Self{Self}}
struct Session{dir:PathBuf,connected:bool,cursor:proteus_client_common::sync::SessionCursor,pending_cursor:proteus_client_common::pending::PendingCursor,link_error:Option<String>,stream_closed:bool,feedback:Feedback}
impl Session{fn new(dir:PathBuf)->Self{Self{dir,connected:false,cursor:Default::default(),pending_cursor:Default::default(),link_error:None,stream_closed:false,feedback:Feedback}}}
struct Chat{api:Option<Api>,session:Session,context_requests:context_requests::ContextRequests,_pump:Option<async_channel::Receiver<PumpItem>>}
impl Chat{
 // GPUI construction/paint/config presentation are omitted. The production
 // new() method below supplies ownership and starts the real SSE pump.
 fn base(api:Option<Api>,_:WeakEntity<Workspace>,session:Session,_:ComposerExtras,_:&mut Window,_:&mut Context<Self>)->Self{Self{api,session,context_requests:Default::default(),_pump:None}}
 fn apply_batch(&mut self,items:Vec<PumpItem>,_:&mut Context<Self>){for item in items{self.observe(item)}}
 fn observe(&mut self,item:PumpItem){self.apply(item,&mut Context::default());}
 fn apply_event(&mut self,_:proteus_contracts::app_protocol::AppServerEvent,_:&mut Context<Self>)->bool{false}
 fn load_config(&mut self,_:&mut Context<Self>){}
 fn receive(&mut self)->PumpItem{let rx=self._pump.as_ref().unwrap();let end=std::time::Instant::now()+std::time::Duration::from_secs(7);loop{if let Ok(p)=rx.try_recv(){return p};assert!(std::time::Instant::now()<end,"timed out waiting for real pump");std::thread::sleep(std::time::Duration::from_millis(10))}}
}
mod pump{use super::*;pub fn start(rx:async_channel::Receiver<PumpItem>,_:&mut Context<Chat>)->async_channel::Receiver<PumpItem>{rx}}
struct OpenChat{view:Entity<Chat>}
struct Workspace{
 api:Option<Api>,windows:WindowGroup,status:Status,notice:Option<String>,spaces:ChatSpaces,layout:TabLayout,chats:HashMap<String,OpenChat>,
 deleting_sessions:HashSet<ChatKey>,creating_chat:Option<()>,startup_streams:HashMap<PathBuf,async_channel::Receiver<PumpItem>>,active_chat:Option<String>,resume_calls:usize,
}
impl Workspace{
 fn fixture(group:WindowGroup,api:Api)->Entity<Self>{
  let w=Entity(Rc::new(RefCell::new(Self{api:Some(api),windows:group.clone(),status:Status::Ready,notice:None,spaces:ChatSpaces::default(),layout:TabLayout::default(),chats:HashMap::new(),deleting_sessions:HashSet::new(),creating_chat:None,startup_streams:HashMap::new(),active_chat:None,resume_calls:0})));
  group.0.borrow_mut().windows.push((WeakEntity(Rc::downgrade(&w.0)),ChatSpaces::default()));w
 }
 fn api(&self)->Option<Api>{self.api.clone()}
 fn composer_extras(&self,_:&Context<Self>)->ComposerExtras{()}
 fn bind_chat(&mut self,id:&str,view:Entity<Chat>,_:&mut Context<Self>){self.chats.insert(id.to_owned(),OpenChat{view});}
 fn begin_navigation(&mut self,_:&mut Context<Self>)->bool{true}
 fn open_catalog_subagent(&mut self,_:&ChatKey,_:&mut Window,_:&mut Context<Self>)->bool{false}
 fn show_external_tab(&mut self,_:&str,_:&mut Context<Self>)->bool{false}
 fn select_chat_space(&mut self,key:&ChatKey,_:&mut Context<Self>)->bool{let id=key.tab_id();let changed=self.spaces.active_root()!=Some(id.as_str());self.spaces.save_active(self.layout.clone());self.spaces.select(&id);self.layout=self.spaces.active_layout().clone();changed}
 fn ensure_chat(&mut self,key:ChatKey,w:&mut Window,cx:&mut Context<Self>){self.resume_key(key,None,w,cx)}
 fn resume_key(&mut self,key:ChatKey,_:Option<OpenDocument>,w:&mut Window,cx:&mut Context<Self>){self.resume_calls+=1;let ChatKey::Proteus(dir)=key else{panic!("Codex not exercised")};self.api().unwrap().resume(&dir).unwrap();self.insert_chat(dir,w,cx);}
 fn show_tab(&mut self,id:&str,_:OpenDocument,_:&mut Window,_:&mut Context<Self>){self.layout.open(id,|_|false);self.spaces.save_active(self.layout.clone());}
 fn focus_active(&self,_:&mut Window,_:&mut Context<Self>){}
 fn release_hidden_chat_activities(&mut self,_:&TabLayout,_:&mut Context<Self>){}
 fn refresh_sessions(&mut self,_:&mut Context<Self>){}
}
include!("generated.rs");
#[cfg(test)]mod audit;
