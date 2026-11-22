use crate::{attention, conversations::ConversationSummary, tabs::{self, ChatKey, ChatSpaces, TabLayout}};
use std::{any::Any,cell::RefCell,collections::{HashMap,VecDeque},marker::PhantomData,ops::Deref,path::PathBuf,time::Instant};
use anyhow::Result;
use proteus_contracts::app_protocol::AppSessionSummary;
mod avail;
use avail::tab_available;

struct App { tracker:attention::Tracker }
struct Context<T> { app:App, events:Vec<HostEvent>, notifications:usize, scope:PhantomData<T> }
impl<T> Default for Context<T> {
    fn default()->Self {
        Self {app:App{tracker:attention::Tracker::default()},events:vec![],notifications:0,scope:PhantomData}
    }
}
impl<T> Deref for Context<T> {
    type Target=App;
    fn deref(&self)->&App {&self.app}
}
impl<T> Context<T> {
    fn default_global<G:Any>(&mut self)->&mut G{
        (&mut self.app.tracker as &mut dyn Any).downcast_mut().unwrap()
    }
    fn entity_id(&self)->u64{42}
    fn emit(&mut self,event:HostEvent){self.events.push(event);}
    fn notify(&mut self){self.notifications+=1;}
}
#[derive(Debug,Clone,Copy,Eq,PartialEq)]
enum HostEvent { NavigationChanged, ContextChanged }
struct Api(RefCell<Option<Result<Vec<AppSessionSummary>>>>);
impl Api { fn sessions(&self)->Result<Vec<AppSessionSummary>>{self.0.borrow_mut().take().unwrap()} }

/// Carrier stubs for the independently checked availability policy.
mod terminal {pub struct Target;impl Target{pub fn parse(_:&str)->Option<Self>{None}}}
mod chat {pub mod readonly {pub struct Target;impl Target{pub fn parse(_:&str)->Option<Self>{None}}}}
mod extensions {
    pub(super) fn document(id:&str,_:&super::App)->Option<()> {
        id.starts_with("files:").then_some(())
    }
}
pub(super) mod motion { pub(super) fn plays(_: &super::App)->bool { false } }
#[derive(Default)]
struct TabMotion(Vec<(TabLayout,TabLayout)>);
impl TabMotion {
    fn record(&mut self,old:&TabLayout,new:&TabLayout,plays:bool) {
        assert!(!plays);
        self.0.push((old.clone(),new.clone()));
    }
}
#[derive(Default)]
struct Windows(Vec<(u64,ChatSpaces)>);
impl Windows {
    fn persist(&mut self,entity:u64,spaces:&ChatSpaces,_:&mut Context<Workspace>){
        self.0.push((entity,spaces.clone()));
    }
}

type Pending=Box<dyn FnOnce(&mut Workspace,&mut Context<Workspace>)>;
#[derive(Default)]
struct Workspace {
    has_api:bool,
    session_projects:HashMap<PathBuf,PathBuf>,
    sessions:Vec<ConversationSummary>,
    sessions_loading:bool,
    sessions_stale:bool,
    session_catalog_epoch:u64,
    sessions_arrived:Option<Instant>,
    chats:HashMap<String,()>,
    layout:TabLayout,
    spaces:ChatSpaces,
    tab_motion:TabMotion,
    documents:HashMap<String,()>,
    document_titles:HashMap<String,String>,
    windows:Windows,
    synced:Vec<TabLayout>,
    pending:VecDeque<Pending>,
    work:VecDeque<Result<Vec<AppSessionSummary>>>,
    calls:usize,
    errors:Vec<String>,
}
impl Workspace {
    fn api(&self)->Option<()> {self.has_api.then_some(())}
    fn call<R:Send+'static>(&mut self,_:&mut Context<Self>,
        job:impl FnOnce(&Api)->Result<R>+Send+'static,
        done:impl FnOnce(&mut Self,R,&mut Context<Self>)+'static) {
        self.calls+=1;
        let next=self.work.pop_front().expect("fixture result provided");
        self.pending.push_back(Box::new(move |ws,cx|{
            let result=job(&Api(RefCell::new(Some(next)))).unwrap();
            done(ws,result,cx);
        }));
    }
    fn finish(&mut self,cx:&mut Context<Self>){
        self.pending.pop_front().expect("exact callback in flight")(self,cx);
    }
    fn sync_chats(&mut self,layout:&TabLayout,_:&mut Context<Self>){self.synced.push(layout.clone());}
    fn report(&mut self,message:String,_:&mut Context<Self>){self.errors.push(message);}
}
include!("catalog.inc.rs");
mod cases;
pub(crate) use cases::run;
