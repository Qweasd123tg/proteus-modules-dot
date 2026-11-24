// Test-only deterministic requested Layout counter, thread-local.
use serde_json::{Value, json};
use std::{
    alloc::{GlobalAlloc, Layout, System},
    cell::Cell,
    thread::ThreadId,
};
#[derive(Clone, Copy, Default)]
struct Stat {
    a: usize,
    d: usize,
    an: usize,
    dn: usize,
    peak: i64,
}
impl Stat {
    const EMPTY: Self = Self {
        a: 0,
        d: 0,
        an: 0,
        dn: 0,
        peak: 0,
    };
    fn update(mut self, a: Option<usize>, d: Option<usize>) -> Self {
        if let Some(a) = a {
            self.a += a;
            self.an += 1;
        }
        if let Some(d) = d {
            self.d += d;
            self.dn += 1;
        }
        self.peak = self.peak.max(self.net());
        self
    }
    fn net(self) -> i64 {
        self.a as i64 - self.d as i64
    }
    fn json(self) -> Value {
        json!({"scopes":1,"alloc_bytes":self.a,"free_bytes":self.d,"allocs":self.an,"frees":self.dn,"net_bytes":self.net(),"peak_net_bytes":self.peak})
    }
}
#[derive(Clone, Copy, Default)]
struct State {
    current: Option<Stat>,
    complete: Option<Stat>,
}
thread_local! {static S:Cell<State>=const{Cell::new(State{current:None,complete:None})};}
fn event(a: Option<usize>, d: Option<usize>) {
    let _ = S.try_with(|s| {
        let mut m = s.get();
        if let Some(t) = m.current {
            m.current = Some(t.update(a, d));
            s.set(m);
        }
    });
}
#[global_allocator]
static ALLOC: A = A;
struct A;
unsafe impl GlobalAlloc for A {
    unsafe fn alloc(&self, l: Layout) -> *mut u8 {
        let p = unsafe { System.alloc(l) };
        if !p.is_null() {
            event(Some(l.size()), None);
        }
        p
    }
    unsafe fn alloc_zeroed(&self, l: Layout) -> *mut u8 {
        let p = unsafe { System.alloc_zeroed(l) };
        if !p.is_null() {
            event(Some(l.size()), None);
        }
        p
    }
    unsafe fn dealloc(&self, p: *mut u8, l: Layout) {
        event(None, Some(l.size()));
        unsafe { System.dealloc(p, l) }
    }
    unsafe fn realloc(&self, p: *mut u8, l: Layout, n: usize) -> *mut u8 {
        let q = unsafe { System.realloc(p, l, n) };
        if !q.is_null() {
            event(Some(n), Some(l.size()));
        }
        q
    }
}
pub struct Scope {
    thread: ThreadId,
}
pub fn reset() {
    S.with(|s| {
        assert!(s.get().current.is_none());
        s.set(State::default());
    });
}
pub fn enter() -> Scope {
    let thread = std::thread::current().id();
    S.with(|s| {
        let mut m = s.get();
        assert!(m.current.is_none() && m.complete.is_none());
        m.current = Some(Stat::EMPTY);
        s.set(m);
    });
    Scope { thread }
}
impl Drop for Scope {
    fn drop(&mut self) {
        assert_eq!(std::thread::current().id(), self.thread);
        S.with(|s| {
            let mut m = s.get();
            assert!(m.complete.is_none());
            m.complete = Some(m.current.take().expect("scope entered"));
            s.set(m);
        });
    }
}
pub fn take() -> Value {
    let v = S.with(|s| {
        let mut m = s.get();
        assert!(m.current.is_none());
        let v = m.complete.take();
        s.set(m);
        v
    });
    v.map_or(Value::Null, Stat::json)
}
