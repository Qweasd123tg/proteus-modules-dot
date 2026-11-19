#![allow(unused)]
mod agents { pub mod codex { include!("codex.rs"); } }
mod transcript;
use transcript::{Transcript, Change};
use proteus_contracts::app_protocol::{AppTranscriptMessage as Row, AppTranscriptSubagent, AppTranscriptTool};
use serde_json::Value;
use std::{hint::black_box, sync::Arc, time::Instant};
use std::alloc::{GlobalAlloc, Layout, System};
use std::sync::atomic::{AtomicBool,AtomicUsize,AtomicIsize,Ordering::Relaxed};
#[cfg(alloc_counts)]
#[global_allocator] static A: Meter = Meter;
struct Meter;
static ENABLED:AtomicBool=AtomicBool::new(false);
static CALLS:AtomicUsize=AtomicUsize::new(0);
static BYTES:AtomicUsize=AtomicUsize::new(0);
static LIVE:AtomicIsize=AtomicIsize::new(0);
static PEAK:AtomicIsize=AtomicIsize::new(0);
fn live_change(d:isize){let now=LIVE.fetch_add(d,Relaxed)+d;if ENABLED.load(Relaxed){PEAK.fetch_max(now,Relaxed);}}
#[repr(C)]
struct Timespec{seconds:i64,nanos:i64}
unsafe extern "C"{fn clock_gettime(kind:i32,value:*mut Timespec)->i32;}
fn cpu_ns()->u64{let mut t=Timespec{seconds:0,nanos:0};assert_eq!(unsafe{clock_gettime(3,&mut t)},0);(t.seconds as u64)*1_000_000_000+t.nanos as u64}
fn count(n:usize){if ENABLED.load(Relaxed){CALLS.fetch_add(1,Relaxed); BYTES.fetch_add(n,Relaxed);}}
unsafe impl GlobalAlloc for Meter {
 unsafe fn alloc(&self,l:Layout)->*mut u8{count(l.size());live_change(l.size() as isize);unsafe{System.alloc(l)}}
 unsafe fn alloc_zeroed(&self,l:Layout)->*mut u8{count(l.size());live_change(l.size() as isize);unsafe{System.alloc_zeroed(l)}}
 unsafe fn realloc(&self,p:*mut u8,l:Layout,n:usize)->*mut u8{count(n);live_change(n as isize-l.size() as isize);unsafe{System.realloc(p,l,n)}}
 unsafe fn dealloc(&self,p:*mut u8,l:Layout){live_change(-(l.size() as isize));unsafe{System.dealloc(p,l)}}
}
fn row(kind:&str, id:usize) -> Row {
 let key=format!("call-{:031}",id);
 let mut row= Row{timestamp_ms:Some(id as i64+42),message_id:None,phase:None,role:"system".into(),text:format!("fixture row {id}"),images:vec![],tool:None,subagent:None,streaming:false};
 match kind {
 "tool"=>row.tool=Some(AppTranscriptTool{terminal:None,call_id:key,name:"tool".into(),args:Value::Null,effective_args:None,status:"done".into(),result:None,metadata:Value::Null}),
 "agent"=>row.subagent=Some(AppTranscriptSubagent{child_thread_id:key,session:None,role:"worker".into(),description:None,status:"done".into(),iterations:None,tools:vec![]}),
 "message"=>{row.message_id=Some(uuid::Uuid::from_u128(id as u128+1));row.role="assistant".into()},
 "anonymous"=>(),
 _=>unreachable!()
 }
 row
}
fn rows(shape:&str,start:usize,len:usize)->Vec<Row>{(start..start+len).map(|id|{let kind=if shape=="mixed"{["message","tool","agent","anonymous"][id%4]}else{shape};row(kind,id)}).collect()}

#[test] fn duplicate_identity_semantics() {
 let mut known=Transcript::default();
 let mut second=row("tool",10);second.timestamp_ms=Some(712);
 let mut m1=row("message",10);m1.text="reasoning".into();m1.role="reasoning".into();
 known.reset(vec![row("tool",10),second,m1,row("message",10),row("agent",10),row("anonymous",10)]);
 let old=known.entries().to_vec();
 let mut page=known.clone(); page.remove(0..old.len());
 let mut inrow=row("tool",10); inrow.timestamp_ms=None;
 let mut msg=row("message",10); msg.tool=Some(row("tool",10).tool.unwrap()); msg.timestamp_ms=None;
 let mut reason=msg.clone(); reason.text="reasoning".into();reason.role="reasoning".into();
 let mut changed=msg.clone();changed.text="changed".into();
 page.append_page(vec![inrow.clone(),inrow.clone(),msg,reason,row("agent",10),row("anonymous",10),changed],&known);
 for (n,i) in [(0,0),(1,0),(2,3),(3,2),(4,4)] {
  let got=&page.entries()[n]; assert_eq!(got.key,old[i].key); assert_eq!(got.time,old[i].time);
  assert!(Arc::ptr_eq(&got.text,&old[i].text));
 }
 assert!(!old.iter().any(|r|r.key==page.entries()[5].key));
 assert_eq!(page.entries()[6].key,old[3].key); assert!(!Arc::ptr_eq(&page.entries()[6].text,&old[3].text));
 known.reset(vec![inrow.clone(),inrow]);
 assert_eq!(known.entries()[0].key,old[1].key); assert_eq!(known.entries()[0].time,Some(712));
 assert!(Arc::ptr_eq(&known.entries()[0].text,&old[1].text));
 assert!(!old.iter().any(|r|r.key==known.entries()[1].key));
}
fn main(){
 let reps=if cfg!(alloc_counts){1}else{8}; let batch=if cfg!(alloc_counts){1}else{64};
 for (scenario,op,shape,known_n,page_start,page_n) in [
 ("tools-disjoint","append","tool",50usize,50usize,50usize),("mixed-half","append","mixed",50,25,50),
 ("messages-match","append","message",50,0,50),("one-tool","append","tool",1,0,1),
 ("tools-reset","reset","tool",50,0,50),("messages-reset","reset","message",50,0,50)
 ]{
  let mut known=Transcript::default(); known.reset(rows(shape,0,known_n));
  let mut archive=known.clone(); archive.remove(0..known_n); archive.prepend(rows(shape,150,50));
  for rep in 0..reps{
   let mut cases:Vec<_>=(0..batch).map(|_| (if op=="reset"{known.clone()}else{archive.clone()},rows(shape,page_start,page_n))).collect();
   CALLS.store(0,Relaxed);BYTES.store(0,Relaxed);
   let start=LIVE.load(Relaxed);PEAK.store(start,Relaxed);ENABLED.store(true,Relaxed);let now=Instant::now();let cpu=cpu_ns();
   for (t,rs) in &mut cases {let rs=std::mem::take(rs);let c=if op=="reset"{t.reset(black_box(rs))}else{t.append_page(black_box(rs),black_box(&known))};black_box(c);}
   let cpu=(cpu_ns()-cpu)/batch as u64;let ns=now.elapsed().as_nanos()/(batch as u128);ENABLED.store(false,Relaxed);
   let peak=PEAK.load(Relaxed)-start;let end=LIVE.load(Relaxed)-start;let n=CALLS.load(Relaxed)/batch;let bytes=BYTES.load(Relaxed)/batch;
   for (t,_) in cases{if op=="reset"{assert_eq!(t.entries().len(),known_n);for(a,b)in t.entries().iter().zip(known.entries()){assert_eq!(a.key,b.key);assert_eq!(a.time,b.time);assert!(Arc::ptr_eq(&a.text,&b.text));}}else{assert_eq!(t.entries().len(),50+page_n);assert_eq!(t.entries()[50].text.as_ref(),format!("fixture row {page_start}"));}}
   println!("{scenario},{rep},{ns},{n},{bytes},{cpu},{peak},{end}");
  }
 }
}
