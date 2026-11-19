// Included at the end of packages/files/src/probe.rs instead of its main().
// No network, no cache bypass: seed a deterministic listing, then call Files::panel.
#[cfg(heap_probe)]
mod meter {
    use std::alloc::{GlobalAlloc, Layout, System};
    use std::sync::atomic::{AtomicUsize, Ordering::Relaxed};
    pub static LIVE: AtomicUsize = AtomicUsize::new(0);
    pub static PEAK: AtomicUsize = AtomicUsize::new(0);
    pub static TOTAL: AtomicUsize = AtomicUsize::new(0);
    pub static CALLS: AtomicUsize = AtomicUsize::new(0);
    struct Meter;
    #[global_allocator]
    static M: Meter = Meter;
    unsafe impl GlobalAlloc for Meter {
        unsafe fn alloc(&self, l:Layout) -> *mut u8 {
            let p=unsafe { System.alloc(l) }; if !p.is_null() { record(0,l.size()); } p
        }
        unsafe fn alloc_zeroed(&self, l:Layout) -> *mut u8 {
            let p=unsafe { System.alloc_zeroed(l) }; if !p.is_null() { record(0,l.size()); } p
        }
        unsafe fn realloc(&self,p:*mut u8,l:Layout,n:usize)->*mut u8 {
            let q=unsafe { System.realloc(p,l,n) }; if !q.is_null() {record(l.size(),n);} q
        }
        unsafe fn dealloc(&self,p:*mut u8,l:Layout) {
            LIVE.fetch_sub(l.size(), Relaxed); unsafe {System.dealloc(p,l)}
        }
    }
    fn record(old:usize,new:usize) {
        let live=if new>=old { LIVE.fetch_add(new-old,Relaxed)+new-old } else { LIVE.fetch_sub(old-new,Relaxed)-(old-new) };
        PEAK.fetch_max(live,Relaxed); TOTAL.fetch_add(new,Relaxed); CALLS.fetch_add(1,Relaxed);
    }
}

fn main() {
    use std::hint::black_box;
    let args:Vec<String>=std::env::args().collect();
    let n:usize=args[1].parse().unwrap();
    let mode=&args[2];
    let mut files=Files::default();
    files.cwd=Some("/demo/Проект".into());
    let host=Host::default();
    let entries = (0..n).map(|i| {
        let name=format!("example_{i:04}_файл.rs");
        tree::Entry { path:name.clone(), name, kind:Kind::File }
    }).collect();
    let mut listing=Some(tree::Listing{ entries, truncated:false });
    files.project.lines("Проект", &mut |_| Ok(listing.take().unwrap())).unwrap();
    let warm = files.panel(&host).unwrap();
    assert_eq!(warm["children"].as_array().unwrap().last().unwrap()["rows"].as_array().unwrap().len(),n+1);
    if mode=="emit" { print!("{}",warm); return; }
    drop(warm);
    if mode=="time" {
        let reps:usize=args[3].parse().unwrap(); let t=Instant::now();
        for _ in 0..reps { drop(black_box(files.panel(&host).unwrap())); }
        println!("{}",t.elapsed().as_nanos()/reps as u128);
    }
    #[cfg(heap_probe)]
    if mode=="heap" {
        use std::sync::atomic::Ordering::Relaxed;
        let base=meter::LIVE.load(Relaxed);
        meter::PEAK.store(base,Relaxed);
        meter::CALLS.store(0,Relaxed); meter::TOTAL.store(0,Relaxed);
        let root=black_box(files.panel(&host).unwrap());
        let (peak,live,total,calls)=(meter::PEAK.load(Relaxed)-base,meter::LIVE.load(Relaxed)-base,meter::TOTAL.load(Relaxed),meter::CALLS.load(Relaxed));
        drop(root); let retained=meter::LIVE.load(Relaxed) as isize - base as isize;
        println!("{{\"peak\":{peak},\"root_live\":{live},\"requested\":{total},\"calls\":{calls},\"after_drop\":{retained}}}");
    }
}
