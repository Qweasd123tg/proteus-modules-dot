extern crate self as proteus_module_sdk; // Only the unchanged SDK re-export.
pub use proteus_contracts as contracts;
mod display_reply;

use contracts::{
    contracts::{
        SessionLocator, SessionStorageRequest, SessionStorageResponse, StorageDisplaySnapshot,
    },
    domain::ImageRef,
    model_standard::{CanonicalMessage, ContentPart, MessageRole},
};
use serde_json::{Value, json};
use std::{
    alloc::{GlobalAlloc, Layout, System},
    cell::Cell,
    io::Write,
    path::Path,
};

#[derive(Clone, Copy, Default)]
struct Meter {
    events: usize,
    requested: usize,
    live: isize,
    peak: isize,
}
thread_local! { static MARK: Cell<Option<Meter>> = const { Cell::new(None) }; }
fn update(bytes: usize, delta: isize, event: bool) {
    let _ = MARK.try_with(|slot| {
        if let Some(mut m) = slot.get() {
            m.events += event as usize;
            m.requested += bytes;
            m.live += delta;
            m.peak = m.peak.max(m.live);
            slot.set(Some(m));
        }
    });
}
struct Heap;
unsafe impl GlobalAlloc for Heap {
    unsafe fn alloc(&self, l: Layout) -> *mut u8 {
        let a = unsafe { System.alloc(l) };
        if !a.is_null() {
            update(l.size(), l.size() as isize, true);
        }
        a
    }
    unsafe fn alloc_zeroed(&self, l: Layout) -> *mut u8 {
        let a = unsafe { System.alloc_zeroed(l) };
        if !a.is_null() {
            update(l.size(), l.size() as isize, true);
        }
        a
    }
    unsafe fn realloc(&self, p: *mut u8, l: Layout, n: usize) -> *mut u8 {
        let a = unsafe { System.realloc(p, l, n) };
        if !a.is_null() {
            update(n, n as isize - l.size() as isize, true);
        }
        a
    }
    unsafe fn dealloc(&self, p: *mut u8, l: Layout) {
        update(0, -(l.size() as isize), false);
        unsafe { System.dealloc(p, l) };
    }
}
#[global_allocator]
static HEAP: Heap = Heap;

fn parse(input: &[u8]) -> SessionStorageResponse {
    let mut v: Value = serde_json::from_slice(input).unwrap();
    serde_json::from_value(v["result"].take()).unwrap()
}

fn projection(v: &mut SessionStorageResponse) -> &mut StorageDisplaySnapshot {
    match v {
        SessionStorageResponse::DisplaySnapshot {
            projection: Some(p),
        } => p,
        _ => panic!("fixture must be an actual display projection"),
    }
}

fn check_other_parts(bytes: &[u8]) {
    let mut r = parse(bytes);
    let working = &mut projection(&mut r).state.conversation.messages;
    let mut row = CanonicalMessage::new(
        MessageRole::User,
        vec![
            ContentPart::Text {
                text: "зеро\t\"\n\u{0}".into(),
            },
            ContentPart::ReasoningSummary {
                text: "keep separate".into(),
            },
            ContentPart::Text {
                text: String::new(),
            },
            ContentPart::Image {
                image: ImageRef {
                    id: "fixture".into(),
                    name: "picture".into(),
                    mime_type: "image/png".into(),
                    path: "/local/fixture.png".into(),
                },
            },
            ContentPart::Opaque {
                format: "fixture".into(),
                data: json!({"z":[false,1.25,"ü"],"a":null}),
            },
            ContentPart::Text {
                text: "tail".into(),
            },
        ],
    );
    row.metadata = json!({"z":0,"a":[true,2,"a\t\n"]});
    row.name = Some("fixture".into());
    *working = vec![
        row,
        CanonicalMessage::from_parts(MessageRole::Assistant, vec![]),
    ];
    let expected = serde_json::to_value(&r).unwrap();
    let actual = display_reply::into_value(r).unwrap();
    assert_eq!(actual, expected);
    // Value equality alone does not protect preserve_order.
    assert_eq!(
        serde_json::to_vec(&actual).unwrap(),
        serde_json::to_vec(&expected).unwrap()
    );
    let r = SessionStorageResponse::DisplaySnapshot { projection: None };
    assert_eq!(
        serde_json::to_value(&r).unwrap(),
        display_reply::into_value(r).unwrap()
    );
    let r = SessionStorageResponse::Done;
    assert_eq!(
        serde_json::to_value(&r).unwrap(),
        display_reply::into_value(r).unwrap()
    );
}

struct Digest(ring::digest::Context);
impl Write for Digest {
    fn write(&mut self, bs: &[u8]) -> std::io::Result<usize> {
        self.0.update(bs);
        Ok(bs.len())
    }
    fn flush(&mut self) -> std::io::Result<()> {
        Ok(())
    }
}
fn now(mut r: SessionStorageResponse, optimized: bool) -> (Meter, usize, usize, String) {
    let original: Vec<_> = projection(&mut r)
        .state
        .conversation
        .messages
        .iter()
        .map(|m| match &m.parts[0].payload {
            ContentPart::Text { text } => (text.as_ptr() as usize, text.len()),
            _ => panic!("not the no-model 50k corpus"),
        })
        .collect();
    MARK.set(Some(Meter::default()));
    let v = if optimized {
        display_reply::into_value(r).unwrap()
    } else {
        serde_json::to_value(r).unwrap()
    };
    let meter = MARK.replace(None).unwrap();
    let messages = v
        .pointer("/projection/state/conversation/messages")
        .unwrap()
        .as_array()
        .unwrap();
    assert_eq!(messages.len(), original.len());
    assert_eq!(messages.len(), 50_000);
    let mut same = 0;
    let mut text_bytes = 0;
    for (m, (ptr, length)) in messages.iter().zip(original) {
        let t = m
            .pointer("/parts/0/payload/Text/text")
            .unwrap()
            .as_str()
            .unwrap();
        assert_eq!(t.len(), length);
        same += usize::from(ptr == t.as_ptr() as usize);
        text_bytes += length;
    }
    let mut d = Digest(ring::digest::Context::new(&ring::digest::SHA256));
    serde_json::to_writer(&mut d, &v).unwrap();
    let digest =
        d.0.finish()
            .as_ref()
            .iter()
            .map(|b| format!("{b:02x}"))
            .collect::<String>();
    (meter, same, text_bytes, digest)
}
fn qualify(label: &str, make: impl Fn() -> SessionStorageResponse) {
    let (old, old_moved, n, a) = now(make(), false);
    let (new, new_moved, z, c) = now(make(), true);
    assert_eq!((n, &a), (z, &c));
    assert_eq!(old_moved, 0);
    assert_eq!(new_moved, 50_000);
    println!(
        "{label} {n} {old_moved} {new_moved} {} {} {} {} {} {} {a}",
        old.events, old.requested, old.peak, new.events, new.requested, new.peak
    );
    assert_eq!(old.requested - new.requested, n);
    assert_eq!(old.events - new.events, 50_000);
    assert!(old.peak.saturating_sub(new.peak) >= n as isize);
}

fn main() {
    let mut arguments = std::env::args_os().skip(1);
    let path = arguments.next().expect("actual projected worker frame");
    let b = std::fs::read(Path::new(&path)).unwrap();
    check_other_parts(&b);
    qualify("OWNER_FRAME", || parse(&b));
    if let Some(path) = arguments.next() {
        let fixtures: Vec<(String, u32, SessionLocator)> =
            serde_json::from_reader(std::fs::File::open(path).unwrap()).unwrap();
        let (_, _, session) = fixtures
            .into_iter()
            .find(|(k, r, _)| k == "Jsonl" && *r == 4)
            .unwrap();
        qualify("OWNER_NATIVE", || {
            use session_storage::{BackendKind, StorageService};
            let s = StorageService::new(BackendKind::Jsonl);
            let mut r = s
                .execute(SessionStorageRequest::OpenDisplaySnapshot {
                    session: session.clone(),
                })
                .unwrap();
            projection(&mut r).snapshot.snapshot_id = "00000000-0000-0000-0000-000000000000".into();
            r
        });
    }
}
