#[path = "../before/value_hash.rs"] mod before;
#[path = "../after/value_hash.rs"] mod after;
use std::{alloc::{GlobalAlloc,Layout,System},sync::atomic::{AtomicBool,AtomicU64,Ordering::Relaxed},hint::black_box};
use serde_json::{Value,json};

struct Meter;
#[global_allocator] static A: Meter = Meter;
static ACTIVE:AtomicBool=AtomicBool::new(false);
static A_COUNT:AtomicU64=AtomicU64::new(0);
static R_COUNT:AtomicU64=AtomicU64::new(0);
static BYTES:AtomicU64=AtomicU64::new(0);
unsafe impl GlobalAlloc for Meter{
   unsafe fn alloc(&self,l:Layout)->*mut u8{if ACTIVE.load(Relaxed){A_COUNT.fetch_add(1,Relaxed);BYTES.fetch_add(l.size() as u64,Relaxed);}unsafe{System.alloc(l)}}
   unsafe fn alloc_zeroed(&self,l:Layout)->*mut u8{if ACTIVE.load(Relaxed){A_COUNT.fetch_add(1,Relaxed);BYTES.fetch_add(l.size() as u64,Relaxed);}unsafe{System.alloc_zeroed(l)}}
   unsafe fn realloc(&self,p:*mut u8,l:Layout,n:usize)->*mut u8{if ACTIVE.load(Relaxed){R_COUNT.fetch_add(1,Relaxed);BYTES.fetch_add(n as u64,Relaxed);}unsafe{System.realloc(p,l,n)}}
   unsafe fn dealloc(&self,p:*mut u8,l:Layout){unsafe{System.dealloc(p,l)}}
}
fn measure(f:fn(&Value)->anyhow::Result<String>,v:&Value)->(String,[u64;3]){
    for a in [&A_COUNT,&R_COUNT,&BYTES]{a.store(0,Relaxed);}
    ACTIVE.store(true,Relaxed);let output=black_box(f(black_box(v)).unwrap());ACTIVE.store(false,Relaxed);
    (output,[A_COUNT.load(Relaxed),R_COUNT.load(Relaxed),BYTES.load(Relaxed)])
}
fn oracle(v:&Value)->String{
   let mut copy=v.clone();copy.sort_all_objects();
   let bytes=serde_json::to_vec(&copy).unwrap();
   ring::digest::digest(&ring::digest::SHA256,&bytes).as_ref().iter().map(|b|format!("{b:02x}")).collect()
}
fn main(){
    let mut vs=vec![("null",Value::Null),("bool",json!(true)),("empty-object",json!({})),("empty-array",json!([])),("known",json!({"z":2,"a":[1,true]})),("nested",json!({"z":[{"q":8,"b":"🚀\""},false],"a":{"z":-0.0,"a":null}})),("large-string",json!("x".repeat(1<<20))),("50-row-page",Value::Array((0..50).map(|n|json!({"text":format!("record {n}"),"children":[],"id":n,"more":{"n":n}})).collect()))];
    for n in 0..4096 {vs.push(("generated",json!(n)));}
    let mut hits=[0u32;256];
    let mut common:Option<(i64,i64,i64)>=None;
    for (shape,v) in &vs {
        let expected=oracle(v);
        let (old,bc)=measure(before::storage_value_etag,v);let (new,ac)=measure(after::storage_value_etag,v);
        assert_eq!(old,expected);assert_eq!(new,expected);assert_eq!(new.len(),64);
        assert!(new.bytes().all(|b|b.is_ascii_digit() || matches!(b,b'a'..=b'f')));
        let delta=(bc[0] as i64-ac[0] as i64,bc[1] as i64-ac[1] as i64,bc[2] as i64-ac[2] as i64);
        assert!(delta.0>=31);assert_eq!(*common.get_or_insert(delta),delta);
        for pair in new.as_bytes().chunks_exact(2){hits[u8::from_str_radix(std::str::from_utf8(pair).unwrap(),16).unwrap()as usize]+=1;}
        if *shape=="known" { assert_eq!(new,"cab2365c93b4de12e8e2b0ec8b7a41a801a294b46c571adfdf87eed1d2342b2a"); }
        if *shape!="generated" { println!("{}",json!({"shape":shape,"etag":new,"before_alloc_realloc_grossreq":bc,"after_alloc_realloc_grossreq":ac})); }
    }
    assert!(hits.iter().all(|n|*n>0));
    println!("{}",json!({"values":vs.len(),"distinct_digest_bytes":256,"delta_alloc_realloc_grossreq":common,"preserve_order":cfg!(feature="preserve_order")}));
}
