use std::alloc::{GlobalAlloc,Layout,System};
use std::cell::RefCell;
use std::collections::HashMap;
use std::sync::atomic::{AtomicBool,AtomicUsize,Ordering::Relaxed};
struct Count;
static ON:AtomicBool=AtomicBool::new(false);
static CALLS:AtomicUsize=AtomicUsize::new(0);
static BYTES:AtomicUsize=AtomicUsize::new(0);
unsafe impl GlobalAlloc for Count{
 unsafe fn alloc(&self,l:Layout)->*mut u8{if ON.load(Relaxed){CALLS.fetch_add(1,Relaxed);BYTES.fetch_add(l.size(),Relaxed);} unsafe{System.alloc(l)} }
 unsafe fn dealloc(&self,p:*mut u8,l:Layout){unsafe{System.dealloc(p,l)}}
 unsafe fn realloc(&self,p:*mut u8,l:Layout,n:usize)->*mut u8{if ON.load(Relaxed){CALLS.fetch_add(1,Relaxed);BYTES.fetch_add(n,Relaxed);} unsafe{System.realloc(p,l,n)}}
}
#[global_allocator] static ALLOC:Count=Count;
fn measured<R>(f:impl FnOnce()->R)->(R,usize,usize){
 CALLS.store(0,Relaxed);BYTES.store(0,Relaxed);ON.store(true,Relaxed);
 let v=f();ON.store(false,Relaxed);(v,CALLS.load(Relaxed),BYTES.load(Relaxed))
}
mod subject {
use super::{HashMap,RefCell};
pub type Pixels=i32; const REACH_Y:Pixels=4;
#[derive(Copy,Clone)]pub struct Point<T>{pub x:T,pub y:T}
#[derive(Copy,Clone)]pub struct Bounds<T>{pub left:T,pub right:T,pub top:T,pub bottom:T}
#[derive(Default)]struct Edges{top:Pixels,bottom:Pixels}
impl Bounds<Pixels>{
 fn contains(&self,p:&Point<Pixels>)->bool{self.left<=p.x&&p.x<=self.right&&self.top<=p.y&&p.y<=self.bottom}
 fn center(self)->Point<Pixels>{Point{x:(self.left+self.right)/2,y:(self.top+self.bottom)/2}}
 fn extend(self,e:Edges)->Self{Self{top:self.top-e.top,bottom:self.bottom+e.bottom,..self}}
}
#[derive(Default,Debug,Copy,Clone,PartialEq,Eq)]pub enum Target{#[default]Home,At(u32,usize)}
pub struct Pane{pub id:u32,pub tabs:Vec<String>,pub pinned:usize}
#[derive(Default)]pub struct State{pub target:Target,pub bounds:HashMap<String,Bounds<Pixels>>}
thread_local!{pub static STATE:RefCell<State>=RefCell::default();}
#[derive(Default)]pub struct Window{pub refreshes:usize}
impl Window{fn refresh(&mut self){self.refreshes+=1;}}
