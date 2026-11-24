// Test-only actual requested Layout and active-index inspection receipts.
use serde_json::{Value, json};
use std::{
    alloc::{GlobalAlloc, Layout, System},
    cell::RefCell,
};
#[derive(Clone, Copy, Default)]
struct Count {
    a: usize,
    d: usize,
    an: usize,
    dn: usize,
}
impl Count {
    const EMPTY: Self = Self {
        a: 0,
        d: 0,
        an: 0,
        dn: 0,
    };
    fn alloc(&mut self, n: usize) {
        self.a += n;
        self.an += 1;
    }
    fn free(&mut self, n: usize) {
        self.d += n;
        self.dn += 1;
    }
    fn minus(self, b: Self) -> Self {
        Self {
            a: self.a - b.a,
            d: self.d - b.d,
            an: self.an - b.an,
            dn: self.dn - b.dn,
        }
    }
    fn json(self) -> Value {
        json!({"alloc_bytes":self.a,"free_bytes":self.d,"allocs":self.an,"frees":self.dn,"net_bytes":self.a as i64-self.d as i64})
    }
}
struct Check {
    index: usize,
    history_len: usize,
    pre_unique: bool,
    pre_present: bool,
    fast: bool,
    rows: usize,
    parts: usize,
    entered: Count,
    traffic: Option<Count>,
    ok: Option<bool>,
}
impl Check {
    fn json(self) -> Value {
        json!({
         "index":self.index,"history_len":self.history_len,"pre_unique":self.pre_unique,"pre_present":self.pre_present,
         "fast":self.fast,"scanned_rows":self.rows,"scanned_parts":self.parts,
         "result_ok":self.ok.unwrap(),"layout":self.traffic.unwrap().json()
        })
    }
}
struct State {
    active: bool,
    total: Count,
    checking: Option<Check>,
    done: Vec<Check>,
}
impl State {
    const fn empty() -> Self {
        Self {
            active: false,
            total: Count::EMPTY,
            checking: None,
            done: Vec::new(),
        }
    }
}
thread_local! {static S:RefCell<State>=const{RefCell::new(State::empty())};}
fn update(f: impl FnOnce(&mut State)) {
    let _ = S.try_with(|s| {
        if let Ok(mut s) = s.try_borrow_mut() {
            f(&mut s);
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
            update(|s| {
                if s.active {
                    s.total.alloc(l.size())
                }
            });
        }
        p
    }
    unsafe fn alloc_zeroed(&self, l: Layout) -> *mut u8 {
        let p = unsafe { System.alloc_zeroed(l) };
        if !p.is_null() {
            update(|s| {
                if s.active {
                    s.total.alloc(l.size())
                }
            });
        }
        p
    }
    unsafe fn dealloc(&self, p: *mut u8, l: Layout) {
        update(|s| {
            if s.active {
                s.total.free(l.size())
            }
        });
        unsafe { System.dealloc(p, l) }
    }
    unsafe fn realloc(&self, p: *mut u8, l: Layout, n: usize) -> *mut u8 {
        let q = unsafe { System.realloc(p, l, n) };
        if !q.is_null() {
            update(|s| {
                if s.active {
                    s.total.free(l.size());
                    s.total.alloc(n);
                }
            });
        }
        q
    }
}
pub fn start() {
    update(|s| {
        assert!(!s.active);
        *s = State::empty();
        s.active = true;
    });
}
pub fn active_begin(index: usize, len: usize, pre_unique: bool, pre_present: bool) {
    update(|s| {
        if !s.active {
            return;
        }
        assert!(s.checking.is_none());
        s.checking = Some(Check {
            index,
            history_len: len,
            pre_unique,
            pre_present,
            fast: false,
            rows: 0,
            parts: 0,
            entered: s.total,
            traffic: None,
            ok: None,
        });
    });
}
pub fn active_fast() {
    update(|s| {
        if !s.active {
            return;
        }
        let c = s.checking.as_mut().unwrap();
        assert!(!c.fast);
        c.fast = true;
    });
}
pub fn rebuild_rows(rows: usize, parts: usize) {
    update(|s| {
        if !s.active {
            return;
        }
        if let Some(c) = s.checking.as_mut() {
            assert!(!c.fast || (rows, parts) == (0, 0));
            c.rows += rows;
            c.parts += parts;
        }
    });
}
pub fn active_finish(index: usize, fast: bool, result_ok: bool) {
    update(|s| {
        if !s.active {
            return;
        }
        let mut c = s.checking.take().unwrap();
        assert_eq!(index, c.index);
        assert_eq!(fast, c.fast);
        c.traffic = Some(s.total.minus(c.entered));
        c.ok = Some(result_ok);
        s.done.push(c);
    });
}
pub fn take() -> Value {
    let mut v = Value::Null;
    update(|s| {
        assert!(s.active && s.checking.is_none());
        s.active = false;
        v = json!({"total":s.total.json(),"active_checks":std::mem::take(&mut s.done).into_iter().map(Check::json).collect::<Vec<_>>()});
    });
    v
}
