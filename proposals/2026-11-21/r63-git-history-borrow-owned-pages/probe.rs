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
fn main() {
    let mode = std::env::args().nth(1).unwrap();
    assert!(mode == "counts" || mode == "wire");
    let host = Host::default();
    for rows in [100, 400, 1000] {
        let entries=(0..rows).map(|i|json!({
            "hash":format!("{i:040x}"),"short":format!("{i:07x}"),
            "summary":format!("Изменение {i}: уточнить описание данных"),
            "author":"Example","email":"example@fixture.local",
            "parents":if i+1<rows {vec![format!("{:040x}",i+1)]} else {vec![]},
            "refs":if i%100==0 {vec![json!({"name":format!("branch-{i}"),"kind":"branch"})]} else {vec![]}
        })).collect::<Vec<_>>();
        let mut git = Git {
            changes: Rc::new(json!({"repository":true,"branch":"main","entries":[]})),
            branches: Some(vec![]),
            log: Some(Log {
                entries: entries.clone(),
                more: false,
            }),
            graph: Some(Log {
                entries,
                more: false,
            }),
            ..Git::default()
        };
        git.tabs.insert("test".into(), 1);
        let (panel, c, b) = measure(|| git.panel(&host, "test", "main").unwrap());
        let serialized = panel.to_string();
        assert!(serialized.contains("Изменение 0") && serialized.contains("Изменение 99"));
        if mode == "wire" {
            println!("{serialized}");
        } else {
            println!("{rows} branch-tab {c} {b} {}", serialized.len());
        }
        let (graph, c, b) = measure(|| git.document(&host, &Document::Graph));
        let serialized = graph.to_string();
        assert!(serialized.contains("Изменение 0") && serialized.contains("Изменение 99"));
        if mode == "wire" {
            println!("{serialized}");
        } else {
            println!("{rows} graph {c} {b} {}", serialized.len());
        }
    }
}
