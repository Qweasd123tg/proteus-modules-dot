use std::{alloc::{GlobalAlloc,Layout,System},cell::Cell,hint::black_box,time::Instant};
use proteus_contracts::{domain::{HostedToolConfig,ModelRef,ToolCall,ToolCallSurface,ToolSafety,ToolSpec,ToolSurface,WebSearchHostedToolConfig},model_standard::{CanonicalModelRequest, ModelResponseValidationContext}};
// Synchronous single-thread scope, measuring Rust allocation requests, not process RSS.
#[derive(Clone,Copy,Default,Debug)]
struct Size{calls:usize,bytes:usize,live:usize,peak:usize}
thread_local!{static TRACK:Cell<Option<Size>>=const{Cell::new(None)};}
#[cfg(probe_heap)]
struct Count;
#[cfg(probe_heap)]
#[global_allocator]
static ALLOC:Count=Count;
#[cfg(probe_heap)]
fn update(old:usize,new:usize,allocate:bool) {
    TRACK.with(|cell|if let Some(mut s)=cell.get(){s.live=s.live.checked_sub(old).unwrap()+new;
        s.peak=s.peak.max(s.live);s.bytes+=new;s.calls+=usize::from(allocate);cell.set(Some(s));});
}
#[cfg(probe_heap)]
unsafe impl GlobalAlloc for Count{
    unsafe fn alloc(&self,l:Layout)->*mut u8{let p=unsafe{System.alloc(l)};if !p.is_null(){update(0,l.size(),true)}p}
    unsafe fn alloc_zeroed(&self,l:Layout)->*mut u8{let p=unsafe{System.alloc_zeroed(l)};if !p.is_null(){update(0,l.size(),true)}p}
    unsafe fn dealloc(&self,p:*mut u8,l:Layout){update(l.size(),0,false);unsafe{System.dealloc(p,l)}}
    unsafe fn realloc(&self,p:*mut u8,l:Layout,n:usize)->*mut u8{let r=unsafe{System.realloc(p,l,n)};if !r.is_null(){update(l.size(),n,true)}r}
}
fn compact(req:&CanonicalModelRequest)->ModelResponseValidationContext<'static>{
    ModelResponseValidationContext::from_request(black_box(req)).into_owned()
}
fn protocol_checks() {
    let spec=|name:&str,surface:ToolSurface|ToolSpec::new(name,"description",serde_json::json!({}),ToolSafety::ReadOnly).with_surface(surface);
    let req=CanonicalModelRequest::new(ModelRef::new("p","m"),vec![]).with_tools(vec![
        spec("duplicate", ToolSurface::freeform_lark("huge instruction")),
        spec("duplicate", ToolSurface::function()),
        spec("hosted", ToolSurface::provider_hosted(HostedToolConfig::WebSearch {config:WebSearchHostedToolConfig::default()})),
        spec("workflow",ToolSurface::workflow_function()),spec("ordinary",ToolSurface::strict_function())
    ]);
    let known=[("duplicate","freeform"),("hosted","hosted"),("workflow","function"),("ordinary","function"),("unknown","unknown")];
    let owned=compact(&req).into_owned().clone();
    for (name,declared) in known {
        for surface in [ToolCallSurface::Function, ToolCallSurface::Freeform] {
            let call=ToolCall::new("id",name,serde_json::json!({})).with_surface(surface);
            let got=owned.validate_tool_call(&call);
            assert_eq!(got,ModelResponseValidationContext::from_request(&req).validate_tool_call(&call));
            let expect=match declared {
                "unknown"=>Ok(()),
                "hosted"=>Err(format!("model response returned provider-hosted tool '{name}' as a client-executed {} call",surface.as_str())),
                d if d==surface.as_str()=>Ok(()),
                d=>Err(format!("model response tool '{name}' used {} surface, but request declared {d} surface",surface.as_str()))
            };
            assert_eq!(got,expect);
        }
    }
}
// Linux x86_64 CLOCK_THREAD_CPUTIME_ID; two reads per whole benchmark batch.
#[repr(C)] struct Spec { sec: std::ffi::c_long, ns: std::ffi::c_long }
unsafe extern "C" { fn clock_gettime(id: std::ffi::c_int, out: *mut Spec) -> std::ffi::c_int; }
fn cpu_ns()->u128 {
    let mut ts=Spec{sec:0,ns:0};
    assert_eq!(unsafe {clock_gettime(3,&mut ts)},0);
    ts.sec as u128*1_000_000_000+ts.ns as u128
}
fn main(){
    protocol_checks();
    let tools:Vec<ToolSpec>=serde_json::from_slice(&std::fs::read(std::env::args_os().nth(1).unwrap()).unwrap()).unwrap();
    let high=ToolSpec::new("structured","a",serde_json::json!({"description":"x".repeat(256*1024)}),ToolSafety::ReadOnly).with_surface(ToolSurface::freeform_lark("g".repeat(256*1024)));
    for (label,set) in [("empty",vec![]),("read_file",tools[..1].to_vec()),("nine_shipped",tools),("synthetic_512KiB",vec![high])] {
        let req=CanonicalModelRequest::new(ModelRef::new("p","m"),vec![]).with_tools(set);
        if cfg!(probe_heap) {
            TRACK.with(|c|c.set(Some(Size::default())));
            let snapshot=black_box(compact(&req));
            let s=TRACK.with(|c|c.take().unwrap());
            assert!(s.live<=s.peak && s.peak<=s.bytes);
            println!("heap {label} {} {} {} {}",s.calls,s.bytes,s.live,s.peak);
            drop(black_box(snapshot));
        } else {
            let n=if label=="synthetic_512KiB"{256}else{4096};
            for rep in 0..9 {
                let start=Instant::now(); let cpu=cpu_ns();
                for _ in 0..n {drop(black_box(compact(&req)));}
                let cpu=cpu_ns()-cpu;
                println!("time {label} {rep} {n} {} {cpu}",start.elapsed().as_nanos());
            }
        }
    }
}
