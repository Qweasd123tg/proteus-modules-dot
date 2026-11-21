// Optional diagnostic module: separately gated, not in the proposed production patch.
use super::*;
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

thread_local! {
    static OBSERVED: Cell<Option<(usize, usize, usize, usize)>> = const { Cell::new(None) };
}

/// Temporary test-only Host::send_ref hook, before its ordinary sent.clone().
/// Does not serialize, allocate or retain the Value, and never runs in a real process.
pub(in crate::host) fn capture(message: &Value) -> bool {
    if !ACTIVE.try_with(Cell::get).unwrap_or(false) {
        return false;
    }
    assert_eq!(message["type"], "badge");
    let lines = message["lines"].as_array().unwrap();
    let line = lines
        .first()
        .and_then(Value::as_str)
        .map_or(0, |text| text.as_ptr() as usize);
    let face = message["face"]["data"]["text"]
        .as_str()
        .map_or(0, |text| text.as_ptr() as usize);
    OBSERVED.with(|cell| {
        assert!(
            cell.replace(Some((lines.len(), lines.capacity(), line, face)))
                .is_none()
        )
    });
    true
}

#[test]
fn meter_owned_badge_envelope() {
    let adopts = match std::env::var("R79_ADOPTS").unwrap().as_str() {
        "yes" => true,
        "no" => false,
        _ => unreachable!(),
    };
    println!();
    for (case, rows, width, reserve, face_kind, error) in [
        ("default-empty", 0, 0, 0, "default", false),
        ("explicit-null", 0, 0, 0, "null", false),
        ("empty-spare", 0, 0, 64, "null", false),
        ("one-spare", 1, 18, 64, "text", false),
        ("nested-face-only", 0, 0, 0, "text", false),
        ("mode-ordinary", 1, 28, 1, "text", true),
        ("context-ordinary", 2, 50, 2, "text", false),
        ("quota-windows", 32, 90, 32, "text", false),
        ("large-owned", 8, 8192, 8, "text", false),
    ] {
        let mut host = Host::default();
        host.session = Some("/synthetic/session".into());
        host.command_error = error.then(|| "fixture command failure".into());
        let mut lines = Vec::with_capacity(reserve);
        lines.extend((0..rows).map(|i| format!("{i:02}: {}", "λ".repeat(width))));
        let input_capacity = lines.capacity();
        let face = match face_kind {
            "text" => Some(
                json!({"type":"text","data":{"text":"Glance λ","z":[null,-0.0,u64::MAX]},"a":true}),
            ),
            "null" => Some(Value::Null),
            _ => None,
        };
        let expected_line = lines.first().map_or(0, |text| text.as_ptr() as usize);
        let expected_face = face
            .as_ref()
            .and_then(|value| value["data"]["text"].as_str())
            .map_or(0, |text| text.as_ptr() as usize);
        OBSERVED.with(|cell| cell.set(None));
        let ((), requests, bytes) =
            measure(|| host.send_badge("fixture", "Показатель", lines, face, false));
        let (seen_rows, output_capacity, seen_line, seen_face) = OBSERVED.with(Cell::get).unwrap();
        assert_eq!(seen_rows, rows + usize::from(error));
        if rows > 0 {
            assert_eq!(seen_line == expected_line, adopts);
        } else {
            assert_eq!(seen_line, 0);
        }
        if expected_face != 0 {
            assert_eq!(seen_face == expected_face, adopts);
        } else {
            assert_eq!(seen_face, 0);
        }
        assert!(host.sent.borrow().is_empty());
        assert!(!host.is_shown("fixture"));
        println!(
            "badge {case} {rows} {width} {input_capacity} {output_capacity} {requests} {bytes}"
        );
    }
}
