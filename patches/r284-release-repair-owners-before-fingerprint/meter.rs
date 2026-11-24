// Test only. Counts requested System Allocator layouts on the current test thread.
use crate::core::session_store::remote::view::SessionReadModel;
use crate::model_standard::ContentPart;
use proteus_contracts::app_protocol::AppTranscriptTool;
use proteus_contracts::domain::ToolContent;
use serde_json::{Value, json};
use std::{
    alloc::{GlobalAlloc, Layout, System},
    cell::RefCell,
    collections::{BTreeMap, HashSet},
    path::Path,
};

const N: usize = 17;
const KEYS: [&str; N] = [
    "canonical_messages",
    "canonical_parts",
    "canonical_text",
    "canonical_other",
    "model_context",
    "history_digests",
    "prefix_messages",
    "prefix_parts",
    "prefix_committed_parts",
    "prefix_turns",
    "prefix_exchanges",
    "prefix_calls",
    "summary",
    "usage",
    "rendered_rows",
    "rendered_owned",
    "unclassified",
];
#[derive(Clone, Copy, Default, Debug, PartialEq, Eq)]
struct Count {
    bytes: usize,
    allocs: usize,
}
#[derive(Clone, Copy)]
struct Owner {
    layout: Layout,
    generation: u64,
    group: usize,
}
struct Mark {
    stats: [Count; N],
    epoch: u64,
    message_n: usize,
    message_cap: usize,
    row_n: usize,
    row_cap: usize,
    context_n: usize,
    digest_n: usize,
}
struct State {
    active: bool,
    generation: u64,
    live: BTreeMap<usize, Owner>,
    mark: Option<Mark>,
    open: Option<[Count; N]>,
    release: Option<[Count; N]>,
}
impl State {
    const fn empty() -> Self {
        Self {
            active: false,
            generation: 0,
            live: BTreeMap::new(),
            mark: None,
            open: None,
            release: None,
        }
    }
    fn insert(&mut self, p: usize, l: Layout) {
        if !self.active || p == 0 {
            return;
        }
        self.generation += 1;
        assert!(
            self.live
                .insert(
                    p,
                    Owner {
                        layout: l,
                        generation: self.generation,
                        group: N - 1
                    }
                )
                .is_none()
        );
    }
    fn record(&mut self, p: usize, group: usize, base: bool, bytes: Option<usize>) {
        let (&k, owner) = self
            .live
            .range_mut(..=p)
            .next_back()
            .filter(|(k, x)| p - **k < x.layout.size())
            .expect("tracked original owner missing");
        if base {
            assert_eq!(k, p)
        }
        if let Some(bytes) = bytes {
            assert_eq!(owner.layout.size(), bytes);
        }
        assert!(
            owner.group == group || owner.group == N - 1,
            "cross-category owner: {} and {}",
            KEYS[group],
            KEYS[owner.group]
        );
        owner.group = group;
    }
    fn v<T>(&mut self, v: &Vec<T>, g: usize) {
        let bytes = v.capacity() * size_of::<T>();
        if bytes > 0 {
            self.record(v.as_ptr() as usize, g, true, Some(bytes))
        }
    }
    fn s(&mut self, s: &String, g: usize) {
        if s.capacity() > 0 {
            self.record(s.as_ptr() as usize, g, true, Some(s.capacity()));
        }
    }
    fn path(&mut self, p: &Path, g: usize) {
        if !p.as_os_str().is_empty() {
            self.record(
                p.as_os_str().as_encoded_bytes().as_ptr() as usize,
                g,
                true,
                None,
            );
        }
    }
    fn string_opt(&mut self, x: Option<&String>, g: usize) {
        if let Some(x) = x {
            self.s(x, g)
        }
    }
    fn set<T>(&mut self, v: &HashSet<T>, g: usize) {
        if let Some(x) = v.iter().next() {
            self.record(std::ptr::from_ref(x) as usize, g, false, None);
        }
    }
    fn j(&mut self, v: &Value, g: usize) {
        match v {
            Value::String(s) => self.s(s, g),
            Value::Array(a) => {
                self.v(a, g);
                for x in a {
                    self.j(x, g);
                }
            }
            // Key references identify actual BTree node or IndexMap bucket allocations
            // containing them, not any implementation-private secondary index.
            Value::Object(o) => {
                for (k, v) in o {
                    self.record(std::ptr::from_ref(k) as usize, g, false, None);
                    self.s(k, g);
                    self.j(v, g);
                }
            }
            _ => {}
        }
    }
    fn tool(&mut self, t: &AppTranscriptTool) {
        let g = 15;
        for s in [&t.call_id, &t.name, &t.status] {
            self.s(s, g)
        }
        self.string_opt(t.result.as_ref(), g);
        self.j(&t.args, g);
        self.j(&t.metadata, g);
        if let Some(args) = &t.effective_args {
            self.j(args, g)
        }
    }
    fn stats(&self, epoch: u64) -> [Count; N] {
        let mut out = [Count::default(); N];
        for x in self.live.values() {
            if x.generation <= epoch {
                out[x.group].bytes += x.layout.size();
                out[x.group].allocs += 1;
            }
        }
        out
    }
}
thread_local! {static S:RefCell<State>=const{RefCell::new(State::empty())};}
fn update(f: impl FnOnce(&mut State)) {
    // Memory used internally by the recorder and diagnostics is untracked.
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
        update(|s| s.insert(p as usize, l));
        p
    }
    unsafe fn alloc_zeroed(&self, l: Layout) -> *mut u8 {
        let p = unsafe { System.alloc_zeroed(l) };
        update(|s| s.insert(p as usize, l));
        p
    }
    unsafe fn dealloc(&self, p: *mut u8, l: Layout) {
        update(|s| {
            s.live.remove(&(p as usize));
        });
        unsafe { System.dealloc(p, l) }
    }
    unsafe fn realloc(&self, p: *mut u8, l: Layout, n: usize) -> *mut u8 {
        let q = unsafe { System.realloc(p, l, n) };
        if !q.is_null() {
            update(|s| {
                s.live.remove(&(p as usize));
                s.insert(q as usize, Layout::from_size_align(n, l.align()).unwrap());
            });
        }
        q
    }
}
pub fn reset() {
    update(|s| *s = State::empty());
}
pub fn begin_project() {
    update(|s| {
        assert!(!s.active && s.mark.is_none());
        s.active = true;
    });
}
pub fn capture(m: &SessionReadModel) {
    update(|s| {
        assert!(s.active && s.mark.is_none());
        s.v(&m.conversation.messages, 0);
        for message in &m.conversation.messages {
            s.v(&message.parts, 1);
            s.string_opt(message.name.as_ref(), 3);
            s.string_opt(message.tool_call_id.as_ref(), 3);
            s.j(&message.metadata, 3);
            for part in &message.parts {
                match &part.payload {
                    ContentPart::Text { text } | ContentPart::ReasoningSummary { text } => {
                        s.s(text, 2)
                    }
                    ContentPart::Reasoning { text, signature } => {
                        s.s(text, 2);
                        s.string_opt(signature.as_ref(), 3);
                    }
                    ContentPart::ToolCall { call } => {
                        s.s(&call.id, 3);
                        s.s(&call.name, 3);
                        s.j(&call.args, 3);
                        s.string_opt(call.raw_arguments.as_ref(), 3);
                    }
                    ContentPart::ToolResult { result } => {
                        s.s(&result.call_id, 3);
                        s.s(&result.output, 3);
                        s.string_opt(result.error.as_ref(), 3);
                        s.j(&result.metadata, 3);
                        s.v(&result.content, 3);
                        for c in &result.content {
                            match c {
                                ToolContent::Text { text } => s.s(text, 3),
                                ToolContent::Json { value } => s.j(value, 3),
                                ToolContent::Image { mime_type, data }
                                | ToolContent::Binary { mime_type, data } => {
                                    s.s(mime_type, 3);
                                    s.s(data, 3);
                                }
                                _ => unreachable!(),
                            }
                        }
                    }
                    ContentPart::Opaque { format, data } => {
                        s.s(format, 3);
                        s.j(data, 3);
                    }
                    ContentPart::FileRef { path, content } => {
                        s.path(path, 3);
                        s.string_opt(content.as_ref(), 3);
                    }
                    _ => {} // provider/image/patch owners not claimed in these fixtures.
                }
            }
        }
        s.v(&m.conversation.model_context, 4);
        let p = m
            .prefix
            .as_ref()
            .expect("model built from validated source");
        s.v(&p.history, 5);
        s.set(&p.messages, 6);
        s.set(&p.parts, 7);
        s.set(&p.explicit_committed_parts, 8);
        s.set(&p.turns, 9);
        s.set(&p.exchanges, 10);
        s.set(&p.calls, 11);
        for call in &p.calls {
            s.s(call, 11);
        }
        s.path(&m.summary.session_dir, 12);
        s.path(&m.summary.workspace_path, 12);
        s.string_opt(m.summary.preview.as_ref(), 12);
        s.v(&m.usage.requests, 13);
        s.v(&m.transcript, 14);
        for row in &m.transcript {
            s.s(&row.role, 15);
            s.s(&row.text, 15);
            s.v(&row.images, 15);
            if let Some(t) = &row.tool {
                s.tool(t);
            }
            if let Some(a) = &row.subagent {
                for x in [&a.child_thread_id, &a.role, &a.status] {
                    s.s(x, 15)
                }
                if let Some(session) = &a.session {
                    s.path(&session.session_dir, 15);
                }
                s.string_opt(a.description.as_ref(), 15);
                s.v(&a.tools, 15);
                for t in &a.tools {
                    s.tool(t);
                }
            }
        }
        s.mark = Some(Mark {
            stats: s.stats(s.generation),
            epoch: s.generation,
            message_n: m.conversation.messages.len(),
            message_cap: m.conversation.messages.capacity(),
            row_n: m.transcript.len(),
            row_cap: m.transcript.capacity(),
            context_n: m.conversation.model_context.len(),
            digest_n: p.history.len(),
        });
    });
}
pub fn at_final_open() {
    update(|s| {
        assert!(s.open.is_none());
        s.open = Some(s.stats(s.mark.as_ref().expect("model capture missing").epoch));
    });
}
pub fn at_final_release() {
    update(|s| {
        assert!(s.open.is_some() && s.release.is_none());
        s.release = Some(s.stats(s.mark.as_ref().unwrap().epoch));
    });
}
fn stats(out: &[Count; N]) -> Value {
    Value::Object(
        KEYS.into_iter()
            .zip(out)
            .map(|(k, c)| (k.to_owned(), json!({"bytes":c.bytes,"allocs":c.allocs})))
            .collect(),
    )
}
pub fn take() -> Value {
    let mut out = Value::Null;
    update(|s| {
        s.active = false;
        if let Some(m) = s.mark.take() {
            out = json!({
             "capture":stats(&m.stats),"final_open":s.open.take().as_ref().map(stats),"final_release":s.release.take().as_ref().map(stats),
             "shape":{"messages":m.message_n,"message_capacity":m.message_cap,"transcript_rows":m.row_n,"transcript_capacity":m.row_cap,"context":m.context_n,"digests":m.digest_n},
            });
        }
        s.live.clear();
    });
    out
}
