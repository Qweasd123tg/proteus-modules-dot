#![allow(dead_code)]
use std::hint::black_box;
#[cfg(not(feature="stats"))]
use std::time::Instant;
#[cfg(not(feature="stats"))]
fn thread_ns()->u64 {
    let mut t=libc::timespec{tv_sec:0,tv_nsec:0};
    assert_eq!(unsafe{libc::clock_gettime(libc::CLOCK_THREAD_CPUTIME_ID,&mut t)},0);
    t.tv_sec as u64*1_000_000_000+t.tv_nsec as u64
}
use html5ever::{ParseOpts,parse_document,tendril::TendrilSink};
use markup5ever_rcdom::RcDom;
use serde_json::{json,Value};
mod html5minify;
fn dom(source:&str)->std::io::Result<RcDom>{
/*INSERT_EXACT_STAGE*/

#[cfg(feature="stats")]
mod stats {
    use std::cell::Cell;
    use std::alloc::{GlobalAlloc,Layout,System};
    #[derive(Copy,Clone,Default)]
    pub struct Sample {pub calls:usize,pub bytes:usize,pub peak:usize,pub live:usize}
    thread_local!{static S:Cell<Option<Sample>>=const{Cell::new(None)};}
    pub fn start(){S.with(|s|s.set(Some(Sample::default())));}
    pub fn stop()->Sample{S.with(|s|s.take().unwrap())}
    fn count(old:usize,new:usize,alloc:bool){S.with(|s|if let Some(mut v)=s.get(){
        v.calls+=usize::from(alloc);v.bytes+=new;v.live=v.live.checked_sub(old).unwrap()+new;
        v.peak=v.peak.max(v.live);s.set(Some(v));});}
    struct A;
    unsafe impl GlobalAlloc for A{
        unsafe fn alloc(&self,l:Layout)->*mut u8{let p=unsafe{System.alloc(l)};if !p.is_null(){count(0,l.size(),true)};p}
        unsafe fn dealloc(&self,p:*mut u8,l:Layout){count(l.size(),0,false);unsafe{System.dealloc(p,l)}}
        unsafe fn realloc(&self,p:*mut u8,l:Layout,n:usize)->*mut u8{let q=unsafe{System.realloc(p,l,n)};if !q.is_null(){count(l.size(),n,true)};q}
    }
    #[global_allocator]static ALLOC:A=A;
}

fn stage(html:&str, passes:usize) {
    // End the transient RcDom lifetime each pass, as widget parsing does; don't simulate holding 2 DOMs.
    for _ in 0..passes {drop(black_box(dom(black_box(html)).unwrap()));}
}
fn main(){
    let raw=std::fs::read_to_string(std::env::args().nth(1).unwrap()).unwrap();
    let rows:Vec<Value>=raw.lines().map(|s|serde_json::from_str(s).unwrap()).collect();
    for (_i,row) in rows.iter().enumerate(){
        let s=row["html"].as_str().unwrap();let name=row["name"].as_str().unwrap();
        for _ in 0..32 {stage(s,1);}
        #[cfg(feature="stats")]
        for passes in [1,2] {
            use stats::*;
            start();stage(s,passes);let sample=stop();assert_eq!(sample.live,0);
            println!("{}",json!({"case":name,"passes":passes,"html_bytes":s.len(),"allocs":sample.calls,"requested":sample.bytes,"peak":sample.peak,"live_after":sample.live}));
        }
        #[cfg(not(feature="stats"))]
        {
            // Tune batch once outside timing to target ~10 ms per 1-stage sample.
            let now=Instant::now();for _ in 0..16 {stage(s,1);}
            let ns_per=now.elapsed().as_nanos().max(16)/16;
            let loops=(10_000_000_u128/ns_per).clamp(16,4096) as usize;
            for pair in 0..14 {
                for (order,passes) in (if (pair+_i)%2==0 {[1,2]} else {[2,1]}).into_iter().enumerate(){
                    let cpu=thread_ns();let now=Instant::now();for _ in 0..loops {stage(s,passes);}
                    let ns=now.elapsed().as_nanos() as u64;let cpu=thread_ns()-cpu;
                    println!("{}",json!({"case":name,"pair":pair+1,"order":order+1,"html_bytes":s.len(),"passes":passes,"loops":loops,"elapsed_ns":ns,"thread_cpu_ns":cpu}));
                }
            }
        }
    }
}
