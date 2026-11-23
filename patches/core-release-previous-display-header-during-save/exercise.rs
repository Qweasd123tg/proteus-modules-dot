#![allow(dead_code, unused_imports)]
extern crate self as proteus_contracts;
use anyhow::{Result, anyhow};
use serde::{Deserialize, Serialize, de::DeserializeOwned};
use serde_json::{Value, json};
use std::{
    cell::{Cell, RefCell},
    collections::BTreeMap,
    fmt,
    path::{Path, PathBuf},
};
use uuid::Uuid;
mod meter;
mod model;
use model::*;
pub mod domain {
    pub use crate::model::*;
}
pub mod contracts {
    pub use crate::model::*;
    pub use crate::value_hash::storage_value_etag;
}
mod core {
    pub mod session_store {
        pub mod json_size;
    }
    pub(crate) fn summarize_context_history(
        history: &[crate::CanonicalMessage],
    ) -> crate::AppContextHistorySummary {
        // Fixed summary boundary, outside the changed owner; domain counts match our all-user fixture.
        crate::AppContextHistorySummary {
            messages: history.len(),
            user_messages: history.len(),
            ..Default::default()
        }
    }
}
mod prefix;
use prefix::PrefixIdentities;
mod baseline;
mod candidate;
mod composed;
mod stock;
mod value_hash;
#[derive(Clone, Debug, PartialEq, Serialize)]
struct Op {
    kind: char,
    key: String,
    wire: Option<Vec<u8>>,
    reply: Option<Vec<u8>>,
}
struct MemoryStore {
    staged: RefCell<Option<SessionReadModel>>,
    validated: Cell<usize>,
    descriptor: StorageSessionDescriptor,
    snap: StorageSnapshot,
    docs: RefCell<BTreeMap<String, Value>>,
    ops: RefCell<Vec<Op>>,
    fault: RefCell<Option<(char, String, char)>>,
    capture: bool,
    snapshots: Cell<usize>,
    stale_on: Cell<Option<usize>>,
}
impl MemoryStore {
    fn new(capture: bool) -> Self {
        let id = Uuid::from_u128(43);
        let loc = SessionLocator {
            session_id: id,
            key: "r267".into(),
        };
        Self {
            staged: Default::default(),
            validated: Default::default(),
            descriptor: StorageSessionDescriptor {
                session: loc.clone(),
                parent_session_id: None,
                workspace_path: "/fixture".into(),
                local_path: Some("/session".into()),
                record_location: None,
                created_at_ms: 0,
                updated_at_ms: 0,
            },
            snap: StorageSnapshot {
                session: loc,
                snapshot_id: "immutable".into(),
                revision: StorageRevision {
                    session_seq: 3,
                    history_revision: 2,
                },
                content_sha256: "a".repeat(64),
            },
            docs: Default::default(),
            ops: Default::default(),
            fault: Default::default(),
            capture,
            snapshots: Cell::new(0),
            stale_on: Default::default(),
        }
    }
    fn session_dir(&self) -> &Path {
        self.descriptor.local_path.as_deref().unwrap()
    }
    fn workspace_path(&self) -> Result<PathBuf> {
        Ok(self.descriptor.workspace_path.clone())
    }
    fn session_id(&self) -> SessionId {
        self.descriptor.session.session_id
    }
    fn parent_session_id(&self) -> Option<SessionId> {
        self.descriptor.parent_session_id
    }
    fn journal_snapshot(&self) -> Result<StorageSnapshot> {
        self.ops.borrow_mut().push(Op {
            kind: 'S',
            key: String::new(),
            wire: None,
            reply: None,
        });
        let n = self.snapshots.get() + 1;
        self.snapshots.set(n);
        let mut s = self.snap.clone();
        if self.stale_on.get() == Some(n) {
            s.content_sha256 = "b".repeat(64)
        };
        Ok(s)
    }
    fn fail(&self, k: char, key: &str, mode: char) {
        *self.fault.borrow_mut() = Some((k, key.into(), mode))
    }
    fn request(&self, req: Request) -> Result<Response> {
        let (kind, key) = match &req {
            Request::ReadCache {
                session,
                key,
                source,
            } => {
                assert_eq!(session, &self.snap.session);
                assert!(source.is_none());
                ('R', key)
            }
            Request::WriteCache {
                session,
                key,
                source,
                ..
            } => {
                assert_eq!(session, &self.snap.session);
                assert_eq!(source, &self.snap);
                ('W', key)
            }
        };
        self.ops.borrow_mut().push(Op {
            kind,
            key: key.clone(),
            reply: None,
            wire: self.capture.then(|| serde_json::to_vec(&req).unwrap()),
        });
        let fail = self
            .fault
            .borrow()
            .as_ref()
            .is_some_and(|(k, s, _)| *k == kind && (s == key || s == "*"));
        let result = if fail {
            let (_, _, mode) = self.fault.borrow_mut().take().unwrap();
            match mode {
                'e' => Err(anyhow!("injected transport error")),
                'd' => Ok(Response::Done),
                'n' => Ok(Response::CacheWritten { etag: None }),
                _ => unreachable!(),
            }
        } else {
            Ok(match req {
                Request::ReadCache { key, .. } => Response::Metadata {
                    document: self
                        .docs
                        .borrow()
                        .get(&key)
                        .map(|v| StorageMetadataDocument {
                            etag: "opaque".into(),
                            value: v.clone(),
                        }),
                },
                Request::WriteCache { key, value, .. } => {
                    self.docs.borrow_mut().insert(key, value);
                    Response::CacheWritten {
                        etag: Some("opaque".into()),
                    }
                }
            })
        };
        if self.capture {
            self.ops.borrow_mut().last_mut().unwrap().reply = Some(match &result {
                Ok(response) => encoded(response),
                Err(error) => format!("injected-error:{error}").into_bytes(),
            });
        }
        result
    }
    fn kinds(&self) -> String {
        self.ops.borrow().iter().map(|op| op.kind).collect()
    }
    fn reset(&self) {
        self.ops.borrow_mut().clear();
        self.snapshots.set(0);
        self.stale_on.set(None);
        self.fault.borrow_mut().take();
    }
}
fn row(
    name: &str,
    id: usize,
    status: &str,
    args: Value,
    effective_args: Option<Value>,
) -> AppTranscriptMessage {
    AppTranscriptMessage {
        message_id: Some(Uuid::from_u128(id as u128)),
        timestamp_ms: Some(1234),
        phase: None,
        role: "tool".into(),
        text: "display-only".into(),
        images: vec![ImageRef {
            id: "img".into(),
            name: "icon".into(),
            mime_type: "image/test".into(),
            path: "fixture".into(),
        }],
        tool: Some(AppTranscriptTool {
            terminal: Some(ToolTerminalRef {
                id: Uuid::from_u128(7),
                title: "display".into(),
                tty: false,
            }),
            call_id: format!("call-{id}"),
            name: name.into(),
            status: status.into(),
            args,
            effective_args,
            result: Some("excluded output".into()),
            metadata: json!({"private_display":["not persisted"]}),
        }),
        subagent: None,
        streaming: false,
    }
}
fn plain(i: usize) -> AppTranscriptMessage {
    AppTranscriptMessage {
        message_id: Some(Uuid::from_u128(i as u128)),
        timestamp_ms: Some(1234),
        phase: None,
        role: "user".into(),
        text: fixture_text(i, 4),
        images: vec![],
        tool: None,
        subagent: None,
        streaming: false,
    }
}
fn nested(n: usize) -> Value {
    let mut obj = serde_json::Map::new();
    obj.insert("z".into(), json!(["🦀",{"n": 123,"s":"x".repeat(n)}]));
    obj.insert("a".into(), json!({"":"\n\t\u{0}","unicode":"Ё"}));
    Value::Object(obj)
}
fn encoded(v: &impl Serialize) -> Vec<u8> {
    serde_json::to_vec(v).unwrap()
}
fn digest(bytes: &[u8]) -> String {
    let h = ring::digest::digest(&ring::digest::SHA256, bytes);
    h.as_ref().iter().map(|b| format!("{b:02x}")).collect()
}
fn expected(r: &AppTranscriptMessage) -> (String, Value) {
    let s = AppToolState::from(r.tool.as_ref().unwrap());
    let v = serde_json::to_value(&s).unwrap();
    let key = contracts::storage_value_etag(&v).unwrap();
    (key, v)
}
#[derive(Default, Debug, PartialEq)]
struct Ledger(Vec<(String, Vec<u8>)>);
// Includes owned array buffers plus all nested string/key buffers, omitting map node storage.
// A lower bound on concurrent page allocation, not serialized size or RSS.
fn value_heap_lower_bound(v: &Value) -> usize {
    match v {
        Value::Array(xs) => {
            xs.capacity() * std::mem::size_of::<Value>()
                + xs.iter().map(value_heap_lower_bound).sum::<usize>()
        }
        Value::Object(xs) => xs
            .iter()
            .map(|(k, v)| k.capacity() + value_heap_lower_bound(v))
            .sum(),
        Value::String(s) => s.capacity(),
        _ => 0,
    }
}
fn main() {
    match std::env::args().nth(1).as_deref() {
        Some("semantics") => {
            let a = stock::run();
            let b = candidate::run();
            let c = composed::run();
            let d = baseline::run();
            assert_eq!(a.0.len(), b.0.len());
            assert_eq!(a.0.len(), c.0.len());
            assert_eq!(d, c);
            for (((n, x), (nb, y)), (nc, z)) in a.0.iter().zip(b.0.iter()).zip(c.0.iter()) {
                assert!(
                    n == nb && n == nc && x == y && x == z,
                    "full observations differ: {n}"
                );
                println!("{n}: {} {}", x.len(), digest(x));
            }
            println!("SEMANTICS PASS");
        }
        Some("lifetime") => {
            for n in [4, 100, 1000] {
                let a = stock::life(n);
                let b = candidate::life(n);
                let c = composed::life(n);
                let d = baseline::life(n);
                assert_eq!(a, d);
                assert_eq!(b, c);
                assert_eq!(a.total, b.total);
                assert_eq!(a.total, c.total);
                assert_eq!(a.page, b.page);
                assert_eq!(b.page, c.page);
                println!(
                    "{n} pages/section stock={a:?} candidate={b:?}; four arms checked (baseline=stock, composed=candidate)"
                );
            }
            println!("LIFETIME PASS");
        }
        _ => panic!("semantics | lifetime"),
    }
}
