use std::{alloc::{GlobalAlloc, Layout, System}, cell::Cell, hint::black_box};
#[derive(Clone, Copy, Default, Debug)]
pub struct Count { pub requests: usize, pub bytes: usize }
thread_local! {
    static COUNT: Cell<(usize,usize)> = const { Cell::new((0,0)) };
}
struct Meter;
#[global_allocator]
static ALLOC: Meter = Meter;
fn count(bytes: usize) { let _ = COUNT.try_with(|n| { let (a,b) = n.get(); n.set((a+1,b+bytes)) }); }
unsafe impl GlobalAlloc for Meter {
    unsafe fn alloc(&self,l:Layout)->*mut u8 { count(l.size()); unsafe {System.alloc(l)} }
    unsafe fn alloc_zeroed(&self,l:Layout)->*mut u8 { count(l.size()); unsafe {System.alloc_zeroed(l)} }
    unsafe fn realloc(&self,p:*mut u8,l:Layout,n:usize)->*mut u8 { count(n); unsafe {System.realloc(p,l,n)} }
    unsafe fn dealloc(&self,p:*mut u8,l:Layout) { unsafe {System.dealloc(p,l)} }
}
pub fn measure<T>(f:impl FnOnce()->T) -> (T, Count) {
    let a=COUNT.with(Cell::get);
    let value=black_box(f());
    let b=COUNT.with(Cell::get);
    (value,Count { requests:b.0-a.0,bytes:b.1-a.1 })
}
