
#[cfg(test)]
mod r7_eviction_allocations {
    use super::*;
    use std::{
        alloc::{GlobalAlloc, Layout, System},
        fs::{File,FileTimes},
        sync::atomic::{AtomicIsize,AtomicUsize,Ordering::Relaxed},
        time::{Duration,UNIX_EPOCH},
    };
    struct Measure;
    #[global_allocator]
    static ALLOCATOR: Measure = Measure;
    thread_local! { static ACTIVE: std::cell::Cell<bool> = const { std::cell::Cell::new(false) }; }
    static CALLS: AtomicUsize=AtomicUsize::new(0);
    static BYTES: AtomicUsize=AtomicUsize::new(0);
    static LIVE: AtomicIsize=AtomicIsize::new(0);
    static PEAK: AtomicIsize=AtomicIsize::new(0);
    fn record(size:usize,old:usize) {
        CALLS.fetch_add(1,Relaxed);
        BYTES.fetch_add(size,Relaxed);
        let delta=size as isize - old as isize;
        let net=LIVE.fetch_add(delta,Relaxed)+delta;
        PEAK.fetch_max(net,Relaxed);
    }
    unsafe impl GlobalAlloc for Measure {
        unsafe fn alloc(&self,l:Layout)->*mut u8 {
            if ACTIVE.get() {record(l.size(),0);}
            unsafe{System.alloc(l)}
        }
        unsafe fn alloc_zeroed(&self,l:Layout)->*mut u8 {
            if ACTIVE.get() {record(l.size(),0);}
            unsafe{System.alloc_zeroed(l)}
        }
        unsafe fn realloc(&self,p:*mut u8,l:Layout,n:usize)->*mut u8 {
            if ACTIVE.get() {record(n,l.size());}
            unsafe{System.realloc(p,l,n)}
        }
        unsafe fn dealloc(&self,p:*mut u8,l:Layout) {
            if ACTIVE.get() {LIVE.fetch_sub(l.size() as isize,Relaxed);}
            unsafe{System.dealloc(p,l)}
        }
    }
    #[test]
    #[ignore="Test-only native allocation measurement; run alone"]
    fn measure_cache_eviction_allocation() {
        for n in [0usize,256,2048,8192] {
            let tmp=tempfile::tempdir().unwrap();
            let dir=tmp.path();
            let keep=dir.join(format!(".storage-cache-{:064x}.json",n));
            File::create(&keep).unwrap();
            for i in 0..n {
                let f=File::create(dir.join(format!(".storage-cache-{i:064x}.json"))).unwrap();
                f.set_len(500).unwrap();
                let stamp=UNIX_EPOCH+Duration::from_nanos((i as u64*2_654_435_761) % (1<<32));
                f.set_times(FileTimes::new().set_modified(stamp)).unwrap();
            }
            for rep in 0..3 {
                CALLS.store(0,Relaxed);BYTES.store(0,Relaxed);
                LIVE.store(0,Relaxed);PEAK.store(0,Relaxed);
                ACTIVE.set(true);evict(dir,&keep).unwrap();ACTIVE.set(false);
                assert_eq!(LIVE.load(Relaxed),0);
                println!("ALLOC seed={n} rep={rep} calls={} bytes={} peak={}",
                    CALLS.load(Relaxed),BYTES.load(Relaxed),PEAK.load(Relaxed));
            }
        }
    }
}
