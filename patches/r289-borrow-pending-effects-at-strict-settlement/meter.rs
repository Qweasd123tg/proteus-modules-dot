// Proof-only exact std::alloc requested layouts, independent of process RSS.
use proteus_contracts::{
    domain::ToolResult,
    model_standard::{CanonicalMessage, ContentPart},
};
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
struct Visit {
    call: String,
    borrowed: bool,
    shared_output: Option<bool>,
    ledger_out: usize,
    out_len: usize,
    result_cap: usize,
    original_cap: usize,
    start: Count,
    capture: Option<Count>,
    canonical: Option<(usize, usize, usize, bool)>,
}
impl Visit {
    fn json(self) -> Value {
        json!({"call":self.call,"borrowed_body":self.borrowed,"shared_output":self.shared_output,"output_len":self.out_len,
  "input_capacity":self.result_cap,"ledger_capacity":self.original_cap,"capture":self.capture.map(Count::json),
  "canonical":self.canonical.map(|(bytes,cap,parts,disjoint)|json!({"bytes":bytes,"capacity":cap,"part_capacity":parts,"owned_output":disjoint}))})
    }
}
struct Pending {
    before: Count,
    map: Option<Count>,
    prepared: Option<Count>,
    done: Option<Count>,
    visits: Vec<Visit>,
}
struct State {
    active: bool,
    all: Count,
    pending: Option<Pending>,
}
impl State {
    const fn empty() -> Self {
        Self {
            active: false,
            all: Count::EMPTY,
            pending: None,
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
                    s.all.alloc(l.size())
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
                    s.all.alloc(l.size())
                }
            });
        }
        p
    }
    unsafe fn dealloc(&self, p: *mut u8, l: Layout) {
        update(|s| {
            if s.active {
                s.all.free(l.size())
            }
        });
        unsafe { System.dealloc(p, l) }
    }
    unsafe fn realloc(&self, p: *mut u8, l: Layout, n: usize) -> *mut u8 {
        let q = unsafe { System.realloc(p, l, n) };
        if !q.is_null() {
            update(|s| {
                if s.active {
                    s.all.free(l.size());
                    s.all.alloc(n);
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
pub fn begin_pending() {
    update(|s| {
        if !s.active {
            return;
        }
        assert!(s.pending.is_none());
        s.pending = Some(Pending {
            before: s.all,
            map: None,
            prepared: None,
            done: None,
            visits: Vec::new(),
        });
    });
}
pub fn after_map_clone() {
    update(|s| {
        if !s.active {
            return;
        }
        let p = s.pending.as_mut().expect("inside pending branch");
        assert!(p.map.replace(s.all.minus(p.before)).is_none());
    });
}
pub fn end_pending_prepare() {
    update(|s| {
        if !s.active {
            return;
        }
        let p = s.pending.as_mut().expect("inside pending branch");
        assert!(p.prepared.replace(s.all).is_none());
    });
}
pub fn visit(result: &ToolResult, original: &ToolResult) {
    update(|s| {
        if !s.active {
            return;
        }
        assert_eq!(result, original);
        let p = s.pending.as_mut().expect("inside pending branch");
        assert!(p.prepared.is_some() && p.done.is_none());
        p.visits.push(Visit {
            call: result.call_id.clone(),
            borrowed: std::ptr::eq(result, original),
            shared_output: (!result.output.is_empty())
                .then(|| result.output.as_ptr() == original.output.as_ptr()),
            ledger_out: original.output.as_ptr() as usize,
            out_len: result.output.len(),
            result_cap: result.output.capacity(),
            original_cap: original.output.capacity(),
            start: s.all,
            capture: None,
            canonical: None,
        });
    });
}
pub fn after_capture(result: &ToolResult, captured: Option<&CanonicalMessage>) {
    update(|s| {
        if !s.active {
            return;
        }
        let p = s.pending.as_mut().unwrap().visits.last_mut().unwrap();
        assert_eq!(p.call, result.call_id);
        assert!(p.capture.replace(s.all.minus(p.start)).is_none());
        if let Some(m) = captured {
            let &[ref part] = m.parts.as_slice() else {
                panic!("capture should own one canonical part")
            };
            let ContentPart::ToolResult { result: stored } = &part.payload else {
                panic!("captured non-tool result")
            };
            assert_eq!(result, stored);
            let disjoint = stored.output.is_empty()
                || ((stored.output.as_ptr() as usize) != p.ledger_out
                    && stored.output.as_ptr() != result.output.as_ptr());
            assert!(
                disjoint,
                "canonical capture must retain independent owned output"
            );
            p.canonical = Some((
                stored.output.len(),
                stored.output.capacity(),
                m.parts.capacity(),
                disjoint,
            ));
        }
    });
}
pub fn finish_pending() {
    update(|s| {
        if !s.active {
            return;
        }
        let p = s.pending.as_mut().unwrap();
        assert!(p.done.replace(s.all).is_none());
    });
}
pub fn take() -> Value {
    let mut out = Value::Null;
    update(|s| {
        assert!(s.active);
        s.active = false;
        let pending=s.pending.take().map(|p|{
   let prep=p.prepared.expect("entered iterator prepare");
   let done=p.done.expect("finished full branch scope even on error");
   json!({"prepare":prep.minus(p.before).json(),"map_clone":p.map.map(Count::json),
          "visit_scope":done.minus(prep).json(),"eligible":p.visits.into_iter().map(Visit::json).collect::<Vec<_>>()})
  });
        out = json!({"settlement":s.all.json(),"pending":pending});
    });
    out
}
