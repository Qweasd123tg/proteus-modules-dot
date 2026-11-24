#![allow(dead_code)]

#[path = "support/r261_stock_ui.rs"]
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

fn payload(v: &Value) -> &String {
    let Value::String(v) = &v["html"] else {
        panic!("html must be a string")
    };
    v
}

fn wire(v: &Value) -> Vec<u8> {
    let keys: Vec<_> = v.as_object().unwrap().keys().map(String::as_str).collect();
    assert_eq!(keys, ["type", "id", "html"]);
    serde_json::to_vec(v).unwrap()
}

#[test]
fn wire_bytes_and_order_match_real_stock() {
    for (id, html) in [
        ("", ""),
        ("html-1", "<p>Обычная строка 🙂 &amp;</p>"),
        ("id\r\n\"\0", "<p title=\"x\">a\r\n\t\0\\🙂Ж &lt;&gt;</p>"),
        (
            "кириллица\u{2028}",
            "<a href=\"https://example.invalid/a?x=1&amp;y=2\">x</a>",
        ),
        ("quote", "<b>&#0; &quot;</b>\n"),
    ] {
        let old = stock_ui::rich_text(id, html);
        let new = ui::rich_text(id, html);
        let owned = ui::rich_text(id, html.to_owned());
        assert_eq!(payload(&old), html);
        assert_eq!(old, new);
        assert_eq!(wire(&old), wire(&new));
        assert_eq!(wire(&old), wire(&owned));
        assert_eq!(payload(&new).capacity(), payload(&old).capacity());
    }
    let sample = ui::rich_text("id", "A\r\n\"\0🙂 &amp;");
    assert_eq!(
        wire(&sample),
        r#"{"type":"rich_text","id":"id","html":"A\r\n\"\u0000🙂 &amp;"}"#.as_bytes()
    );
}

struct Once<'a>(&'a Cell<usize>, String);
impl<'a> From<Once<'a>> for String {
    fn from(once: Once<'a>) -> Self {
        once.0.set(once.0.get() + 1);
        once.1
    }
}

#[test]
fn tight_ownership_and_single_conversion_without_spare_retention() {
    let calls = Cell::new(0);
    let tight = "<b>содержимое</b>".to_owned();
    let ptr = tight.as_ptr();
    assert_eq!(tight.capacity(), tight.len());
    let actual = ui::rich_text("node", Once(&calls, tight));
    assert_eq!(calls.get(), 1);
    assert_eq!(payload(&actual).as_ptr(), ptr);
    let borrowed = "<b>содержимое</b>".to_owned();
    assert_eq!(actual, ui::rich_text("node", &borrowed));
    for html in ["", "x", "Ж 🙂"] {
        let mut loose = String::with_capacity(8_191);
        loose.push_str(html);
        let ptr = loose.as_ptr();
        let stock = stock_ui::rich_text("node", loose.clone());
        let actual = ui::rich_text("node", loose);
        assert_eq!(actual, stock);
        assert_eq!(payload(&actual).capacity(), html.len());
        assert_ne!(payload(&actual).as_ptr(), ptr);
    }
}

#[test]
fn one_scoped_requested_buffer_removed_only_for_tight_owned_html() {
    let html = "<p>Ж &amp; 🙂</p>".repeat(60_000);
    assert!(html.len() > 1_048_576);
    for (name, text, extra, expect) in [
        ("tight-large", html.as_str(), 0, true),
        ("loose-large", html.as_str(), 650_000, false),
        ("tight-small", "<b>x</b>", 0, true),
        ("loose-small", "<b>x</b>", 4_096, false),
        ("empty", "", 0, false),
        ("empty-overreserved", "", 4_096, false),
    ] {
        let mk = || {
            let mut x = String::with_capacity(text.len() + extra);
            x.push_str(text);
            assert_eq!(x.capacity(), text.len() + extra);
            x
        };
        let (old_input, new_input) = (mk(), mk());
        let new_ptr = new_input.as_ptr();
        let (old, a) = measured(move || stock_ui::rich_text("node", black_box(old_input)));
        let (new, b) = measured(move || ui::rich_text("node", black_box(new_input)));
        assert_eq!(wire(&old), wire(&new));
        assert_eq!(payload(&new).capacity(), text.len());
        if expect {
            assert_eq!(payload(&new).as_ptr(), new_ptr);
        }
        let n = usize::from(expect);
        assert_eq!(a.alloc, b.alloc + n);
        assert_eq!(a.realloc, b.realloc);
        assert_eq!(a.bytes, b.bytes + n * text.len());
        println!("{name} len={} stock={a:?} candidate={b:?}", text.len());
    }
}
