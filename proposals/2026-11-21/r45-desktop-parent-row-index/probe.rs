#![allow(dead_code)]
#[path = "src/conversations.rs"]
mod conversations;
mod agents {
    pub(crate) mod codex {
        include!("src/agents/codex/types.rs");
    }
}
use conversations::{ConversationSummary, from_proteus};
use proteus_contracts::{
    app_protocol::{AppSessionActivity, AppSessionSummary},
    domain::SessionId,
};
use proteus_tabs::ChatKey;
use std::collections::hash_map::DefaultHasher;
use std::hash::{Hash, Hasher};
use std::hint::black_box;
use std::time::Instant;

#[cfg(count)]
mod accounting {
    use std::alloc::{GlobalAlloc, Layout, System};
    use std::sync::atomic::{AtomicUsize, Ordering::Relaxed};
    struct Counter;
    static CALLS: AtomicUsize = AtomicUsize::new(0);
    static BYTES: AtomicUsize = AtomicUsize::new(0);
    #[global_allocator]
    static ALLOCATOR: Counter = Counter;
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

fn sample(i: usize, n: usize, name: &str) -> AppSessionSummary {
    let parent = match name {
        "one" if i == n / 2 => Some(n - 1),
        "siblings" if i % 2 != 0 => Some(0),
        "forest" if i % 8 != 0 => Some(i - i % 8),
        "chain" if i > 0 => Some(i - 1),
        "missing" if i > 0 => Some(n + i),
        _ => None,
    };
    let mut row = AppSessionSummary::new(
        format!("/data/local/share/Proteus/sessions/session-{i:032x}").into(),
        SessionId::from_u128(i as u128),
        format!("/projects/{}", i % 11).into(),
        i + 1,
        Some(i as u64),
        (i % 3 != 0).then(|| format!("preview {i}")),
    );
    row.parent_session_id = parent.map(|id| SessionId::from_u128(id as u128));
    if i % 13 == 0 {
        row.activity = Some(AppSessionActivity::from_counts(i % 4, i % 5, 0));
    }
    row
}
fn parity(input: &[AppSessionSummary], output: &[ConversationSummary]) {
    assert_eq!(input.len(), output.len());
    for (row, out) in input.iter().zip(output) {
        assert_eq!(out.key, ChatKey::Proteus(row.session_dir.clone()));
        assert_eq!(out.proteus_session_id, Some(row.session_id));
        let parent = row.parent_session_id.and_then(|id| {
            input
                .iter()
                .rev()
                .find(|s| s.session_id == id)
                .map(|s| ChatKey::Proteus(s.session_dir.clone()))
        });
        assert_eq!(out.parent, parent);
        assert_eq!(
            (
                &out.workspace_path,
                out.message_count,
                out.updated_at_ms,
                &out.preview,
                &out.activity
            ),
            (
                &row.workspace_path,
                row.message_count,
                row.updated_at_ms,
                &row.preview,
                &row.activity
            )
        );
    }
}
fn main() {
    let arm = std::env::args().nth(1).unwrap();
    for (name, n) in [
        ("empty", 0),
        ("roots", 16),
        ("roots", 4096),
        ("one", 4096),
        ("siblings", 4096),
        ("forest", 4096),
        ("chain", 4096),
        ("missing", 128),
    ] {
        let input: Vec<_> = (0..n).map(|i| sample(i, n, name)).collect();
        let output = from_proteus(input.clone());
        parity(&input, &output);
        let mut h = DefaultHasher::new();
        for row in output {
            row.key.hash(&mut h);
            row.parent.hash(&mut h);
        }
        let digest = h.finish();
        #[cfg(count)]
        {
            let data = input.clone();
            let (a, b) = accounting::read();
            let rows = from_proteus(black_box(data));
            let (c, d) = accounting::read();
            black_box(&rows);
            println!("alloc\t{arm}\t{name}\t{n}\t{digest}\t{}\t{}", c - a, d - b);
        }
        #[cfg(not(count))]
        {
            let mut t = Vec::new();
            for _ in 0..22 {
                let data = input.clone();
                let begin = Instant::now();
                let rows = from_proteus(black_box(data));
                t.push(begin.elapsed().as_nanos());
                black_box(&rows);
            }
            t.remove(0);
            t.sort_unstable();
            println!("time\t{arm}\t{name}\t{n}\t{digest}\t{}", t[t.len() / 2]);
        }
    }
}
