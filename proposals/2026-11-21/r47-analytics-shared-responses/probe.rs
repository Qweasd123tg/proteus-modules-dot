// Built as a temporary SDK example by reproduce.py. This is not production code.
use proteus_extension::{Analytics, Host, Server};
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
        unsafe { System.dealloc(p, layout) };
    }

    unsafe fn realloc(&self, p: *mut u8, layout: Layout, size: usize) -> *mut u8 {
        let ret = unsafe { System.realloc(p, layout, size) };
        if !ret.is_null() {
            record(size);
        }
        ret
    }
}

fn main() {
    let mut host = Host::default();
    host.session = Some("/fixture/active".into());
    host.server = Some(Server {
        origin: std::env::args().nth(1).unwrap(),
        token: "fixture".into(),
    });
    let mut cache = Analytics::new(None);
    for case in ["tiny", "scalar-1m", "nested", "oversized"] {
        let path = format!("/{case}");
        for pass in ["first", "repeat"] {
            CALLS.store(0, Relaxed);
            BYTES.store(0, Relaxed);
            let value = cache.__FETCH__(&host, &path, &[], false).unwrap();
            let calls = CALLS.load(Relaxed);
            let bytes = BYTES.load(Relaxed);
            println!("{case} {pass} {calls} {bytes}");
            assert_eq!(value["case"], case);
            assert_eq!(value["revision"], 1);
            std::hint::black_box(value);
        }
    }

    // Compatibility entrypoint returns an independently mutable JSON value,
    // not the retained snapshot. This check is outside allocation accounting.
    let mut owned = cache.fetch(&host, "/tiny", &[], false).unwrap();
    owned["revision"] = serde_json::json!(2);
    assert_eq!(
        cache.__FETCH__(&host, "/tiny", &[], false).unwrap()["revision"],
        1
    );
}
