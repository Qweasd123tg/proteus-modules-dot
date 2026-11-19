use serde::{Deserialize,Serialize};
use std::{alloc::{GlobalAlloc,Layout,System},sync::atomic::{AtomicU64,Ordering::Relaxed},path::PathBuf,time::Instant,hint::black_box};
#[cfg(counting)] struct Count;
#[cfg(counting)] #[global_allocator] static ALLOC: Count=Count;
static N: AtomicU64=AtomicU64::new(0); static B: AtomicU64=AtomicU64::new(0);
#[cfg(counting)] unsafe impl GlobalAlloc for Count {
    unsafe fn alloc(&self,l:Layout)->*mut u8{N.fetch_add(1,Relaxed);B.fetch_add(l.size() as u64,Relaxed);unsafe{System.alloc(l)}}
    unsafe fn alloc_zeroed(&self,l:Layout)->*mut u8{N.fetch_add(1,Relaxed);B.fetch_add(l.size() as u64,Relaxed);unsafe{System.alloc_zeroed(l)}}
    unsafe fn realloc(&self,p:*mut u8,l:Layout,s:usize)->*mut u8{N.fetch_add(1,Relaxed);B.fetch_add(s as u64,Relaxed);unsafe{System.realloc(p,l,s)}}
    unsafe fn dealloc(&self,p:*mut u8,l:Layout){unsafe{System.dealloc(p,l)}}
}
#[derive(Serialize,Deserialize)]
#[serde(tag="storage",rename_all="snake_case",deny_unknown_fields)]
enum StoredPayload { Inline{value:serde_json::Value}, Blob{sha256:String,bytes:u64,relative_path:PathBuf} }
#[path="modules/storage/session-storage/src/codec/payload.rs"] mod payload;
#[derive(Deserialize)] struct Stock {payload:StoredPayload}
#[derive(Deserialize)] struct Candidate {#[serde(deserialize_with="payload::read")] payload:StoredPayload}
fn main(){
    let arg: Vec<_>=std::env::args().collect();
    let bytes=std::fs::read(&arg[1]).unwrap();let rows: Vec<_>=bytes.split(|b|*b==b'\n').filter(|r|!r.is_empty()).collect();
    let stock=arg[2]=="stock";
    let start=Instant::now(); let n=N.load(Relaxed);let b=B.load(Relaxed);
    for row in &rows{
        let payload=if stock{serde_json::from_slice::<Stock>(black_box(row)).unwrap().payload}else{serde_json::from_slice::<Candidate>(black_box(row)).unwrap().payload};
        black_box(payload);
    }
    println!("{} {} {} {} {} {}",arg[2],rows.len(),bytes.len(),start.elapsed().as_micros(),N.load(Relaxed)-n,B.load(Relaxed)-b);
}
