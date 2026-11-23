#![allow(dead_code, unused_imports, private_interfaces)]
extern crate self as proteus_contracts;
use anyhow::{Result, anyhow, bail};
use serde::{Deserialize, Serialize, de::DeserializeOwned};
use serde_json::{Value, json};
use std::{
    cell::{Cell, RefCell},
    collections::BTreeMap,
    ffi::OsString,
    fmt,
    os::unix::ffi::{OsStrExt, OsStringExt},
    path::{Path, PathBuf},
    rc::Rc,
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
pub mod app_protocol {
    pub use crate::model::*;
}
mod core {
    pub mod session_store {
        pub mod json_size;
    }
    pub(crate) fn summarize_context_history(
        x: &[crate::CanonicalMessage],
    ) -> crate::AppContextHistorySummary {
        crate::AppContextHistorySummary {
            messages: x.len(),
            user_messages: x.len(),
            ..Default::default()
        }
    }
}
mod prefix;
use prefix::PrefixIdentities;
mod candidate;
mod stock;
mod value_hash;
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
enum Attempt {
    Error,
    ValidateError,
    Cold(usize),
    Warm(usize),
    EmptyCache(usize),
}
#[derive(Clone, Debug, Serialize, PartialEq, Eq)]
struct Event(String, Vec<u8>);
#[derive(Clone, Default)]
struct CacheFixture {
    path: PathBuf,
    docs: BTreeMap<String, Value>,
}
struct Service {
    wire: Vec<u8>,
    template: Option<Vec<StorageSessionDescriptor>>,
    error: bool,
    raw: Vec<(usize, Vec<u8>)>,
    plans: Vec<Attempt>,
    opens: Cell<usize>,
    events: RefCell<Vec<Event>>,
    cache: CacheFixture,
    capture: bool,
}
impl Service {
    fn new(reply: Response, plans: Vec<Attempt>, capture: bool) -> Self {
        Self {
            wire: encode(&reply),
            template: None,
            error: false,
            raw: vec![],
            plans,
            opens: Cell::new(0),
            events: Default::default(),
            cache: Default::default(),
            capture,
        }
    }
    fn mark(&self, kind: &str, path: &Path) {
        if self.capture {
            self.events
                .borrow_mut()
                .push(Event(kind.into(), path.as_os_str().as_bytes().to_vec()))
        }
    }
    fn execute_blocking(&self, r: Request) -> Result<Response> {
        match &r {
            Request::ListCandidates {
                config_root,
                workspace_path,
            } => {
                assert_eq!(config_root, Path::new("/cfg"));
                assert_eq!(workspace_path.as_deref(), Some(Path::new("/work")));
            }
            _ => panic!("unexpected operation"),
        }
        if self.capture {
            self.events
                .borrow_mut()
                .push(Event("list-candidates".into(), encode(&r)));
        }
        if self.error {
            bail!("injected catalog transport failure")
        }
        if self.capture {
            self.events
                .borrow_mut()
                .push(Event("list-reply".into(), self.wire.clone()));
        }
        let mut reply: Response = if let Some(t) = &self.template {
            Response::Candidates {
                sessions: t.clone(),
            }
        } else {
            serde_json::from_slice(&self.wire)?
        };
        if let Response::Candidates { sessions } = &mut reply {
            meter::input_capacity(
                sessions.capacity() * std::mem::size_of::<StorageSessionDescriptor>(),
            );
            for (i, raw) in &self.raw {
                sessions[*i].local_path = Some(PathBuf::from(OsString::from_vec(raw.clone())));
            }
        }
        meter::checkpoint(1);
        Ok(reply)
    }
}
fn vec_bytes<T>(v: &Vec<T>) -> usize {
    v.capacity() * std::mem::size_of::<T>()
}
fn locator() -> SessionLocator {
    SessionLocator {
        session_id: Uuid::from_u128(43),
        key: "selected-fixture".into(),
    }
}
fn snapshot() -> StorageSnapshot {
    StorageSnapshot {
        session: locator(),
        snapshot_id: "immutable".into(),
        revision: StorageRevision {
            session_seq: 3,
            history_revision: 2,
        },
        content_sha256: "a".repeat(64),
    }
}
struct Opened {
    descriptor: StorageSessionDescriptor,
    path: PathBuf,
    plan: Attempt,
    service: Rc<Service>,
    writes: RefCell<BTreeMap<String, Value>>,
}
impl Opened {
    fn new(path: PathBuf, plan: Attempt, service: Rc<Service>) -> Self {
        Self {
            descriptor: descriptor(43, 0, None, false, 1, 1, 1),
            path,
            plan,
            service,
            writes: Default::default(),
        }
    }
    fn session_dir(&self) -> &Path {
        &self.path
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
        Ok(snapshot())
    }
    fn request(&self, req: Request) -> Result<Response> {
        match req {
            Request::ReadCache {
                session,
                key,
                source,
            } => {
                assert_eq!(session, self.descriptor.session);
                assert!(source.is_none());
                if self.service.capture {
                    self.service
                        .events
                        .borrow_mut()
                        .push(Event("cache-read".into(), key.as_bytes().to_vec()))
                }
                let val = self
                    .writes
                    .borrow()
                    .get(&key)
                    .cloned()
                    .or_else(|| match self.plan {
                        Attempt::Warm(_) | Attempt::EmptyCache(_) => {
                            self.service.cache.docs.get(&key).cloned()
                        }
                        _ => None,
                    });
                Ok(Response::Metadata {
                    document: val.map(|value| StorageMetadataDocument {
                        value,
                        etag: "opaque".into(),
                    }),
                })
            }
            Request::WriteCache {
                session,
                key,
                source,
                value,
            } => {
                assert_eq!(session, self.descriptor.session);
                assert_eq!(source, snapshot());
                if self.service.capture {
                    self.service
                        .events
                        .borrow_mut()
                        .push(Event("cache-write".into(), key.as_bytes().to_vec()))
                }
                self.writes.borrow_mut().insert(key, value);
                Ok(Response::CacheWritten {
                    etag: Some("opaque".into()),
                })
            }
            _ => panic!("unexpected cache operation"),
        }
    }
}
fn encode(v: &impl Serialize) -> Vec<u8> {
    serde_json::to_vec(v).unwrap()
}
fn canonical(i: usize) -> CanonicalMessage {
    CanonicalMessage {
        id: Uuid::from_u128(i as u128),
        role: MessageRole::User,
        phase: None,
        parts: vec![CanonicalPart {
            part_id: Uuid::from_u128(i as u128 + 100_000),
            scope: PartScope::Conversation,
            provenance: PartProvenance::User,
            payload: ContentPart::Text {
                text: format!("genuine typed row {i}"),
            },
        }],
        name: None,
        tool_call_id: None,
        metadata: Value::Null,
    }
}
fn transcript(i: usize) -> AppTranscriptMessage {
    AppTranscriptMessage {
        message_id: Some(Uuid::from_u128(i as u128)),
        timestamp_ms: Some(13),
        phase: None,
        role: "user".into(),
        text: format!("genuine typed row {i}"),
        images: vec![],
        tool: None,
        subagent: None,
        streaming: false,
    }
}
fn descriptor(
    i: usize,
    t: i64,
    path: Option<PathBuf>,
    child: bool,
    k: usize,
    w: usize,
    l: usize,
) -> StorageSessionDescriptor {
    StorageSessionDescriptor {
        session: if i == 43 && path.is_none() && k == 1 {
            locator()
        } else {
            SessionLocator {
                session_id: Uuid::from_u128(i as u128),
                key: format!("s{i:06}{}", "k".repeat(k)),
            }
        },
        parent_session_id: child.then(|| Uuid::from_u128(43)),
        workspace_path: PathBuf::from(format!("/work/{}", "w".repeat(w))),
        local_path: path,
        record_location: (l > 0).then(|| PathBuf::from(format!("/physical/{}", "j".repeat(l)))),
        created_at_ms: t,
        updated_at_ms: t,
    }
}
fn digest(bytes: &[u8]) -> String {
    ring::digest::digest(&ring::digest::SHA256, bytes)
        .as_ref()
        .iter()
        .map(|b| format!("{b:02x}"))
        .collect()
}
fn allocations() {
    for (n, shape, k, w, l, path_len, order) in [
        (0, 0, 0, 0, 0, 0, "ordered"),
        (1, 0, 0, 0, 0, 0, "ordered"),
        (31, 0, 0, 0, 0, 0, "ordered"),
        (32, 0, 0, 0, 0, 0, "ordered"),
        (33, 0, 0, 0, 0, 0, "reverse"),
        (128, 0, 10, 68, 40, 24, "ordered"),
        (128, 0, 10, 68, 40, 24, "shuffle"),
        (128, 1, 10, 68, 40, 24, "ordered"),
        (128, 2, 10, 68, 40, 24, "ordered"),
        (4096, 0, 1, 1, 0, 1, "ordered"),
        (4096, 0, 1, 1, 0, 1, "shuffle"),
        (4096, 0, 1, 1, 0, 200, "shuffle"),
        (4096, 0, 1024, 512, 1200, 200, "shuffle"),
        (4096, 3, 1, 1, 0, 1, "shuffle"),
        (4096, 1, 1, 1, 0, 1, "ordered"),
        (4096, 2, 1, 1, 0, 1, "ordered"),
        (4096, 4, 10, 67, 39, 20, "reverse"),
    ] {
        for ingress in ["json", "typed"] {
            let s = || allocation_service(n, shape, k, w, l, path_len, order, ingress);
            let a = stock::alloc(s());
            let b = candidate::alloc(s());
            assert_eq!(a.0, b.0);
            assert_eq!(a.1.checkpoint[1], b.1.checkpoint[1]);
            // Guard both direct and extra-conservative moved-allocation overlap.
            assert!(
                b.1.peak <= a.1.peak
                    && b.1.peak_with_moved_realloc_overlap <= a.1.peak_with_moved_realloc_overlap,
                "peak regression: {n} {shape} {order} {ingress}, {a:?}/{b:?}"
            );
            if n >= 32 && shape == 0 && order == "ordered" {
                assert!(!a.1.sort_called && !b.1.sort_called);
            }
            if n >= 128 && a.0 > 0 {
                assert!(
                    a.1.checkpoint[4] >= b.1.checkpoint[4] + n * 32
                        && a.1.checkpoint[5] >= b.1.checkpoint[5] + n * 32,
                    "material live change: {a:?}/{b:?}"
                );
            }
            println!(
                "{ingress}/{n}/{shape}/{k}/{w}/{l}/{path_len}/{order}: attempts={}; stock={:?}; candidate={:?}",
                a.0, a.1, b.1
            );
        }
    }
    println!("ALLOCATION PASS")
}
fn allocation_service(
    n: usize,
    shape: u8,
    k: usize,
    w: usize,
    l: usize,
    path_len: usize,
    order: &str,
    ingress: &str,
) -> Rc<Service> {
    let rows = (0..n)
        .map(|i| {
            // Odd-multiply permutation for the power-of-two shuffled populations.
            let v = match order {
                "ordered" => n - i,
                "reverse" => i + 1,
                "shuffle" => 1 + ((i * 37 + 13) % n),
                _ => unreachable!(),
            };
            descriptor(
                v,
                v as i64,
                if shape == 2 || (shape == 3 && v % 5 == 0) {
                    None
                } else {
                    Some(PathBuf::from(format!(
                        "/catalog/s{v:06}{}",
                        "p".repeat(path_len)
                    )))
                },
                shape == 1 || (shape == 3 && v % 7 == 0),
                k,
                w,
                l,
            )
        })
        .collect();
    let plans = if shape == 4 {
        vec![Attempt::Cold(0), Attempt::Cold(0), Attempt::Cold(1)]
    } else {
        vec![]
    };
    if ingress == "typed" {
        let mut s = Service::new(Response::Done, plans, false);
        s.template = Some(rows);
        Rc::new(s)
    } else {
        Rc::new(Service::new(
            Response::Candidates { sessions: rows },
            plans,
            false,
        ))
    }
}
fn main() {
    match std::env::args().nth(1).as_deref() {
        Some("semantics") => {
            let a = stock::semantics();
            let b = candidate::semantics();
            assert_eq!(a.len(), b.len());
            for ((an, ar), (bn, br)) in a.iter().zip(&b) {
                assert!(an == bn && ar == br, "mismatch for {an}");
                println!("{an}: {} {}", ar.len(), digest(ar))
            }
            println!("SEMANTICS PASS");
        }
        Some("allocation") => allocations(),
        _ => panic!("semantics | allocation"),
    }
}
