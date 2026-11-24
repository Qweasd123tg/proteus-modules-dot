#![allow(dead_code,unused_imports)]
use anyhow::{Result,bail};
use serde_json::{Value,json};
use std::{future::Future,hint::black_box,path::{Path,PathBuf},sync::{Arc,Mutex as StdMutex,atomic::{AtomicBool,AtomicU64,AtomicUsize,Ordering}},task::{Context,Poll,Waker}};
use tokio::sync::Mutex;
use uuid::Uuid;
pub use proteus_contracts::{contracts,domain,model_standard};
use proteus_contracts::{contracts::*,domain::*,model_standard::*};
use proteus_contracts::contracts::{SessionStorageRequest as Request,SessionStorageResponse as Response};
use proteus_session_semantics::{HistoryCapture,ModelContextState};
mod core;mod store;mod stock;mod candidate;mod meter;mod controls;
use core::SessionStore;
pub(crate) struct SteeringModel; // Unused source field; steering is not a route under test.
const REV:u64=13;
enum Arm{Stock(stock::TurnHistoryRecorder),Candidate(candidate::TurnHistoryRecorder)}
macro_rules! field{($s:expr,$f:ident)=>{match $s{Arm::Stock(x)=>&x.$f,Arm::Candidate(x)=>&x.$f}}}
impl Arm{
 fn recorder(&self)->&dyn ToolExecutionRecorder{match self{Self::Stock(x)=>x,Self::Candidate(x)=>x}}
 fn history(&self)->&Arc<Mutex<Vec<CanonicalMessage>>>{field!(self,history)}
 fn effects(&self)->&Mutex<Vec<ToolResult>>{field!(self,pending_effects)}
 fn capture(&self)->&Mutex<HistoryCapture>{field!(self,capture)}
 fn revision(&self)->&Arc<AtomicU64>{field!(self,revision)}
 async fn settle(&self)->Result<()>{match self{Self::Stock(x)=>x.settle_in_memory_effects().await,Self::Candidate(x)=>x.settle_in_memory_effects().await}}
}
fn attr()->ExecutionAttribution{ExecutionAttribution::for_turn(ExecutionId::from_uuid(Uuid::from_u128(4)),Uuid::from_u128(1),Uuid::from_u128(2),Uuid::from_u128(3))}
fn other()->ExecutionAttribution{ExecutionAttribution::detached(ExecutionId::from_uuid(Uuid::from_u128(34)))}
fn binding_seed(n:usize,shape:&str,bound:bool)->(Vec<CanonicalMessage>,Vec<WorkflowToolResultBinding>){
 let mut rows=public_rows(n,4);
 for (i,m) in rows.iter_mut().enumerate(){m.id=Uuid::from_u128(1000+i as u128);m.parts[0].part_id=Uuid::from_u128(100000+i as u128);}
 if shape!="plain"{
  let m=match shape{
   "nan32"|"infinity32"|"negative-zero32"=>{
    let score=match shape{"nan32"=>f32::from_bits(0x7fc00037),"infinity32"=>f32::INFINITY,_=>-0.0};
    CanonicalMessage::new(MessageRole::Assistant,vec![ContentPart::Context{chunk:ContextChunk::new("fixture","typed score").with_score(score).with_metadata(json!({"q":"ß"}))}])
   },
   "nan64"|"minus-infinity64"|"positive-zero64"=>{
    let score=match shape{"nan64"=>f64::from_bits(0x7ff8000000000053),"minus-infinity64"=>f64::NEG_INFINITY,_=>0.0};
    CanonicalMessage::new(MessageRole::Assistant,vec![ContentPart::HostedToolActivity{activity:HostedToolActivity::FileSearch{
     id:"provider-fixture".into(),status:HostedToolStatus::Completed,queries:vec!["fixture".into()],
     results:vec![FileSearchResult::new("fid",Some("synthetic".into()),Some(score),Some("résultat".into()),json!({"m":[1,"😀"]}))],
    }}])
   },
   _=>panic!("bad shape {shape}")
  };
  let mut m=m;m.id=Uuid::from_u128(900001);m.parts[0].part_id=Uuid::from_u128(900002);rows.push(m);
 }
 let mut bindings=Vec::new();
 if bound{
  let mut parts=Vec::new();
  for (i,id) in ["a","b","c"].into_iter().enumerate(){
   let original=ToolCall::new(id,"model selected",json!({"path":"/fixture"}));
   let executed=ToolCall::new(id,"workflow selected",json!({"path":"/fixture/normalized"}));
   let mut binding=WorkflowToolResultBinding::new(executed);
   binding.message_id=Uuid::from_u128(910000+i as u128);binding.part_id=Uuid::from_u128(910100+i as u128);
   bindings.push(binding);
   parts.push(ContentPart::ToolCall{call:original});
  }
  let mut message=CanonicalMessage::new(MessageRole::Assistant,parts);message.id=Uuid::from_u128(930000);
  for(i,p)in message.parts.iter_mut().enumerate(){p.part_id=Uuid::from_u128(930001+i as u128);}
  rows.push(message);
 }
 (rows,bindings)
}
fn result(id:&str)->ToolResult {
 ToolResult::ok(id.into(),format!("synthetic result for {id} 🧪")).with_content(vec![ToolContent::Json{value:json!({"route":[id,1]})}]).with_metadata(json!({"owner":"fixture","id":id}))
}
fn raw(id:&str)->ToolResult{
 ToolResult::ok(id.into(),format!("raw {id} {}",'ж'.to_string().repeat(256))).with_metadata(json!({"raw":true}))
}
fn fingerprint(rows:&[CanonicalMessage])->String{
 use ring::digest::{Context,SHA256};
 use std::io::{self,Write};
 struct W(Context);impl Write for W{fn write(&mut self,x:&[u8])->io::Result<usize>{self.0.update(x);Ok(x.len())}fn flush(&mut self)->io::Result<()>{Ok(())}}
 let mut h=W(Context::new(&SHA256));serde_json::to_writer(&mut h,&rows).unwrap();
 for m in rows{for p in &m.parts{
  match &p.payload{
   ContentPart::Context{chunk}=>{if let Some(s)=chunk.score{h.0.update(&s.to_bits().to_le_bytes());}},
   ContentPart::HostedToolActivity{activity:HostedToolActivity::FileSearch{results,..}}=>for r in results{if let Some(s)=r.score{h.0.update(&s.to_bits().to_le_bytes());}},
   _=>()
  }
 }}
 h.0.finish().as_ref().iter().map(|x|format!("{x:02x}")).collect()
}
fn construct(candidate:bool,mut rows:Vec<CanonicalMessage>,bindings:&[WorkflowToolResultBinding],persisted:bool,lost:bool)->(Arm,Arc<Sink>,Arc<ProbeStorage>){
 let sink=Arc::new(Sink::new());
 let io=Arc::new(ProbeStorage(AtomicUsize::new(0)));
 let store=persisted.then(||SessionStore::open(io.clone(),"/fixture/session".into()).unwrap());
 let capture=HistoryCapture::new(&rows,bindings).unwrap();
 for b in bindings{assert!(capture.has_binding(b));}
 if lost{rows.pop().unwrap();}
 rows.reserve_exact(8);
 let history=Arc::new(Mutex::new(rows));
 let revision=Arc::new(AtomicU64::new(REV));
 macro_rules! rec{($module:ident)=>{$module::TurnHistoryRecorder{
  attribution:attr(),store,history,revision,model_context:Arc::new(Mutex::new(ModelContextState::default())),
  interrupted_turns:Default::default(),initial_history:Vec::new(),current_user:CanonicalMessage::text(MessageRole::User,"fixture"),
  steering:None,tools:sink.clone(),capture:Mutex::new(capture),admitted_calls:(!persisted).then(Default::default),
  recorded_changed_compactions:Default::default(),recorded_compactions:Default::default(),pending_effects:Default::default(),
 }}}
 let recorder=if candidate{Arm::Candidate(rec!(candidate))}else{Arm::Stock(rec!(stock))};
 (recorder,sink,io)
}
#[derive(Clone,Copy)]struct Case{n:usize,shape:&'static str,op:&'static str,mode:&'static str}
impl Case{fn bound(&self)->bool{!matches!(self.mode,"unbound"|"empty"|"foreign"|"persisted-noop")}}
fn pending<T,F:Future<Output=T>+?Sized>(f:std::pin::Pin<&mut F>)->Poll<T>{f.poll(&mut Context::from_waker(Waker::noop()))}
async fn one(c:Case){
 let (seed,bindings)=binding_seed(c.n,c.shape,c.bound());
 let stable_before=fingerprint(&seed);
 let mut first=None;let mut summaries=Vec::new();let mut baseline=None;
 for selected in [false,true]{
  let (r,sink,io)=construct(selected,seed.clone(),&bindings,c.mode.starts_with("persisted"),c.mode=="lost");
  let tools=r.recorder();
  // Authenticate the real declaration through the source ToolExecutionRecorder
  // callback; canonical model call has same exact id, different execution args.
  for b in &bindings{
   let mut wrong=b.execution_call.clone();wrong.args=json!({"different":true});
   assert_eq!(tools.tool_call_requested(attr(),OperationOwner::Workflow,&wrong).await.unwrap_err().to_string(),"executed tool call disagrees with checkpoint execution binding");
   tools.tool_call_requested(attr(),OperationOwner::Workflow,&b.execution_call).await.unwrap();
   tools.tool_call_resolved(attr(),&b.execution_call,&ToolCallResolution::Allowed).await.unwrap();
  }
  let mut expected_outcome="ok";let mut expected_suffix=Vec::<ToolResult>::new();let mut expected_raw=Vec::<ToolResult>::new();
  let mut expected_revision=if c.mode=="wrap"{u64::MAX}else{REV};
  r.revision().store(expected_revision,Ordering::SeqCst);
  let nan=c.shape.starts_with("nan");
  if c.op=="final"{
   if c.mode=="duplicate"{
    tools.tool_result_recorded(attr(),&result("a")).await.unwrap();
    expected_revision=expected_revision.wrapping_add(1);expected_suffix.push(result("a"));
   }
   tools.tool_effect_recorded(attr(),&raw("a")).await.unwrap();
   tools.tool_effect_recorded(attr(),&raw("b")).await.unwrap();
   tools.tool_effect_recorded(other(),&raw("foreign")).await.unwrap();
   if !c.mode.starts_with("persisted"){expected_raw.extend([raw("a"),raw("b")]);}
  }else{
   let batch:&[&str]=match c.mode{"empty"|"persisted-noop"=>&[],"unbound"=>&["a","b"],"partial"=>&["b","b","c"],"lost"=>&["a","b"],_=>&["c","b","a"]};
   for x in batch{tools.tool_effect_recorded(attr(),&raw(x)).await.unwrap();expected_raw.push(raw(x));}
  }
  let from_len=r.history().lock().await.len();
  let scope_ref={
   let h=r.history().lock().await;
   meter::reset();let scoped=meter::enter();
   let v=h.clone();black_box(&v);drop(v);drop(scoped);
   meter::take()
  };
  if let Some(b)=&baseline{assert_eq!(&scope_ref,b)}else{baseline=Some(scope_ref);}
  meter::reset();
  sink.events.lock().unwrap().clear();
  let res=if c.op=="final"{
   let value=result("a");
   if c.mode=="sink-error"{sink.fail.store(true,Ordering::SeqCst);}
   let a=if c.mode=="foreign"{other()}else{attr()};
   match c.mode{
    "cancel-sink"|"resume-sink"|"sink-error"=>{
     let g=sink.gate.lock().await;
     let mut f=tools.tool_result_recorded(a,&value);
     assert!(pending(f.as_mut()).is_pending());assert!(r.capture().try_lock().is_err());assert!(r.effects().try_lock().is_ok() && r.history().try_lock().is_ok());
     assert_eq!(sink.events(),vec![("final-enter",a,"a".into())]);
     if c.mode=="cancel-sink"{drop(f);drop(g);Ok(())}else{drop(g);f.await}
    },
    "cancel-effects"=>{
     let g=r.effects().lock().await;
     let mut f=tools.tool_result_recorded(a,&value);
     assert!(pending(f.as_mut()).is_pending());assert!(r.capture().try_lock().is_err() && r.history().try_lock().is_ok());
     assert_eq!(sink.events(),vec![("final-enter",a,"a".into()),("final-ok",a,"a".into())]);
     drop(f);drop(g);Ok(())
    },
    "cancel-history"|"resume-history"|"cancel-grant"=>{
     let g=r.history().lock().await;
     let mut f=tools.tool_result_recorded(a,&value);
     assert!(pending(f.as_mut()).is_pending());assert!(r.capture().try_lock().is_err() && r.effects().try_lock().is_err());
     assert_eq!(sink.events(),vec![("final-enter",a,"a".into()),("final-ok",a,"a".into())]);
     if c.mode=="resume-history"{drop(g);f.await}else if c.mode=="cancel-grant"{drop(g);drop(f);Ok(())}else{drop(f);drop(g);Ok(())}
    },
    _=>tools.tool_result_recorded(a,&value).await
   }
  }else{
    match c.mode{
     "persisted-noop"=>{let cap=r.capture().lock().await;let raw=r.effects().lock().await;let h=r.history().lock().await;
      let mut f=Box::pin(r.settle());assert!(matches!(pending(f.as_mut()),Poll::Ready(Ok(()))));drop(f);drop(h);drop(raw);drop(cap);Ok(())},
     "cancel-history"|"resume-history"=>{let g=r.history().lock().await;let mut f=Box::pin(r.settle());
      assert!(pending(f.as_mut()).is_pending());assert!(r.capture().try_lock().is_err() && r.effects().try_lock().is_err());
      if c.mode=="cancel-history"{drop(f);drop(g);Ok(())}else{drop(g);f.await}},
     _=>r.settle().await
    }
  };
  let measured=meter::take();
  assert!(r.capture().try_lock().is_ok() && r.effects().try_lock().is_ok() && r.history().try_lock().is_ok());
  // Independent state oracle. No fixture uses candidate result to generate expected output.
  if c.op=="final"{
   match c.mode{
    "sink-error"=>expected_outcome="typed recorder sink failed",
    "duplicate"=>expected_outcome="checkpoint received a duplicate tool result",
    "lost"=>expected_outcome="checkpoint history suffix was lost",
    "foreign"|"cancel-sink"|"cancel-effects"|"cancel-history"|"cancel-grant"=>(),
    _=>{
     expected_raw.retain(|x|x.call_id!="a");
     if c.mode!="unbound"{expected_suffix.push(result("a"));}
     if !c.mode.starts_with("persisted")&&(c.mode!="unbound"||nan){expected_revision=expected_revision.wrapping_add(1);}
    }
   }
  }else{
   match c.mode{
    "empty"|"persisted-noop"|"cancel-history"=>(),
    "partial"=>{expected_outcome="checkpoint received a duplicate tool result";expected_raw.clear();expected_suffix.push(raw("b"));},
    "lost"=>{expected_outcome="checkpoint history suffix was lost";expected_raw.clear();},
    "unbound"=>{expected_raw.clear();if nan{expected_revision=expected_revision.wrapping_add(1);}},
    _=>{expected_revision=expected_revision.wrapping_add(1);expected_raw.clear();expected_suffix.extend([raw("a"),raw("b"),raw("c")]);}
   }
  }
  let text=match res{Ok(())=>"ok".to_owned(),Err(e)=>{
   if c.mode=="sink-error"{assert!(e.downcast_ref::<SinkError>().is_some());}
   e.to_string()
  }};
  assert_eq!(text,expected_outcome);
  assert_eq!(*r.effects().lock().await,expected_raw);
  assert_eq!(r.revision().load(Ordering::SeqCst),expected_revision);
  let history=r.history().lock().await;
  let retained=if c.mode=="lost"{&seed[..seed.len()-1]}else{seed.as_slice()};
  assert_eq!(fingerprint(&history[..retained.len()]),if c.mode=="lost"{fingerprint(retained)}else{stable_before.clone()});
  assert_eq!(history.len(),retained.len()+expected_suffix.len());
  for (m,x) in history[retained.len()..].iter().zip(&expected_suffix){
   let b=bindings.iter().find(|b|b.call_id==x.call_id).unwrap();
   assert_eq!(*m,b.message(x.clone()));
  }
  let events=sink.events();
  let ordering=if c.op=="settle"{vec![]}else{
   let a=if c.mode=="foreign"{other()}else{attr()};
   match c.mode{"cancel-sink"=>vec![("final-enter",a,"a".into())],"sink-error"=>vec![("final-enter",a,"a".into()),("final-error",a,"a".into())],_=>vec![("final-enter",a,"a".into()),("final-ok",a,"a".into())]}
  };
  assert_eq!(events,ordering);
  assert_eq!(io.0.load(Ordering::SeqCst),usize::from(c.mode.starts_with("persisted")));
  if c.mode.starts_with("cancel")||matches!(c.mode,"sink-error"|"foreign"|"empty"|"persisted-noop"){assert!(measured.is_null());}
  else{assert!(!measured.is_null());}
  let state=json!({"from_rows":from_len,"rows":history.len(),"revision":expected_revision,"retained":fingerprint(&history),"suffix":expected_suffix.iter().map(|x|x.call_id.as_str()).collect::<Vec<_>>(),"effects":expected_raw.iter().map(|x|x.call_id.as_str()).collect::<Vec<_>>(),"events":events,"outcome":text,"all_locks_released":true});
  drop(history);
  if c.mode=="partial"{
    // The first B inserted before failure must remain recorded; the drained C
    // was removed from the raw queue, but a subsequent legitimate final C inserts.
    assert_eq!(tools.tool_result_recorded(attr(),&result("b")).await.unwrap_err().to_string(),"checkpoint received a duplicate tool result");
    let _=meter::take();
    tools.tool_result_recorded(attr(),&result("c")).await.unwrap();
    let h=r.history().lock().await;assert_eq!(h.len(),retained.len()+2);
    assert_eq!(r.revision().load(Ordering::SeqCst),REV+1);
    assert_eq!(h.last().unwrap().tool_call_id.as_deref(),Some("c"));
  }
  if c.mode.starts_with("cancel"){
    if c.op=="final"{tools.tool_result_recorded(attr(),&result("a")).await.unwrap();assert_eq!(r.history().lock().await.len(),retained.len()+1);assert_eq!(*r.effects().lock().await,vec![raw("b")]);}
    else{r.settle().await.unwrap();assert_eq!(r.history().lock().await.len(),retained.len()+3);assert!(r.effects().lock().await.is_empty());}
    assert_eq!(r.revision().load(Ordering::SeqCst),REV+1);let _=meter::take();
  }
  if let Some(old)=&first{assert_eq!(&state,old)}else{first=Some(state);}
  summaries.push(measured);
 }
 println!("{}",json!({"n":c.n,"shape":c.shape,"op":c.op,"mode":c.mode,"state":first.unwrap(),"baseline":baseline.unwrap(),"meters":{"stock":summaries.remove(0),"candidate":summaries.remove(0)}}));
}
async fn run(mode:&str){
 if mode=="full"{
  for n in [5000,50000]{
   for (op,m) in [("final","unbound"),("final","bound"),("final","persisted-bound"),("settle","unbound"),("settle","bound"),("settle","partial")]{
    one(Case{n,shape:"plain",op,mode:m}).await;
   }
  }
  return;
 }
 assert_eq!(mode,"controls");
 for n in [0,1]{
  for (op,m) in [
   ("final","unbound"),("final","bound"),("final","persisted-bound"),("final","duplicate"),("final","lost"),("final","foreign"),
   ("final","sink-error"),("final","cancel-sink"),("final","resume-sink"),("final","cancel-effects"),("final","cancel-history"),("final","cancel-grant"),("final","resume-history"),
   ("settle","empty"),("settle","unbound"),("settle","bound"),("settle","persisted-noop"),("settle","lost"),("settle","partial"),("settle","cancel-history"),("settle","resume-history")
  ] {one(Case{n,shape:"plain",op,mode:m}).await;}
 }
 for shape in ["nan32","nan64","infinity32","minus-infinity64","negative-zero32","positive-zero64"]{
  for (op,m) in [("final","unbound"),("final","persisted-bound"),("final","foreign"),("settle","unbound"),("settle","partial")] {one(Case{n:1,shape,op,mode:m}).await;}
 }
 for op in ["final","settle"]{one(Case{n:1,shape:"plain",op,mode:"wrap"}).await;}
 controls::equality_controls();
}
fn main(){let mode=std::env::args().nth(1).expect("controls or full");tokio::runtime::Builder::new_current_thread().build().unwrap().block_on(tokio::task::unconstrained(run(&mode)));}
