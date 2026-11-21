mod project_rows;
mod stock;
use conversations::ConversationSummary;
use desktop_project_rows_probe::{conversations, sessions};
use proteus_tabs::ChatKey;
use sessions::{Project, SessionMarks, View};
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

fn summaries(size: usize, projects: usize) -> Vec<ConversationSummary> {
    fn row(
        key: ChatKey,
        parent: Option<ChatKey>,
        project: usize,
        time: u64,
    ) -> ConversationSummary {
        ConversationSummary {
            key,
            proteus_session_id: None,
            parent,
            workspace_path: format!("/synthetic/project-{project}").into(),
            message_count: 1,
            updated_at_ms: Some(time),
            preview: Some("Normal Разговор".to_owned()),
            activity: None,
        }
    }
    let mut data = Vec::new();
    for g in 0..projects {
        for n in 0..size {
            let key = ChatKey::Codex(format!("p{g}-root-{n}"));
            let stamp = 1000 - n as u64 * 3;
            data.push(row(key.clone(), None, g, stamp));
            let child = ChatKey::Codex(format!("p{g}-child-{n}"));
            data.push(row(child.clone(), Some(key), g, stamp - 1));
            data.push(row(
                ChatKey::Codex(format!("p{g}-nested-{n}")),
                Some(child),
                g,
                stamp - 2,
            ));
        }
    }
    data
}

fn compare(project: &Project<'_>, current: Option<&ChatKey>, all: bool, moving: bool) {
    let mut a = Vec::new();
    let mut b = Vec::new();
    let (h1, x) = stock::visit(project, current, all, moving, |r| a.push(&r.summary.key));
    let (h2, y) = project_rows::visit(&project.rows, current, all, moving, |r| {
        b.push(&r.summary.key)
    });
    assert_eq!(a, b);
    assert_eq!(h1, h2);
    assert_eq!(
        x.iter().map(|r| &r.summary.key).collect::<Vec<_>>(),
        y.iter().map(|r| &r.summary.key).collect::<Vec<_>>()
    );
}

fn parity() {
    let mut n = 0;
    for size in [1, 4, 5, 6, 8, 27, 100] {
        for projects in [1, 3] {
            let data = summaries(size, projects);
            let mut marks = SessionMarks::default();
            for (i, summary) in data.iter().enumerate() {
                if i % 29 == 16 {
                    marks.set_pinned(&summary.key, true);
                }
                if i % 31 == 19 {
                    marks.set_archived(&summary.key, true);
                }
            }
            for marks in [&SessionMarks::default(), &marks] {
                for archived in [false, true] {
                    for search in ["", "разговор", "missing"] {
                        let listing = marks.arrange(&data, &View { archived, search });
                        for project in &listing.projects {
                            let nested = ChatKey::Codex(format!("p0-nested-{}", size - 1));
                            let missing = ChatKey::Codex("not present".to_owned());
                            for key in [None, Some(&data[0].key), Some(&nested), Some(&missing)] {
                                for all in [false, true] {
                                    for moving in [false, true] {
                                        compare(project, key, all, moving);
                                        n += 1;
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    }
    let data = summaries(1, 1);
    let mut listing = SessionMarks::default().arrange(
        &data,
        &View {
            archived: false,
            search: "",
        },
    );
    listing.projects[0].rows.clear();
    compare(&listing.projects[0], None, false, false);
    n += 1;
    println!(
        "PASS {n} actual project-root projections, exact visible/animated keys and hidden count"
    );
}

fn measure<T>(call: impl Fn() -> T, arm: &str, name: &str, _n: usize) {
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
        for _ in 0..40 {
            drop(black_box(call()));
        }
        let now = std::time::Instant::now();
        for _ in 0.._n {
            drop(black_box(call()));
        }
        let ns = now.elapsed().as_nanos() as f64 / _n as f64;
        println!("time\t{arm}\t{name}\t{ns:.3}");
    }
}

fn main() {
    let arm = std::env::args().nth(1).unwrap();
    if arm == "parity" {
        parity();
        return;
    }
    for (name, size, all, moving, has_current, iters) in [
        ("five-collapsed", 5, false, false, false, 25000),
        ("eight-collapsed-active", 8, false, false, true, 15000),
        ("eight-expanded", 8, true, false, true, 15000),
        ("eight-animated", 8, true, true, true, 15000),
        ("forty-collapsed-active", 40, false, false, true, 8000),
        ("forty-expanded", 40, true, false, true, 8000),
        ("large-expanded", 200, true, false, true, 1500),
    ] {
        let data = summaries(size, 1);
        let marks = SessionMarks::default();
        let listing = marks.arrange(
            &data,
            &View {
                archived: false,
                search: "",
            },
        );
        let project = &listing.projects[0];
        assert_eq!(project.rows.len(), size);
        let key = ChatKey::Codex(format!("p0-nested-{}", size - 1));
        let current = has_current.then_some(&key);
        compare(project, current, all, moving);
        let call = || {
            let (root, current) = (black_box(project), black_box(current));
            let consume = |row: &sessions::Row<'_>| {
                black_box(&row.summary.key);
            };
            let (n, extra) = match arm.as_str() {
                "stock" => stock::visit(root, current, black_box(all), black_box(moving), consume),
                "candidate" => project_rows::visit(
                    &root.rows,
                    current,
                    black_box(all),
                    black_box(moving),
                    consume,
                ),
                _ => panic!("expected stock or candidate"),
            };
            for row in extra {
                black_box(&row.summary.key);
            }
            n
        };
        measure(call, &arm, name, iters);
    }
}
