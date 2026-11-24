use std::{
    alloc::{GlobalAlloc, Layout, System},
    cell::Cell,
};
#[derive(Clone, Copy, Default, Debug, PartialEq, Eq)]
pub struct Stat {
    pub a: i64,
    pub d: i64,
    pub na: i64,
    pub nd: i64,
}
thread_local! {static M: Cell<Stat>=const{Cell::new(Stat{a:0,d:0,na:0,nd:0})};}
pub fn mark() -> Stat {
    M.with(Cell::get)
}
#[inline]
fn bump(a: usize, d: usize, na: i64, nd: i64) {
    let _ = M.try_with(|m| {
        let v = m.get();
        m.set(Stat {
            a: v.a + a as i64,
            d: v.d + d as i64,
            na: v.na + na,
            nd: v.nd + nd,
        })
    });
}
impl Stat {
    pub fn minus(self, x: Self) -> Self {
        Self {
            a: self.a - x.a,
            d: self.d - x.d,
            na: self.na - x.na,
            nd: self.nd - x.nd,
        }
    }
    pub fn net(self) -> i64 {
        self.a - self.d
    }
    pub fn json(self) -> serde_json::Value {
        serde_json::json!({"alloc_bytes":self.a,"free_bytes":self.d,"net_bytes":self.net(),"alloc_n":self.na,"free_n":self.nd})
    }
}
struct A;
#[global_allocator]
static ALLOC: A = A;
unsafe impl GlobalAlloc for A {
    unsafe fn alloc(&self, l: Layout) -> *mut u8 {
        let p = unsafe { System.alloc(l) };
        if !p.is_null() {
            bump(l.size(), 0, 1, 0)
        }
        p
    }
    unsafe fn alloc_zeroed(&self, l: Layout) -> *mut u8 {
        let p = unsafe { System.alloc_zeroed(l) };
        if !p.is_null() {
            bump(l.size(), 0, 1, 0)
        }
        p
    }
    unsafe fn dealloc(&self, p: *mut u8, l: Layout) {
        bump(0, l.size(), 0, 1);
        unsafe { System.dealloc(p, l) }
    }
    unsafe fn realloc(&self, p: *mut u8, l: Layout, n: usize) -> *mut u8 {
        let q = unsafe { System.realloc(p, l, n) };
        if !q.is_null() {
            bump(n, l.size(), 1, 1)
        }
        q
    }
}
