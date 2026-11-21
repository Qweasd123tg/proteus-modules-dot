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
fn reset_counters() {
    CALLS.store(0, Relaxed);
    BYTES.store(0, Relaxed);
}
fn measure<T>(f: impl FnOnce() -> T) -> (T, usize, usize) {
    reset_counters();
    let output = std::hint::black_box(f());
    (output, CALLS.load(Relaxed), BYTES.load(Relaxed))
}
fn cold(path: String, origin: String) {
    let mut host = Host::default();
    host.session = Some("/worktree-fixture".into());
    host.server = Some(proteus_extension::Server {
        origin,
        token: "fixture".into(),
    });
    let mut git = Git::default();
    git.update(json!({"entries":[{"path":path,"status":"modified","revision":"v1"}]}));
    let is_cached = path == "a.txt";
    let doc = Document::Diff(path.clone());
    let (output, calls, bytes) = measure(|| git.document(&host, &doc));
    assert_eq!(git.diffs.get(&path).is_some(), is_cached);
    let serialized = output.to_string();
    assert!(serialized.contains("cold fixture"));
    eprintln!(
        "cold {} {} {}",
        if is_cached {
            "cacheable"
        } else {
            "null-revision"
        },
        calls,
        bytes
    );
    println!("{serialized}");
}
fn main() {
    let mut args = std::env::args().skip(1);
    let mode = args.next().unwrap();
    if mode == "cold" {
        cold(args.next().unwrap(), args.next().unwrap());
        return;
    }
    assert!(mode == "counts" || mode == "wire");
    let host = Host::default();
    for (n, size) in [(1, 2048), (1, 65536), (1, 393216), (8, 262144)] {
        let paths: Vec<_> = (0..n).map(|i| format!("src/пример-{i}.rs")).collect();
        let entries = paths
            .iter()
            .map(|path| json!({"path":path, "status":"modified","revision":"v1"}))
            .collect::<Vec<_>>();
        let mut git = Git::default();
        git.update(json!({"entries":entries,"added":n,"deleted":0}));
        let line = "+ demo строка\n";
        let mut patch = line.repeat(size / line.len());
        patch.push_str(&"x".repeat(size - patch.len()));
        for path in &paths {
            git.diffs.insert(
                path.clone(),
                json!({"kind":"text","path":path,"patch":patch,"revision":"v1"}).into(),
            );
        }
        for (view, doc) in [
            ("single", Document::Diff(paths[0].clone())),
            ("aggregate", Document::Changes),
        ] {
            let (output, calls, bytes) = measure(|| git.document(&host, &doc));
            let serialized = output.to_string();
            assert!(serialized.contains("+ demo строка"));
            if mode == "wire" {
                println!("{serialized}");
            } else {
                println!("{n} {size} {view} {calls} {bytes} {}", serialized.len());
            }
        }
    }
}
