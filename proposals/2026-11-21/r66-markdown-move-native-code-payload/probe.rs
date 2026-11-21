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
    use render::Document;
    let mode = std::env::args().nth(1).unwrap();
    assert!(mode == "counts" || mode == "outputs");
    for (case, repeat, blocks) in [
        ("embedded-small", 8, 1),
        ("embedded-large", 1024, 2),
        ("embedded-open", 256, 1),
        ("indented-eof", 6, 1),
        ("claimed-large", 1024, 2),
        ("retained-hit", 1024, 2),
        ("plain-prose", 128, 0),
    ] {
        let example = "    let a = 'пример λ & <data>';\n".repeat(repeat);
        let fence = char::from(96).to_string().repeat(3);
        let source = if blocks == 0 {
            "Параграф о фикстуре, обычный формат.\n".repeat(repeat)
        } else if case == "indented-eof" {
            example.trim_end_matches('\n').to_owned()
        } else {
            let line = if case == "claimed-large" { "mermaid" } else { "rust" };
            let segment = if case == "embedded-open" {
                format!("{fence}{line}\n{example}")
            } else {
                format!("{fence}{line}\n{example}{fence}\n")
            };
            segment.repeat(blocks)
        };
        let languages = ["mermaid".to_owned()];
        let mut document = Document::default();
        if case == "retained-hit" {
            document.render(&source, &languages).unwrap();
        }
        let (value, calls, bytes) = measure(|| document.render(&source, &languages));
        let value = value.unwrap();
        let children = value["children"].as_array().unwrap();
        let node_type = if blocks == 0 { "rich_text" } else if case == "claimed-large" { "content" } else { "code" };
        assert_eq!(children.iter().filter(|node| node["type"] == node_type).count(), blocks.max(1));
        if mode == "counts" {
            let (len, capacity) = document.probe_code_size();
            println!("{case} {} {calls} {bytes} {len} {capacity}", source.len());
        } else {
            println!("{}", proteus_extension::json!([case, value]));
        }
    }
}
