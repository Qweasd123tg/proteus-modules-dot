mod stock;
use desktop_row_membership_probe::{
    conversations::ConversationSummary,
    sessions::{self, Row, SessionMarks, View},
};
use proteus_tabs::ChatKey;
use std::hint::black_box;

#[cfg(feature = "count")]
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

fn key(i: usize, is_codex: bool) -> ChatKey {
    if is_codex {
        ChatKey::Codex(format!("/synthetic/s{i}"))
    } else {
        ChatKey::Proteus(format!("/synthetic/s{i}").into())
    }
}

fn data(
    n: usize,
    parent: impl Fn(usize) -> Option<usize>,
    mixed: bool,
) -> Vec<ConversationSummary> {
    let id = |i| key(i, mixed && i % 2 == 1);
    (0..n)
        .map(|i| ConversationSummary {
            key: id(i),
            proteus_session_id: None,
            parent: parent(i).map(id),
            workspace_path: "/synthetic/project".into(),
            message_count: 1,
            updated_at_ms: Some(i as u64),
            preview: Some(format!("Session group {}", i % 5)),
            activity: None,
        })
        .collect()
}

fn tree<'a>(marks: &SessionMarks, data: &'a [ConversationSummary]) -> sessions::Listing<'a> {
    marks.arrange(
        data,
        &View {
            archived: false,
            search: "",
        },
    )
}

fn parity() {
    let mut comparisons = 0;
    for size in [1, 2, 3, 6, 9, 18, 31, 64, 129, 256] {
        for shape in 0..5 {
            for mixed in [false, true] {
                let rows = data(
                    size,
                    |i| {
                        if i == 0 {
                            None
                        } else {
                            match shape {
                                0 => None,
                                1 => Some(i - 1),
                                2 => Some(0),
                                3 => Some((i - 1) / 3),
                                _ => (i % 4 != 0).then_some(i - 1),
                            }
                        }
                    },
                    mixed,
                );
                let mut marks = SessionMarks::default();
                for (i, s) in rows.iter().enumerate() {
                    if i % 11 == 4 {
                        marks.set_pinned(&s.key, true);
                    }
                    if i % 17 == 6 {
                        marks.set_archived(&s.key, true);
                    }
                }
                for marks in [&SessionMarks::default(), &marks] {
                    for (archived, search) in [
                        (false, ""),
                        (true, ""),
                        (false, "group 2"),
                        (false, "missing"),
                    ] {
                        let listing = marks.arrange(&rows, &View { archived, search });
                        for root in listing
                            .pinned
                            .iter()
                            .chain(listing.archived.iter())
                            .chain(listing.projects.iter().flat_map(|p| &p.rows))
                        {
                            for i in 0..=size + 1 {
                                for test_key in [key(i, false), key(i, true)] {
                                    assert_eq!(
                                        root.contains(&test_key),
                                        stock::contains(root, &test_key),
                                        "shape {shape}, size {size}, key {test_key:?}"
                                    );
                                    comparisons += 1;
                                }
                            }
                        }
                    }
                }
            }
        }
    }
    println!("PASS {comparisons} membership comparisons on exact SessionMarks::arrange output");
}

fn measure<T>(call: impl Fn() -> T, arm: &str, name: &str, _iterations: usize) {
    #[cfg(feature = "count")]
    {
        let (a, b) = counter::read();
        let result = black_box(call());
        let (c, d) = counter::read();
        black_box(&result);
        println!("alloc\t{arm}\t{name}\t{}\t{}", c - a, d - b);
    }
    #[cfg(not(feature = "count"))]
    {
        for _ in 0..32 {
            drop(black_box(call()));
        }
        let started = std::time::Instant::now();
        for _ in 0.._iterations {
            drop(black_box(call()));
        }
        let ns = started.elapsed().as_nanos() as f64 / _iterations as f64;
        println!("time\t{arm}\t{name}\t{ns:.3}");
    }
}

fn main() {
    let arm = std::env::args().nth(1).unwrap();
    if arm == "parity" {
        parity();
        return;
    }
    fn candidate(row: &Row<'_>, dir: &ChatKey) -> bool {
        row.contains(dir)
    }
    let contains = match arm.as_str() {
        "stock" => stock::contains as fn(&Row<'_>, &ChatKey) -> bool,
        "candidate" => candidate,
        _ => panic!("expected stock or candidate"),
    };
    let marks = SessionMarks::default();
    let leaf_data = data(1, |_| None, false);
    let chain_data = data(6, |i| i.checked_sub(1), false);
    let wide_data = data(33, |i| (i > 0).then_some(0), false);
    let balanced_data = data(121, |i| i.checked_sub(1).map(|i| i / 3), false);
    let sidebar_data = data(48, |i| if i % 2 == 0 { None } else { Some(i - 1) }, true);
    let leaf = tree(&marks, &leaf_data);
    let chain = tree(&marks, &chain_data);
    let wide = tree(&marks, &wide_data);
    let balanced = tree(&marks, &balanced_data);
    let sidebar = tree(&marks, &sidebar_data);
    let missing = key(1000, false);
    for (name, listing, active, cycles) in [
        ("leaf-match", &leaf, &leaf_data[0].key, 70000),
        ("leaf-miss", &leaf, &missing, 70000),
        ("chain-6", &chain, &chain_data[5].key, 40000),
        ("wide-32", &wide, &missing, 10000),
        ("balanced-121", &balanced, &missing, 4500),
        ("sidebar-folded-24", &sidebar, &sidebar_data[1].key, 10000),
    ] {
        let rows = &listing.projects[0].rows;
        let roots = if name == "sidebar-folded-24" {
            &rows[5..]
        } else {
            rows.as_slice()
        };
        let call = || {
            black_box(roots)
                .iter()
                .filter(|row| contains(row, black_box(active)))
                .count()
        };
        measure(call, &arm, name, cycles);
    }
}
