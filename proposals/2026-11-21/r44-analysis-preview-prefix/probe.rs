// Compiled into each arm's analysis binary by reproduce.py, outside the shipped patch.
mod probe_alloc {
    use std::alloc::{GlobalAlloc, Layout, System};
    use std::sync::atomic::{AtomicBool, AtomicU64, Ordering::Relaxed};
    static ACTIVE: AtomicBool = AtomicBool::new(false);
    static BYTES: AtomicU64 = AtomicU64::new(0);
    static CALLS: AtomicU64 = AtomicU64::new(0);
    pub struct Counter;
    fn count(n: usize) {
        if ACTIVE.load(Relaxed) {
            BYTES.fetch_add(n as u64, Relaxed);
            CALLS.fetch_add(1, Relaxed);
        }
    }
    unsafe impl GlobalAlloc for Counter {
        unsafe fn alloc(&self, l: Layout) -> *mut u8 { count(l.size()); unsafe { System.alloc(l) } }
        unsafe fn alloc_zeroed(&self, l: Layout) -> *mut u8 { count(l.size()); unsafe { System.alloc_zeroed(l) } }
        unsafe fn dealloc(&self, p: *mut u8, l: Layout) { unsafe { System.dealloc(p,l) } }
        unsafe fn realloc(&self, p: *mut u8, l: Layout, n: usize) -> *mut u8 { count(n); unsafe { System.realloc(p,l,n) } }
    }
    pub fn measure(f: impl FnOnce()) -> (u64, u64) {
        CALLS.store(0, Relaxed);
        BYTES.store(0, Relaxed);
        ACTIVE.store(true, Relaxed);
        f();
        ACTIVE.store(false, Relaxed);
        (BYTES.load(Relaxed), CALLS.load(Relaxed))
    }
}
#[global_allocator]
static ALLOC: probe_alloc::Counter = probe_alloc::Counter;
fn probe_step(body: &str) -> Value {
    json!({"sequence":1, "data":{"kind":"model","request":{"model":{"model":"fixture"},
        "messages":[{"role":"User","parts":[{"payload":{"Text":{"text":body}}}]}]}}})
}
fn probe_time(n: u32, mut f: impl FnMut()) -> u128 {
    let start = std::time::Instant::now();
    for _ in 0..n { f(); }
    start.elapsed().as_nanos() / u128::from(n)
}
fn main() {
    use std::hint::black_box;
    use std::io::Write;
    let mode = std::env::args().nth(1).unwrap();
    for (case, body) in [
        ("empty", "".to_owned()), ("chat", "  Привет!\tРазберём этот пример? 👋 ".repeat(2)),
        ("prose64K", "alpha  beta\n\tgamma delta ".repeat(2622)),
        ("prose1M", "alpha  beta\n\tgamma delta ".repeat(41944)),
        ("word1M", "界".repeat(349526)),
        ("spaces64K", " ".repeat(65536)),
    ] {
        let step = probe_step(&body);
        let headline = || text::preview(black_box(&body), 90);
        let card = || details::step_card(black_box(&step), &nodes::Open);
        if mode == "wire" {
            let mut out = std::io::stdout().lock();
            for s in [headline(), serde_json::to_string(&card()).unwrap()] {
                out.write_all(&(s.len() as u64).to_le_bytes()).unwrap();
                out.write_all(s.as_bytes()).unwrap();
            }
        } else {
            drop(black_box(headline()));
            drop(black_box(card()));
            let (hb, hc) = probe_alloc::measure(|| drop(black_box(headline())));
            let (cb, cc) = probe_alloc::measure(|| drop(black_box(card())));
            let ht = probe_time(if body.len()>100000 {3} else if body.len()>1000 {30} else {1000}, || drop(black_box(headline())));
            let ct = probe_time(if body.len()>100000 {2} else if body.len()>1000 {7} else {40}, || drop(black_box(card())));
            println!("{case} {} {hb} {hc} {cb} {cc} {ht} {ct}",body.len());
        }
    }
}
