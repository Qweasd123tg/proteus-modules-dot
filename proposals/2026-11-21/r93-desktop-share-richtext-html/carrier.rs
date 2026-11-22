use crate::declarative::{self,widget::{InlineContent,Node}};
use std::{cell::{Cell,Ref,RefCell},collections::HashMap,marker::PhantomData,ops::Deref,rc::Rc,sync::Arc};
use serde_json::{json,Value};

#[derive(Default)]
struct Observations {
    constructors: Vec<String>,
    text_updates: Vec<String>,
    entity_updates: usize,
    observers: usize,
    notifications: usize,
    syncs: Vec<InlineCall>,
    rehost: usize,
}
#[derive(Debug,PartialEq)]
struct InlineCall {
    id: String,
    slots: Vec<InlineContent>,
    host: Option<u64>,
    parent: Option<u64>,
    state: u64,
}
#[derive(Clone,Default)]
struct App {
    events: Rc<RefCell<Observations>>,
    next_id: Rc<Cell<u64>>,
}
struct Context<T>(App,PhantomData<fn()->T>);
impl<T> Context<T> {
    fn fixture(app:&App)->Self {Self(app.clone(),PhantomData)}
    fn new<U>(&mut self, new:impl FnOnce(&mut Context<U>)->U)->Entity<U> {
        let id=self.0.next_id.get()+1;
        self.0.next_id.set(id);
        Entity {id,value:Rc::new(RefCell::new(new(&mut Context::fixture(&self.0))))}
    }
    fn observe<U>(&mut self,_:&Entity<U>,_:impl FnMut(&mut T,Entity<U>,&mut Context<T>))->Subscription {
        self.0.events.borrow_mut().observers+=1;
        Subscription
    }
    fn notify(&mut self){self.0.events.borrow_mut().notifications+=1;}
}
impl<T> Deref for Context<T>{
    type Target=App;
    fn deref(&self)->&App{&self.0}
}
struct Entity<T>{id:u64,value:Rc<RefCell<T>>}
impl<T> Entity<T> {
    fn read(&self,_:&App)->Ref<'_,T>{self.value.borrow()}
    fn update<ContextEntity,U>(&self,cx:&mut Context<ContextEntity>, f:impl FnOnce(&mut T,&mut Context<T>)->U)->U {
        cx.0.events.borrow_mut().entity_updates+=1;
        f(&mut self.value.borrow_mut(),&mut Context::fixture(&cx.0))
    }
}
struct Subscription;
struct Window;
struct WeakEntity<T>(PhantomData<fn()->T>);
type Host=u64;
struct TextViewState {
    submitted: String,
    committed_revision: usize,
    parsed_error: Option<String>,
    scrollable: bool,
}
impl TextViewState {
    fn html(html:&str,cx:&mut Context<Self>)->Self {
        cx.events.borrow_mut().constructors.push(html.to_owned());
        Self{submitted:html.to_owned(),committed_revision:0,parsed_error:None,scrollable:true}
    }
    fn scrollable(mut self,value:bool)->Self { self.scrollable=value; self }
    fn set_text(&mut self, html:&str, cx:&mut Context<Self>){
        cx.events.borrow_mut().text_updates.push(html.to_owned());
        self.submitted=html.to_owned();
        self.parsed_error=None;
    }
    fn is_ready(&self)->bool { self.committed_revision>0 || self.parsed_error.is_some() }
}
#[derive(Debug,PartialEq)]
struct AnyElement {state:u64,selectable:bool,inline_ids:Vec<String>}
struct TextView(AnyElement);
impl TextView {
    fn new(state:&Entity<TextViewState>)->Self{Self(AnyElement{state:state.id,selectable:false,inline_ids:vec![]})}
    fn selectable(mut self,enabled:bool)->Self{self.0.selectable=enabled;self}
    fn markdown_extensions(mut self, inlines:Vec<String>)->Self{self.0.inline_ids=inlines;self}
    fn into_any_element(self)->AnyElement{self.0}
}

#[derive(Default)]
pub(crate) struct Slots {pub(crate) extensions:Vec<String>}
impl Slots {
    // Capture the exact adapter call; actual slot/renderer/native implementations
    // are not compiled for these fixture assertions.
    fn sync(&mut self,id:&str,slots:&[InlineContent],host:Option<Host>,parent:Option<&u64>,
        state:&Entity<TextViewState>,_:&mut Window,cx:&mut Context<DeclarativeView>) {
        cx.events.borrow_mut().syncs.push(InlineCall{id:id.to_owned(),slots:slots.to_vec(),
            host,parent:parent.copied(),state:state.id});
        self.extensions=slots.iter().map(|s|s.id.clone()).collect();
    }
    fn rehost(&self,_:WeakEntity<crate::ui::workspace::Workspace>,_:&mut Window,cx:&mut Context<DeclarativeView>){
        cx.events.borrow_mut().rehost+=1;
    }
}
#[derive(Default)]
struct Fields {rich_text:HashMap<String,RichText>}
#[derive(Default)]
struct DeclarativeView {
    root:Option<Rc<Node>>,
    fields:Fields,
    layout_owner:Option<u64>,
    host:Option<Host>,
    error:Option<String>,
    source_revision:Option<u64>,
    accepted_source_revision:Option<u64>,
}
impl DeclarativeView {
    fn host(&self,_:&App)->Option<Host>{self.host}
    fn error(&self,_:&App)->Option<&str>{self.error.as_deref()}
}
include!("rich.inc.rs");
include!("owner.inc.rs");
include!("cases.rs");
