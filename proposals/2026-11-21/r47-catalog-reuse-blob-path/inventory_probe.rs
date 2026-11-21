// Local synthetic test only.
use std::{
    alloc::{GlobalAlloc, Layout, System},
    cell::Cell,
    time::Instant,
};
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
        }
    });
}
struct ProbeAlloc;
#[global_allocator]
static R47_PROBE_ALLOC: ProbeAlloc = ProbeAlloc;
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

type Inventory = fn(&Path) -> Option<BlobStamps>;

#[test]
#[ignore = "manual local allocation and CPU microbenchmark"]
fn r47_measure_blob_inventory() {
    let modes: [(&str, Inventory); 2] = [("stock", stock), ("candidate", blob_stamps)];
    for case in ["missing", "flat", "nested"] {
        let dir = tempfile::tempdir().unwrap();
        let root = dir.path().join("blobs");
        let expected_len = match case {
            "missing" => 0,
            "flat" | "nested" => {
                std::fs::create_dir(&root).unwrap();
                if case == "nested" {
                    for i in 0..8 {
                        std::fs::create_dir(root.join(format!("bucket-{i:02}"))).unwrap();
                    }
                }
                for i in 0..492 {
                    let name = format!("file-{i:04}-{}.bin", "z".repeat(i % 17));
                    let file = if case == "nested" {
                        root.join(format!("bucket-{:02}", i % 8)).join(name)
                    } else {
                        root.join(name)
                    };
                    std::fs::write(file, []).unwrap();
                }
                492 + if case == "nested" { 8 } else { 0 }
            }
            _ => unreachable!(),
        };
        let expected = stock(dir.path()).unwrap();
        assert_eq!(expected.len(), expected_len);
        let digest = blob_stamp_digest(&expected);
        assert!(blob_stamps(dir.path()).unwrap() == expected);
        let trials = 40;
        for trial in 0..trials {
            for pos in 0..2 {
                let (name, run) = modes[(pos + (trial / 2) + (trial % 2)) % 2];
                ALL.set(Some(Traffic::default()));
                let observed = run(dir.path()).unwrap();
                let traffic = ALL.replace(None).unwrap();
                assert!(!traffic.bad);
                assert!(observed == expected);
                assert_eq!(blob_stamp_digest(&observed), digest);
                drop(observed);

                let wall0 = Instant::now();
                let cpu0 = cpu_ns();
                let observed = run(dir.path()).unwrap();
                let cpu = cpu_ns() - cpu0;
                let wall = wall0.elapsed().as_nanos();
                assert_eq!(observed.len(), expected_len);
                println!(
                    "R47,{case},{expected_len},{trial},{name},{},{},{},{cpu},{wall}",
                    traffic.ops, traffic.bytes, traffic.peak
                );
            }
        }
    }
}
