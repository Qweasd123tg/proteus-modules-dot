// Test-only child of the exact Mermaid worker module, never installed.
use super::*;
use serde_json::json;
use std::alloc::{GlobalAlloc, Layout, System};
use std::cell::Cell;
use std::hint::black_box;

thread_local! {
    static METER: Cell<Option<(usize, usize)>> = const { Cell::new(None) };
}

fn record(size: usize) {
    let _ = METER.try_with(|meter| {
        if let Some((calls, bytes)) = meter.get() {
            meter.set(Some((calls + 1, bytes + size)));
        }
    });
}

struct Allocations;

unsafe impl GlobalAlloc for Allocations {
    unsafe fn alloc(&self, layout: Layout) -> *mut u8 {
        let ptr = unsafe { System.alloc(layout) };
        if !ptr.is_null() {
            record(layout.size());
        }
        ptr
    }

    unsafe fn alloc_zeroed(&self, layout: Layout) -> *mut u8 {
        let ptr = unsafe { System.alloc_zeroed(layout) };
        if !ptr.is_null() {
            record(layout.size());
        }
        ptr
    }

    unsafe fn dealloc(&self, ptr: *mut u8, layout: Layout) {
        unsafe { System.dealloc(ptr, layout) };
    }

    unsafe fn realloc(&self, ptr: *mut u8, old: Layout, size: usize) -> *mut u8 {
        let ptr = unsafe { System.realloc(ptr, old, size) };
        if !ptr.is_null() {
            record(size);
        }
        ptr
    }
}

#[global_allocator]
static GLOBAL: Allocations = Allocations;

fn payload_len(value: &Value) -> (usize, usize, *const u8) {
    if let Value::String(text) = value {
        (text.len(), text.capacity(), text.as_ptr())
    } else {
        (0, 0, std::ptr::null())
    }
}

fn measure(name: &str, raw: &[u8], error: Option<&str>) {
    // Identical serde_json API to the worker; loading/parsing/shell verification
    // are outside the measured interval. Only the reply projection is counted.
    let decoded: Value = serde_json::from_slice(raw).unwrap();
    let (len, cap, ptr) = payload_len(&decoded["svg"]);
    let expected = error.is_none().then(|| {
        ui::svg(
            decoded["svg"].as_str().unwrap(),
            decoded["width"].as_f64().unwrap(),
            decoded["height"].as_f64().unwrap(),
        ).to_string()
    });
    METER.with(|meter| assert!(meter.replace(Some((0, 0))).is_none()));
    let output = black_box(svg_root(black_box(decoded)));
    let (calls, bytes) = METER.with(|meter| meter.take().unwrap());
    let (outcap, moved) = if let Some(expected) = expected {
        let root = output.unwrap();
        let (root_len, root_cap, root_ptr) = payload_len(&root["source"]);
        assert_eq!(root_len, len);
        assert_eq!(root.to_string(), expected);
        (root_cap, usize::from(root_ptr == ptr))
    } else {
        assert_eq!(output.unwrap_err().to_string(), error.unwrap());
        (0, 0)
    };
    println!("\nprojection {name} {} {len} {cap} {outcap} {moved} {calls} {bytes}", raw.len());
}

#[test]
fn meter_decoded_svg_projection() {
    let path = std::env::var_os("R88_SVG_REPLY").unwrap();
    let large = std::fs::read(path).unwrap();
    let source = "<svg><!--éЖ🦀 \n\t\r \" \\ --></svg>";
    let small = json!({"ok":true,"svg":source,"width":640,"height":1.5});
    let limit = 1024 * 1024;
    let payload = format!(
        "<svg><!--{}--></svg>",
        "x".repeat(limit - "<svg><!----></svg>".len())
    );
    assert_eq!(payload.len(), limit);
    let at_limit = json!({"ok":true,"svg":payload,"width":1,"height":4096});
    let over_limit = json!({"ok":true,"svg":payload+"x","width":0,"height":null});
    measure("small-escaped", small.to_string().as_bytes(), None);
    measure("actual-large", &large, None);
    measure("synthetic-at-limit", at_limit.to_string().as_bytes(), None);
    measure(
        "synthetic-over",
        over_limit.to_string().as_bytes(),
        Some("invalid Mermaid SVG output"),
    );
    measure(
        "invalid-dimensions",
        json!({"ok":true,"svg":source,"width":0,"height":1}).to_string().as_bytes(),
        Some("invalid Mermaid dimensions"),
    );
    measure(
        "bad-status",
        br#"{"ok":false,"error":"fixture render failed","svg":null}"#,
        Some("fixture render failed"),
    );
}
