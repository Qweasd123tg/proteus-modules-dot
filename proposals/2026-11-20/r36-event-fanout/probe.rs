pub use proteus_contracts::{contracts, domain};
mod before;
mod after;
use std::{alloc::{GlobalAlloc, System, Layout}, sync::{Arc, atomic::{AtomicUsize, Ordering::Relaxed}}};
use contracts::EventSink;
use domain::{Event, EventContext, EventEnvelope, ToolResult, new_call_id, new_session_id, new_thread_id};
struct Count;
static CALLS: AtomicUsize = AtomicUsize::new(0);
static BYTES: AtomicUsize = AtomicUsize::new(0);
fn count(n:usize){CALLS.fetch_add(1,Relaxed);BYTES.fetch_add(n,Relaxed);}
unsafe impl GlobalAlloc for Count {
    unsafe fn alloc(&self, l:Layout)->*mut u8 { count(l.size()); unsafe{ System.alloc(l) } }
    unsafe fn alloc_zeroed(&self, l:Layout)->*mut u8 { count(l.size()); unsafe{System.alloc_zeroed(l)} }
    unsafe fn dealloc(&self, p:*mut u8, l:Layout) { unsafe{System.dealloc(p,l)} }
    unsafe fn realloc(&self, p:*mut u8,l:Layout,n:usize)->*mut u8 { count(n);unsafe{System.realloc(p,l,n)} }
}
#[global_allocator] static A:Count=Count;
struct Consume;
#[async_trait::async_trait]
impl EventSink for Consume {
    async fn append(&self, e:EventEnvelope)->anyhow::Result<()> {std::hint::black_box(e); Ok(())}
}
fn event(size:usize,nested:bool)->EventEnvelope {
    let e=if nested {
        let mut r=ToolResult::ok(new_call_id(),"ok");
        r.metadata=serde_json::json!({"rows":(0..size).map(|i| serde_json::json!({"id":i,"label":format!("row {i}"),"tags":["A","B"]})).collect::<Vec<_>>()});
        Event::ToolFinished{result:r}
    } else {Event::AssistantReasoningDelta{text:"x".repeat(size)}};
    EventEnvelope::new(EventContext::new(new_session_id(), new_thread_id(), None),7,e)
}
fn main(){
    let rt=tokio::runtime::Builder::new_current_thread().build().unwrap();
    println!("case,sinks,round,arm,alloc_realloc,requested_bytes");
    rt.block_on(async {
        for (name,size,nested) in [("empty",0,false),("tiny",32,false),("text1m",1<<20,false),("nested128",128,true)] {
            let reference=event(size,nested);
            for sinks in [0,1,2,4] {
                let delegates=(0..sinks).map(|_|Arc::new(Consume) as Arc<dyn EventSink>).collect::<Vec<_>>();
                let baseline=before::FanoutEventSink::new(delegates.clone());
                let candidate=after::FanoutEventSink::new(delegates);
                for (round,arm) in ["baseline","patch","patch","baseline"].into_iter().enumerate() {
                    let sink:&dyn EventSink=if arm=="baseline"{&baseline}else{&candidate};
                    let envelope=reference.clone(); // outside window
                    let a=CALLS.load(Relaxed); let b=BYTES.load(Relaxed);
                    sink.append(envelope).await.unwrap();
                    let dc=CALLS.load(Relaxed)-a; let db=BYTES.load(Relaxed)-b;
                    println!("{name},{sinks},{round},{arm},{dc},{db}");
                }
            }
        }
    });
}
