// Inserted only in a separate temporary release measurement build.
use std::alloc::{GlobalAlloc, Layout, System};
use std::sync::atomic::{AtomicUsize, Ordering::Relaxed};
struct Meter;
#[global_allocator]
static METER: Meter = Meter;
static CALLS: AtomicUsize = AtomicUsize::new(0);
static BYTES: AtomicUsize = AtomicUsize::new(0);
fn record(size: usize) {
    CALLS.fetch_add(1, Relaxed);
    BYTES.fetch_add(size, Relaxed);
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
        unsafe { System.dealloc(p, layout) }
    }
    unsafe fn realloc(&self, p: *mut u8, layout: Layout, size: usize) -> *mut u8 {
        let p = unsafe { System.realloc(p, layout, size) };
        if !p.is_null() {
            record(size);
        }
        p
    }
}
fn measure<T>(f: impl FnOnce() -> T) -> (T, usize, usize) {
    CALLS.store(0, Relaxed);
    BYTES.store(0, Relaxed);
    let output = std::hint::black_box(f());
    (output, CALLS.load(Relaxed), BYTES.load(Relaxed))
}
static PARENT_STEPS: AtomicUsize = AtomicUsize::new(0);

fn record_parent_step() {
    PARENT_STEPS.fetch_add(1, Relaxed);
}

fn main() {
    use std::collections::BTreeSet;
    let mode = std::env::args().nth(1).unwrap();
    assert!(mode == "counts" || mode == "wire");
    for (case, files, groups, depth) in [
        ("single", 1, 1, 4),
        ("distinct", 100, 100, 6),
        ("clustered", 1_000, 20, 6),
        ("monorepo", 4_000, 32, 10),
    ] {
        let roster: Vec<_> = (0..files)
            .map(|i| {
                let group = i % groups;
                let folder = (0..depth)
                    .map(|j| format!("group-{group}-{j}-ветка"))
                    .collect::<Vec<_>>()
                    .join("/");
                let status = ["untracked", "modified", "deleted", "conflict"][(i / groups) % 4];
                (format!("{folder}/file-{i}.rs"), status)
            })
            .collect();
        let input = json!({
            "repository": true,
            "entries": roster.iter().map(|(path, status)| json!({"path": path, "status": status}))
                .collect::<Vec<_>>()
        });

        PARENT_STEPS.store(0, Relaxed);
        let (git, calls, bytes) = measure(|| Git::parse(&input));
        let steps = PARENT_STEPS.load(Relaxed);
        assert!(git.repository);
        if mode == "counts" {
            println!("{case} {files} {groups} {depth} {calls} {bytes} {steps}");
        } else {
            let mut folders = BTreeSet::new();
            let rows: Vec<_> = roster
                .iter()
                .map(|(path, raw)| {
                    for (pos, _) in path.match_indices('/') {
                        folders.insert(&path[..pos]);
                    }
                    assert_eq!(git.change(path), Some(*raw));
                    (path, git.change(path), git.status(path, false).map(|s| s as u8), git.restorable(path))
                })
                .collect();
            folders.insert("");
            let directories: Vec<_> = folders.into_iter()
                .map(|path| (path, git.status(path, true).map(|s| s as u8))).collect();
            println!("{}", json!([case, rows, directories]));
        }
    }
}
