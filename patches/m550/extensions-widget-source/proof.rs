#![allow(dead_code)]

#[path = "support/stock_ui.rs"]
mod stock_ui;

use proteus_extension::{Value, ui};
use std::{
    alloc::{GlobalAlloc, Layout, System},
    cell::Cell,
    hint::black_box,
};

#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
struct Requests {
    alloc: usize,
    realloc: usize,
    bytes: usize,
}

thread_local! {
    static METER: Cell<Option<Requests>> = const { Cell::new(None) };
}

fn count(size: usize, realloc: bool) {
    let _ = METER.try_with(|meter| {
        if let Some(mut r) = meter.get() {
            if realloc {
                r.realloc += 1;
            } else {
                r.alloc += 1;
            }
            r.bytes += size;
            meter.set(Some(r));
        }
    });
}

struct Meter;
unsafe impl GlobalAlloc for Meter {
    unsafe fn alloc(&self, layout: Layout) -> *mut u8 {
        count(layout.size(), false);
        unsafe { System.alloc(layout) }
    }

    unsafe fn alloc_zeroed(&self, layout: Layout) -> *mut u8 {
        count(layout.size(), false);
        unsafe { System.alloc_zeroed(layout) }
    }

    unsafe fn realloc(&self, ptr: *mut u8, layout: Layout, size: usize) -> *mut u8 {
        count(size, true);
        unsafe { System.realloc(ptr, layout, size) }
    }

    unsafe fn dealloc(&self, ptr: *mut u8, layout: Layout) {
        unsafe { System.dealloc(ptr, layout) }
    }
}

#[global_allocator]
static ALLOCATOR: Meter = Meter;

fn measured(f: impl FnOnce() -> Value) -> (Value, Requests) {
    METER.with(|m| assert_eq!(m.replace(Some(Requests::default())), None));
    let v = black_box(f());
    (v, METER.with(|m| m.replace(None)).unwrap())
}

#[test]
fn exact_wire_ownership_capacity_and_meter() {
    use std::cell::Cell;
    struct Once<'a>(&'a Cell<usize>, String);
    impl From<Once<'_>> for String {
        fn from(o: Once<'_>) -> Self {
            o.0.set(o.0.get() + 1);
            o.1
        }
    }
    let text = "<g>Я🦀 &quot;\0\r\n</g>".repeat(50_000);
    for (kind, field) in [("svg", "source"), ("content", "source"), ("rich", "html")] {
        for (s, extra) in [
            (&text[..], 0),
            (&text[..], 1_000_000),
            ("", 0),
            ("", 16_384),
        ] {
            let make = || {
                let mut v = String::with_capacity(s.len() + extra);
                v.push_str(s);
                v
            };
            let (input, orig_input) = (make(), make());
            let ptr = input.as_ptr();
            let calls = Cell::new(0);
            let (old, a) = measured(|| match kind {
                "content" => stock_ui::content("猫", "x", orig_input),
                "svg" => stock_ui::svg(orig_input, f64::NAN, 23.5),
                _ => stock_ui::rich_text("猫", orig_input),
            });
            let (new, b) = measured(|| {
                let input = Once(&calls, input);
                match kind {
                    "content" => ui::content("猫", "x", input),
                    "svg" => ui::svg(input, f64::NAN, 23.5),
                    _ => ui::rich_text("猫", input),
                }
            });
            assert_eq!(calls.get(), 1);
            assert_eq!(
                serde_json::to_vec(&new).unwrap(),
                serde_json::to_vec(&old).unwrap()
            );
            let Value::String(ref value) = new[field] else {
                panic!()
            };
            assert_eq!(value.capacity(), value.len());
            if !s.is_empty() && extra == 0 {
                assert_eq!(value.as_ptr(), ptr);
            }
            if extra != 0 {
                assert_ne!(value.as_ptr(), ptr);
            }
            let saved = usize::from(kind != "rich" && !s.is_empty() && extra == 0);
            assert_eq!(a.alloc, b.alloc + saved);
            assert_eq!(a.realloc, b.realloc);
            assert_eq!(a.bytes, b.bytes + saved * s.len());
            println!(
                "{kind} len={} spare={extra} stock={a:?} candidate={b:?}",
                s.len()
            );
        }
    }
}
