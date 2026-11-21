// Temporary allocator probe; appended after renaming the binary's main.
use std::alloc::{GlobalAlloc, Layout, System};
use std::sync::atomic::{AtomicUsize, Ordering::Relaxed};

struct Meter;

#[global_allocator]
static METER: Meter = Meter;
static BYTES: AtomicUsize = AtomicUsize::new(0);
static CALLS: AtomicUsize = AtomicUsize::new(0);

fn record(size: usize) {
    BYTES.fetch_add(size, Relaxed);
    CALLS.fetch_add(1, Relaxed);
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
        unsafe { System.dealloc(p, layout) };
    }

    unsafe fn realloc(&self, p: *mut u8, layout: Layout, size: usize) -> *mut u8 {
        let moved = unsafe { System.realloc(p, layout, size) };
        if !moved.is_null() {
            record(size);
        }
        moved
    }
}

fn main() {
    let mode = std::env::args().nth(1).unwrap();
    let theme = serde_json::json!({"z":"метка\r\n\t\"\\🦀", "foreground":"#e8e8ed",
        "a":[false, null, 1.5, {"family":"sans-serif"}]});
    let mut large_theme = theme.clone();
    large_theme["a"] = Value::Array(
        (0..2400)
            .map(|index| serde_json::json!({"index":index,"label":"Проект-🦀-notes"}))
            .collect(),
    );
    let near_limit = format!("{SAMPLE}{}", " ".repeat(50_000 - SAMPLE.len()));
    let diagram = "flowchart LR\n".to_owned()
        + &(0..120)
            .map(|index| format!(" n{index}[Запрос {index}] --> d{index}[Ответ {index}]\n"))
            .collect::<String>();

    for (case, source, context) in [
        ("short", SAMPLE, serde_json::json!({"theme": theme})),
        ("no-theme", SAMPLE, Value::Null),
        ("medium", &diagram, serde_json::json!({"theme": theme})),
        (
            "source-limit",
            &near_limit,
            serde_json::json!({"theme": theme}),
        ),
        (
            "nested-theme",
            SAMPLE,
            serde_json::json!({"theme": large_theme}),
        ),
    ] {
        let content = proteus_extension::Content {
            language: "mermaid".into(),
            source: source.to_owned(),
            context,
            source_revision: Some(1),
        };
        CALLS.store(0, Relaxed);
        BYTES.store(0, Relaxed);
        let wire = __BUILD__;
        let bytes = BYTES.load(Relaxed);
        let calls = CALLS.load(Relaxed);
        if mode == "measure" {
            println!("{case} {} {} {calls} {bytes}", source.len(), wire.len());
        } else {
            assert_eq!(mode, "wire");
            println!("{wire}");
        }
    }
}
