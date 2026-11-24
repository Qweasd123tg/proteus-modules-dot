// Test-only allocation-generation ledger for exact typed warm content readers.
use proteus_contracts::{
    app_protocol::{AppTranscriptMessage, AppTranscriptTool},
    contracts::ModelContextObservation,
    domain::ToolContent,
    model_standard::{CanonicalMessage, ContentPart},
};
use serde_json::{Value, json};
use std::{
    alloc::{GlobalAlloc, Layout, System},
    any::{Any, TypeId},
    cell::RefCell,
    collections::BTreeMap,
    path::Path,
};

const N: usize = 10;
const GROUPS: [&str; N] = [
    "canonical_leaf",
    "canonical_aggregate",
    "canonical_parts",
    "canonical_text",
    "canonical_other",
    "context_leaf",
    "context_aggregate",
    "transcript_leaf",
    "transcript_aggregate",
    "transcript_other",
];
const SECTION: [&str; 3] = ["canonical", "context", "transcript"];
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
struct Count {
    bytes: usize,
    allocs: usize,
}
impl Count {
    fn add(&mut self, b: usize) {
        self.bytes += b;
        self.allocs += 1;
    }
    fn sub(&mut self, b: usize) {
        self.bytes -= b;
        self.allocs -= 1;
    }
    fn add_from(&mut self, x: Self) {
        self.bytes += x.bytes;
        self.allocs += x.allocs;
    }
    fn json(self) -> Value {
        json!({"bytes":self.bytes,"allocs":self.allocs})
    }
}
type ByGroup = [Count; N];
#[derive(Clone, Copy)]
struct AInfo {
    l: Layout,
    g: u64,
    owner: Option<(usize, u64)>,
}
#[derive(Clone, Copy, Default)]
struct Section {
    started: bool,
    enter: ByGroup,
    leaves: usize,
    accepted: usize,
    decoded: usize,
    max_leaf_rows: usize,
    leaf_owners: ByGroup,
    aggregate_bytes: Count,
    aggregate_peak_rows: usize,
}
struct State {
    active: bool,
    load_n: usize,
    phase: Option<usize>,
    generation: u64,
    fault: bool,
    map: BTreeMap<usize, AInfo>,
    live: ByGroup,
    typed_canonical_high_water: usize,
    sections: [Section; 3],
    final_live: Option<ByGroup>,
}
impl State {
    const fn empty() -> Self {
        const C: Count = Count {
            bytes: 0,
            allocs: 0,
        };
        const X: Section = Section {
            started: false,
            enter: [C; N],
            leaves: 0,
            accepted: 0,
            decoded: 0,
            max_leaf_rows: 0,
            leaf_owners: [C; N],
            aggregate_bytes: C,
            aggregate_peak_rows: 0,
        };
        Self {
            active: false,
            load_n: 0,
            phase: None,
            generation: 0,
            fault: false,
            map: BTreeMap::new(),
            live: [C; N],
            typed_canonical_high_water: 0,
            sections: [X; 3],
            final_live: None,
        }
    }
    fn alloc(&mut self, p: usize, l: Layout) {
        if self.active && p != 0 {
            self.generation += 1;
            if self
                .map
                .insert(
                    p,
                    AInfo {
                        l,
                        g: self.generation,
                        owner: None,
                    },
                )
                .is_some()
            {
                self.fault = true;
            }
        }
    }
    fn free(&mut self, p: usize) {
        if let Some(info) = self.map.remove(&p) {
            if let Some((group, g)) = info.owner {
                if g != info.g {
                    self.fault = true;
                    return;
                }
                self.live[group].sub(info.l.size());
            }
        }
    }
    fn owner(&mut self, p: usize, group: usize, exact: Option<usize>) -> Option<usize> {
        let (&base, slot) = self
            .map
            .range_mut(..=p)
            .next_back()
            .filter(|(k, s)| p - **k < s.l.size())
            .expect("typed owner must come from original warmed decode or aggregate allocation");
        if let Some(b) = exact {
            assert_eq!((base, slot.l.size()), (p, b));
        }
        if let Some((old, g)) = slot.owner {
            assert_eq!((old, g), (group, slot.g));
            return None;
        }
        slot.owner = Some((group, slot.g));
        self.live[group].add(slot.l.size());
        Some(slot.l.size())
    }
    fn v<T>(&mut self, v: &Vec<T>, group: usize) -> Option<usize> {
        let b = v.capacity() * size_of::<T>();
        if b == 0 {
            None
        } else {
            self.owner(v.as_ptr() as usize, group, Some(b))
        }
    }
    fn string(&mut self, s: &String, group: usize) {
        if s.capacity() > 0 {
            self.owner(s.as_ptr() as usize, group, Some(s.capacity()));
        }
    }
    fn path(&mut self, p: &Path, group: usize) {
        if !p.as_os_str().is_empty() {
            self.owner(
                p.as_os_str().as_encoded_bytes().as_ptr() as usize,
                group,
                None,
            );
        }
    }
    fn optional(&mut self, s: Option<&String>, g: usize) {
        if let Some(s) = s {
            self.string(s, g);
        }
    }
    fn json(&mut self, v: &Value, g: usize) {
        match v {
            Value::String(s) => self.string(s, g),
            Value::Array(a) => {
                self.v(a, g);
                for x in a {
                    self.json(x, g);
                }
            }
            Value::Object(o) => {
                for (k, v) in o {
                    self.owner(std::ptr::from_ref(k) as usize, g, None);
                    self.string(k, g);
                    self.json(v, g);
                }
            }
            _ => {}
        }
    }
    fn canonical(&mut self, m: &CanonicalMessage) {
        self.v(&m.parts, 2);
        self.optional(m.name.as_ref(), 4);
        self.optional(m.tool_call_id.as_ref(), 4);
        self.json(&m.metadata, 4);
        for p in &m.parts {
            match &p.payload {
                ContentPart::Text { text } | ContentPart::ReasoningSummary { text } => {
                    self.string(text, 3)
                }
                ContentPart::Reasoning { text, signature } => {
                    self.string(text, 3);
                    self.optional(signature.as_ref(), 4);
                }
                ContentPart::ToolCall { call } => {
                    self.string(&call.id, 4);
                    self.string(&call.name, 4);
                    self.optional(call.raw_arguments.as_ref(), 4);
                    self.json(&call.args, 4);
                }
                ContentPart::ToolResult { result } => {
                    self.string(&result.call_id, 4);
                    self.string(&result.output, 4);
                    self.optional(result.error.as_ref(), 4);
                    self.json(&result.metadata, 4);
                    self.v(&result.content, 4);
                    for c in &result.content {
                        match c {
                            ToolContent::Text { text } => self.string(text, 4),
                            ToolContent::Json { value } => self.json(value, 4),
                            ToolContent::Image { mime_type, data }
                            | ToolContent::Binary { mime_type, data } => {
                                self.string(mime_type, 4);
                                self.string(data, 4);
                            }
                            _ => {}
                        }
                    }
                }
                ContentPart::FileRef { path, content } => {
                    self.path(path, 4);
                    self.optional(content.as_ref(), 4);
                }
                ContentPart::Opaque { format, data } => {
                    self.string(format, 4);
                    self.json(data, 4);
                }
                _ => {} // Unmapped optional variants are not assigned an estimated size.
            }
        }
    }
    fn tool(&mut self, t: &AppTranscriptTool) {
        for s in [&t.call_id, &t.status, &t.name] {
            self.string(s, 9);
        }
        self.optional(t.result.as_ref(), 9);
        self.json(&t.metadata, 9);
        self.json(&t.args, 9);
        if let Some(v) = &t.effective_args {
            self.json(v, 9);
        }
    }
    fn transcript(&mut self, r: &AppTranscriptMessage) {
        self.string(&r.role, 9);
        self.string(&r.text, 9);
        self.v(&r.images, 9);
        if let Some(t) = &r.tool {
            self.tool(t);
        }
        if let Some(a) = &r.subagent {
            for s in [&a.child_thread_id, &a.role, &a.status] {
                self.string(s, 9);
            }
            if let Some(x) = &a.session {
                self.path(&x.session_dir, 9);
            }
            self.optional(a.description.as_ref(), 9);
            self.v(&a.tools, 9);
            for t in &a.tools {
                self.tool(t);
            }
        }
    }
    fn high(&mut self) {
        self.typed_canonical_high_water = self
            .typed_canonical_high_water
            .max(self.live[..5].iter().map(|c| c.bytes).sum());
    }
}
fn by_group(g: ByGroup) -> Value {
    Value::Object(
        GROUPS
            .into_iter()
            .zip(g)
            .map(|(k, c)| (k.to_owned(), c.json()))
            .collect(),
    )
}
fn kind<T: 'static>() -> Option<usize> {
    let ty = TypeId::of::<T>();
    if ty == TypeId::of::<CanonicalMessage>() {
        Some(0)
    } else if ty == TypeId::of::<ModelContextObservation>() {
        Some(1)
    } else if ty == TypeId::of::<AppTranscriptMessage>() {
        Some(2)
    } else {
        None
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
        update(|s| s.alloc(p as usize, l));
        p
    }
    unsafe fn alloc_zeroed(&self, l: Layout) -> *mut u8 {
        let p = unsafe { System.alloc_zeroed(l) };
        update(|s| s.alloc(p as usize, l));
        p
    }
    unsafe fn dealloc(&self, p: *mut u8, l: Layout) {
        update(|s| s.free(p as usize));
        unsafe { System.dealloc(p, l) }
    }
    unsafe fn realloc(&self, p: *mut u8, l: Layout, n: usize) -> *mut u8 {
        let q = unsafe { System.realloc(p, l, n) };
        if !q.is_null() {
            update(|s| {
                s.free(p as usize);
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
pub fn begin_cache_load() {
    update(|s| {
        assert!(!s.active && s.load_n == 0);
        s.active = true;
        s.load_n = 1;
    });
}
pub fn end_cache_load() {
    update(|s| {
        assert!(s.active && !s.fault);
        s.active = false;
    });
}
pub fn before_section<T: 'static>() {
    update(|s| {
        if !s.active {
            return;
        }
        let k = kind::<T>().expect("unexpected typed warm section");
        assert!(!s.sections[k].started);
        assert_eq!(s.phase.map(|x| x + 1).unwrap_or(0), k);
        s.phase = Some(k);
        s.sections[k].started = true;
        s.sections[k].enter = s.live;
    });
}
pub fn after_leaf<T: 'static>(rows: &Vec<T>) {
    update(|s| {
        if !s.active {
            return;
        }
        let k = kind::<T>().unwrap();
        assert_eq!(s.phase, Some(k));
        let prev = s.live;
        let untyped = rows as &dyn Any;
        match k {
            0 => {
                s.v(rows, 0);
                for x in untyped.downcast_ref::<Vec<CanonicalMessage>>().unwrap() {
                    s.canonical(x);
                }
            }
            1 => {
                s.v(rows, 5);
            }
            2 => {
                s.v(rows, 7);
                for x in untyped.downcast_ref::<Vec<AppTranscriptMessage>>().unwrap() {
                    s.transcript(x);
                }
            }
            _ => unreachable!(),
        }
        let q = &mut s.sections[k];
        q.leaves += 1;
        q.decoded += rows.len();
        q.max_leaf_rows = q.max_leaf_rows.max(rows.len());
        for (i, a) in s.live.iter().enumerate() {
            q.leaf_owners[i].add_from(Count {
                bytes: a.bytes - prev[i].bytes,
                allocs: a.allocs - prev[i].allocs,
            });
        }
        if k == 0 {
            s.high();
        }
    });
}
pub fn aggregate<T: 'static>(rows: &Vec<T>) {
    update(|s| {
        if !s.active {
            return;
        }
        let k = kind::<T>().unwrap();
        assert_eq!(s.phase, Some(k));
        let g = [1, 6, 8][k];
        if let Some(n) = s.v(rows, g) {
            s.sections[k].aggregate_bytes.add(n);
        }
        s.sections[k].aggregate_peak_rows = s.sections[k].aggregate_peak_rows.max(rows.len());
        if k == 0 {
            s.high();
        }
    });
}
pub fn accept<T: 'static>(_: &T) {
    update(|s| {
        if !s.active {
            return;
        }
        let k = kind::<T>().unwrap();
        assert_eq!(s.phase, Some(k));
        s.sections[k].accepted += 1;
    });
}
pub fn final_recheck() {
    update(|s| {
        if !s.active {
            return;
        }
        assert_eq!(s.phase, Some(2));
        assert!(s.final_live.is_none());
        s.final_live = Some(s.live);
    });
}
pub fn take() -> Value {
    let mut v = Value::Null;
    update(|s| {
        assert!(!s.active && !s.fault);
        if s.load_n != 0 {
            let sections=SECTION.into_iter().zip(s.sections).map(|(k,q)|(k.to_owned(),json!({
    "entered":q.started,"enter_owners":by_group(q.enter),"leaves":q.leaves,"decoded":q.decoded,"accepted":q.accepted,"max_leaf_rows":q.max_leaf_rows,
    "leaf_layouts":by_group(q.leaf_owners),"aggregate_layouts":q.aggregate_bytes.json(),"aggregate_peak_rows":q.aggregate_peak_rows,
   }))).collect::<serde_json::Map<_,_>>();
            v = json!({"load_n":s.load_n,"sections":sections,"canonical_typed_high_water":s.typed_canonical_high_water,"final_owners":s.final_live.map(by_group)});
        }
        s.map.clear();
    });
    v
}
