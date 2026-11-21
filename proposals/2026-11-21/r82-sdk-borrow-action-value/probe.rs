// Optional separate diagnostic; measures existing production Host::handle action delivery.
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

#[derive(Default)]
struct Observer {
    seen: Option<usize>,
}

fn first_text(value: &Value) -> Option<usize> {
    value
        .as_str()
        .or_else(|| value["z"][0]["title"].as_str())
        .map(|text| text.as_ptr() as usize)
}

impl Extension for Observer {
    fn render(&mut self, _: &mut Host, _: &str, _: Surface, _: Option<&str>) -> Result {
        Ok(())
    }

    fn action(&mut self, _: &mut Host, _: &str, _: &str, value: &Value) -> Result {
        self.seen = first_text(value);
        Ok(())
    }
}

#[test]
fn meter_borrowed_action_payload() {
    let adopts = match std::env::var("R81_BORROWS").unwrap().as_str() {
        "yes" => true,
        "no" => false,
        _ => unreachable!(),
    };
    println!();
    for (case, value) in [
        ("missing", None),
        ("null", Some(Value::Null)),
        ("number", Some(json!(4))),
        ("small-query", Some(json!("Поиск λ"))),
        ("draft-16k", Some(Value::String("λ".repeat(8192)))),
        (
            "nested-32",
            Some(
                json!({"z":(0..32).map(|i| json!({"title":format!("Ход λ {i:03}"),
                        "z":[-0.0,u64::MAX,null], "a":"synthetic evidence".repeat(16)}))
                        .collect::<Vec<_>>(),"a":false}),
            ),
        ),
    ] {
        let (mut host, mut extension) = (Host::default(), Observer::default());
        host.handle(
            &mut extension,
            json!({"type":"render","context":"fixture","view":"panel",
                "session_dir":"/action-fixture","surface":"panel"}),
        )
        .unwrap();
        let mut message = json!({"type":"action","view":"panel","action":"edit","sequence":1});
        if let Some(value) = value {
            message["value"] = value;
        }
        let input = first_text(message.at("value"));
        let raw_bytes = message.at("value").to_string().len();
        let (result, calls, bytes) = measure(|| host.handle(&mut extension, message));
        result.unwrap();
        assert!(host.current_view.is_none());
        assert_eq!(host.sequence("panel"), 1);
        assert!(host.sent.borrow().is_empty());
        if input.is_some() {
            assert!(extension.seen.is_some());
            assert_eq!(extension.seen == input, adopts, "{case}");
        } else {
            assert_eq!(extension.seen, None);
        }
        println!("action {case} {raw_bytes} {calls} {bytes}");
    }
}
