// Test-only per-thread requested Layout and allocation-generation ledger.
use crate::{CanonicalMessage, ContentPart, JournalEntry, JournalRecord};
use serde_json::{Value, json};
use std::{
    alloc::{GlobalAlloc, Layout, System},
    cell::RefCell,
    collections::BTreeMap,
    path::Path,
};

const KEYS: [&str; 4] = ["message_slots", "parts", "text", "other"];
#[derive(Clone, Copy, Default, Debug, PartialEq, Eq)]
struct Amount {
    bytes: usize,
    allocs: usize,
}
impl Amount {
    fn add(&mut self, b: usize) {
        self.bytes += b;
        self.allocs += 1;
    }
    fn sub(&mut self, b: usize) {
        self.bytes -= b;
        self.allocs -= 1;
    }
}
type Owners = [Amount; 4];
fn values(v: Owners) -> Value {
    Value::Object(
        KEYS.into_iter()
            .zip(v)
            .map(|(k, c)| (k.to_string(), json!({"bytes":c.bytes,"allocs":c.allocs})))
            .collect(),
    )
}
#[derive(Clone, Copy)]
struct Tag {
    group: usize,
    row: Option<usize>,
    generation: u64,
}
#[derive(Clone, Copy)]
struct Alloc {
    layout: Layout,
    generation: u64,
    tag: Option<Tag>,
}
const SAMPLES: usize = 5;
struct Record {
    sequence: u64,
    n: usize,
    visited: usize,
    outer_cap: usize,
    indexes: [usize; SAMPLES],
    pre: [Owners; SAMPLES],
    actual: [Option<Owners>; SAMPLES],
    initial: Owners,
    left: Owners,
    exit: Owners,
    start: usize,
    peak: usize,
    alloc_traffic: Amount,
}
impl Record {
    fn new(sequence: u64, n: usize, outer_cap: usize, start: usize) -> Self {
        Self {
            sequence,
            n,
            visited: 0,
            outer_cap,
            indexes: [
                0,
                n / 4,
                n / 2,
                n.saturating_mul(3) / 4,
                n.saturating_sub(1),
            ],
            pre: [[Amount::default(); 4]; SAMPLES],
            actual: [None; SAMPLES],
            initial: [Amount::default(); 4],
            left: [Amount::default(); 4],
            exit: [Amount::default(); 4],
            start,
            peak: start,
            alloc_traffic: Amount::default(),
        }
    }
    fn add_original(&mut self, t: Tag, bytes: usize) {
        self.initial[t.group].add(bytes);
        self.left[t.group].add(bytes);
        for (k, ix) in self.indexes.iter().enumerate() {
            if t.row.is_none_or(|row| row >= *ix) {
                self.pre[k][t.group].add(bytes)
            }
        }
    }
    fn json(self) -> Value {
        let marks=(0..SAMPLES).map(|i|json!({"before_row":self.indexes[i],"actual_live":self.actual[i].map(values),"suffix_expected":values(self.pre[i])})).collect::<Vec<_>>();
        json!({"seq":self.sequence,"rows":self.n,"visited":self.visited,"outer_capacity":self.outer_cap,
   "initial_owners":values(self.initial),"milestones":marks,"exit_owners":values(self.exit),
   "visit":{"initial":self.start,"peak":self.peak,"alloc_bytes":self.alloc_traffic.bytes,"alloc_n":self.alloc_traffic.allocs}})
    }
}
struct State {
    enabled: bool,
    generation: u64,
    live: usize,
    scan_n: usize,
    decodes: usize,
    fault: bool,
    map: BTreeMap<usize, Alloc>,
    record: Option<Record>,
    records: Vec<Record>,
}
impl State {
    const fn empty() -> Self {
        Self {
            enabled: false,
            generation: 0,
            live: 0,
            scan_n: 0,
            decodes: 0,
            fault: false,
            map: BTreeMap::new(),
            record: None,
            records: Vec::new(),
        }
    }
    fn alloc(&mut self, p: usize, l: Layout) {
        if !self.enabled || p == 0 {
            return;
        }
        self.generation += 1;
        if self
            .map
            .insert(
                p,
                Alloc {
                    layout: l,
                    generation: self.generation,
                    tag: None,
                },
            )
            .is_some()
        {
            self.fault = true;
            return;
        }
        self.live += l.size();
        if let Some(r) = &mut self.record {
            r.peak = r.peak.max(self.live);
            r.alloc_traffic.add(l.size());
        }
    }
    fn free(&mut self, p: usize) {
        if let Some(a) = self.map.remove(&p) {
            self.live -= a.layout.size();
            if let Some(t) = a.tag {
                if t.generation != a.generation {
                    self.fault = true;
                    return;
                }
                if let Some(r) = &mut self.record {
                    r.left[t.group].sub(a.layout.size())
                }
            }
        }
    }
    fn tag(&mut self, p: usize, row: Option<usize>, group: usize, exact: Option<usize>) {
        let (&base, a) = self
            .map
            .range_mut(..=p)
            .next_back()
            .filter(|(k, a)| p - **k < a.layout.size())
            .expect("original allocation not recorded");
        if let Some(n) = exact {
            assert_eq!((p, n), (base, a.layout.size()))
        }
        if let Some(t) = a.tag {
            assert_eq!((t.group, t.row), (group, row));
            return;
        }
        let t = Tag {
            group,
            row,
            generation: a.generation,
        };
        a.tag = Some(t);
        self.record
            .as_mut()
            .unwrap()
            .add_original(t, a.layout.size());
    }
    fn v<T>(&mut self, v: &Vec<T>, row: Option<usize>, g: usize) {
        let len = v.capacity() * size_of::<T>();
        if len > 0 {
            self.tag(v.as_ptr() as usize, row, g, Some(len));
        }
    }
    fn s(&mut self, s: &String, i: usize, g: usize) {
        if s.capacity() > 0 {
            self.tag(s.as_ptr() as usize, Some(i), g, Some(s.capacity()));
        }
    }
    fn str_opt(&mut self, s: Option<&String>, i: usize) {
        if let Some(s) = s {
            self.s(s, i, 3);
        }
    }
    fn path(&mut self, p: &Path, i: usize) {
        if !p.as_os_str().is_empty() {
            self.tag(
                p.as_os_str().as_encoded_bytes().as_ptr() as usize,
                Some(i),
                3,
                None,
            );
        }
    }
    fn j(&mut self, v: &Value, i: usize) {
        match v {
            Value::String(s) => self.s(s, i, 3),
            Value::Array(v) => {
                self.v(v, Some(i), 3);
                for x in v {
                    self.j(x, i);
                }
            }
            Value::Object(o) => {
                for (k, v) in o {
                    self.tag(std::ptr::from_ref(k) as usize, Some(i), 3, None);
                    self.s(k, i, 3);
                    self.j(v, i);
                }
            }
            _ => {}
        }
    }
    fn row(&mut self, i: usize, message: &CanonicalMessage) {
        use proteus_contracts::domain::ToolContent;
        self.v(&message.parts, Some(i), 1);
        self.str_opt(message.name.as_ref(), i);
        self.str_opt(message.tool_call_id.as_ref(), i);
        self.j(&message.metadata, i);
        for part in &message.parts {
            match &part.payload {
                ContentPart::Text { text } | ContentPart::ReasoningSummary { text } => {
                    self.s(text, i, 2)
                }
                ContentPart::Reasoning { text, signature } => {
                    self.s(text, i, 2);
                    self.str_opt(signature.as_ref(), i);
                }
                ContentPart::ToolCall { call } => {
                    self.s(&call.id, i, 3);
                    self.s(&call.name, i, 3);
                    self.str_opt(call.raw_arguments.as_ref(), i);
                    self.j(&call.args, i);
                }
                ContentPart::ToolResult { result } => {
                    self.s(&result.call_id, i, 3);
                    self.s(&result.output, i, 3);
                    self.str_opt(result.error.as_ref(), i);
                    self.j(&result.metadata, i);
                    self.v(&result.content, Some(i), 3);
                    for c in &result.content {
                        match c {
                            ToolContent::Text { text } => self.s(text, i, 3),
                            ToolContent::Json { value } => self.j(value, i),
                            ToolContent::Image { mime_type, data }
                            | ToolContent::Binary { mime_type, data } => {
                                self.s(mime_type, i, 3);
                                self.s(data, i, 3);
                            }
                            _ => {}
                        }
                    }
                }
                ContentPart::Opaque { format, data } => {
                    self.s(format, i, 3);
                    self.j(data, i);
                }
                ContentPart::FileRef { path, content } => {
                    self.path(path, i);
                    self.str_opt(content.as_ref(), i);
                }
                _ => {} // extra nested variants are semantic controls, not measured estimates.
            }
        }
    }
}
thread_local! {static S:RefCell<State>=const{RefCell::new(State::empty())};}
fn update(f: impl FnOnce(&mut State)) {
    let _ = S.try_with(|s| {
        if let Ok(mut st) = s.try_borrow_mut() {
            f(&mut st);
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
                if let Ok(l) = Layout::from_size_align(n, l.align()) {
                    s.alloc(q as usize, l)
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
pub fn begin_scan() {
    update(|s| {
        assert!(!s.enabled);
        s.scan_n += 1;
        s.enabled = true;
    });
}
pub fn end_scan() {
    update(|s| {
        assert!(s.enabled && s.record.is_none() && !s.fault);
        s.enabled = false;
    });
}
pub fn begin_decode() {
    update(|s| {
        if s.enabled {
            s.decodes += 1;
        }
    });
}
pub fn begin_record(r: &JournalRecord) {
    update(|s| {
        if !s.enabled {
            return;
        }
        assert!(s.record.is_none());
        let (n, cap) = match &r.entry {
            JournalEntry::HistoryMutated(m) => (m.messages.len(), m.messages.capacity()),
            _ => (0, 0),
        };
        s.record = Some(Record::new(r.session_seq, n, cap, s.live));
        if let JournalEntry::HistoryMutated(m) = &r.entry {
            s.v(&m.messages, None, 0);
            for (i, row) in m.messages.iter().enumerate() {
                s.row(i, row);
            }
        }
    });
}
pub fn mid_row(_: &CanonicalMessage) {
    update(|s| {
        if !s.enabled {
            return;
        }
        let Some(r) = &mut s.record else { return };
        assert!(r.visited < r.n);
        for (i, ix) in r.indexes.iter().enumerate() {
            if *ix == r.visited {
                r.actual[i] = Some(r.left);
            }
        }
        r.visited += 1;
    });
}
pub fn finish_record() {
    update(|s| {
        if !s.enabled {
            return;
        }
        let mut r = s.record.take().expect("missing before-enter record");
        r.exit = r.left;
        assert_eq!(r.visited, r.n);
        s.records.push(r);
    });
}
pub fn take() -> Value {
    let mut out = Value::Null;
    update(|s| {
        assert!(!s.enabled && !s.fault);
        if s.scan_n > 0 {
            out = json!({"scans":s.scan_n,"decodes":s.decodes,"records":std::mem::take(&mut s.records).into_iter().map(Record::json).collect::<Vec<_>>()});
        }
        s.map.clear();
        s.live = 0;
    });
    out
}
