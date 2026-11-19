#![allow(dead_code,unused_imports)]
mod agents { pub(crate) mod codex { mod types; pub use types::*; pub mod projection; mod router; pub fn channel()->impl FnMut(proteus_codex_client::Event)->Event { let mut router=router::Router::default(); let (events,_,_)=router.register("chat").unwrap();move |raw|{assert!(router.raw(raw).is_none());events.try_recv().unwrap()} } } }
mod transcript;
use agents::codex::{Event,Item};
use agents::codex::projection::{notification,item};
use transcript::{Transcript,Change};
use serde_json::{json,Value};
use std::{hint::black_box, time::Instant};
const ROWS:usize=50;
const BYTES:usize=8*1024*1024;
fn parse(raw:&str) -> Event{
    let val:Value=serde_json::from_str(raw).unwrap();
    notification("item/agentMessage/delta",&val).unwrap()
}
fn fill(rows:usize,fields:usize) -> Transcript {
    let mut t=Transcript::default();
    let rag=(0..fields).map(|i| json!({"path":format!("src/part-{i}.rs"),"line":i*3,"flag":true})).collect::<Vec<_>>();
    for i in 0..rows {
        let v=json!({"id":format!("call-{i}"),"type":"dynamicToolCall","tool":"inspect_workspace","arguments":{"files":rag},"result":"ok"});
        t.external_upsert(item(&v,"turn",true,Some(321)).unwrap());
    }
    let v=json!({"id":"answer","type":"agentMessage","text":""});
    t.external_upsert(item(&v,"turn",false,Some(322)).unwrap());
    t
}
fn main(){
    let mut a=std::env::args().skip(1).map(|x|x.parse::<usize>().unwrap());
    let rows=a.next().unwrap();let fields=a.next().unwrap();let n=a.next().unwrap();let width=a.next().unwrap();
    let mut t=fill(rows,fields);
    #[cfg(not(fast))] let _=t.external_trim_budget(ROWS,BYTES);
    #[cfg(fast)] let (_,mut left)=t.external_trim_budget(ROWS,BYTES);
    let initial=t.entries().iter().map(|x|x.retained_bytes()).sum::<usize>();
    let hold=t.entries().len(); let raw=json!({"turnId":"turn","itemId":"answer","delta":"x".repeat(width)}).to_string();
    let pipe=std::env::var("PIPE").ok().map(|p| {
        let mut launch=proteus_codex_client::Launch::codex("python3".into(), std::env::current_dir().unwrap());
        launch.args=vec!["-u".into(),p];
        let child=proteus_codex_client::Client::spawn(launch).unwrap();
        let ev=child.take_events().unwrap();
        (child,ev)
    });
    let mut project = agents::codex::channel();
    let batch=32;
    let clock=Instant::now();let mut removed=0;
    for i in 0..n {
        let event=if let Some((child,ev))=&pipe {
            if i % batch==0 { child.notify("replay",json!({"batch":batch.min(n-i),"width":width})).unwrap(); }
            project(ev.recv_blocking().unwrap())
        } else { parse(black_box(&raw)) };
        let Event::TextDelta{id,turn_id,delta}=event else { unreachable!() };
        let changed=t.external_delta(&turn_id,&id,&delta,false,false);
        if !matches!(changed,Change::None) {
            #[cfg(not(fast))] let trim=t.external_trim_budget(ROWS,BYTES);
            #[cfg(fast)] let trim=t.external_trim_after_change(ROWS,BYTES,&mut left, if matches!(changed,Change::Updated(_)){Some(delta.len())}else{None});
            if let Change::Spliced{removed:r,..}=trim{removed+=r;}
        }
    }
    let micros=clock.elapsed().as_micros(); let len=t.entries().last().unwrap().text.len();assert_eq!(len,(width*n).min(128*1024));
    let end=t.entries().iter().map(|x|x.retained_bytes()).sum::<usize>();
    println!("{rows},{fields},{n},{width},{hold},{initial},{removed},{end},{len},{micros}");
}
