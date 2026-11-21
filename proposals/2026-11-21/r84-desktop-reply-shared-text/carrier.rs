use crate::preferences::ExtensionPreferences;
use std::{cell::RefCell,marker::PhantomData,ops::Deref,rc::Rc};
#[derive(Clone,Copy)]
pub enum Lucide { ChartColumn, FileText, Workflow, Puzzle }
impl Lucide {
    pub const ALL: &'static [Self] = &[Self::ChartColumn, Self::FileText, Self::Workflow, Self::Puzzle];
    pub fn path(&self)->&'static str {
        match self {
            Self::ChartColumn=>"icons/chart-column.svg",Self::FileText=>"icons/file-text.svg",
            Self::Workflow=>"icons/workflow.svg",Self::Puzzle=>"icons/puzzle.svg",
        }
    }
}
#[derive(Default)]
pub struct App { pub visual: Visual, pub events: RefCell<Events>, pub theme: RefCell<serde_json::Value> }
#[derive(Default)]
pub struct Events {
    pub created: usize, pub set_content: usize, pub set_source: usize, pub notified: usize,
    pub wire: Vec<String>,
}
#[derive(Default)]
pub struct Visual { pub extensions: ExtensionPreferences }
pub mod prefs {
    use super::*;
    pub fn visual(cx:&App)->&Visual { &cx.visual }
}
pub struct Context<T> {
    pub app: Rc<App>,
    t: PhantomData<T>,
}
impl<T> Deref for Context<T> {
    type Target=App;
    fn deref(&self)->&App { &self.app }
}
impl<T> Default for Context<T> {
    fn default()->Self { Self { app: Rc::default(), t:PhantomData } }
}
impl<T> Context<T> {
    pub fn cast<U>(&self)->Context<U> { Context { app:self.app.clone(), t:PhantomData } }
    pub fn weak_entity(&self)->WeakEntity<T> { WeakEntity(PhantomData) }
    pub fn new<U>(&mut self, make: impl FnOnce(&mut Context<U>)->U)->Entity<U> {
        Entity(Rc::new(RefCell::new(make(&mut self.cast()))))
    }
    pub fn observe<U,F>(&mut self,_:&Entity<U>,_:F)->Subscription where F: Fn(&mut T,&Entity<U>,&mut Context<T>) {
        Subscription
    }
    pub fn subscribe<U,E,F>(&mut self,_:&Entity<U>,_:F)->Subscription where F: Fn(&mut T,&Entity<U>,&E,&mut Context<T>) {
        Subscription
    }
    pub fn notify(&mut self) { self.events.borrow_mut().notified += 1; }
    pub fn prefs(&mut self)->&mut ExtensionPreferences {
        &mut Rc::get_mut(&mut self.app).unwrap().visual.extensions
    }
}
pub struct WeakEntity<T>(PhantomData<T>);
impl<T> Default for WeakEntity<T> { fn default()->Self { Self(PhantomData) } }
pub struct Entity<T>(pub Rc<RefCell<T>>);
impl<T> Clone for Entity<T> { fn clone(&self)->Self { Self(self.0.clone()) } }
impl<T> Entity<T> {
    pub fn update<C,R>(&self,cx:&mut Context<C>,f:impl FnOnce(&mut T,&mut Context<T>)->R)->R {
        f(&mut self.0.borrow_mut(),&mut cx.cast())
    }
}
pub struct Subscription;
pub struct Workspace;
pub struct ChatKey;
pub struct Chat { pub scroller: Entity<Scroller> }
impl Chat {
    pub fn row_of(&self, _key:u64)->Option<usize> { unreachable!("native subscription not run") }
    pub fn remeasure_row(&mut self, _key:u64, _cx:&mut Context<Self>) { unreachable!("native subscription not run") }
}
pub struct Scroller;
impl Scroller {
    pub fn toggled(&mut self,_:std::ops::Range<usize>,_:&mut Context<Self>) { unreachable!("native subscription not run") }
}
pub struct Window;
pub struct Host {
    pub ext: &'static str,
    pub readonly: bool,
}
impl Host {
    pub fn new(_:WeakEntity<Workspace>,extension:&'static str)->Self { Self { ext:extension,readonly:false } }
    pub fn for_chat(self,_:WeakEntity<Chat>,_:ChatKey)->Self { self }
    pub fn content_only(mut self)->Self { self.readonly=true; self }
}

// Only text value/owned-Arc conversion for the native fallback seam.
#[derive(Clone)]
pub struct SharedString(pub std::sync::Arc<str>);
impl From<String> for SharedString {
    fn from(value: String) -> Self { Self(value.into()) }
}
impl From<std::sync::Arc<str>> for SharedString {
    fn from(value: std::sync::Arc<str>) -> Self { Self(value) }
}
impl AsRef<str> for SharedString {
    fn as_ref(&self) -> &str { &self.0 }
}
