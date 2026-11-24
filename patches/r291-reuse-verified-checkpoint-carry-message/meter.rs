// Exclusive synchronous test scope; an observer's metadata allocation is not
// charged to the genuine carry. Generations survive address reuse correctly.
use proteus_contracts::{
    domain::ToolContent,
    model_standard::{CanonicalMessage, ContentPart},
};
use serde_json::{Value, json};
use std::{
    alloc::{GlobalAlloc, Layout, System},
    cell::RefCell,
    mem::size_of_val,
};

#[derive(Clone, Copy, Default)]
struct Count {
    a: usize,
    d: usize,
    an: usize,
    dn: usize,
}
impl Count {
    fn json(self) -> Value {
        json!({"alloc_bytes":self.a,"free_bytes":self.d,"allocs":self.an,"frees":self.dn,
               "net_bytes":self.a as i64-self.d as i64})
    }
}
#[derive(Clone, Copy)]
struct Allocation {
    address: usize,
    generation: usize,
    requested: usize,
}
impl Allocation {
    fn json(self) -> Value {
        // Deliberately omit pointers; the recorded comparisons include them,
        // but the result must not depend on where the allocator placed bytes.
        json!({"generation":self.generation,"requested":self.requested})
    }
}
const OWNERS: usize = 5;
struct Message {
    id: uuid::Uuid,
    part_id: uuid::Uuid,
    lens: [usize; OWNERS],
    caps: [usize; OWNERS],
    owners: [Option<Allocation>; OWNERS],
}
impl Message {
    fn json(self) -> Value {
        json!({"id":self.id.to_string(),"part_id":self.part_id.to_string(),
               "lengths":self.lens,"capacities":self.caps,
               "owners":self.owners.map(|a|a.map(Allocation::json))})
    }
}

#[derive(Default)]
struct Carry {
    count: Count,
    live: Vec<Allocation>,
    prepared: Option<Message>,
    inserted: Option<Message>,
    prep_count: Option<Count>,
    prepared_live_at_insert: Option<[bool; OWNERS]>,
    prepared_owner_reused: Option<[bool; OWNERS]>,
}
impl Carry {
    fn observe(&self, address: usize) -> Option<Allocation> {
        self.live.iter().find(|a| a.address == address).copied()
    }
    fn describe(&self, m: &CanonicalMessage) -> Message {
        let [part] = m.parts.as_slice() else {
            panic!("unexpected prepared or inserted row shape")
        };
        let ContentPart::ToolResult { result } = &part.payload else {
            panic!("missing typed result in owner observation")
        };
        let error = result.error.as_ref();
        let structured_text = result.content.iter().find_map(|part| match part {
            ToolContent::Text { text } => Some(text),
            _ => None,
        });
        let lens = [
            result.output.len(),
            error.map_or(0, String::len),
            m.parts.len(),
            result.content.len(),
            structured_text.map_or(0, String::len),
        ];
        let caps = [
            result.output.capacity(),
            error.map_or(0, String::capacity),
            m.parts.capacity(),
            result.content.capacity(),
            structured_text.map_or(0, String::capacity),
        ];
        let pointers = [
            result.output.as_ptr() as usize,
            error.map_or(0, |e| e.as_ptr() as usize),
            m.parts.as_ptr() as usize,
            result.content.as_ptr() as usize,
            structured_text.map_or(0, |s| s.as_ptr() as usize),
        ];
        let owners = std::array::from_fn(|i| {
            if caps[i] == 0 {
                None
            } else {
                let a = self
                    .observe(pointers[i])
                    .expect("owner must be from a genuine tracked Layout request");
                if i <= 1 || i == 4 {
                    assert_eq!(a.requested, caps[i]);
                } else if i == 2 {
                    assert_eq!(a.requested, caps[i] * size_of_val(part));
                } else {
                    assert!(!result.content.is_empty());
                    assert_eq!(a.requested, caps[i] * size_of_val(&result.content[0]));
                }
                Some(a)
            }
        });
        Message {
            id: m.id,
            part_id: part.part_id,
            lens,
            caps,
            owners,
        }
    }
    fn json(self) -> Value {
        json!({"layout":self.count.json(),"prepared_layout":self.prep_count.map(Count::json),
               "prepared":self.prepared.map(Message::json),"inserted":self.inserted.map(Message::json),
               "prepared_live_at_insert":self.prepared_live_at_insert,
               "prepared_owner_reused":self.prepared_owner_reused})
    }
}

#[derive(Default)]
struct State {
    active: bool,
    generation: usize,
    current: Option<Carry>,
    completed: Vec<Carry>,
}
thread_local! {static S:RefCell<State>=const{RefCell::new(State{
    active:false,generation:0,current:None,completed:Vec::new()
})};}
fn update(f: impl FnOnce(&mut State)) {
    // Borrow is already held during allocation of meter-only metadata.
    // Ignore those nested requests, not any production allocations.
    let _ = S.try_with(|s| {
        if let Ok(mut s) = s.try_borrow_mut() {
            f(&mut s);
        }
    });
}

fn remember(s: &mut State, address: usize, requested: usize) {
    if let Some(c) = s.current.as_mut() {
        s.generation += 1;
        c.live.push(Allocation {
            address,
            generation: s.generation,
            requested,
        });
        c.count.a += requested;
        c.count.an += 1;
    }
}
fn retire(s: &mut State, address: usize, requested: usize) {
    if let Some(c) = s.current.as_mut() {
        let at = c.live.iter().position(|a| a.address == address);
        if let Some(i) = at {
            c.live.swap_remove(i);
        }
        c.count.d += requested;
        c.count.dn += 1;
    }
}

#[global_allocator]
static ALLOC: A = A;
struct A;
unsafe impl GlobalAlloc for A {
    unsafe fn alloc(&self, l: Layout) -> *mut u8 {
        let p = unsafe { System.alloc(l) };
        if !p.is_null() {
            update(|s| remember(s, p as usize, l.size()));
        }
        p
    }
    unsafe fn alloc_zeroed(&self, l: Layout) -> *mut u8 {
        let p = unsafe { System.alloc_zeroed(l) };
        if !p.is_null() {
            update(|s| remember(s, p as usize, l.size()));
        }
        p
    }
    unsafe fn dealloc(&self, p: *mut u8, l: Layout) {
        update(|s| retire(s, p as usize, l.size()));
        unsafe { System.dealloc(p, l) }
    }
    unsafe fn realloc(&self, p: *mut u8, l: Layout, n: usize) -> *mut u8 {
        let q = unsafe { System.realloc(p, l, n) };
        if !q.is_null() {
            update(|s| {
                retire(s, p as usize, l.size());
                remember(s, q as usize, n);
            });
        }
        q
    }
}
pub fn start() {
    update(|s| {
        assert!(!s.active && s.current.is_none());
        *s = State::default();
        s.active = true;
    });
}
pub fn begin_carry() {
    update(|s| {
        if s.active {
            assert!(s.current.is_none());
            s.current = Some(Carry::default());
        }
    });
}
pub fn prepared(m: &CanonicalMessage) {
    update(|s| {
        if let Some(c) = s.current.as_mut() {
            assert!(c.prepared.is_none());
            c.prep_count = Some(c.count);
            c.prepared = Some(c.describe(m));
        }
    });
}
pub fn inserted(m: &CanonicalMessage) {
    update(|s| {
        if let Some(c) = s.current.as_mut() {
            assert!(c.inserted.is_none());
            let inserted = c.describe(m);
            let prep = c.prepared.as_ref().unwrap();
            c.prepared_live_at_insert = Some(prep.owners.map(|a| {
                a.is_some_and(|a| {
                    c.observe(a.address)
                        .is_some_and(|x| x.generation == a.generation)
                })
            }));
            c.prepared_owner_reused = Some(std::array::from_fn(|i| {
                prep.owners[i]
                    .zip(inserted.owners[i])
                    .is_some_and(|(a, b)| a.address == b.address && a.generation == b.generation)
            }));
            c.inserted = Some(inserted);
        }
    });
}
pub fn finish_carry() {
    update(|s| {
        if s.active {
            let c = s.current.take().unwrap();
            assert!(c.prepared.is_some());
            s.completed.push(c);
        }
    });
}
pub fn take() -> Value {
    let mut v = Value::Null;
    update(|s| {
        assert!(s.active && s.current.is_none());
        s.active = false;
        let done = std::mem::take(&mut s.completed);
        v = json!({"carries":done.into_iter().map(Carry::json).collect::<Vec<_>>()});
    });
    v
}
