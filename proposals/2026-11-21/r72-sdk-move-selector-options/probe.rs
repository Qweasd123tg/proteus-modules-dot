// Build as a temporary SDK example, never in the shipped binaries.
use proteus_extension::{Value, json, ui};
use std::alloc::{GlobalAlloc, Layout, System};
use std::cell::Cell;

thread_local! {
    static ACTIVE: Cell<bool> = const { Cell::new(false) };
    static COUNTS: Cell<(usize, usize)> = const { Cell::new((0, 0)) };
}

struct Meter;

#[global_allocator]
static METER: Meter = Meter;

fn record(bytes: usize) {
    if ACTIVE.try_with(Cell::get).unwrap_or(false) {
        COUNTS.with(|c| {
            let (calls, old_bytes) = c.get();
            c.set((calls + 1, old_bytes + bytes));
        });
    }
}

unsafe impl GlobalAlloc for Meter {
    unsafe fn alloc(&self, layout: Layout) -> *mut u8 {
        let ptr = unsafe { System.alloc(layout) };
        if !ptr.is_null() {
            record(layout.size());
        }
        ptr
    }

    unsafe fn dealloc(&self, ptr: *mut u8, layout: Layout) {
        unsafe { System.dealloc(ptr, layout) };
    }

    unsafe fn realloc(&self, ptr: *mut u8, previous: Layout, bytes: usize) -> *mut u8 {
        let ptr = unsafe { System.realloc(ptr, previous, bytes) };
        if !ptr.is_null() {
            record(bytes);
        }
        ptr
    }
}

fn measure<T>(f: impl FnOnce() -> T) -> (T, usize, usize) {
    COUNTS.with(|c| c.set((0, 0)));
    ACTIVE.with(|a| a.set(true));
    let out = std::hint::black_box(f());
    ACTIVE.with(|a| a.set(false));
    let (calls, bytes) = COUNTS.with(Cell::get);
    (out, calls, bytes)
}

fn option_rows(n: usize, structured: bool) -> Vec<(Value, String)> {
    (1..=n)
        .map(|i| {
            let id = format!("{i:036}");
            let value = if structured {
                json!({"z":[id,null,-0.0,u64::MAX],"a":false})
            } else {
                Value::String(id)
            };
            (value, format!("Ход {i} λ"))
        })
        .collect()
}

fn main() {
    let mode = std::env::args().nth(1).unwrap();
    assert!(mode == "wire" || mode == "counts");
    for kind in ["select", "picker"] {
        for (case, size, structured) in [
            ("empty", 0, false),
            ("small", 8, false),
            ("ordinary-large", 512, false),
            ("large", 2048, false),
            ("structured-duplicates", 3, true),
        ] {
            let mut rows = option_rows(size, structured);
            if structured {
                rows[0].0 = Value::Null;
                rows[2].0 = rows[1].0.clone();
            }
            let selected = rows.get(size / 2).map_or(&Value::Null, |(id, _)| id);
            let (view, calls, bytes) = measure(|| match kind {
                "select" => ui::select("fixture", "Опции λ", &rows, selected, "choose"),
                _ => ui::picker("fixture", &rows, selected, "choose"),
            });
            let options = view["options"].as_array().unwrap();
            assert_eq!(options.len(), size);
            let matches = options
                .iter()
                .filter(|row| row["selected"] == true)
                .count();
            assert_eq!(matches, if size == 0 { 0 } else if structured { 2 } else { 1 });
            if mode == "counts" {
                println!("{kind} {case} {size} {calls} {bytes} {}", options.capacity());
            } else {
                println!("{}", json!([kind, case, view]));
            }
        }
    }
    let data = vec![json!({"type":"text","text":"control λ stays"})];
    let (view, calls, bytes) = measure(|| ui::fill(data));
    if mode == "counts" {
        println!("fill unchanged-control 1 {calls} {bytes} {}", view["children"].as_array().unwrap().capacity());
    } else {
        println!("{}", json!(["fill", "unchanged-control", view]));
    }
}
