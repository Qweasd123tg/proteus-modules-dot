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
        assert!(history.is_empty());
        Default::default()
    }
}
type CanonicalMessage = Value;
type ModelContextObservation = Value;
#[derive(Debug)]
struct PrefixIdentities;
mod candidate;
mod stock;
mod value_hash;
#[derive(Clone, Debug, PartialEq, Serialize)]
struct Op {
    kind: char,
    key: String,
    wire: Option<Vec<u8>>,
}
struct RemoteSessionStore {
    descriptor: StorageSessionDescriptor,
    snap: StorageSnapshot,
    docs: RefCell<BTreeMap<String, Value>>,
    ops: RefCell<Vec<Op>>,
    fault: RefCell<Option<(char, String, char)>>,
    capture: bool,
    snapshots: Cell<usize>,
    stale_on: Cell<Option<usize>>,
}
impl RemoteSessionStore {
    fn new(capture: bool) -> Self {
        let id = Uuid::from_u128(43);
        let loc = SessionLocator {
            session_id: id,
            key: "r266".into(),
        };
        Self {
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
            wire: self.capture.then(|| serde_json::to_vec(&req).unwrap()),
        });
        let fail = self
            .fault
            .borrow()
            .as_ref()
            .is_some_and(|(k, s, _)| *k == kind && (s == key || s == "*"));
        if fail {
            let (_, _, mode) = self.fault.borrow_mut().take().unwrap();
            return match mode {
                'e' => Err(anyhow!("injected transport error")),
                'd' => Ok(Response::Done),
                'n' => Ok(Response::CacheWritten { etag: None }),
                _ => unreachable!(),
            };
        }
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
impl Ledger {
    fn take(
        &mut self,
        label: &str,
        s: &RemoteSessionStore,
        map: &BTreeMap<String, String>,
        result: &impl Serialize,
    ) {
        self.0.push((
            label.into(),
            encoded(&(s.ops.borrow().as_slice(), &*s.docs.borrow(), map, result)),
        ));
    }
}
fn main() {
    match std::env::args().nth(1).as_deref() {
        Some("semantics") => {
            let a = stock::run();
            let b = candidate::run();
            assert_eq!(a.0.len(), b.0.len());
            let mut rec = ring::digest::Context::new(&ring::digest::SHA256);
            for ((n, x), (nn, y)) in a.0.iter().zip(&b.0) {
                assert_eq!(n, nn);
                assert!(x == y, "observable transcript differs: {n}");
                rec.update(n.as_bytes());
                rec.update(&(x.len() as u64).to_le_bytes());
                rec.update(x);
            }
            println!(
                "matched {} typed byte/state/trace observations, receipt {:x?}",
                a.0.len(),
                rec.finish().as_ref()
            );
            println!("SEMANTICS PASS");
        }
        Some("alloc") => {
            for label in [
                "no-tools-50k",
                "skipped",
                "small",
                "nested",
                "nested-effective",
                "oversize-reject",
            ] {
                let rows = match label {
                    "no-tools-50k" => (0..50_000).map(plain).collect(),
                    "skipped" => vec![row(
                        "read",
                        3,
                        "denied",
                        nested(1 << 20),
                        Some(nested(2 << 20)),
                    )],
                    "small" => vec![row("read", 4, "completed", json!(42), None)],
                    "nested" => vec![row("read", 5, "completed", nested(1 << 20), None)],
                    "nested-effective" => vec![row(
                        "read",
                        6,
                        "running",
                        nested(1 << 20),
                        Some(nested(2 << 20)),
                    )],
                    "oversize-reject" => vec![row(
                        "read",
                        7,
                        "",
                        Value::String("x".repeat(SESSION_STORAGE_MAX_CACHE_BYTES)),
                        None,
                    )],
                    _ => unreachable!(),
                };
                let a = stock::cost(&rows);
                let b = candidate::cost(&rows);
                assert_eq!(a.live, 0);
                assert_eq!(b.live, 0);
                match label {
                    "no-tools-50k" | "skipped" => {
                        assert_eq!(
                            (a.peak, a.req, a.allocs, a.reallocs),
                            (b.peak, b.req, b.allocs, b.reallocs)
                        );
                        assert_eq!(a.req, 0);
                    }
                    _ => {
                        let min = match label {
                            "nested" => 1 << 20,
                            "nested-effective" => 3 << 20,
                            "oversize-reject" => SESSION_STORAGE_MAX_CACHE_BYTES,
                            _ => 1,
                        };
                        assert!(
                            a.req >= b.req + min && a.allocs > b.allocs && a.peak >= b.peak + min,
                            "cost guard {label}: {a:?}/{b:?}"
                        );
                    }
                }
                println!("{label} stock={a:?} candidate={b:?}");
            }
            let input = || {
                vec![row(
                    "big",
                    6,
                    "running",
                    nested(1 << 20),
                    Some(nested(2 << 20)),
                )]
            };
            let a = stock::cold_cost(input());
            let b = candidate::cold_cost(input());
            assert!(
                a.live == 0
                    && b.live == 0
                    && a.req >= b.req + (3 << 20)
                    && a.allocs > b.allocs
                    && a.peak >= b.peak,
                "real cold caller cost guard: {a:?}/{b:?}"
            );
            println!("cold-save-3MiB stock={a:?} candidate={b:?}");
            println!("ALLOC PASS");
        }
        _ => panic!("semantics | alloc"),
    }
}
