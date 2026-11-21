// Append to packages/files/src/main.rs in a temporary checkout (main renamed).
use std::alloc::{GlobalAlloc, Layout, System};
use std::sync::atomic::{AtomicUsize, Ordering::Relaxed};

struct Meter;
static CALLS: AtomicUsize = AtomicUsize::new(0);
static REQUESTED: AtomicUsize = AtomicUsize::new(0);
static LIVE: AtomicUsize = AtomicUsize::new(0);
static PEAK: AtomicUsize = AtomicUsize::new(0);
#[global_allocator]
static METER: Meter = Meter;

fn record(size: usize) {
    CALLS.fetch_add(1, Relaxed);
    REQUESTED.fetch_add(size, Relaxed);
    let live = LIVE.fetch_add(size, Relaxed) + size;
    PEAK.fetch_max(live, Relaxed);
}

unsafe impl GlobalAlloc for Meter {
    unsafe fn alloc(&self, layout: Layout) -> *mut u8 {
        let p = unsafe { System.alloc(layout) };
        if !p.is_null() {
            record(layout.size());
        }
        p
    }

    unsafe fn dealloc(&self, p: *mut u8, layout: Layout) {
        LIVE.fetch_sub(layout.size(), Relaxed);
        unsafe { System.dealloc(p, layout) };
    }

    unsafe fn realloc(&self, p: *mut u8, layout: Layout, size: usize) -> *mut u8 {
        let ret = unsafe { System.realloc(p, layout, size) };
        if !ret.is_null() {
            LIVE.fetch_sub(layout.size(), Relaxed);
            record(size);
        }
        ret
    }
}

fn item(folder: &str, name: String, kind: Kind) -> tree::Entry {
    let path = if folder.is_empty() {
        name.clone()
    } else {
        format!("{folder}/{name}")
    };
    tree::Entry { name, path, kind }
}

fn fixture(case: &str) -> (Files, HashMap<String, tree::Listing>) {
    let mut files = Files::default();
    let mut listings = HashMap::new();
    let files_in = |folder: &str, count| {
        (0..count)
            .map(|i| item(folder, format!("файл-{i:04}.rs"), Kind::File))
            .collect::<Vec<_>>()
    };
    let mut root = match case {
        "flat-8" => files_in("", 8),
        "flat-2000" => files_in("", 2000),
        _ => Vec::new(),
    };
    if case == "mixed" {
        for i in 0..40 {
            let dir = item("", format!("проект-{i:02}"), Kind::Directory);
            files.project.expanded.insert(dir.path.clone());
            listings.insert(
                dir.path.clone(),
                tree::Listing {
                    entries: files_in(&dir.path, 50),
                    truncated: false,
                },
            );
            root.push(dir);
        }
    }
    if case == "fold-32" {
        let mut folder = String::new();
        for i in 0..32 {
            let child = item(&folder, format!("ветка-{i:02}"), Kind::Directory);
            let path = child.path.clone();
            if folder.is_empty() {
                root.push(child);
            } else {
                listings.insert(
                    folder,
                    tree::Listing {
                        entries: vec![child],
                        truncated: false,
                    },
                );
            }
            folder = path;
        }
        listings.insert(
            folder.clone(),
            tree::Listing {
                entries: files_in(&folder, 2),
                truncated: false,
            },
        );
    }
    listings.insert(
        String::new(),
        tree::Listing {
            entries: root,
            truncated: case == "flat-2000",
        },
    );
    (files, listings)
}

fn main() {
    let mode = std::env::args().nth(1).unwrap();
    for case in ["empty", "flat-8", "flat-2000", "mixed", "fold-32"] {
        let (mut files, mut listings) = fixture(case);
        for arm in ["cold", "warm"] {
            let reads = std::cell::Cell::new(0);
            let mut load = |path: &str| {
                reads.set(reads.get() + 1);
                Ok(listings
                    .remove(path)
                    .expect("unexpected extra workspace read"))
            };
            let baseline = LIVE.load(Relaxed);
            CALLS.store(0, Relaxed);
            REQUESTED.store(0, Relaxed);
            PEAK.store(baseline, Relaxed);
            let rows = files.project.lines("Проект", &mut load).unwrap();
            if mode == "measure" {
                let calls = CALLS.load(Relaxed);
                let bytes = REQUESTED.load(Relaxed);
                let peak = PEAK.load(Relaxed) - baseline;
                println!(
                    "{case} {arm} {} {} {calls} {bytes} {peak}",
                    rows.len(),
                    reads.get()
                );
            } else {
                assert_eq!(mode, "wire");
                let rows = rows.iter().map(|line| files.row(line)).collect::<Vec<_>>();
                let widget = proteus_extension::ui::tree("files", rows, "files");
                println!(
                    "{}",
                    json!({
                        "case":case, "arm":arm, "reads":reads.get(),
                        "truncated":files.project.truncated, "widget":widget
                    })
                );
            }
        }
    }
}
