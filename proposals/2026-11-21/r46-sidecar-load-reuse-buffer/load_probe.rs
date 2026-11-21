// Disposable test instrumentation only. Never add this module to a production build.
use crate::service::views::PrefixCache;
use crate::tests::{Fixture, backends, text};
use std::{
    alloc::{GlobalAlloc, Layout, System},
    cell::Cell,
    time::Instant,
};

struct R46Digest(ring::digest::Context);
impl std::io::Write for R46Digest {
    fn write(&mut self, bytes: &[u8]) -> std::io::Result<usize> {
        self.0.update(bytes);
        Ok(bytes.len())
    }
    fn flush(&mut self) -> std::io::Result<()> {
        Ok(())
    }
}

#[derive(Clone, Copy, Default, Debug)]
struct Traffic {
    ops: u64,
    bytes: usize,
    live: usize,
    peak: usize,
    bad: bool,
}
impl Traffic {
    fn add(&mut self, n: usize) {
        self.ops += 1;
        self.bytes += n;
        self.live += n;
        self.peak = self.peak.max(self.live);
    }
}
thread_local! {
    static ALL: Cell<Option<Traffic>> = const { Cell::new(None) };
    static HASH: Cell<bool> = const { Cell::new(false) };
    static HASH_TRAFFIC: Cell<Traffic> = const { Cell::new(Traffic { ops:0, bytes:0, live:0, peak:0, bad:false }) };
    static CPU_MODE: Cell<bool> = const { Cell::new(false) };
    static CPU_HASH_NS: Cell<u64> = const { Cell::new(0) };
}
fn record(old: usize, new: usize) {
    let _ = ALL.try_with(|all| {
        if let Some(mut t) = all.get() {
            if old > t.live {
                t.bad = true;
            }
            t.live = t.live.saturating_sub(old);
            if new != 0 {
                t.add(new);
            }
            all.set(Some(t));
            if HASH.get() {
                let mut h = HASH_TRAFFIC.get();
                h.live = t.live;
                h.peak = h.peak.max(h.live);
                if new != 0 {
                    h.ops += 1;
                    h.bytes += new;
                }
                HASH_TRAFFIC.set(h);
            }
        }
    });
}
struct ProbeAlloc;
#[global_allocator]
static R46_PROBE_ALLOC: ProbeAlloc = ProbeAlloc;
// Forward the original pointer/layout to System without changing any allocation.
// Realloc is counted as the newly requested bytes, and peak is logical live bytes,
// not physical allocator internals while moving blocks.
unsafe impl GlobalAlloc for ProbeAlloc {
    unsafe fn alloc(&self, layout: Layout) -> *mut u8 {
        let ptr = unsafe { System.alloc(layout) };
        if !ptr.is_null() {
            record(0, layout.size());
        }
        ptr
    }
    unsafe fn alloc_zeroed(&self, layout: Layout) -> *mut u8 {
        let ptr = unsafe { System.alloc_zeroed(layout) };
        if !ptr.is_null() {
            record(0, layout.size());
        }
        ptr
    }
    unsafe fn realloc(&self, ptr: *mut u8, layout: Layout, size: usize) -> *mut u8 {
        let ptr = unsafe { System.realloc(ptr, layout, size) };
        if !ptr.is_null() {
            record(layout.size(), size);
        }
        ptr
    }
    unsafe fn dealloc(&self, ptr: *mut u8, layout: Layout) {
        unsafe { System.dealloc(ptr, layout) };
        record(layout.size(), 0);
    }
}

#[cfg(all(target_os = "linux", target_arch = "x86_64"))]
fn cpu_ns() -> u64 {
    #[repr(C)]
    struct Timespec {
        sec: i64,
        nsec: i64,
    }
    unsafe extern "C" {
        fn clock_gettime(clock: core::ffi::c_int, out: *mut Timespec) -> core::ffi::c_int;
    }
    let mut ts = Timespec { sec: 0, nsec: 0 };
    // Linux x86-64 CLOCK_THREAD_CPUTIME_ID; pointer holds a writable timespec.
    assert_eq!(unsafe { clock_gettime(3, &mut ts) }, 0);
    (ts.sec as u64) * 1_000_000_000 + ts.nsec as u64
}
#[cfg(not(all(target_os = "linux", target_arch = "x86_64")))]
fn cpu_ns() -> u64 {
    0
}

fn r46_checksum<T>(operation: impl FnOnce() -> T) -> T {
    if let Some(t) = ALL.get() {
        HASH_TRAFFIC.set(Traffic {
            live: t.live,
            peak: t.live,
            ..Traffic::default()
        });
        HASH.set(true);
        let result = operation();
        HASH.set(false);
        return result;
    }
    if CPU_MODE.get() {
        let t = cpu_ns();
        let result = operation();
        CPU_HASH_NS.set(cpu_ns() - t);
        return result;
    }
    operation()
}

type Loader = fn(
    &Path,
    &StorageSessionDescriptor,
    &SourceStamp,
) -> Option<(StorageSessionSummary, PrefixCache)>;

#[test]
#[ignore = "manual synthetic benchmark; not a product test"]
fn r46_measure_durable_sidecar_load() {
    let modes: [(&str, Loader); 5] = [
        ("stock", stock),
        ("early_drop", early_drop),
        ("reuse", reuse),
        ("stream", stream),
        ("buffered", buffered),
    ];
    let heavy = std::env::var_os("R46_NEAR_LIMIT").is_some();
    let sizes: &[usize] = if heavy { &[0, 492, 12_000] } else { &[0, 492] };
    for kind in backends() {
        for &count in sizes {
            let mut f = Fixture::new(kind);
            for _ in 0..8 {
                f.append(vec![text(&"p".repeat(512))]);
            }
            let dir = f.descriptor.local_path.as_ref().unwrap();
            let blobs = dir.join("blobs");
            if count != 0 {
                std::fs::create_dir_all(&blobs).unwrap();
                let tail = if count > 492 {
                    "p".repeat(190)
                } else {
                    String::new()
                };
                for i in 0..count {
                    std::fs::write(blobs.join(format!("inventory-{i:05}{tail}")), b"").unwrap();
                }
            }
            let wanted = StorageService::new(kind)
                .catalog_summary(dir, false)
                .unwrap();
            let descriptor = wanted.descriptor.clone();
            let stamps = source_stamp(dir, kind).unwrap();
            let in_bytes = std::fs::metadata(dir.join(FILE)).unwrap().len();
            if count > 492 {
                assert!((3_500_000..=MAX_BYTES as u64).contains(&in_bytes));
            }
            let (summary, prefix) = load(dir, &descriptor, &stamps).unwrap();
            assert_eq!(wanted, summary);
            let check = |(summary, actual): (StorageSessionSummary, PrefixCache)| {
                assert_eq!(summary, wanted);
                assert_eq!(actual.revision, prefix.revision);
                assert_eq!(actual.hint.extent, prefix.hint.extent);
                assert_eq!(actual.hint.fingerprint, prefix.hint.fingerprint);
                assert_eq!(actual.blob_digest, prefix.blob_digest);
                assert!(actual.stamps == prefix.stamps);
            };
            let trials = if count > 492 { 7 } else { 16 };
            for trial in 0..trials {
                for position in 0..modes.len() {
                    let (name, func) = modes[(position + trial) % modes.len()];
                    ALL.set(Some(Traffic::default()));
                    let result = func(dir, &descriptor, &stamps).unwrap();
                    let traffic = ALL.replace(None).unwrap();
                    assert!(!traffic.bad, "pre-existing allocation released in probe");
                    let hash = HASH_TRAFFIC.get();
                    check(result);
                    CPU_MODE.set(true);
                    let wall_start = Instant::now();
                    let cpu_start = cpu_ns();
                    let result = func(dir, &descriptor, &stamps).unwrap();
                    let cpu = cpu_ns() - cpu_start;
                    let wall = wall_start.elapsed().as_nanos();
                    CPU_MODE.set(false);
                    check(result);
                    println!(
                        "R46,{kind:?},{count},{in_bytes},{trial},{name},{},{},{},{},{},{},{cpu},{},{wall}",
                        traffic.ops,
                        traffic.bytes,
                        traffic.peak,
                        hash.ops,
                        hash.bytes,
                        hash.peak,
                        CPU_HASH_NS.get()
                    );
                }
            }
        }
    }
}
