#![allow(dead_code)]
#[path = "src/conversations.rs"]
mod conversations;
#[path = "src/sessions.rs"]
mod sessions;
mod agents {
    pub(crate) mod codex {
        include!("src/agents/codex/types.rs");
    }
}

use conversations::ConversationSummary;
use proteus_tabs::ChatKey;
use sessions::{Listing, Row, SessionMarks, View};
use std::collections::hash_map::DefaultHasher;
use std::hash::{Hash, Hasher};
use std::hint::black_box;
use std::time::Instant;

fn fixture(n: usize, projects: usize, child_every: usize) -> Vec<ConversationSummary> {
    let key = |i| ChatKey::Codex(format!("id:{i}"));
    (0..n)
        .map(|i| ConversationSummary {
            key: key(i),
            proteus_session_id: None,
            parent: (child_every != 0 && i % child_every == 1).then(|| key(i - 1)),
            workspace_path: format!("/projects/{}", i % projects).into(),
            message_count: i % 11,
            updated_at_ms: Some(((i * 7919) % (3 * n / 2)) as u64),
            preview: Some(format!("Thread {i}")),
            activity: None,
        })
        .collect()
}

fn digest(list: &Listing<'_>) -> u64 {
    fn rows(group: &[Row<'_>], h: &mut DefaultHasher) {
        group.len().hash(h);
        for row in group {
            row.summary.key.hash(h);
            rows(&row.children, h);
        }
    }
    let mut h = DefaultHasher::new();
    for p in &list.projects {
        p.path.hash(&mut h);
        rows(&p.rows, &mut h);
    }
    list.archived_count.hash(&mut h);
    rows(&list.pinned, &mut h);
    rows(&list.archived, &mut h);
    h.finish()
}

fn main() {
    let arm = std::env::args().nth(1).expect("arm");
    for &(n, projects, child_every, search) in &[
        (32, 1, 0, ""),
        (4096, 1, 0, ""),
        (4096, 8, 0, ""),
        (4096, 256, 0, ""),
        (4096, 256, 5, ""),
        (4096, 256, 5, "Thread 1"),
    ] {
        let data = fixture(n, projects, child_every);
        let marks = SessionMarks::default();
        let view = View {
            archived: false,
            search,
        };
        let iters = if n < 128 { 24 } else { 1 };
        let mut times = Vec::new();
        let reference = digest(&marks.arrange(&data, &view));
        for _ in 0..5 {
            let mut ns = 0;
            for _ in 0..iters {
                let start = Instant::now();
                let list = black_box(marks.arrange(black_box(&data), black_box(&view)));
                ns += start.elapsed().as_nanos();
                assert_eq!(digest(&list), reference);
            }
            times.push(ns / iters);
        }
        times.sort_unstable();
        println!(
            "{arm}\t{n}\t{projects}\t{child_every}\t{}\t{reference:016x}\t{}",
            if search.is_empty() { "all" } else { "filter" },
            times[2]
        );
    }
}
