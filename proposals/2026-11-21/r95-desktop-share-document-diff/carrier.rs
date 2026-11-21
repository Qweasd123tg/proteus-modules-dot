use crate::declarative::{self,widget::Node};
use crate::diff::{self,File,FileInfo};
use std::{cell::{Cell,Ref,RefCell},collections::{HashMap,HashSet},marker::PhantomData,ops::Range,rc::Rc,sync::Arc};
use serde_json::{json,Value};

pub(crate) mod component {pub mod highlighter {#[derive(Default)] pub struct HighlightTheme;}}
use component::highlighter::HighlightTheme;
struct SyntaxHighlighter;
impl SyntaxHighlighter {fn language_revision()->Option<u64>{Some(3)}}
mod syntax {
    use super::*;
    pub(super) struct Syntax;
    impl Syntax {pub(super) fn new(_:&File,_:&Arc<HighlightTheme>)->Self{Self}}
}
type Pixels=f32;
fn px(x:f32)->Pixels{x}
struct Font;
#[derive(Clone,Debug,PartialEq,Eq)]
struct FocusHandle(u64);
#[derive(Clone,Default,Debug,PartialEq,Eq)]
struct ScrollHandle(u8);
#[derive(Clone,Default,Debug,PartialEq)]
struct ListOffset {item_ix:usize,offset_in_item:Pixels}
enum ListAlignment {Top}
#[derive(Debug,Default,PartialEq)]
struct ListData {
    count:usize, anchor:ListOffset, splices:Vec<(Range<usize>,usize)>, remeasures:Vec<Range<usize>>,
    scroll:Vec<ListOffset>,
}
struct ListState(RefCell<ListData>);
impl ListState {
    fn new(count:usize,_:ListAlignment,_:Pixels)->Self{Self(RefCell::new(ListData{count,..Default::default()}))}
    fn logical_scroll_top(&self)->ListOffset{self.0.borrow().anchor.clone()}
    fn item_count(&self)->usize{self.0.borrow().count}
    fn remeasure_items(&self,r:Range<usize>){self.0.borrow_mut().remeasures.push(r);}
    fn splice(&self,r:Range<usize>,n:usize){
        let mut a=self.0.borrow_mut();
        a.count=a.count-r.len()+n;
        a.splices.push((r,n));
    }
    fn scroll_to(&self,cursor:ListOffset){
        let mut a=self.0.borrow_mut();a.anchor=cursor.clone();a.scroll.push(cursor);
    }
}
#[derive(Default)]
struct Theme {highlight_theme:Arc<HighlightTheme>}
#[derive(Default)]
struct Events {
    update:usize, notify:usize, resize:usize, clipboard:Vec<String>, stopped:usize,
}
#[derive(Clone,Default)]
struct App {e:Rc<RefCell<Events>>, theme:Rc<Theme>, focus:Rc<Cell<u64>>}
struct Context<T>(App,PhantomData<fn()->T>);
trait EventEmitter<T>{}
type Listener<T>=Box<dyn Fn(&mut T,(),(),&mut Context<T>)>;
impl<T> Context<T> {
    fn from(app:&App)->Self{Self(app.clone(),PhantomData)}
    fn new<U>(&mut self,new:impl FnOnce(&mut Context<U>)->U)->Entity<U>{
        Entity(RefCell::new(new(&mut Context::from(&self.0))))
    }
    fn theme(&self)->&Theme{&self.0.theme}
    fn focus_handle(&self)->FocusHandle{
        self.0.focus.set(self.0.focus.get()+1);
        FocusHandle(self.0.focus.get())
    }
    fn notify(&mut self){self.0.e.borrow_mut().notify+=1;}
    fn emit<U>(&mut self,_:U) where T:EventEmitter<U>{self.0.e.borrow_mut().resize+=1;}
    fn listener(&self,f:impl Fn(&mut T,(),(),&mut Context<T>)+'static)->Listener<T>{Box::new(f)}
    fn write_to_clipboard(&mut self,item:ClipboardItem){self.0.e.borrow_mut().clipboard.push(item.0);}
    fn stop_propagation(&mut self){self.0.e.borrow_mut().stopped+=1;}
}
struct Entity<T>(RefCell<T>);
impl<T> Entity<T> {
    fn update<U>(&self,cx:&mut Context<U>,f:impl FnOnce(&mut T,&mut Context<T>)){
        cx.0.e.borrow_mut().update+=1;
        f(&mut self.0.borrow_mut(),&mut Context::from(&cx.0));
    }
}
struct ClipboardItem(String);
impl ClipboardItem {fn new_string(s:String)->Self{Self(s)}}
#[derive(Default)]
struct CopyAll {disabled:bool,hint:&'static str,listener:Option<Listener<DiffView>>}
impl CopyAll {
    fn disabled(mut self,disabled:bool)->Self{self.disabled=disabled;self}
    fn hint(mut self,hint:&'static str,_:&mut Context<DiffView>)->Self{self.hint=hint;self}
    fn on_click(mut self,click:Listener<DiffView>)->Self{self.listener=Some(click);self}
    fn press(&self,view:&Entity<DiffView>,cx:&mut Context<DiffView>){
        if !self.disabled {self.listener.as_ref().unwrap()(&mut view.0.borrow_mut(),(),(),cx);}
    }
}
#[derive(Default)]
struct CopyFile {disabled:bool,hint:&'static str,click:Option<Box<dyn Fn((),(),&mut Context<DiffView>)>>}
impl CopyFile {
    fn disabled(mut self,disabled:bool)->Self{self.disabled=disabled;self}
    fn hint(mut self,hint:&'static str,_:&mut Context<DiffView>)->Self{self.hint=hint;self}
    fn on_click(mut self,click:impl Fn((),(),&mut Context<DiffView>)+'static)->Self{self.click=Some(Box::new(click));self}
    fn press(&self,cx:&mut Context<DiffView>){if !self.disabled{self.click.as_ref().unwrap()((),(),cx);}}
}
#[derive(Default)]
struct Fields {diffs:HashMap<String,Entity<DiffView>>}
#[derive(Default)]
struct DeclarativeView {fields:Fields,root:Option<Rc<Node>>}

include!("diff.inc.rs");
include!("fields.inc.rs");
include!("copy-all.inc.rs");
include!("copy-file.inc.rs");
include!("owner.inc.rs");
include!("cases.rs");
