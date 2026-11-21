// Added only to the temporary measurement binary; not part of the production patch.
use std::alloc::{GlobalAlloc, Layout, System};
use std::sync::atomic::{AtomicUsize, Ordering::Relaxed};
struct Meter;
#[global_allocator] static METER: Meter = Meter;
static CALLS: AtomicUsize = AtomicUsize::new(0);
static BYTES: AtomicUsize = AtomicUsize::new(0);
unsafe impl GlobalAlloc for Meter {
    unsafe fn alloc(&self, l: Layout) -> *mut u8 {
        let p = unsafe { System.alloc(l) }; if !p.is_null() { CALLS.fetch_add(1,Relaxed); BYTES.fetch_add(l.size(),Relaxed); } p
    }
    unsafe fn dealloc(&self, p: *mut u8, l: Layout) { unsafe { System.dealloc(p,l) } }
    unsafe fn realloc(&self, p: *mut u8, l: Layout, n:usize) -> *mut u8 {
        let p = unsafe { System.realloc(p,l,n) }; if !p.is_null() { CALLS.fetch_add(1,Relaxed); BYTES.fetch_add(n,Relaxed); } p
    }
}
fn measured<T>(op: impl FnOnce() -> T) -> (T,usize,usize) {
    CALLS.store(0,Relaxed); BYTES.store(0,Relaxed);
    let result=std::hint::black_box(op());
    (result,CALLS.load(Relaxed),BYTES.load(Relaxed))
}
fn main() {
    let mode=std::env::args().nth(1).unwrap();
    if mode=="matrix" {
        let prototypes=[
            json!({"status":"added","staged":"added"}),json!({"status":"modified","staged":false}),
            json!({"status":"renamed","staged":true}),json!({"status":"deleted","staged":null}),
            json!({"status":"untracked"}),json!({"status":"conflict","staged":false}),json!({"status":"unknown"}),
        ];
        for n in 0..=4 {
            for mut code in 0..prototypes.len().pow(n) {
                let data=(0..n).map(|i|{
                    let mut e=prototypes[code%prototypes.len()].clone(); code/=prototypes.len();
                    e["path"]=json!(format!("src/{i}-файл")); e
                }).collect::<Vec<_>>();
                println!("{}",json!(model::suggestion(&data)));
            }
        }
        return;
    }
    assert_eq!(mode,"counts");
    let host=Host::default();
    for n in [1,32,512,2000] {
        for shape in ["unstaged","one-staged","all-staged","only-untracked","late-conflict"] {
            let entries=(0..n).map(|i|{
                let staged=match shape { "one-staged"|"late-conflict" => i==0, "all-staged"=>true, _=>false };
                let status=if shape=="only-untracked" { "untracked" } else if shape=="late-conflict" && i==n-1 { "conflict" } else { "modified" };
                json!({"path":format!("src/файл-{i}.rs"),"status":status,"staged":staged,"unstaged":!staged})
            }).collect::<Vec<_>>();
            let (s,c,b)=measured(||model::suggestion(&entries));
            println!("{n} {shape} suggestion {c} {b} {:?}",s);
            let git=Git::default();
            let (editor,c,b)=measured(||git.probe_editor(&Value::Null,&entries));
            println!("{n} {shape} editor {c} {b} {}", editor.to_string().len());
            if n<=32 {
                let mut git=Git{branches:Some(vec![]),changes:Rc::new(json!({"repository":true,"entries":entries})),..Git::default()};
                let (page,c,b)=measured(||git.panel(&host,"test","main").unwrap());
                println!("{n} {shape} panel {c} {b} {}",page.to_string().len());
            }
        }
    }
}
