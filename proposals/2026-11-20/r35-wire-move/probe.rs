// Differential probe only; not linked into the product. See README.
use proteus_contracts::contracts::{ProcessComponentExportRef, SessionStorageRequest};
pub use proteus_module_protocol::ProcessModuleRpcError;
use serde_json::{Value, json};
use std::{
    alloc::{GlobalAlloc, Layout, System},
    sync::atomic::{AtomicUsize, Ordering::Relaxed},
};
mod invocation {
    pub use proteus_module_protocol::v3::CancelCause;
}
#[allow(dead_code)]
mod wire;

static ALLOCS: AtomicUsize = AtomicUsize::new(0);
static REQUESTED: AtomicUsize = AtomicUsize::new(0);
struct Counts;
#[global_allocator]
static COUNTS: Counts = Counts;
unsafe impl GlobalAlloc for Counts {
    unsafe fn alloc(&self, l: Layout) -> *mut u8 {
        add(l.size());
        unsafe { System.alloc(l) }
    }
    unsafe fn alloc_zeroed(&self, l: Layout) -> *mut u8 {
        add(l.size());
        unsafe { System.alloc_zeroed(l) }
    }
    unsafe fn realloc(&self, p: *mut u8, l: Layout, n: usize) -> *mut u8 {
        add(n);
        unsafe { System.realloc(p, l, n) }
    }
    unsafe fn dealloc(&self, p: *mut u8, l: Layout) {
        unsafe { System.dealloc(p, l) }
    }
}
fn add(n: usize) {
    ALLOCS.fetch_add(1, Relaxed);
    REQUESTED.fetch_add(n, Relaxed);
}
fn snap() -> (usize, usize) {
    (ALLOCS.load(Relaxed), REQUESTED.load(Relaxed))
}
fn cache_write(value: Value) -> Value {
    let session = json!({"session_id":"00000000-0000-4000-8000-000000000001","key":"slot"});
    let source = json!({"session":session,"snapshot_id":"fixed","revision":{"session_seq":7,"history_revision":1},"content_sha256":"0".repeat(64)});
    let typed:SessionStorageRequest = serde_json::from_value(json!({"operation":"write_cache","session":session,"key":"header","source":source,"value":value})).unwrap();
    typed.validate().unwrap();
    serde_json::to_value(typed).unwrap()
}
fn main() {
    let out = std::env::args_os().nth(1).expect("output directory");
    let dir = std::path::Path::new(&out);
    std::fs::create_dir_all(dir).unwrap();
    let shapes = vec![
        ("null", Value::Null),
        ("bool", json!(false)),
        ("i64_min", json!(i64::MIN)),
        ("u64_max", json!(u64::MAX)),
        ("float_negative_zero", json!(-0.0)),
        (
            "reordered_duplicate",
            serde_json::from_str(r#"{"z":1,"q":[],"a":null,"z":2}"#).unwrap(),
        ),
        (
            "escaping",
            json!({"z":"\n\r\t\u{0}\\\"Ж😀","a": [null,true,{},[]]}),
        ),
        ("write_cache_empty", cache_write(json!([]))),
        (
            "write_cache_1m",
            cache_write(Value::String("x".repeat(1 << 20))),
        ),
        (
            "write_cache_4k_rows",
            cache_write(Value::Array(
                (0..4096)
                    .map(|i| json!({"seq":i,"text":"факт","z":[i,true,null]}))
                    .collect(),
            )),
        ),
    ];
    println!("case,wire_bytes,alloc_or_realloc_calls,requested_bytes");
    let export = ProcessComponentExportRef::new("session_storage", "fixture");
    for (name, params) in shapes {
        for nested in [false, true] {
            let payload = params.clone();
            let begin = snap();
            let frame = wire::invocation_request(
                "h:7:3",
                "execute",
                &export,
                if nested { "h:7:1" } else { "h:7:3" },
                nested.then_some("h:7:2"),
                if nested { 2 } else { 0 },
                payload,
            )
            .unwrap();
            let end = snap();
            let b = serde_json::to_vec(&frame).unwrap();
            let case = format!("{}-{}", name, if nested { "nested" } else { "root" });
            println!(
                "{},{},{},{}",
                case,
                b.len(),
                end.0 - begin.0,
                end.1 - begin.1
            );
            std::fs::write(dir.join(case), b).unwrap();
        }
    }
    let init =
        json!({"z":1,"_meta":{"z":"escaped\n","a":null},"exports":[{"z":true,"a":false}],"a":{}});
    let init = serde_json::to_value(init).unwrap(); // same post-DTO boundary as initialize_transport
    let start = snap();
    let frame = wire::initialize_request(7, init);
    let end = snap();
    let bytes = serde_json::to_vec(&frame).unwrap();
    println!(
        "initialize,{},{},{}",
        bytes.len(),
        end.0 - start.0,
        end.1 - start.1
    );
    std::fs::write(dir.join("initialize"), bytes).unwrap();
}
