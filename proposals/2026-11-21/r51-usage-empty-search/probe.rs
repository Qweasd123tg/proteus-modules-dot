// Temporary counting allocator and main added only to the benchmark build.
mod measure {
    use super::*;
    use proteus_extension::json;
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
            if !p.is_null() { record(layout.size()); }
            p
        }
        unsafe fn dealloc(&self, p: *mut u8, layout: Layout) {
            unsafe { System.dealloc(p, layout) };
        }
        unsafe fn realloc(&self, p: *mut u8, layout: Layout, size: usize) -> *mut u8 {
            let new = unsafe { System.realloc(p, layout, size) };
            if !new.is_null() { record(size); }
            new
        }
    }


    pub fn run() {
        let mode = std::env::args().nth(1).unwrap();
        for n in [20, 400, 2000] {
            let rows: Vec<_> = (0..n).map(|i| json!({
                "exchange_id":format!("request-{i}"),
                "turn_id":format!("turn-{}", i/8),
                "status": if i%5==0 {"error"} else {"completed"},
                "model":if i%8==0 {
                    json!({"provider":"Пример","model":"İstanbul"})
                } else {
                    json!({"provider":"Fixture","model":"gpt-6-astra"})
                },
                "usage": if i%7==0 {Value::Null} else {json!({"input_tokens":100,"output_tokens":25})},
                "started_at_ms": 1700000000000_u64 + i*2000,
                "finished_at_ms": 1700000001000_u64 + i*2000
            })).collect();
            let snapshot = json!({"latest_turn_id": format!("turn-{}",(n-1)/8), "requests":rows});
            let rows = snapshot["requests"].as_array().unwrap().iter().collect::<Vec<_>>();
            for (name,query,status,order) in [
                ("default", "", "all", "oldest"),
                ("blank", "  \t\u{2003}", "all", "oldest"),
                ("typed", "FiXTURE astra", "all", "oldest"),
                ("unicode", "İSTANBUL\u{2003}ПРИМЕР", "problems", "tokens"),
                ("miss", "absent", "all", "newest"),
            ] {
                CALLS.store(0, Relaxed);
                BYTES.store(0, Relaxed);
                let result = report::filtered(&rows,status,query,order).unwrap();
                let (select_calls,select_b) = (CALLS.load(Relaxed),BYTES.load(Relaxed));
                let mut state = Usage {
                    query: query.into(), status: status.into(), order: order.into(),
                    ..Usage::default()
                };
                CALLS.store(0, Relaxed);
                BYTES.store(0, Relaxed);
                let page = state.page(Value::Null, &snapshot).unwrap();
                let (page_calls,page_b) = (CALLS.load(Relaxed),BYTES.load(Relaxed));
                let serialized = page.to_string();
                if name=="default" || name=="blank" { assert_eq!(result.len(), rows.len()); }
                if name=="miss" { assert!(result.is_empty()); }
                if name=="typed" || name=="unicode" { assert!(!result.is_empty()); }
                if mode=="measure" {
                    println!("{n} {name} {} {select_calls} {select_b} {page_calls} {page_b} {}",result.len(),serialized.len());
                } else {
                    assert_eq!(mode,"wire");
                    let ids = result.iter().map(|r| r["exchange_id"].as_str().unwrap()).collect::<Vec<_>>();
                    println!("{}",json!({"ids":ids,"root":page}));
                }
            }
        }
    }
}
fn main() { measure::run(); }
