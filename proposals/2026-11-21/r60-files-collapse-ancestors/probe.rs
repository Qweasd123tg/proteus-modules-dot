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
static PREFIX_CHECKS: AtomicUsize = AtomicUsize::new(0);

fn record_prefix_check() {
    PREFIX_CHECKS.fetch_add(1, Relaxed);
}

fn main() {
    use tree::{Entry, Kind, Listing, Project};
    let mode = std::env::args().nth(1).unwrap();
    assert!(mode == "counts" || mode == "wire");
    for (depth, unrelated) in [(1, 0), (4, 8), (12, 256), (32, 1024)] {
        let mut workspace = HashMap::new();
        let mut current = String::new();
        let mut ancestors = Vec::new();
        for level in 0..depth {
            let name = format!("folder-{level}-ветка");
            let next = if current.is_empty() {
                name.clone()
            } else {
                format!("{current}/{name}")
            };
            workspace.insert(
                current,
                Listing {
                    entries: vec![Entry {
                        name,
                        path: next.clone(),
                        kind: Kind::Directory,
                    }],
                    truncated: false,
                },
            );
            ancestors.push(next.clone());
            current = next;
        }
        workspace.insert(current.clone(), Listing::default());
        let mut project = Project::default();
        let rows = project
            .lines("fixture", &mut |path| Ok(workspace[path].clone()))
            .unwrap();
        assert_eq!(rows.len(), 2);
        assert_eq!(rows[1].path, current);
        let descendant = format!("{current}/retained-child");
        project.expanded.extend(ancestors);
        project.expanded.insert(descendant.clone());
        project
            .expanded
            .extend((0..unrelated).map(|i| format!("other-{i}")));
        PREFIX_CHECKS.store(0, Relaxed);
        let (_, calls, bytes) = measure(|| project.collapse(&current));
        let checks = PREFIX_CHECKS.load(Relaxed);
        assert_eq!(project.expanded.len(), unrelated + 2);
        assert!(project.expanded.contains("") && project.expanded.contains(&descendant));
        if mode == "counts" {
            println!("{depth} {unrelated} {calls} {bytes} {checks}");
        } else {
            let mut surviving: Vec<_> = project.expanded.iter().collect();
            surviving.sort_unstable();
            println!("{}", serde_json::to_string(&surviving).unwrap());
        }
    }
}
