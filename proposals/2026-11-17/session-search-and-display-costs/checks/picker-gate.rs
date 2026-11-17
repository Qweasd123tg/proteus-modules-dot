use gpui_shared_string::SharedString;
use std::alloc::{GlobalAlloc, Layout, System};
use std::sync::atomic::{AtomicUsize, Ordering::Relaxed};
struct Counter;
static ALLOCS: AtomicUsize = AtomicUsize::new(0);
static BYTES: AtomicUsize = AtomicUsize::new(0);
#[global_allocator] static COUNTING_ALLOCATOR: Counter = Counter;
unsafe impl GlobalAlloc for Counter {
    unsafe fn alloc(&self, layout: Layout) -> *mut u8 {
        ALLOCS.fetch_add(1,Relaxed); BYTES.fetch_add(layout.size(),Relaxed);
        unsafe { System.alloc(layout) }
    }
    unsafe fn realloc(&self, p:*mut u8, old:Layout, new:usize)->*mut u8 {
        ALLOCS.fetch_add(1,Relaxed); BYTES.fetch_add(new,Relaxed);
        unsafe { System.realloc(p,old,new) }
    }
    unsafe fn dealloc(&self,p:*mut u8,l:Layout){ unsafe {System.dealloc(p,l)} }
}

__CHOICE__

mod old {use super::*; pub(super) __OLD__ }
mod candidate {use super::*; pub(super) __NEW__ }
type MatchFn = fn(&[Choice<usize>],&str)->Vec<usize>;
fn measure(f:MatchFn, opts:&[Choice<usize>], q:&str)->(Vec<usize>,usize,usize){
    ALLOCS.store(0,Relaxed); BYTES.store(0,Relaxed);
    let v=std::hint::black_box(f(std::hint::black_box(opts),std::hint::black_box(q)));
    let allocations=ALLOCS.load(Relaxed); let bytes=BYTES.load(Relaxed);
    (v,allocations,bytes)
}
fn main(){
    let mut comparisons=0;
    for n in [0,1,16,256,4096] {
        let opts:Vec<_>=(0..n).map(|i| Choice{
            value:i,selected:i==2,
            label:format!("{} {}",["Быстрая","ТИХАЯ","Local","AİA","école","起点","🙂","Straße"][i%8],i%7).into()
        }).collect();
        for q in [""," ","\t\n","\u{2003}\u{a0}","обычная","тих","起","i\u{307}","🙂","école","лок 2","a 4","2 école","1 1","str","ße","NONE"] {
            let (a,ac,ab)=measure(old::matching,&opts,q);
            let (b,bc,bb)=measure(candidate::matching,&opts,q);
            let wanted:Vec<_>=opts.iter().enumerate().filter(|(_,o)| q.split_whitespace().all(|t| o.label.to_lowercase().contains(t))).map(|(i,_)|i).collect();
            assert_eq!(a,wanted); assert_eq!(b,wanted); comparisons+=1;
            if q.trim().is_empty() {
                assert_eq!(b,(0..n).collect::<Vec<_>>());
                assert_eq!(bc,usize::from(n>0));
                if n>=16 {assert!(ac>=n); assert!(bb<ab);}
            } else {assert_eq!((ac,ab),(bc,bb));}
            if q.is_empty(){println!("{n} options: allocation/reallocation calls {ac} -> {bc}; requested bytes {ab} -> {bb}");}
        }
    }
    println!("PASS {comparisons} option/query combinations; selected indices and order agree.");
}
