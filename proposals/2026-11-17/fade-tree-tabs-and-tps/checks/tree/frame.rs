use std::{alloc::{GlobalAlloc,Layout,System},cell::RefCell,collections::{HashMap,HashSet},ops::Range,sync::atomic::{AtomicUsize,Ordering::Relaxed}};
struct Counter;
#[global_allocator] static GLOBAL:Counter=Counter;
static CALLS:AtomicUsize=AtomicUsize::new(0);static BYTES:AtomicUsize=AtomicUsize::new(0);
unsafe impl GlobalAlloc for Counter {
    unsafe fn alloc(&self,l:Layout)->*mut u8 {CALLS.fetch_add(1,Relaxed);BYTES.fetch_add(l.size(),Relaxed);unsafe{System.alloc(l)}}
    unsafe fn realloc(&self,p:*mut u8,l:Layout,n:usize)->*mut u8 {CALLS.fetch_add(1,Relaxed);BYTES.fetch_add(n,Relaxed);unsafe{System.realloc(p,l,n)}}
    unsafe fn dealloc(&self,p:*mut u8,l:Layout){unsafe{System.dealloc(p,l)}}
}
#[derive(Clone)] struct Row{id:String,depth:usize}
#[derive(Clone)] struct Fold{id:String,open:bool}
#[derive(Debug,PartialEq,Eq)] struct Span{branch:usize,children:Range<usize>,fold:usize}
#[derive(Default,Clone)] struct List{rem:Vec<Range<usize>>}
impl List{fn remeasure_items(&mut self,r:Range<usize>){self.rem.push(r)}}
type SharedString=String;
#[derive(Clone)]struct Tree{rows:Vec<Row>,folds:Vec<Fold>,list:List,entity:u64}
struct App{moving:HashSet<String>, calls:RefCell<Vec<(String,bool)>>}
mod motion{use super::*;pub(super) fn moving(k:&str,o:bool,cx:&App)->bool{cx.calls.borrow_mut().push((k.to_owned(),o));cx.moving.contains(k)}}
impl Tree{
/*KEY*/
/*BASE*/
/*AFTER*/
}
/*CHILDREN*/
fn measure(t:&mut Tree,c:&App,f:fn(&mut Tree,&App)->Vec<Span>)->(Vec<Span>,usize,usize){
    CALLS.store(0,Relaxed);BYTES.store(0,Relaxed);
    let got=std::hint::black_box(f(std::hint::black_box(t),c));
    (got,CALLS.load(Relaxed),BYTES.load(Relaxed))
}
fn rows(n:usize)->Vec<Row>{(0..n).map(|i| Row{id:format!("item-{i}"),depth:[0,1,2,1,0,1,0,1][i%8]}).collect()}
fn app()->App{App{moving:HashSet::new(),calls:RefCell::new(vec![])}}
fn tree(n:usize)->Tree{Tree{rows:rows(n),folds:vec![],list:List::default(),entity:7}}
fn main(){
    for n in [0,1,64,512,2000] {
        let t=tree(n);let c=app();let(mut a,mut b)=(t.clone(),t);
        let (ar,ac,ab)=measure(&mut a,&c,Tree::before_spans);let(br,bc,bb)=measure(&mut b,&c,Tree::after_spans);
        assert!(ar.is_empty()&&br.is_empty()&&c.calls.borrow().is_empty()&&a.list.rem.is_empty()&&b.list.rem.is_empty());
        assert_eq!((bc,bb),(0,0));
        if n>0 {assert!(ac>0&&ab>0)}
        println!("idle, {n} rows: requested allocator calls {ac} -> {bc}; bytes {ab} -> {bb}");
    }
    let ids=[0,1,4,7,11];let mut cases=0;
    // A branch may have disappeared between updates; every case is checked both ways.
    for present in 0u32..32 {for moving in 0u32..32 {
        let mut t=tree(8);let mut ca=app();let mut cb=app();let mut expected_rem=vec![];let mut expected_spans=vec![];let mut survivors=0;
        for (k,i) in ids.iter().copied().enumerate() {
            if present&(1<<k)==0 {continue;}
            t.folds.push(Fold{id:format!("item-{i}"),open:k%2==0});
            let range=match i {0=>1..4,1=>2..3,4=>5..6,7=>8..8,11=>0..0,_=>unreachable!()};
            if moving&(1<<k)!=0{
                ca.moving.insert(format!("tree-7-item-{i}"));cb.moving.insert(format!("tree-7-item-{i}"));
                if i<8{expected_spans.push(Span{branch:i,children:range,fold:survivors});}survivors+=1;
            } else if i<8{expected_rem.push(i..range.end);}
        }
        let(mut a,mut b)=(t.clone(),t);
        let old=a.before_spans(&ca);let new=b.after_spans(&cb);
        assert_eq!(old,expected_spans);assert_eq!(new,expected_spans);
        assert_eq!(a.list.rem,expected_rem);assert_eq!(b.list.rem,expected_rem);
        assert_eq!(a.folds.len(),survivors);assert_eq!(b.folds.len(),survivors);
        assert_eq!(ca.calls,cb.calls);
        cases+=1;
    }}
    println!("{cases} active/settled/absent combinations agree with independent spans and invalidation ranges");
}
