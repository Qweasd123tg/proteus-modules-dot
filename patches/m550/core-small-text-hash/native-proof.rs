pub use proteus_contracts::model_standard;
#[path = "../baseline/message_hash.rs"] mod before;
#[path = "../../src/crates/proteus-session-semantics/src/journal/message_hash.rs"] mod after;
use model_standard::{CanonicalMessage,ContentPart,MessageRole};
use proteus_contracts::domain::{ToolCall,ToolResult};
use serde_json::json;
use uuid::Uuid;
use std::{hint::black_box,time::Instant};
#[repr(C)]
struct Timespec {sec:i64,nsec:i64}
unsafe extern "C" { fn clock_gettime(kind:i32,t:*mut Timespec)->i32; }
fn thread_ns()->u128{
    let mut t=Timespec{sec:0,nsec:0}; assert_eq!(unsafe{clock_gettime(3,&mut t)},0);
    (t.sec as u128)*1_000_000_000+(t.nsec as u128)
}

type Hash = fn(&CanonicalMessage)->anyhow::Result<[u8;32]>;
fn row(i: usize, parts: Vec<ContentPart>) -> CanonicalMessage {
    let mut m=CanonicalMessage::new(if i%2==0{MessageRole::User}else{MessageRole::Assistant},parts)
        .with_id(Uuid::from_u128(i as u128+1));
    for (j,p) in m.parts.iter_mut().enumerate(){p.part_id=Uuid::from_u128(((i as u128+1)<<16)+(j as u128));}
    m
}
fn text(s: String)->ContentPart{ ContentPart::Text{text:s} }
fn verify(m:&CanonicalMessage){
    let ser=serde_json::to_vec(m);
    let x=before::history_message_sha256(m);
    let y=after::history_message_sha256(m);
    match ser{
        Ok(v)=>{let oracle=ring::digest::digest(&ring::digest::SHA256,&v);assert_eq!(&x.unwrap(),oracle.as_ref());assert_eq!(&y.unwrap(),oracle.as_ref());}
        Err(_)=>{assert_eq!(format!("{:#}",x.unwrap_err()),format!("{:#}",y.unwrap_err()));}
    }
}
fn checks()->usize{
    let mut n=0;
    for len in (0..=1025).chain([4095,4096,4097,8191,8192,8193,1_048_576]){
        let m=row(len,vec![text("x".repeat(len)),text("\\\"\n\r\t🚀\u{0}".repeat(1+len%17))])
            .with_name("модель").with_metadata(json!({"z":-0.0,"a":["é","é中",[],{}],"b":null}));
        verify(&m);n+=1;
    }
    for m in [
        row(3,vec![]),row(4,vec![ContentPart::FileRef{ path:"a/b".into(),content:Some("aa".into()) }]),
        row(5,vec![ContentPart::Opaque{format:"local".into(),data:json!({"k3":9,"k2":-3,"k1":false})}]),
        row(6,vec![ContentPart::ToolCall{call:ToolCall::new("id","test",json!({"a":["中","\t"]}))},ContentPart::ToolResult{result:ToolResult::ok("id".into(),"output")}]),
    ]{verify(&m);n+=1;}
    #[cfg(unix)]{
       use std::{ffi::OsString,os::unix::ffi::OsStringExt};
       let bad=row(7,vec![ContentPart::FileRef{path:OsString::from_vec(vec![0xff,0xfe]).into(),content:None}]);
       assert!(serde_json::to_vec(&bad).is_err());verify(&bad);n+=1;
    }
    n
}
fn rows(n:usize,shape:&str)->Vec<CanonicalMessage>{
  (0..n).map(|i|match shape{
    "maxfast"=>row(i,vec![text("x".repeat(85))]),
    "oneover"=>row(i,vec![text("x".repeat(86))]),
    "escaped"=>row(i,vec![text("\u{0000}".repeat(512))]),
    "medium"=>row(i,vec![text("x".repeat(512))]),
    "long"=> row(i,vec![text(format!("{:07}-{}",i,"x".repeat(1_048_576)))]),
    "mixed" if i%5==0=>row(i,vec![ContentPart::ToolCall{call:ToolCall::new(format!("call-{i}"),"read",json!({"path":"файл","range":[i,i+1]}))},text("quoted: \"new line\n\t end".into())]),
    "mixed" if i%5==1=>row(i,vec![ContentPart::ToolResult{result:ToolResult::ok(format!("call-{}",i-1),"content".repeat(80))}]),
    _=>row(i,vec![text(format!("Message {i}, sample text in a saved conversation."))]),
  }).collect()
}
#[inline(never)]
fn timed(f:Hash, rows:&[CanonicalMessage])->(u128,[u8;32],u128){
    let t=Instant::now();let cpu=thread_ns();
    let digests:Vec<_>=rows.iter().map(|m|f(black_box(m)).unwrap()).collect();
    black_box(&digests);
    let elapsed=t.elapsed().as_nanos();let cpu_ns=thread_ns()-cpu;
    let sum:[u8;32]=ring::digest::digest(&ring::digest::SHA256,digests.as_flattened()).as_ref().try_into().unwrap();
    (elapsed,sum,cpu_ns)
}
fn main(){
 let cases=checks();
 for (shape,n) in [("plain",50_000),("mixed",50_000),("maxfast",25_000),("oneover",25_000),("medium",20_000),("escaped",3_000),("long",24)]{
    let data=rows(n,shape); data.iter().for_each(verify);
    let mut bs=Vec::new();let mut as_=Vec::new();let mut bc=Vec::new();let mut ac=Vec::new();let mut checksums=vec![];
    let _=timed(before::history_message_sha256,&data);let _=timed(after::history_message_sha256,&data);
    for i in 0..16{
        let (b,a)=if i%2==0{(timed(before::history_message_sha256,&data),timed(after::history_message_sha256,&data))}else{
            let a=timed(after::history_message_sha256,&data);(timed(before::history_message_sha256,&data),a)
        };
        assert_eq!(a.1,b.1); bs.push(b.0);as_.push(a.0);bc.push(b.2);ac.push(a.2);
        checksums.push(a.1);
    }
    assert!(checksums.windows(2).all(|p|p[0]==p[1]));
    println!("{}",json!({"shape":shape,"rows":n,"extra_cases":cases,"repeats":16,"before_cpu_ns":bc,"after_cpu_ns":ac,"before_ns":bs,"after_ns":as_,"sha_dataset":checksums[0],"preserve_order":cfg!(feature="preserve_order")}));
 }
}
