#![allow(dead_code, unused_imports)]

mod ui;
use proteus_contracts::app_protocol::{AppTranscriptBase, AppTranscriptCursor};
use proteus_tabs::ChatKey;
use std::hint::black_box;
use ui::chat::history::{baseline, candidate};
use ui::chat::{Session, scroller::HeightCacheKey};
use uuid::Uuid;

mod counter {
    use std::alloc::{GlobalAlloc, Layout, System};
    use std::sync::atomic::{AtomicUsize, Ordering::Relaxed};
    struct Counter;
    static CALLS: AtomicUsize = AtomicUsize::new(0);
    static BYTES: AtomicUsize = AtomicUsize::new(0);
    #[global_allocator]
    static A: Counter = Counter;
    unsafe impl GlobalAlloc for Counter {
        unsafe fn alloc(&self, layout: Layout) -> *mut u8 {
            CALLS.fetch_add(1, Relaxed);
            BYTES.fetch_add(layout.size(), Relaxed);
            unsafe { System.alloc(layout) }
        }
        unsafe fn dealloc(&self, p: *mut u8, layout: Layout) {
            unsafe { System.dealloc(p, layout) }
        }
        unsafe fn realloc(&self, p: *mut u8, layout: Layout, new: usize) -> *mut u8 {
            CALLS.fetch_add(1, Relaxed);
            BYTES.fetch_add(new, Relaxed);
            unsafe { System.realloc(p, layout, new) }
        }
    }
    pub fn read() -> (usize, usize) {
        (CALLS.load(Relaxed), BYTES.load(Relaxed))
    }
}

fn session(key: ChatKey, durable_id: Option<Uuid>, process: &str) -> Session {
    Session {
        key,
        snapshot_identity: durable_id.map(|id| (id, process.to_owned())),
    }
}

fn cursor(revision: &str, before: usize, base: Option<(&str, usize)>) -> AppTranscriptCursor {
    AppTranscriptCursor {
        revision: revision.into(),
        before,
        base: base.map(|(old, common_prefix)| AppTranscriptBase {
            revision: old.into(),
            common_prefix,
        }),
    }
}

fn parity() {
    let mut keys = vec![
        ChatKey::Proteus("/synthetic/normal-session".into()),
        ChatKey::Proteus("/synthetic//session/".into()),
        ChatKey::Proteus("/synthetic/каталог/🦀".into()),
        ChatKey::Proteus("/synthetic/colon:containing\npath".into()),
        ChatKey::Codex("thread:opaque:child".into()),
        ChatKey::Codex("thread:мир:🦀".into()),
        ChatKey::Codex("".into()),
    ];
    for n in [
        0, 1, 27, 28, 29, 31, 32, 49, 50, 51, 55, 56, 57, 63, 64, 65, 127, 128, 129, 4096,
    ] {
        keys.push(ChatKey::Codex("a".repeat(n)));
        keys.push(ChatKey::Proteus(
            format!("/synthetic/{}é", "b".repeat(n)).into(),
        ));
    }
    #[cfg(unix)]
    {
        use std::ffi::OsString;
        use std::os::unix::ffi::OsStringExt;
        keys.push(ChatKey::Proteus(
            OsString::from_vec(b"/synthetic/lossy-\xff-directory".to_vec()).into(),
        ));
    }
    let mut cases = 0;
    for key in keys {
        for id in [
            None,
            Some(Uuid::nil()),
            Some(Uuid::max()),
            Some(Uuid::from_u128(1)),
            Some(Uuid::from_u128(0xabcdef)),
            Some(Uuid::from_u128(0x997766554433221100ff1144aabbccdd)),
        ] {
            let old_process = session(key.clone(), id, "old-process");
            let new_process = session(key.clone(), id, "new-process");
            for before in [0, 1, 2, 49, 50, 550, usize::MAX] {
                for revision in ["", "canonical", "synthetic:new:повтор"] {
                    for base in [
                        None,
                        Some(("", 0)),
                        Some(("old", 1)),
                        Some(("previous", 42)),
                        Some(("previous", usize::MAX)),
                    ] {
                        let cursor = cursor(revision, before, base);
                        let old = baseline(&old_process, &cursor);
                        let new = candidate(&old_process, &cursor);
                        assert_eq!(old, new);
                        assert_eq!(new, candidate(&new_process, &cursor));
                        cases += 1;
                    }
                }
            }
        }
    }
    #[cfg(unix)]
    assert_eq!(cases, 30_240);
    #[cfg(not(unix))]
    assert_eq!(cases, 29_610);
    println!("PASS {cases} exact complete history keys plus reconnect-generation comparisons");
}

type DeriveKey = fn(&Session, &AppTranscriptCursor) -> Option<HeightCacheKey>;

fn measure(arm: &str, name: &str, derive: DeriveKey, s: &Session, c: &AppTranscriptCursor) {
    let before = counter::read();
    let key = black_box(derive(black_box(s), black_box(c)));
    let after = counter::read();
    black_box(&key);
    println!(
        "alloc\t{arm}\t{name}\t{}\t{}",
        after.0 - before.0,
        after.1 - before.1
    );
}

fn allocations(arm: &str) {
    let derive: DeriveKey = match arm {
        "stock" => baseline,
        "candidate" => candidate,
        _ => panic!("data arm"),
    };
    let key = ChatKey::Proteus("/synthetic/projects/lab/session-00000000-0000-0000".into());
    let id = Some(Uuid::from_u128(0xabcdef));
    let standard = cursor("canonical-v12", 550, None);
    let common_prefix = cursor("canonical-v13", 550, Some(("canonical-v12", 536)));
    for (case, key, id, cursor) in [
        ("restored-history", key.clone(), id, &standard),
        ("rewritten-suffix", key.clone(), id, &common_prefix),
        (
            "unicode-tab",
            ChatKey::Proteus("/synthetic/каталог/🦀".into()),
            id,
            &standard,
        ),
        (
            "opaque-tab-control",
            ChatKey::Codex("thread:opaque:child".into()),
            id,
            &standard,
        ),
        ("unidentified-chat", key, None, &standard),
    ] {
        let session = session(key, id, "idle-restored-process");
        measure(arm, case, derive, &session, cursor);
    }
}

fn main() {
    let arm = std::env::args().nth(1).unwrap();
    if arm == "parity" {
        parity();
    } else {
        allocations(&arm);
    }
}
