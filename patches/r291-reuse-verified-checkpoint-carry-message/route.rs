#![allow(dead_code,unused_imports)]
use anyhow::Result;
use proteus_contracts::{contracts::*,domain::*,model_standard::*,storage::journal::*};
use proteus_session_semantics::{HistoryCapture,JournalValidationState,ModelContextProjection,UsageProjection};
pub(crate) use proteus_session_semantics::journal::proof;
use proof::Observer;
use serde::Serialize;
use serde_json::{Value,json};
use std::{future::Future,task::{Context,Poll,Waker},io::{BufRead,BufReader,BufWriter,Seek,Write},path::PathBuf,sync::{Arc,atomic::{AtomicU64,Ordering}}};
use tokio::sync::Mutex;
use uuid::Uuid;
pub use proteus_contracts::{contracts,domain,model_standard};
mod meter;mod edge;mod live;mod history_prepare;mod steering;
mod core{
 pub(crate) mod session_journal{pub(crate) use proteus_session_semantics::journal::history_capture;}
 pub(crate) mod model_context{pub(crate) use proteus_session_semantics::ModelContextState;}
 // These methods are compile-only: exact lifted caller runs with no store.
 pub(crate) struct SessionStore;
 impl SessionStore{
  pub(crate) async fn history_revision(&self)->anyhow::Result<u64>{panic!("no store is present in live proof")}
  pub(crate) async fn checkpoint_history(&self,_:crate::ThreadId,_:crate::TurnId,_:&[crate::CanonicalMessage],_:Option<crate::HistoryCompactionReport>,_:Vec<crate::WorkflowToolResultBinding>)->anyhow::Result<()>{panic!("no store is present in live proof")}
 }
}
const SESSION:Uuid=Uuid::from_u128(1);const THREAD:Uuid=Uuid::from_u128(2);
const TURN:Uuid=Uuid::from_u128(3);const EXEC:ExecutionId=ExecutionId::from_uuid(Uuid::from_u128(4));
pub(crate) const OBS:Observer=Observer{begin_carry:meter::begin_carry,prepared:meter::prepared,inserted:meter::inserted,finish_carry:meter::finish_carry};
fn attr()->ExecutionAttribution{ExecutionAttribution::for_turn(EXEC,SESSION,THREAD,TURN)}
fn message(role:MessageRole,id:u128,text:&str)->CanonicalMessage{
 let mut m=CanonicalMessage::text(role,text);m.id=Uuid::from_u128(id);m.parts[0].part_id=Uuid::from_u128(id+1000);m
}
fn payload(id:&str,n:usize,shape:&str)->ToolResult{
 let token="строка 🦀\t\"\\\n";
 let mut raw=if shape=="output"{"x".repeat(n)}else{token.repeat(n/token.len())};
 raw.extend(std::iter::repeat_n('q',n-raw.len()));
 let meta=json!({"route":id,"nested":{"z":"запись","a":[true, {}, 1]}});
 match shape{
  "output"=>ToolResult::ok(id.into(),raw).with_metadata(meta),
  "error"=>ToolResult::new(id.into(),false,"secondary".into(),vec![ToolContent::Json{value:json!({"tiny":[1,false]})}],Some(raw),meta),
  "structured"=>ToolResult::ok(id.into(),"").with_content(vec![ToolContent::Text{text:raw},ToolContent::Json{value:json!({"note":"text"})},
   ToolContent::Image{mime_type:"image/png".into(),data:"AA==".into()},ToolContent::Binary{mime_type:"application/octet-stream".into(),data:"AA==".into()}]).with_metadata(meta),
  _=>panic!("unknown shape")
 }
}
fn digest(v:&impl Serialize)->String{
 use ring::digest::{Context,SHA256};use std::io::{Result,Write};
 struct W(Context);impl Write for W{fn write(&mut self,b:&[u8])->Result<usize>{self.0.update(b);Ok(b.len())}fn flush(&mut self)->Result<()>{Ok(())}}
 let mut w=W(Context::new(&SHA256));serde_json::to_writer(&mut w,v).unwrap();
 w.0.finish().as_ref().iter().map(|v|format!("{v:02x}")).collect()
}
fn kind(seq:u64,e:JournalEntry)->JournalRecord{
 let execution_id=(!matches!(&e,JournalEntry::HistoryMutated(_)|JournalEntry::TurnSettled(_))).then_some(EXEC);
 JournalRecord{schema_version:JOURNAL_SCHEMA_VERSION,record_id:Uuid::from_u128(1000+seq as u128),session_seq:seq,
  timestamp_ms:100+seq as i64,session_id:SESSION,execution_id,thread_id:Some(THREAD),turn_id:Some(TURN),entry:e}
}
fn push(v:&mut Vec<JournalRecord>,e:JournalEntry){v.push(kind(v.len() as u64+1,e));}
fn mutation(r:u64,history:Vec<CanonicalMessage>,bindings:Vec<WorkflowToolResultBinding>,compaction:Option<HistoryCompactionReport>)->JournalEntry{
 JournalEntry::HistoryMutated(HistoryMutated{previous_revision:r,new_revision:r+1,mutation:HistoryMutationKind::Checkpoint,messages:history,compaction,tool_results:bindings})
}
#[derive(Clone,Copy)]struct Case{n:usize,mode:&'static str,shape:&'static str,route:&'static str}
struct Fixture{
 prefix:Vec<CanonicalMessage>,bindings:Vec<WorkflowToolResultBinding>,results:Vec<ToolResult>,
 recorded:Vec<&'static str>,history:Vec<CanonicalMessage>,proposed:Vec<CanonicalMessage>,
 offered:Vec<WorkflowToolResultBinding>,expected:Vec<CanonicalMessage>,prepared:Vec<&'static str>,
 compacted:Option<HistoryCompactionReport>,error:Option<&'static str>,
}
fn fixture(c:Case)->Fixture{
 let mut bindings=Vec::new();let mut calls=Vec::new();
 for (i,id) in ["a","b","c","d"].into_iter().enumerate(){
  let call=ToolCall::new(id,"model-call",json!({"query":id}));
  let selected=ToolCall::new(id,"approved-call",json!({"normalized":{"query":id}}));
  calls.push(ContentPart::ToolCall{call});
  let mut bound=WorkflowToolResultBinding::new(selected);
  bound.message_id=Uuid::from_u128(600+i as u128);bound.part_id=Uuid::from_u128(1600+i as u128);bindings.push(bound);
 }
 let mut bot=CanonicalMessage::new(MessageRole::Assistant,calls);bot.id=Uuid::from_u128(101);
 for(i,p)in bot.parts.iter_mut().enumerate(){p.part_id=Uuid::from_u128(2000+i as u128);}
 let user=message(MessageRole::User,100,"fixture user");
 let prefix=vec![user.clone(),bot];
 let results=["a","b","c","d"].into_iter().map(|id|payload(id,if id=="b"{c.n}else{31},c.shape)).collect::<Vec<_>>();
 let recorded=match c.mode{"none"=>vec![],"partial-ack"|"ack-all"|"late-active"=>vec!["c","a","b"],_=>vec!["b"]};
 let list=|ids:&[&str]|bindings.iter().filter(|x|ids.contains(&x.call_id.as_str())).map(|b|b.message(results.iter().find(|z|z.call_id==b.call_id).unwrap().clone())).collect::<Vec<_>>();
 let history=[prefix.clone(),list(&recorded)].concat();
 let mut proposed=prefix.clone();let mut offered=bindings.clone();
 let mut prepared=Vec::new();let mut error=None;let mut report=None;
 let later=message(MessageRole::Assistant,102,"later assistant turn progress");
 match c.mode{
  "partial-ack"|"late-active"=>{
   proposed.extend(list(&["a"]));proposed.push(later.clone());
   offered=vec![bindings[2].clone(),bindings[1].clone(),bindings[3].clone()];
   prepared.extend(["b","c"]);
   if c.mode=="late-active"{proposed.push(later);error=Some("active history contains duplicate message id");}
  },
  "ack-all"=>{proposed=history.clone();proposed.push(later);offered=vec![bindings[3].clone()];},
  "changed-ack"=>{
   let mut ack=list(&["b"]).pop().unwrap();
   let ContentPart::ToolResult{result}=&mut ack.parts[0].payload else{unreachable!()};
   result.output.push_str("-changed");
   // Only the direct rebase/live branch can reach ACK comparison. The
   // strict validator first rejects reused part with changed canonical payload.
   proposed.push(ack);proposed.push(later);offered=vec![bindings[3].clone()];
   error=Some(if c.route=="strict"{"changed after it was recorded"}else{"checkpoint changed a committed tool result"});
  },
  "delete-binding"=>{proposed.push(later);offered.retain(|b|b.call_id!="b");error=Some("checkpoint discarded a committed tool result");},
  "changed-binding"=>{
   proposed.push(later);offered[1].execution_call.args=json!({"different":true});
   error=Some(if c.route=="strict"{"checkpoint reuses a previously recorded result part identity"}else{"checkpoint changed a pending tool result binding"});
  },
  "changed-pending-binding"=>{
   proposed.push(later);offered[0].execution_call.args=json!({"different":true});error=Some("checkpoint changed a pending tool result binding");
  },
  "compacted"=>{
   proposed=vec![user,later];offered.clear();
   let mut r=HistoryCompactionReport::unchanged(history.len(),Some("fixture reset".into()));r.changed=true;r.output_messages=proposed.len();
   report=Some(r);
  },
  "equal-prefix"=>{proposed=history.clone();offered.retain(|b|b.call_id!="b");},
  "before-revision"=>{proposed.push(later);error=Some(if c.route=="strict"{"history revision mismatch"}else{"stale context preparation target"});},
  _=>{proposed.push(later);if c.mode!="none"{prepared.push("b");}}
 }
 let mut expected=proposed.clone();
 for b in &offered{
  if prepared.contains(&b.call_id.as_str()){expected.push(b.message(results.iter().find(|x|x.call_id==b.call_id).unwrap().clone()));}
 }
 Fixture{prefix,bindings,results,recorded,history,proposed,offered,expected,prepared,compacted:report,error}
}
fn physical_seed(f:&Fixture)->(JournalValidationState,u64,u64){
 let mut records=Vec::new();
 push(&mut records,JournalEntry::TurnOpened(TurnOpened{
  task:AgentTask::new("archive proof",PathBuf::from("/fixture")),intent:None,base_history_revision:0,module_epoch:0,config_snapshot:json!({}),
 }));
 push(&mut records,mutation(0,f.prefix.clone(),f.bindings.clone(),None));
 for b in &f.bindings{
  push(&mut records,JournalEntry::ToolCallRecorded(ToolCallRecorded{call:b.execution_call.clone(),phase:ToolCallRecordPhase::Requested{owner:OperationOwner::Workflow}}));
  push(&mut records,JournalEntry::ToolCallRecorded(ToolCallRecorded{call:b.execution_call.clone(),phase:ToolCallRecordPhase::Resolved{resolution:ToolCallResolution::Allowed}}));
 }
 for id in &f.recorded{
  let r=f.results.iter().find(|r|r.call_id==*id).unwrap();
  push(&mut records,JournalEntry::ToolResultRecorded(ToolResultRecorded{result:r.clone()}));
 }
 let mut file=tempfile::tempfile().unwrap();
 {let mut output=BufWriter::new(&mut file);for r in &records{serde_json::to_writer(&mut output,&r).unwrap();output.write_all(b"\n").unwrap();}output.flush().unwrap();}
 let bytes=file.metadata().unwrap().len();file.rewind().unwrap();
 let mut buf=BufReader::new(file);let mut line=Vec::new();let mut seq=1;let mut state=JournalValidationState::default();
 for expected in &records{
  assert!(buf.read_until(b'\n',&mut line).unwrap()>0 && line.ends_with(b"\n"));
  let actual:JournalRecord=serde_json::from_slice(&line).unwrap();assert_eq!(&actual,expected);
  state.apply_sequenced(SESSION,&actual,&mut seq).unwrap();line.clear();
 }
 assert_eq!(buf.read_until(b'\n',&mut line).unwrap(),0);
 assert_eq!(state.history(),f.history);
 (state,seq,bytes)
}
fn outcome(result:Result<()>,err:Option<&str>)->Option<String>{
 match(result,err){
  (Ok(()),None)=>None,
  (Err(e),Some(s))=>{let x=e.to_string();assert!(x.contains(s),"expected {s}: {x}");Some(x)},
  (a,b)=>panic!("unexpected outcome {a:?}, {b:?}")
 }
}
fn strict(c:Case){
 let f=fixture(c);
 proof::configure(false,None);let (base,seq,physical)=physical_seed(&f);
 let rev=base.history_revision();let hash=digest(&base.history());
 let wanted=kind(seq,mutation(rev+u64::from(c.mode=="before-revision"),f.proposed.clone(),f.offered.clone(),f.compacted.clone()));
 let (wanted,checkpoint_bytes)={
  let mut file=tempfile::tempfile().unwrap();serde_json::to_writer(&mut file,&wanted).unwrap();file.write_all(b"\n").unwrap();
  let bytes=file.metadata().unwrap().len();file.rewind().unwrap();
  let mut in_=BufReader::new(file);let mut line=Vec::new();
  assert_eq!(in_.read_until(b'\n',&mut line).unwrap() as u64,bytes);assert!(line.ends_with(b"\n"));
  let parsed:JournalRecord=serde_json::from_slice(&line).unwrap();assert_eq!(parsed,wanted);
  line.clear();assert_eq!(in_.read_until(b'\n',&mut line).unwrap(),0);
  (parsed,bytes)
 };
 let mut all=Vec::new();let mut probe=Vec::new();
 for candidate in [false,true]{
  let mut state=base.clone();let mut next=seq;
  proof::configure(candidate,Some(OBS));meter::start();
  let r=state.apply_sequenced(SESSION,&wanted,&mut next);
  let metrics=meter::take();proof::configure(false,None);
  let error=outcome(r,f.error);
  if f.error.is_none()||c.mode=="late-active"{assert_eq!(state.history(),f.expected);}
  else{assert_eq!(state.history(),f.history);}
  assert_eq!(digest(&base.history()),hash);assert_eq!(base.history_revision(),rev);
  assert_eq!(state.history_revision(),rev+u64::from(f.error.is_none()));
  assert_eq!(next,seq+u64::from(f.error.is_none()));
  let witness=json!({"error":error,"history":digest(&state.history()),"rows":state.history().len(),"revision":state.history_revision(),"seq":next});
  if f.error.is_none()&&f.offered.iter().any(|b|b.call_id=="d"){
   let mut follow=state.clone();let mut nseq=next;
   follow.apply_sequenced(SESSION,&kind(next,JournalEntry::ToolResultRecorded(ToolResultRecorded{result:f.results[3].clone()})),&mut nseq).unwrap();
   let b=&f.bindings[3];assert!(follow.history().iter().any(|x|*x==b.message(f.results[3].clone())));
   let rev=follow.history_revision();
   let plan=mutation(rev,follow.history().to_vec(),vec![],None);
   let after=kind(nseq,plan);follow.apply_sequenced(SESSION,&after,&mut nseq).unwrap();assert_eq!(follow.history_revision(),rev+1);
  }
  all.push(witness);probe.push(metrics);
 }
 assert_eq!(all[0],all[1]);
 emit(c,physical+checkpoint_bytes,&f,&all[0],probe);
}
#[derive(Default)]
struct ProofSink(std::sync::Mutex<Vec<(&'static str,String)>>);
impl ProofSink{
 fn save(&self,label:&'static str,a:ExecutionAttribution,id:&str){
  assert_eq!(a,attr());self.0.lock().unwrap().push((label,id.into()));
 }
 fn trace(&self)->Vec<(&'static str,String)>{self.0.lock().unwrap().clone()}
}
#[async_trait::async_trait]
impl ToolExecutionRecorder for ProofSink{
 async fn tool_call_requested(&self,a:ExecutionAttribution,own:OperationOwner,call:&ToolCall)->Result<()>{
  assert_eq!(own,OperationOwner::Workflow);self.save("request",a,&call.id);Ok(())
 }
 async fn tool_call_resolved(&self,a:ExecutionAttribution,call:&ToolCall,res:&ToolCallResolution)->Result<()>{
  assert_eq!(*res,ToolCallResolution::Allowed);self.save("resolve",a,&call.id);Ok(())
 }
 async fn tool_approval_requested(&self,_:ExecutionAttribution,_:&ToolCall,_:&str)->Result<()>{panic!("no approval path in fixture")}
 async fn tool_result_recorded(&self,a:ExecutionAttribution,result:&ToolResult)->Result<()>{
  self.save("final",a,&result.call_id);Ok(())
 }
}
fn live_recorder(f:&Fixture,sink:Arc<ProofSink>)->live::TurnHistoryRecorder{
 live::TurnHistoryRecorder{
  attribution:attr(),store:None,history:Arc::new(Mutex::new(vec![f.prefix[0].clone()])),revision:Arc::new(AtomicU64::new(0)),
  model_context:Arc::new(Mutex::new(proteus_session_semantics::ModelContextState::default())),interrupted_turns:Default::default(),
  initial_history:vec![f.prefix[0].clone()],current_user:f.prefix[0].clone(),steering:None,tools:sink,
  capture:Mutex::new(HistoryCapture::default()),admitted_calls:Some(Default::default()),recorded_changed_compactions:Default::default(),
  recorded_compactions:Default::default(),pending_effects:Default::default()
 }
}
fn request(progress:WorkflowHistoryUpdate,b:Vec<WorkflowToolResultBinding>,target:Option<ContextPreparationTarget>)->WorkflowHistoryCheckpoint{
 WorkflowHistoryCheckpoint{history:progress,tool_results:b,preparation_target:target}
}
async fn live(c:Case){
 let f=fixture(c);let mut all=Vec::new();let mut probe=Vec::new();
 for candidate in [false,true]{
  proof::configure(false,None);let sink=Arc::new(ProofSink::default());let r=live_recorder(&f,sink.clone());
  r.checkpoint(request(WorkflowHistoryUpdate::new(f.prefix[1..].to_vec()),f.bindings.clone(),None)).await.unwrap();
  for b in &f.bindings{
   r.tool_call_requested(attr(),OperationOwner::Workflow,&b.execution_call).await.unwrap();
   r.tool_call_resolved(attr(),&b.execution_call,&ToolCallResolution::Allowed).await.unwrap();
  }
  for id in &f.recorded{r.tool_result_recorded(attr(),f.results.iter().find(|z|z.call_id==*id).unwrap()).await.unwrap();}
  assert_eq!(*r.history.lock().await,f.history);
  let rev=r.revision.load(Ordering::SeqCst);
  let checkpoint=if let Some(report)=&f.compacted{
   let w=WorkflowHistoryUpdate::new(f.proposed[1..].to_vec()).with_history_replacement(vec![f.proposed[0].clone()]).with_compactions(vec![report.clone()]);
   request(w,f.offered.clone(),None)
  }else{
   let w=WorkflowHistoryUpdate::new(f.proposed[1..].to_vec());
   request(w,f.offered.clone(),(c.mode=="before-revision").then(||ContextPreparationTarget{execution_id:EXEC,revision:rev+1}))
  };
  let expect_ack=digest(&checkpoint.history);
  let events=sink.trace();
  let mut expected=f.bindings.iter().flat_map(|b|[("request",b.call_id.clone()),("resolve",b.call_id.clone())]).collect::<Vec<_>>();
  expected.extend(f.recorded.iter().map(|x|("final",String::from(*x))));
  assert_eq!(events,expected);
  proof::configure(candidate,Some(OBS));meter::start();
  let held=c.n==173&&c.mode=="carry"&&c.shape=="output";
  let ack=if held{
   let g=r.history.lock().await;let mut f=r.checkpoint(checkpoint);
   assert!(matches!(f.as_mut().poll(&mut Context::from_waker(Waker::noop())),Poll::Pending));
   assert!(r.capture.try_lock().is_err()&&r.recorded_compactions.try_lock().is_err());assert_eq!(sink.trace(),events);
   drop(g);f.await
  }else{r.checkpoint(checkpoint).await};
  assert_eq!(sink.trace(),events);
  let metrics=meter::take();proof::configure(false,None);
  let error=match ack{
   Ok(a)=>{
    assert!(f.error.is_none());assert_eq!(digest(&a.history),expect_ack);
    assert_eq!(a.messages,f.expected);
    assert_eq!(a.revision,Some(rev+u64::from(f.history!=f.expected)));None
   },
   Err(e)=>outcome(Err(e),f.error),
  };
  assert!(r.capture.try_lock().is_ok() && r.history.try_lock().is_ok()&&r.recorded_compactions.try_lock().is_ok());
  assert_eq!(&*r.history.lock().await,if f.error.is_none(){&f.expected}else{&f.history});
  assert_eq!(r.revision.load(Ordering::SeqCst),rev+u64::from(f.error.is_none()&&f.expected!=f.history));
  let (history_hash,history_rows)={let h=r.history.lock().await;(digest(&*h),h.len())};
  let witness=json!({"error":error,"history":history_hash,"rows":history_rows,
   "revision":r.revision.load(Ordering::SeqCst),"model_context":r.model_context.lock().await.snapshot(),"ack_progress":expect_ack,"sink_trace":events,"checkpoint_locks_confirmed":held});
  if f.error.is_none()&&f.offered.iter().any(|b|b.call_id=="d"){
   r.tool_result_recorded(attr(),&f.results[3]).await.unwrap();
   let h=r.history.lock().await.clone();
   assert!(h.iter().any(|x|*x==f.bindings[3].message(f.results[3].clone())));
   let ack=r.checkpoint(request(WorkflowHistoryUpdate::new(h[1..].to_vec()),vec![],None)).await.unwrap();
   assert_eq!(ack.messages,h);
  }
  all.push(witness);probe.push(metrics);
 }
 assert_eq!(all[0],all[1]);
 emit(c,0,&f,&all[0],probe);
}
fn emit(c:Case,physical:u64,f:&Fixture,witness:&Value,mut probe:Vec<Value>){
 println!("{}",json!({"route":c.route,"n":c.n,"mode":c.mode,"shape":c.shape,"physical_bytes":physical,
  "carry":f.prepared,"state":witness,"meters":{"stock":probe.remove(0),"candidate":probe.remove(0)}}));
}
async fn run(mode:&str){
 if mode=="full"{
  for n in [1<<20,4<<20,8<<20]{for shape in ["output","error","structured"]{
   strict(Case{n,mode:"carry",shape,route:"strict"});live(Case{n,mode:"carry",shape,route:"live"}).await;
  }}
 }else{
  assert_eq!(mode,"controls");
  for m in ["carry","partial-ack","ack-all","none","changed-ack","delete-binding","changed-binding","changed-pending-binding","compacted","equal-prefix","before-revision"]{
   for shape in ["output","error","structured"]{
    strict(Case{n:173,mode:m,shape,route:"strict"});live(Case{n:173,mode:m,shape,route:"live"}).await;
   }
  }
  for shape in ["output","error","structured"]{strict(Case{n:173,mode:"late-active",shape,route:"strict"});}
  strict(Case{n:0,mode:"carry",shape:"output",route:"strict"});live(Case{n:0,mode:"carry",shape:"output",route:"live"}).await;
  edge::run();
 }
}
fn main(){let mode=std::env::args().nth(1).expect("full or controls");tokio::runtime::Builder::new_current_thread().build().unwrap().block_on(tokio::task::unconstrained(run(&mode)));}
