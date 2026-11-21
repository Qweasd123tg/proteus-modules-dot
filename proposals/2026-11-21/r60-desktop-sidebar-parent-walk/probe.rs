mod stock;
use desktop_sidebar_parent_walk_probe::{
    conversations::ConversationSummary,
    sessions::{self, Listing, Row, SessionMarks, View},
};
use proteus_tabs::ChatKey;
use std::hint::black_box;
use std::io::{self, BufWriter, Write};

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

fn edges() {
    let mut cases = 0;
    for n in 0usize..=6 {
        let radix = n + 1;
        for mut encoded in 0..radix.pow(n as u32) {
            let mut seed = [None; 6];
            for edge in &mut seed[..n] {
                let elem = encoded % radix;
                *edge = (elem != 0).then(|| elem - 1);
                encoded /= radix;
            }
            let (mut a, mut b) = (seed, seed);
            stock::break_cycles(&mut a[..n]);
            sessions::probe_break_cycles(&mut b[..n]);
            assert_eq!(a, b, "parent graph {:?}", &seed[..n]);
            cases += 1;
        }
    }
    assert_eq!(cases, 126126);
    println!("PASS {cases} exhaustive parent graph edge comparisons");
}

fn key(id: usize, codex: bool) -> ChatKey {
    if codex {
        ChatKey::Codex(format!("opaque-session-{id}"))
    } else {
        ChatKey::Proteus(format!("/synthetic/session/{id}").into())
    }
}

fn shape(id: usize, n: usize, flavor: usize) -> Option<usize> {
    match flavor {
        0 => None,
        1 => (id + 1 < n).then_some(id + 1),
        2 => (id % 4 != 0).then_some(id - id % 4),
        3 => (id % 5 != 0).then_some((id * 7 + 4) % n),
        4 => match id % 7 {
            0 => Some(id + n + 7), // unavailable parent
            1 => Some(id),         // same conversation
            2 => Some((id + 1) % n),
            3 => id.checked_sub(1),
            _ => id.checked_sub(8),
        },
        _ => unreachable!(),
    }
}

fn listing_data(
    n: usize,
    flavor: usize,
    folders: usize,
    with_marks: bool,
) -> (Vec<ConversationSummary>, SessionMarks) {
    let id_key = |id| key(id, (id % 3) == 1);
    let data: Vec<_> = (0..n)
        .map(|id| ConversationSummary {
            key: id_key(id),
            proteus_session_id: ((id % 3) != 1).then(|| uuid::Uuid::from_u128(id as u128 + 1)),
            parent: shape(id, n, flavor).map(id_key),
            workspace_path: format!("/synthetic/project-{}", id % folders).into(),
            message_count: id % 11,
            updated_at_ms: (id % 5 != 2).then_some((id % 7) as u64),
            preview: match id % 5 {
                0 => None,
                2 => Some(" Ångström ".into()),
                3 => Some(" NEEDLE  ".into()),
                _ => Some(format!("history #{id}")),
            },
            activity: None,
        })
        .collect();
    let mut marks = SessionMarks::default();
    if with_marks {
        for (id, item) in data.iter().enumerate() {
            if id % 9 == 0 {
                marks.set_archived(&item.key, true);
            }
            if id % 15 == 1 {
                marks.set_pinned(&item.key, true);
            }
            if id % 11 == 2 {
                marks.rename(&item.key, " Custom  NeedLe  ");
            }
        }
    }
    (data, marks)
}

fn row_trace(out: &mut impl Write, rows: &[Row<'_>]) -> io::Result<()> {
    write!(out, "[")?;
    for row in rows {
        write!(out, "({:?},{:?},", row.summary.key, row.mark)?;
        row_trace(out, &row.children)?;
        write!(out, ")")?;
    }
    write!(out, "]")
}

fn trace(out: &mut impl Write, model: &Listing<'_>) -> io::Result<()> {
    write!(out, "archived_count={}|pinned=", model.archived_count)?;
    row_trace(out, &model.pinned)?;
    write!(out, "|archived=")?;
    row_trace(out, &model.archived)?;
    for project in &model.projects {
        write!(out, "|{:?}=", project.path)?;
        row_trace(out, &project.rows)?;
    }
    writeln!(out)
}

fn listings() -> io::Result<()> {
    let mut out = BufWriter::new(io::stdout().lock());
    let mut cases = 0;
    for n in [0, 1, 2, 5, 16, 33, 96] {
        for flavor in 0..5 {
            for folders in [1, 4] {
                for with_marks in [false, true] {
                    let (data, marks) = listing_data(n, flavor, folders, with_marks);
                    for search in ["", " NEEDLE ", "ÅNGSTRÖM", "новая сессия", "no result"]
                    {
                        for archived in [false, true] {
                            trace(&mut out, &marks.arrange(&data, &View { search, archived }))?;
                            cases += 1;
                        }
                    }
                }
            }
        }
    }
    writeln!(out, "listing cases\t{cases}")?;
    out.flush()
}

fn measure<T>(name: &str, make: impl FnOnce() -> T) {
    let before = counter::read();
    let result = black_box(make());
    let after = counter::read();
    black_box(&result);
    println!(
        "alloc\t{name}\t{}\t{}",
        after.0 - before.0,
        after.1 - before.1
    );
}

fn allocations() {
    let size = 64;
    let empty = View {
        search: "",
        archived: false,
    };
    let search = View {
        search: "needle",
        archived: true,
    };
    for (name, n, flavor, folders, marks, view) in [
        ("empty", 0, 0, 1, false, &empty),
        ("roots-64", size, 0, 1, false, &empty),
        ("chain-64", size, 1, 1, false, &empty),
        ("branches-64", size, 2, 4, false, &empty),
        ("mixed-filter-64", size, 4, 4, true, &search),
    ] {
        let (data, marks) = listing_data(n, flavor, folders, marks);
        let row_marks: Vec<_> = data.iter().map(|row| marks.get(&row.key)).collect();
        let mut graph: Vec<_> = (0..n)
            .map(|i| {
                shape(i, n, flavor).filter(|&j| {
                    j < n
                        && i != j
                        && !row_marks[i].pinned
                        && row_marks[i].archived == row_marks[j].archived
                })
            })
            .collect();
        measure(&format!("parent-{name}"), || {
            sessions::probe_break_cycles(black_box(&mut graph))
        });
        measure(&format!("listing-{name}"), || {
            marks.arrange(black_box(&data), view)
        });
        // The exact number of removed requests in both windows should match:
        // nothing other than the parent-walk scratch changed.
    }
}

fn main() -> io::Result<()> {
    match std::env::args().nth(1).as_deref() {
        Some("edges") => {
            edges();
            Ok(())
        }
        Some("listings") => listings(),
        Some("alloc") => {
            allocations();
            Ok(())
        }
        _ => panic!("expected edges, listings or alloc"),
    }
}
