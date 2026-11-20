#![allow(dead_code)]
use std::alloc::{GlobalAlloc, Layout, System};
use std::path::PathBuf;
use std::sync::atomic::{AtomicU64, Ordering::Relaxed};

use proteus_tabs::ChatKey;
mod candidate;
mod codex_types;
mod agents {
    pub mod codex {
        pub use crate::codex_types::*;
    }
}
mod conversations;
mod stock;
use conversations::ConversationSummary;

struct Counting;
static CALLS: AtomicU64 = AtomicU64::new(0);
static BYTES: AtomicU64 = AtomicU64::new(0);
#[global_allocator]
static ALLOC: Counting = Counting;
unsafe impl GlobalAlloc for Counting {
    unsafe fn alloc(&self, l: Layout) -> *mut u8 {
        CALLS.fetch_add(1, Relaxed);
        BYTES.fetch_add(l.size() as u64, Relaxed);
        unsafe { System.alloc(l) }
    }
    unsafe fn alloc_zeroed(&self, l: Layout) -> *mut u8 {
        CALLS.fetch_add(1, Relaxed);
        BYTES.fetch_add(l.size() as u64, Relaxed);
        unsafe { System.alloc_zeroed(l) }
    }
    unsafe fn realloc(&self, p: *mut u8, l: Layout, n: usize) -> *mut u8 {
        CALLS.fetch_add(1, Relaxed);
        BYTES.fetch_add(n as u64, Relaxed);
        unsafe { System.realloc(p, l, n) }
    }
    unsafe fn dealloc(&self, p: *mut u8, l: Layout) {
        unsafe { System.dealloc(p, l) }
    }
}
fn measure<T>(f: impl FnOnce() -> T) -> (T, u64, u64) {
    let a = CALLS.load(Relaxed);
    let b = BYTES.load(Relaxed);
    let result = std::hint::black_box(f());
    (result, CALLS.load(Relaxed) - a, BYTES.load(Relaxed) - b)
}

#[derive(Debug, PartialEq)]
struct Flat<'a> {
    groups: Vec<(PathBuf, Vec<FlatRow<'a>>)>,
    pinned: Vec<FlatRow<'a>>,
    archived: Vec<FlatRow<'a>>,
    archived_count: usize,
}
#[derive(Debug, PartialEq)]
struct FlatRow<'a> {
    summary: &'a ConversationSummary,
    title: Option<&'a str>,
    pinned: bool,
    archived: bool,
    depth: usize,
}
macro_rules! flatten {
    ($mod:ident, $list:ident) => {{
        fn rows<'a>(rows: &'a [$mod::Row<'a>]) -> Vec<FlatRow<'a>> {
            let mut result = Vec::new();
            let mut pending: Vec<_> = rows.iter().rev().map(|row| (0, row)).collect();
            while let Some((depth, row)) = pending.pop() {
                result.push(FlatRow {
                    summary: row.summary,
                    title: row.mark.title.as_deref(),
                    pinned: row.mark.pinned,
                    archived: row.mark.archived,
                    depth,
                });
                pending.extend(row.children.iter().rev().map(|child| (depth + 1, child)));
            }
            result
        }
        Flat {
            groups: $list
                .projects
                .iter()
                .map(|project| (project.path.into(), rows(&project.rows)))
                .collect(),
            pinned: rows(&$list.pinned),
            archived: rows(&$list.archived),
            archived_count: $list.archived_count,
        }
    }};
}

fn rng(s: &mut u64) -> usize {
    *s = s
        .wrapping_mul(6364136223846793005)
        .wrapping_add(1442695040888963407);
    (*s >> 32) as usize
}
fn key(n: usize) -> ChatKey {
    if n % 2 == 0 {
        ChatKey::Proteus(format!("/s/{n}").into())
    } else {
        ChatKey::Codex(format!("codex-thread-{n}"))
    }
}
fn summary(
    n: usize,
    path: String,
    parent: Option<usize>,
    stamp: Option<u64>,
    title: &str,
) -> ConversationSummary {
    ConversationSummary {
        key: key(n),
        proteus_session_id: None,
        parent: parent.map(key),
        workspace_path: path.into(),
        message_count: n % 8,
        updated_at_ms: stamp,
        preview: Some(title.into()),
        activity: None,
    }
}

fn parity() -> usize {
    let mut count = 0;
    for seed in 0..=640 {
        let mut s = seed;
        let n = rng(&mut s) % 53;
        let k = 1 + rng(&mut s) % 19;
        let mut a = stock::SessionMarks::default();
        let mut b = candidate::SessionMarks::default();
        let mut data = Vec::new();
        for i in 0..n {
            let path = format!("/w/{}", rng(&mut s) % k);
            let parent = (rng(&mut s) % 3 != 0).then(|| rng(&mut s) % (n + 3));
            let stamp = (rng(&mut s) % 4 != 0).then(|| (rng(&mut s) % 6) as u64);
            let title =
                ["Root", "Что искать", "Worker", "needle", "До", "", "Σίγμα"][rng(&mut s) % 7];
            let row = summary(i, path, parent, stamp, title);
            match rng(&mut s) % 9 {
                0 => {
                    a.set_pinned(&row.key, true);
                    b.set_pinned(&row.key, true);
                }
                1 => {
                    a.set_archived(&row.key, true);
                    b.set_archived(&row.key, true);
                }
                2 => {
                    a.rename(&row.key, "Искомый Title");
                    b.rename(&row.key, "Искомый Title");
                }
                _ => {}
            }
            data.push(row);
        }
        for i in (1..n).rev() {
            let j = rng(&mut s) % (i + 1);
            data.swap(i, j);
        }
        for archived in [false, true] {
            for search in [
                "",
                "  ",
                "ROOT",
                "needle",
                "исКоМЫЙ",
                "Σ",
                " НОВАЯ СЕССИЯ ",
                "nonefound",
            ] {
                let l = a.arrange(&data, &stock::View { archived, search });
                let r = b.arrange(&data, &candidate::View { archived, search });
                assert_eq!(
                    flatten!(stock, l),
                    flatten!(candidate, r),
                    "case {seed} {archived} {search}"
                );
                count += 1;
            }
        }
    }
    count
}
fn fixture(
    projects: usize,
    roots: usize,
    descendants: usize,
    shape: &str,
) -> Vec<ConversationSummary> {
    let mut data = Vec::new();
    for project in 0..projects {
        for root in 0..roots {
            let rootid = data.len();
            for depth in 0..=descendants {
                let id = data.len();
                let path = format!("/workspace/{project}");
                let parent = (depth > 0).then(|| {
                    if shape == "branch" {
                        rootid + (depth - 1) / 2
                    } else {
                        id - 1
                    }
                });
                let stamp = match shape {
                    "ties" => Some(1),
                    "ordered" => Some((projects - project) as u64),
                    _ => Some(((project * 23 + 57) % projects * 1000 + root * 13 + depth) as u64),
                };
                data.push(summary(
                    id,
                    path,
                    parent,
                    stamp,
                    if depth == 0 { "root" } else { "child" },
                ));
            }
        }
    }
    data
}
fn main() {
    println!("exact_listing_comparisons={}", parity());
    println!(
        "case,projects,roots_per_project,descendants_per_root,stock_requests,candidate_requests,stock_bytes,candidate_bytes"
    );
    for (name, projects, roots, kids, shape, search) in [
        ("empty", 0, 0, 0, "", ""),
        ("one-flat", 1, 6, 0, "", ""),
        ("one-deep", 1, 4, 160, "", ""),
        ("two-small", 2, 3, 2, "", ""),
        ("three-small", 3, 2, 0, "", ""),
        ("eight-flat", 8, 1, 0, "ordered", ""),
        ("eight-tied", 8, 3, 2, "ties", ""),
        ("many-flat", 64, 1, 0, "", ""),
        ("many-roots", 48, 8, 0, "", ""),
        ("many-visible-children", 32, 4, 16, "branch", ""),
        ("many-hidden-children", 32, 4, 16, "branch", "root"),
        ("tied-descendants", 32, 4, 16, "ties", ""),
    ] {
        let data = fixture(projects, roots, kids, shape);
        let a = stock::SessionMarks::default();
        let b = candidate::SessionMarks::default();
        let (l, ac, ab) = measure(|| {
            a.arrange(
                &data,
                &stock::View {
                    archived: false,
                    search,
                },
            )
        });
        let (r, bc, bb) = measure(|| {
            b.arrange(
                &data,
                &candidate::View {
                    archived: false,
                    search,
                },
            )
        });
        assert_eq!(flatten!(stock, l), flatten!(candidate, r), "{name}");
        if projects <= 1 {
            assert_eq!((ac, ab), (bc, bb), "{name}");
        }
        println!("{name},{projects},{roots},{kids},{ac},{bc},{ab},{bb}");
    }
}
