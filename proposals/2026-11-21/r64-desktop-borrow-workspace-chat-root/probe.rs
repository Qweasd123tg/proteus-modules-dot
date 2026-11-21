#![allow(dead_code)]

use desktop_workspace_chat_root_probe::{
    conversations::ConversationSummary,
    {candidate, stock},
};
use proteus_tabs::{ChatKey, ChatSpaces, TabLayout};
use std::hint::black_box;

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

fn key(id: usize, codex: bool) -> ChatKey {
    if codex {
        ChatKey::Codex(format!("opaque:profile:{id}"))
    } else {
        ChatKey::Proteus(format!("/synthetic/session/{id}").into())
    }
}

fn row(key: ChatKey, parent: Option<ChatKey>) -> ConversationSummary {
    ConversationSummary {
        key,
        proteus_session_id: None,
        parent,
        workspace_path: "/synthetic/project".into(),
        message_count: 0,
        updated_at_ms: None,
        preview: None,
        activity: None,
    }
}

fn saved() -> ChatSpaces {
    let mut layout = TabLayout::default();
    layout.open("codex:saved:owner", |_| false);
    layout.open(&key(51, true).tab_id(), |_| false);
    layout.open(&key(51, false).tab_id(), |_| false);
    layout.activate(
        layout.pane_of("codex:saved:owner").unwrap(),
        "codex:saved:owner",
    );
    ChatSpaces::from_layout(layout)
}

fn check(rows: &[ConversationSummary], spaces: &ChatSpaces, requested: &ChatKey) {
    assert_eq!(
        stock::resolve_space_root(rows, spaces, requested),
        candidate::resolve_space_root(rows, spaces, requested),
        "{rows:?} requested {requested:?}",
    );
}

fn parity() {
    let empty = ChatSpaces::default();
    let saved = saved();
    assert_eq!(
        saved.owner_of_chat(&key(51, false).tab_id()),
        Some("codex:saved:owner")
    );
    let mut count = 0;
    for n in 0..=5usize {
        let radix = n + 2;
        for encoded in 0..radix.pow(n as u32) {
            for mixed in [false, true] {
                let key_at = |i: usize| key(i, !mixed || i % 2 == 1);
                let mut encoded = encoded;
                let rows: Vec<_> = (0..n)
                    .map(|i| {
                        let digit = encoded % radix;
                        encoded /= radix;
                        let link = match digit {
                            0 => None,
                            d if d == n + 1 => Some(key(51, !mixed)),
                            d => Some(key_at(d - 1)),
                        };
                        row(key_at(i), link)
                    })
                    .collect();
                for ix in 0..n {
                    check(&rows, &empty, &key_at(ix));
                    count += 1;
                }
                for request in [key(51, false), key(51, true)] {
                    check(&rows, &empty, &request);
                    check(&rows, &saved, &request);
                    count += 2;
                }
            }
        }
    }
    let third = key(71, true);
    let rows = [
        row(
            ChatKey::Codex("/synthetic/session/7".into()),
            Some(third.clone()),
        ),
        row(key(7, false), None),
        row(key(7, false), Some(third.clone())),
        row(third, None),
    ];
    for row in &rows {
        check(&rows, &saved, &row.key);
        count += 1;
    }
    assert!(count > 300_000);
    println!("PASS {count} exact serialized workspace root decisions");
}

type Resolve = fn(&[ConversationSummary], &ChatSpaces, &ChatKey) -> String;

fn measure(
    arm: &str,
    name: &str,
    resolve: Resolve,
    rows: &[ConversationSummary],
    spaces: &ChatSpaces,
    requested: &ChatKey,
) {
    let before = counter::read();
    let picked = black_box(resolve(
        black_box(rows),
        black_box(spaces),
        black_box(requested),
    ));
    let after = counter::read();
    black_box(&picked);
    println!(
        "alloc\t{arm}\t{name}\t{}\t{}",
        after.0 - before.0,
        after.1 - before.1
    );
}

fn allocations(arm: &str) {
    let resolve: Resolve = match arm {
        "stock" => stock::resolve_space_root,
        "candidate" => candidate::resolve_space_root,
        _ => panic!("data arm"),
    };
    let spaces = saved();
    let direct = [row(key(0, false), None)];
    let mut chain: Vec<_> = (0..48)
        .map(|i| {
            row(
                key(i, i % 3 == 2),
                i.checked_sub(1).map(|i| key(i, i % 3 == 2)),
            )
        })
        .collect();
    let cycle = [
        row(key(0, true), Some(key(1, true))),
        row(key(1, true), Some(key(0, true))),
    ];
    let missing = [row(key(0, false), Some(key(51, true)))];
    for (name, rows, request) in [
        ("listed-root", direct.as_slice(), key(0, false)),
        ("one-parent", chain.as_slice(), key(1, false)),
        ("two-parents-cross-driver", chain.as_slice(), key(2, true)),
        ("deep-47-parents", chain.as_slice(), key(47, true)),
        ("missing-parent", missing.as_slice(), key(0, false)),
        ("cycle", cycle.as_slice(), key(0, true)),
        ("unlisted-saved-owner", chain.as_slice(), key(51, true)),
        ("unlisted-no-owner", chain.as_slice(), key(80, false)),
    ] {
        measure(arm, name, resolve, rows, &spaces, &request);
    }
    black_box(&mut chain);
}

fn main() {
    let arm = std::env::args().nth(1).unwrap();
    if arm == "parity" {
        parity();
    } else {
        allocations(&arm);
    }
}
