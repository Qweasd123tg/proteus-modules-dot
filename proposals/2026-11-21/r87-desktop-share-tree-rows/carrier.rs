use crate::declarative::{self,tree::Row,widget::Node};
use std::{alloc::{GlobalAlloc, Layout as AllocLayout, System}, cell::{Cell, RefCell}, collections::HashMap, marker::PhantomData, ops::{Deref,DerefMut,Range}, rc::Rc, sync::{Arc,atomic::{AtomicBool,AtomicUsize,Ordering::Relaxed}}};
use serde_json::{json,Value};

struct Counting;
static COUNT: AtomicBool = AtomicBool::new(false);
static CALLS: AtomicUsize = AtomicUsize::new(0);
static BYTES: AtomicUsize = AtomicUsize::new(0);
fn count(bytes: usize) {
    if COUNT.load(Relaxed) {
        CALLS.fetch_add(1,Relaxed);
        BYTES.fetch_add(bytes,Relaxed);
    }
}
unsafe impl GlobalAlloc for Counting {
    unsafe fn alloc(&self, l: AllocLayout) -> *mut u8 { count(l.size()); unsafe { System.alloc(l) } }
    unsafe fn alloc_zeroed(&self, l: AllocLayout) -> *mut u8 { count(l.size()); unsafe { System.alloc_zeroed(l) } }
    unsafe fn realloc(&self,p: *mut u8,l: AllocLayout,n:usize)->*mut u8 { count(n); unsafe { System.realloc(p,l,n) } }
    unsafe fn dealloc(&self,p: *mut u8,l: AllocLayout) { unsafe {System.dealloc(p,l)} }
}
#[global_allocator]
static ALLOC: Counting = Counting;
fn counted(f: impl FnOnce()) -> (usize,usize) {
    CALLS.store(0,Relaxed); BYTES.store(0,Relaxed);
    COUNT.store(true,Relaxed);
    f();
    COUNT.store(false,Relaxed);
    (CALLS.load(Relaxed),BYTES.load(Relaxed))
}
#[derive(Clone, Default)]
struct App(Rc<RefCell<Events>>);
#[derive(Default)]
struct Events {
    motions: Vec<(String,bool)>, notifications: usize, stops: usize,
    actions: Vec<(String,Value)>, menus: Vec<(String,Option<Value>,String)>,
    moving: bool,
}
struct Context<T>(App, PhantomData<fn()->T>);
impl<T> Context<T> {
    fn from(app:&App)->Self { Self(app.clone(),PhantomData) }
    fn new<U>(&mut self, create: impl FnOnce(&mut Context<U>)->U)->Entity<U> {
        Entity(RefCell::new(create(&mut Context::from(&self.0))))
    }
    fn focus_handle(&self)->FocusHandle { FocusHandle }
    fn entity_id(&self)->EntityId { 77 }
    fn weak_entity(&self)->WeakEntity<T> { WeakEntity(PhantomData) }
    fn notify(&mut self) { self.0.0.borrow_mut().notifications+=1; }
    fn stop_propagation(&mut self) { self.0.0.borrow_mut().stops+=1; }
}
impl<T> Deref for Context<T> { type Target=App; fn deref(&self)->&App { &self.0 } }
impl<T> DerefMut for Context<T> { fn deref_mut(&mut self)->&mut App { &mut self.0 } }
struct Entity<T>(RefCell<T>);
impl<T> Entity<T> {
    fn update<U>(&self,cx: &mut Context<U>,f:impl FnOnce(&mut T,&mut Context<T>)){
        f(&mut self.0.borrow_mut(),&mut Context::from(&cx.0))
    }
}
struct WeakEntity<T>(PhantomData<fn()->T>);
impl<T> Clone for WeakEntity<T> { fn clone(&self)->Self {Self(PhantomData)} }
#[derive(Clone)]
struct FocusHandle;
impl FocusHandle { fn tab_stop(self,_:bool)->Self {self} }
type EntityId=u64;
type SharedString=String;
enum ListAlignment { Top }
fn px(x:f32)->f32{x}
#[derive(Default)]
struct ListState {
    splices:Vec<(Range<usize>,usize)>, reveals:Vec<usize>, remeasures:Vec<Range<usize>>,
}
impl ListState {
    fn new(_:usize,_:ListAlignment,_:f32)->Self{Self::default()}
    fn splice(&mut self,r:Range<usize>,n:usize){self.splices.push((r,n));}
    fn scroll_to_reveal_item(&mut self,n:usize){self.reveals.push(n);}
    fn remeasure_items(&mut self,r:Range<usize>){self.remeasures.push(r);}
}
struct KeyDownEvent {keystroke:KeyStroke}
struct KeyStroke {key:String}
mod motion {
    use super::*;
    pub(super) fn toggled<T>(key:String,open:bool,cx:&mut Context<T>) {
        cx.0.0.borrow_mut().motions.push((key,open));
    }
    pub(super) fn moving(_: &str, _:bool, cx:&App)->bool {cx.0.borrow().moving}
}
impl DeclarativeView {
    fn widget_action(&self, action:&str, _: &mut Context<Self>)->WidgetAction {
        WidgetAction::new(action, |name,value,cx| cx.0.borrow_mut().actions.push((name,value)))
    }
}
include!("tree.inc.rs");
include!("fields.inc.rs");
include!("ownership.inc.rs");

pub(crate) mod menu {
    use super::*;
    use crate::declarative::control::{Confirm,MenuItem,Prompt};
    #[derive(Default)]
    pub(super) struct PopupMenu(pub Vec<Option<PopupMenuItem>>);
    type Click = Box<dyn Fn(&mut Window,&mut App)>;
    pub(crate) struct PopupMenuItem {pub name:String,pub disabled:bool,pub checked:Option<bool>,pub icon:Option<String>,pub click:Option<Click>}
    impl PopupMenuItem {
        pub fn label(name:String)->Self {Self::new(name)}
        pub fn new(name:String)->Self { Self{name,disabled:false,checked:None,icon:None,click:None} }
        fn element(f:impl Fn((),&App)->Div)->Self {Self::new(f((), &App::default()).0)}
        fn disabled(mut self,b:bool)->Self {self.disabled=b;self}
        fn checked(mut self,b:bool)->Self {self.checked=Some(b);self}
        fn icon(mut self,i:String)->Self{self.icon=Some(i);self}
        fn when_some<T>(self,v:Option<T>,f:impl FnOnce(Self,T)->Self)->Self{
            if let Some(v)=v { f(self,v) } else {self}
        }
        fn on_click(mut self,f:impl Fn((),&mut Window,&mut App)+'static)->Self{
            self.click=Some(Box::new(move |w,a|f((),w,a)));self
        }
    }
    impl PopupMenu {
        fn separator(mut self)->Self {self.0.push(None);self}
        fn item(mut self,i:PopupMenuItem)->Self {self.0.push(Some(i));self}
    }
    pub(super) struct Window;
    struct Div(String);
    impl Div {
        fn text_color(self,_:())->Self{self}
        fn child(self,s:String)->Self{Self(s)}
    }
    fn div()->Div{Div(String::new())}
    struct Theme{danger:()}
    impl App { fn theme(&self)->Theme{Theme{danger:()}} }
    fn send(_: &WeakEntity<DeclarativeView>,action:&str,value:Option<Value>,ask:Ask,w:&mut Window,cx:&mut App) {
        let _=w;
        let ask=match ask { Ask::Nothing=>"none".into(),Ask::Confirm(c)=>format!("confirm:{}",c.title),Ask::Prompt(p)=>format!("prompt:{}",p.title) };
        cx.0.borrow_mut().menus.push((action.into(),value,ask));
    }
    include!("menu.inc.rs");
}
fn icon(icon:Option<&str>)->String{icon.unwrap().into()}
pub(crate) fn menu_option(label:String,_:bool)->menu::PopupMenuItem{menu::PopupMenuItem::new(label)}
include!("cases.rs");
