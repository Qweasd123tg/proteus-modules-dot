use anyhow::{Result, bail, ensure};
use proteus_contracts::{
    app_protocol::AppSessionSummary,
    contracts::{
        SessionLocator, SessionStorageRequest as Request, SessionStorageResponse as Response,
        StorageSessionDescriptor,
    },
    domain::{SessionId, ToolContent, ToolResult, new_session_id},
    model_standard::{CanonicalMessage, ContentPart, MessageRole},
};
use std::{
    alloc::{GlobalAlloc, Layout, System},
    path::Path,
    sync::atomic::{AtomicBool, AtomicUsize, Ordering::Relaxed},
};

mod candidate;
mod stock;

struct RemoteSessionStore {
    descriptor: StorageSessionDescriptor,
    mode: u8,
}

impl RemoteSessionStore {
    fn fixture() -> Self {
        Self {
            descriptor: StorageSessionDescriptor {
                session: SessionLocator {
                    session_id: new_session_id(),
                    key: "s".into(),
                },
                parent_session_id: Some(new_session_id()),
                workspace_path: "w".into(),
                local_path: Some("s".into()),
                record_location: None,
                created_at_ms: 52,
                updated_at_ms: 72,
            },
            mode: 0,
        }
    }
    fn request(&self, req: Request) -> Result<Response> {
        assert!(matches!(req, Request::Describe { session } if session == self.descriptor.session));
        let mut descriptor = self.descriptor.clone();
        match self.mode {
            0 => Ok(Response::Session { descriptor }),
            1 => {
                descriptor.session.key.push('!');
                Ok(Response::Session { descriptor })
            }
            2 => Ok(Response::Candidates { sessions: vec![] }),
            _ => bail!("synthetic read error"),
        }
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

fn msg(role: MessageRole, text: String, variant: usize) -> CanonicalMessage {
    let part = match variant {
        0 => ContentPart::Text { text },
        1 => ContentPart::ReasoningSummary { text },
        2 => ContentPart::Reasoning {
            text,
            signature: Some("signature".into()),
        },
        3 => ContentPart::ToolResult {
            result: ToolResult::ok("a".into(), text),
        },
        4 => ContentPart::ToolResult {
            result: ToolResult::error("b".into(), text),
        },
        5 => ContentPart::ToolResult {
            result: ToolResult::ok("c".into(), "").with_content(vec![ToolContent::Text { text }]),
        },
        _ => ContentPart::Opaque {
            format: "skip".into(),
            data: serde_json::Value::String(text),
        },
    };
    CanonicalMessage::new(role, vec![part])
}

#[test]
fn complete_summary_parity() {
    let s = RemoteSessionStore::fixture();
    let mut inputs = vec![
        String::new(),
        " \t\u{3000}".into(),
        "🙂".into(),
        " 𐄂e\u{301}\n".into(),
        format!("{}  X", "x".repeat(158)),
        format!("{}\u{2003}\u{2003}", "中".repeat(160)),
    ];
    for size in [1, 158, 159, 160, 161, 162, 257] {
        for ch in ['a', 'Ж', '界', '🙂', '\u{301}'] {
            inputs.push(ch.to_string().repeat(size));
        }
    }
    let roles = [
        MessageRole::User,
        MessageRole::Assistant,
        MessageRole::Tool,
        MessageRole::Developer,
        MessageRole::System,
    ];
    let mut checked = 0;
    for text in inputs {
        for role in &roles {
            for variant in 0..7 {
                let current = msg(role.clone(), text.clone(), variant);
                let fallback = msg(MessageRole::Assistant, "earlier".into(), 0);
                let blank = msg(MessageRole::User, "\u{2002}".into(), 1);
                let preferred = msg(MessageRole::User, "late".into(), 2);
                let mut mixed = current.clone();
                mixed.parts.insert(0, blank.parts[0].clone());
                mixed.parts.push(preferred.parts[0].clone());
                for history in [
                    &[current.clone()][..],
                    &[fallback.clone(), blank.clone(), current.clone()][..],
                    &[current.clone(), blank, preferred][..],
                    &[mixed][..],
                ] {
                    let before = stock::summary(&s, history).unwrap();
                    assert_eq!(before, candidate::summary(&s, history).unwrap());
                    checked += 1;
                }
            }
        }
    }
    assert_eq!(
        stock::summary(&s, &[]).unwrap(),
        candidate::summary(&s, &[]).unwrap()
    );
    println!("full DTO comparisons: {}", checked + 1);
    let mut s = s;
    s.descriptor.updated_at_ms = -1;
    s.descriptor.parent_session_id = None;
    assert_eq!(
        stock::summary(&s, &[]).unwrap(),
        candidate::summary(&s, &[]).unwrap()
    );
    for mode in 1..=3 {
        s.mode = mode;
        assert_eq!(
            stock::summary(&s, &[]).unwrap_err().to_string(),
            candidate::summary(&s, &[]).unwrap_err().to_string()
        );
    }
}

struct Counting;
static ON: AtomicBool = AtomicBool::new(false);
static N: AtomicUsize = AtomicUsize::new(0);
static BYTES: AtomicUsize = AtomicUsize::new(0);
fn count(size: usize) {
    if ON.load(Relaxed) {
        N.fetch_add(1, Relaxed);
        BYTES.fetch_add(size, Relaxed);
    }
}
unsafe impl GlobalAlloc for Counting {
    unsafe fn alloc(&self, l: Layout) -> *mut u8 {
        count(l.size());
        unsafe { System.alloc(l) }
    }
    unsafe fn alloc_zeroed(&self, l: Layout) -> *mut u8 {
        count(l.size());
        unsafe { System.alloc_zeroed(l) }
    }
    unsafe fn realloc(&self, p: *mut u8, l: Layout, n: usize) -> *mut u8 {
        count(n);
        unsafe { System.realloc(p, l, n) }
    }
    unsafe fn dealloc(&self, p: *mut u8, l: Layout) {
        unsafe { System.dealloc(p, l) }
    }
}
#[global_allocator]
static ALLOCATOR: Counting = Counting;

#[test]
fn summary_allocation_requests() {
    let s = RemoteSessionStore::fixture();
    let cases = [
        ("text32", "a".repeat(32), 0),
        ("text160", "a".repeat(160), 0),
        ("text161", "a".repeat(161), 0),
        ("text1MiB", "x".repeat(1024 * 1024), 0),
        ("reason1MiB", "🙂".repeat(256 * 1024), 2),
        ("output1MiB", "o".repeat(1024 * 1024), 3),
        ("blank1MiB", " ".repeat(1024 * 1024), 0),
        ("opaque1MiB", "x".repeat(1024 * 1024), 6),
    ];
    println!("fixture,arm,allocs_and_reallocs,bytes_requested");
    for (name, text, v) in cases {
        let messages = [msg(MessageRole::User, text, v)];
        let mut reads = [(0, 0); 4];
        for (i, f) in [
            stock::summary,
            candidate::summary,
            candidate::summary,
            stock::summary,
        ]
        .into_iter()
        .enumerate()
        {
            N.store(0, Relaxed);
            BYTES.store(0, Relaxed);
            ON.store(true, Relaxed);
            let out =
                std::hint::black_box(f(std::hint::black_box(&s), std::hint::black_box(&messages)))
                    .unwrap();
            ON.store(false, Relaxed);
            reads[i] = (N.load(Relaxed), BYTES.load(Relaxed));
            drop(out);
        }
        assert_eq!(reads[0], reads[3]);
        assert_eq!(reads[1], reads[2]);
        assert!(reads[1].1 <= reads[0].1);
        if matches!(name, "text1MiB" | "reason1MiB" | "output1MiB") {
            assert!(reads[0].1 - reads[1].1 >= 1024 * 1024);
        }
        println!("{name},stock,{},{}", reads[0].0, reads[0].1);
        println!("{name},candidate,{},{}", reads[1].0, reads[1].1);
    }
}
