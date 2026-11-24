// Isolated proof-only ledger for the real noncausal final-result append.
use proteus_contracts::{
    app_protocol::AppTranscriptTool,
    domain::ToolResult,
    storage::journal::{JournalEntry, JournalRecord},
};
use serde_json::{Value, json};
use std::{
    alloc::{GlobalAlloc, Layout, System},
    cell::RefCell,
    collections::BTreeMap,
};

#[derive(Clone, Copy, Default)]
struct Traffic {
    a: usize,
    d: usize,
    an: usize,
    dn: usize,
}
impl Traffic {
    fn alloc(&mut self, n: usize) {
        self.a += n;
        self.an += 1;
    }
    fn free(&mut self, n: usize) {
        self.d += n;
        self.dn += 1;
    }
    fn minus(self, base: Self) -> Self {
        Self {
            a: self.a - base.a,
            d: self.d - base.d,
            an: self.an - base.an,
            dn: self.dn - base.dn,
        }
    }
    fn json(self) -> Value {
        json!({"alloc_bytes":self.a,"free_bytes":self.d,"allocs":self.an,"frees":self.dn})
    }
}
#[derive(Clone, Copy)]
struct Block {
    layout: Layout,
    generation: u64,
}
#[derive(Clone, Copy)]
struct Owner {
    base: usize,
    generation: u64,
    len: usize,
    capacity: usize,
}
impl Owner {
    fn info(self) -> Value {
        json!({"len":self.len,"capacity":self.capacity,"generation":self.generation})
    }
    fn same(self, b: Self) -> bool {
        self.base == b.base && self.generation == b.generation
    }
}
struct Probe {
    seq: u64,
    call: String,
    field: Option<&'static str>,
    original: Option<Owner>,
    row: Option<Owner>,
    capture: Traffic,
    append: Option<Traffic>,
    assembled: Option<Traffic>,
}
struct Report {
    p: Probe,
    after: Traffic,
    original_live: bool,
    row_live: bool,
}
impl Report {
    fn json(self) -> Value {
        let p = self.p;
        let same = p.original.zip(p.row).is_some_and(|(a, b)| a.same(b));
        json!({"seq":p.seq,"call":p.call,"selected":p.field,"original":p.original.map(Owner::info),
  "accepted":p.append.is_some(),"row":p.row.map(Owner::info),"same_generation":same,
  "original_alive_after_record_drop":self.original_live,"row_alive_after_record_drop":self.row_live,
  "append":p.append.zip(p.assembled).map(|(a,b)|b.minus(a).json()),"callback":self.after.minus(p.capture).json()})
    }
}
struct State {
    active: bool,
    entered: usize,
    generation: u64,
    fault: bool,
    traffic: Traffic,
    live: BTreeMap<usize, Block>,
    current: Option<Probe>,
    out: Vec<Report>,
}
impl State {
    const fn empty() -> Self {
        Self {
            active: false,
            entered: 0,
            generation: 0,
            fault: false,
            traffic: Traffic {
                a: 0,
                d: 0,
                an: 0,
                dn: 0,
            },
            live: BTreeMap::new(),
            current: None,
            out: Vec::new(),
        }
    }
    fn alloc(&mut self, p: usize, l: Layout) {
        if !self.active || p == 0 {
            return;
        }
        self.generation += 1;
        if self
            .live
            .insert(
                p,
                Block {
                    layout: l,
                    generation: self.generation,
                },
            )
            .is_some()
        {
            self.fault = true;
            return;
        }
        self.traffic.alloc(l.size());
    }
    fn free(&mut self, p: usize, l: Layout) {
        if self.active {
            self.traffic.free(l.size());
        }
        if let Some(x) = self.live.remove(&p) {
            if x.layout != l {
                self.fault = true;
            }
        }
    }
    fn owner(&self, s: &String) -> Owner {
        let base = s.as_ptr() as usize;
        let b = self
            .live
            .get(&base)
            .expect("selected/rendered String allocation was recorded within real replay");
        assert_eq!(b.layout.size(), s.capacity());
        Owner {
            base,
            generation: b.generation,
            len: s.len(),
            capacity: s.capacity(),
        }
    }
    fn alive(&self, o: Owner) -> bool {
        self.live
            .get(&o.base)
            .is_some_and(|x| x.generation == o.generation)
    }
}
fn selected(r: &ToolResult) -> Option<(&'static str, &String)> {
    r.error
        .as_ref()
        .filter(|s| !s.is_empty())
        .map(|s| ("error", s))
        .or_else(|| (!r.output.is_empty()).then_some(("output", &r.output)))
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
        update(|s| s.alloc(p as usize, l));
        p
    }
    unsafe fn alloc_zeroed(&self, l: Layout) -> *mut u8 {
        let p = unsafe { System.alloc_zeroed(l) };
        update(|s| s.alloc(p as usize, l));
        p
    }
    unsafe fn dealloc(&self, p: *mut u8, l: Layout) {
        update(|s| s.free(p as usize, l));
        unsafe { System.dealloc(p, l) }
    }
    unsafe fn realloc(&self, p: *mut u8, l: Layout, n: usize) -> *mut u8 {
        let q = unsafe { System.realloc(p, l, n) };
        if !q.is_null() {
            update(|s| {
                s.free(p as usize, l);
                if let Ok(nl) = Layout::from_size_align(n, l.align()) {
                    s.alloc(q as usize, nl);
                } else {
                    s.fault = true;
                }
            });
        }
        q
    }
}
pub fn reset() {
    update(|s| *s = State::empty());
}
pub fn begin_replay() {
    update(|s| {
        assert!(!s.active);
        s.entered += 1;
        s.active = true;
    });
}
pub fn end_replay() {
    update(|s| {
        assert!(s.active && s.current.is_none() && !s.fault);
        s.active = false;
    });
}
pub fn begin_record(r: &JournalRecord) {
    update(|s| {
        if !s.active {
            return;
        }
        assert!(s.current.is_none());
        let JournalEntry::ToolResultRecorded(t) = &r.entry else {
            return;
        };
        let choice = selected(&t.result);
        s.current = Some(Probe {
            seq: r.session_seq,
            call: t.result.call_id.clone(),
            field: choice.map(|(key, _)| key),
            original: choice.map(|(_, v)| s.owner(v)),
            row: None,
            capture: s.traffic,
            append: None,
            assembled: None,
        });
    });
}
pub fn accepted(r: &ToolResult) {
    update(|s| {
        if !s.active {
            return;
        }
        let Some(p) = &s.current else { return };
        assert_eq!(p.call, r.call_id);
        let now = selected(r).map(|(_, w)| s.owner(w));
        assert_eq!(now.is_some(), p.original.is_some());
        if let Some(x) = now {
            assert!(x.same(p.original.unwrap()));
        }
        let p = s.current.as_mut().unwrap();
        assert!(p.append.replace(s.traffic).is_none());
    });
}
pub fn end_record(tool: Option<&AppTranscriptTool>) {
    update(|s| {
        if !s.active {
            return;
        }
        let Some(p) = &s.current else { return };
        let row = if p.append.is_some() {
            let result = tool.expect("accepted final result always has an output row");
            assert_eq!(result.call_id, p.call);
            Some(s.owner(result.result.as_ref().expect("accepted tool result string")))
        } else {
            None
        };
        let p = s.current.as_mut().unwrap();
        p.row = row;
        p.assembled = Some(s.traffic);
    });
}
pub fn finish_record() {
    update(|s| {
        if !s.active {
            return;
        }
        let Some(p) = s.current.take() else { return };
        assert!(p.assembled.is_some());
        let original_live = p.original.is_some_and(|o| s.alive(o));
        let row_live = p.row.is_some_and(|o| s.alive(o));
        s.out.push(Report {
            p,
            after: s.traffic,
            original_live,
            row_live,
        });
    });
}
pub fn take() -> Value {
    let mut out = Value::Null;
    update(|s| {
        assert!(!s.active && s.current.is_none() && !s.fault);
        if s.entered != 0 {
            out = json!({"replays":s.entered,"records":std::mem::take(&mut s.out).into_iter().map(Report::json).collect::<Vec<_>>()});
        }
        s.live.clear();
    });
    out
}
