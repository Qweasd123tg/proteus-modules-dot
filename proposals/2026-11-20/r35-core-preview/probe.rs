use anyhow::{Result, bail, ensure};
use proteus_contracts::{
    app_protocol::AppSessionSummary,
    contracts::{
        SessionLocator, SessionStorageRequest as Request, SessionStorageResponse as Response,
        StorageSessionDescriptor,
    },
    domain::{SessionId, ToolResult, new_call_id, new_session_id},
    model_standard::{CanonicalMessage, ContentPart, MessageRole},
};
use std::{
    alloc::{GlobalAlloc, Layout, System},
    hint::black_box,
    path::Path,
    sync::atomic::{AtomicUsize, Ordering::Relaxed},
};

struct Count;
#[global_allocator]
static ALLOC: Count = Count;
static CALLS: AtomicUsize = AtomicUsize::new(0);
static BYTES: AtomicUsize = AtomicUsize::new(0);
unsafe impl GlobalAlloc for Count {
    unsafe fn alloc(&self, l: Layout) -> *mut u8 {
        CALLS.fetch_add(1, Relaxed);
        BYTES.fetch_add(l.size(), Relaxed);
        unsafe { System.alloc(l) }
    }
    unsafe fn dealloc(&self, p: *mut u8, l: Layout) {
        unsafe { System.dealloc(p, l) }
    }
    unsafe fn realloc(&self, p: *mut u8, l: Layout, n: usize) -> *mut u8 {
        CALLS.fetch_add(1, Relaxed);
        BYTES.fetch_add(n, Relaxed);
        unsafe { System.realloc(p, l, n) }
    }
}
struct RemoteSessionStore {
    descriptor: StorageSessionDescriptor,
}
impl RemoteSessionStore {
    fn request(&self, r: Request) -> Result<Response> {
        let Request::Describe { session } = r else {
            panic!("unexpected side effect")
        };
        assert_eq!(session, self.descriptor.session);
        Ok(Response::Session {
            descriptor: self.descriptor.clone(),
        })
    }
    fn session_dir(&self) -> &Path {
        self.descriptor.local_path.as_deref().unwrap()
    }
    fn session_id(&self) -> SessionId {
        self.descriptor.session.session_id
    }
    fn parent_session_id(&self) -> Option<SessionId> {
        self.descriptor.parent_session_id
    }
}

fn main() {
    let store = RemoteSessionStore {
        descriptor: StorageSessionDescriptor {
            session: SessionLocator {
                session_id: new_session_id(),
                key: "fixture".into(),
            },
            parent_session_id: Some(new_session_id()),
            workspace_path: "/workspace".into(),
            local_path: Some("/session".into()),
            record_location: None,
            created_at_ms: 1,
            updated_at_ms: 123,
        },
    };
    println!("fixture,variant,pass,iterations,alloc_or_realloc_per_call,requested_bytes_per_call");
    for (case, msg, iterations) in [
        (
            "64B-ascii",
            CanonicalMessage::text(MessageRole::User, "x".repeat(64)),
            1000,
        ),
        (
            "1MiB-ascii",
            CanonicalMessage::text(MessageRole::User, "x".repeat(1 << 20)),
            100,
        ),
        (
            "16MiB-ascii",
            CanonicalMessage::text(MessageRole::User, "x".repeat(16 << 20)),
            8,
        ),
        (
            "1MiB-unicode",
            CanonicalMessage::text(MessageRole::Assistant, "🦀".repeat(1 << 18)),
            100,
        ),
        (
            "1MiB-tool",
            CanonicalMessage::new(
                MessageRole::Tool,
                vec![ContentPart::ToolResult {
                    result: ToolResult::ok(new_call_id(), "x".repeat(1 << 20)),
                }],
            ),
            100,
        ),
        (
            "1MiB-blank",
            CanonicalMessage::text(MessageRole::User, " ".repeat(1 << 20)),
            10,
        ),
    ] {
        let msgs = [msg];
        let expected = stock::summary(&store, &msgs).unwrap();
        assert_eq!(expected, candidate::summary(&store, &msgs).unwrap());
        type Fn = fn(&RemoteSessionStore, &[CanonicalMessage]) -> Result<AppSessionSummary>;
        for (pass, (variant, f)) in [
            ("stock", stock::summary as Fn),
            ("candidate", candidate::summary),
            ("candidate", candidate::summary),
            ("stock", stock::summary),
        ]
        .into_iter()
        .enumerate()
        {
            let nc = CALLS.load(Relaxed);
            let nb = BYTES.load(Relaxed);
            for _ in 0..iterations {
                black_box(f(black_box(&store), black_box(&msgs)).unwrap());
            }
            let c = CALLS.load(Relaxed) - nc;
            let b = BYTES.load(Relaxed) - nb;
            assert!(c % iterations == 0 && b % iterations == 0);
            println!(
                "{case},{variant},{pass},{iterations},{},{}",
                c / iterations,
                b / iterations
            );
        }
    }
}
