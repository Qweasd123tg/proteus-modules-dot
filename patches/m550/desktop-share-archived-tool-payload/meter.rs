use std::{alloc::{GlobalAlloc, Layout, System}, cell::Cell, hint::black_box};
#[derive(Clone, Copy, Default, Debug)]
pub struct Count {
    pub live: isize, pub peak: usize, pub requests: usize, pub bytes: usize,
    pub largest: usize, pub raw_len: usize, pub raw_capacity: usize,
    pub hint_received: usize, pub hint_capacity: usize, pub hint_chosen: usize,
}
thread_local! { static COUNT: Cell<Option<Count>> = const { Cell::new(None) }; }
struct Meter;
#[global_allocator] static ALLOC: Meter = Meter;
fn mod_count(f:impl FnOnce(&mut Count)) {
    let _=COUNT.try_with(|r| if let Some(mut c)=r.get(){f(&mut c);r.set(Some(c));});
}
fn change(old:usize,new:usize,request:bool){
    mod_count(|c| {
        c.live+=new as isize - old as isize;
        c.peak=c.peak.max(c.live.max(0) as usize);
        if request {c.requests+=1;c.bytes+=new;c.largest=c.largest.max(new);}
    });
}
unsafe impl GlobalAlloc for Meter {
    unsafe fn alloc(&self,l:Layout)->*mut u8 {let p=unsafe {System.alloc(l)};if !p.is_null(){change(0,l.size(),true);}p}
    unsafe fn alloc_zeroed(&self,l:Layout)->*mut u8 {let p=unsafe {System.alloc_zeroed(l)};if !p.is_null(){change(0,l.size(),true);}p}
    unsafe fn realloc(&self,p:*mut u8,l:Layout,n:usize)->*mut u8 {let p=unsafe {System.realloc(p,l,n)};if !p.is_null(){change(l.size(),n,true);}p}
    unsafe fn dealloc(&self,p:*mut u8,l:Layout) {change(l.size(),0,false);unsafe {System.dealloc(p,l)}}
}
pub fn measure<T>(f:impl FnOnce()->T)->(T,Count){
    COUNT.with(|r|assert!(r.replace(Some(Count::default())).is_none()));
    let result=black_box(f());
    let count=COUNT.with(|r|r.replace(None).unwrap());
    (result,count)
}
pub(crate) fn body(len:usize,capacity:usize){mod_count(|c|{c.raw_len=len;c.raw_capacity=capacity;});}
pub(crate) fn tight_hint(received:usize,capacity:usize,size:usize){mod_count(|c|{c.hint_received=received;c.hint_capacity=capacity;c.hint_chosen=size;});}
