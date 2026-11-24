#![allow(dead_code,unused_imports,unreachable_patterns)]
use anyhow::{Result,bail,ensure};use serde::{Serialize,Deserialize};use serde_json::{Value,json};
use std::{cell::{Cell,RefCell},collections::{BTreeMap,HashMap,HashSet},path::{Path,PathBuf},sync::{Arc,Mutex,atomic::{AtomicUsize,Ordering}}};
use uuid::Uuid;
pub use proteus_contracts::{contracts,domain,model_standard};
use proteus_contracts::{app_protocol::*,contracts::*,domain::*,model_standard::*,storage::journal::*};
use proteus_contracts::contracts::{SessionStorageRequest as Request,SessionStorageResponse as Response};
mod core;mod snap;use snap::{RemoteJournalCursor,RemoteJournalSnapshot,RemoteValidatedRead};type JournalReadSnapshot=RemoteJournalSnapshot;
mod stage;use stage::{DisplayRecords,DisplayRecordWriter,is_display_kind};mod render;mod render_stock;mod render_candidate;
mod meter;mod supplement;
thread_local!{
 static EVENTS:RefCell<Vec<String>>=const{RefCell::new(Vec::new())};
 static FINAL:Cell<bool>=const{Cell::new(false)};
 static CHANGED:Cell<bool>=const{Cell::new(false)};
 static UNSTAGED:Cell<bool>=const{Cell::new(false)};
 static STAGE:Cell<(usize,u64,bool)>=const{Cell::new((0,0,false))};
 static READ_FAULT:RefCell<Option<String>>=const{RefCell::new(None)};
}
const TURN:Uuid=Uuid::from_u128(71);const EXEC:ExecutionId=ExecutionId::from_uuid(Uuid::from_u128(79));const DETACHED:ExecutionId=ExecutionId::from_uuid(Uuid::from_u128(89));
fn trace(s:String){EVENTS.with(|t|t.borrow_mut().push(s))}
fn bytes(v:&impl Serialize)->Vec<u8>{serde_json::to_vec(v).unwrap()}
fn sha(v:&[u8])->String{ring::digest::digest(&ring::digest::SHA256,v).as_ref().iter().map(|v|format!("{v:02x}")).collect()}
fn owning_caps(rows:&Vec<AppTranscriptMessage>)->String{
 fn val(v:&Value,a:&mut Vec<usize>){
  match v{
   Value::String(s)=>a.push(s.capacity()),
   Value::Array(x)=>{a.push(x.capacity());for v in x{val(v,a)}},
   Value::Object(x)=>{for (k,v) in x{a.push(k.capacity());val(v,a)}},
   _=>()
  }
 }
 let mut a=vec![rows.capacity()];
 for r in rows{
  a.extend([r.role.capacity(),r.text.capacity(),r.images.capacity()]);
  if let Some(t)=&r.tool{
   a.extend([t.call_id.capacity(),t.name.capacity(),t.status.capacity()]);
   if let Some(s)=&t.result{a.push(s.capacity());}
   if let Some(term)=&t.terminal{a.push(term.title.capacity());}
   val(&t.args,&mut a);if let Some(v)=&t.effective_args{val(v,&mut a);}val(&t.metadata,&mut a);
  }
 }
 sha(&bytes(&a))
}
fn push(records:&mut Vec<JournalRecord>,entry:JournalEntry,execution_id:Option<ExecutionId>,scoped:bool){
 let seq=records.len() as u64+1;
 records.push(JournalRecord{schema_version:JOURNAL_SCHEMA_VERSION,record_id:Uuid::from_u128(100+seq as u128),session_seq:seq,timestamp_ms:1100+seq as i64,session_id:SESSION,execution_id,thread_id:scoped.then_some(THREAD),turn_id:scoped.then_some(TURN),entry});
}
fn result(bytes_n:usize,shape:&str)->ToolResult{
 let payload=match shape{
  "error"=>{let base="Ж🦀\\n\t\"";let mut out=base.repeat(bytes_n/base.len());out.extend(std::iter::repeat_n('e',bytes_n-out.len()));out}
  _=> "x".repeat(bytes_n)
 };
 let source="call-visible".to_owned();
 let result=match shape{
  "error"|"both"|"denied"=>ToolResult::new(source,false,"other raw output".into(),vec![],Some(payload),Value::Null),
  "whitespace-error"=>ToolResult::new(source,false,"masked output".into(),vec![],Some(" \n\t".into()),Value::Null),
  "whitespace-output"=>ToolResult::ok(source," \n").with_content(vec![ToolContent::Text{text:"must not display".into()}]),
  "empty-error"=>ToolResult::new(source,true,payload,vec![],Some(String::new()),Value::Null),
  "structured"=>ToolResult::ok(source,"").with_content(vec![
   ToolContent::Text{text:"abc".into()},ToolContent::Json{value:json!({"foo":42})},
   ToolContent::Image{mime_type:"image/png".into(),data:"AA==".into()},ToolContent::Binary{mime_type:"application/octet-stream".into(),data:"AA==".into()}]),
  "status-ok"=>ToolResult::ok(source,""),
  "status-fail"=>ToolResult::new(source,false,String::new(),vec![],None,Value::Null),
  _=>ToolResult::ok(source,payload)
 };
 let terminal=if shape=="structured"{json!({"unexpected":"bad terminal"})}else{json!({"id":Uuid::from_u128(120),"title":"synthetic","tty":false})};
 result.with_metadata(json!({"stage":"final","tool_terminal":terminal,"extra":{"b":1,"a":["кириллица",true]}}))
}
fn make_case(n:usize,shape:&str)->(Arc<Vec<JournalRecord>>,u64,ToolResult,i64){
 let rst=result(n,shape);let mut v=vec![];
 let task=AgentTask::new("synthetic fixture","/fixture".into());
 push(&mut v,JournalEntry::TurnOpened(TurnOpened{task,intent:None,base_history_revision:0,module_epoch:0,config_snapshot:json!({})}),Some(EXEC),true);
 let mut m=CanonicalMessage::text(MessageRole::User,"synthetic question");
 m.id=Uuid::from_u128(12345);m.parts[0].part_id=Uuid::from_u128(12346);
 push(&mut v,JournalEntry::HistoryMutated(HistoryMutated{previous_revision:0,new_revision:1,mutation:HistoryMutationKind::Append,messages:vec![m],compaction:None,tool_results:vec![]}),None,true);
 if shape=="causal" || shape=="embedded"{
  if shape=="embedded"{
   let mut m=CanonicalMessage::new(MessageRole::Tool,vec![ContentPart::ToolResult{result:rst.clone()}]);
   m.id=Uuid::from_u128(12347);m.parts[0].part_id=Uuid::from_u128(12348);
   push(&mut v,JournalEntry::HistoryMutated(HistoryMutated{previous_revision:1,new_revision:2,mutation:HistoryMutationKind::Append,messages:vec![m],compaction:None,tool_results:vec![]}),None,true);
  }
  push(&mut v,JournalEntry::TurnSettled(TurnSettled{status:TurnSettlementStatus::Success,output:None,error:None}),None,true);
  return (Arc::new(v),if shape=="embedded"{2}else{1},rst,1103)
 }
 let call=ToolCall::new("call-visible","fixture-tool",json!({"probe":"not executed"}));
 push(&mut v,JournalEntry::ToolCallRecorded(ToolCallRecorded{call:call.clone(),phase:ToolCallRecordPhase::Requested{owner:OperationOwner::Workflow}}),Some(EXEC),true);
 let date=v.last().unwrap().timestamp_ms;
 let resolution=if shape=="denied"{ToolCallResolution::PolicyDenied{reason:"fixture policy".into()}}else{ToolCallResolution::Allowed};
 push(&mut v,JournalEntry::ToolCallRecorded(ToolCallRecorded{call,phase:ToolCallRecordPhase::Resolved{resolution}}),Some(EXEC),true);
 // Separate truly detached, valid tool lifecycle: its raw payload must stay hidden.
 let h=ToolCall::new("detached","fixture-hidden",json!({}));
 push(&mut v,JournalEntry::ToolCallRecorded(ToolCallRecorded{call:h.clone(),phase:ToolCallRecordPhase::Requested{owner:OperationOwner::Workflow}}),Some(DETACHED),false);
 push(&mut v,JournalEntry::ToolCallRecorded(ToolCallRecorded{call:h,phase:ToolCallRecordPhase::Resolved{resolution:ToolCallResolution::Allowed}}),Some(DETACHED),false);
 push(&mut v,JournalEntry::ToolResultRecorded(ToolResultRecorded{result:ToolResult::ok("detached".into(),"hidden detached raw")}),Some(DETACHED),false);
 let mut revision=1;
 if shape=="reset"{
  push(&mut v,JournalEntry::HistoryMutated(HistoryMutated{previous_revision:1,new_revision:2,mutation:HistoryMutationKind::Replace,messages:vec![],compaction:None,tool_results:vec![]}),None,false);revision=2;
 }
 if matches!(shape,"effect-final"|"effect-only"){
  let mut e=rst.clone();e.output="raw effect only".into();e.metadata["stage"]=json!("effect");
  push(&mut v,JournalEntry::ToolEffectRecorded(ToolResultRecorded{result:e}),Some(EXEC),true);
 }
 if shape!="effect-only"{
  push(&mut v,JournalEntry::ToolResultRecorded(ToolResultRecorded{result:rst.clone()}),Some(EXEC),true);
 }
 if shape=="duplicate"{
  push(&mut v,JournalEntry::ToolResultRecorded(ToolResultRecorded{result:rst.clone()}),Some(EXEC),true);
 }
 push(&mut v,JournalEntry::TurnSettled(TurnSettled{status:TurnSettlementStatus::Success,output:None,error:None}),None,true);
 if shape=="subagent"{
   push(&mut v,JournalEntry::SubagentSessionBoundRecorded(SubagentSessionBinding{source_call_id:"call-visible".into(),child_thread_id:Uuid::from_u128(950),session_id:Uuid::from_u128(951),session_dir:"/fixture/child".into()}),Some(EXEC),true);
 }
 (Arc::new(v),revision,rst,date)
}
#[derive(Clone,Copy)]struct Case{n:usize,route:&'static str,shape:&'static str,fault:&'static str}
fn run_case(c:Case){
 let (records,revision,witness,date)=make_case(c.n,c.shape);
 let mut prev=None;let mut report=Vec::new();
 for changed in [false,true]{
  CHANGED.set(changed);UNSTAGED.set(c.route=="unstaged");meter::reset();EVENTS.with(|e|*e.borrow_mut()=Vec::with_capacity(256));STAGE.set((0,0,false));
  let docs=Default::default();
  let adapter_fault=if c.shape=="loose"{"loose"}else{c.fault};
  let store=RemoteSessionStore::new(records.clone(),revision,c.route,adapter_fault,docs);
  let planned=store.test_revision();
  let out=store.project_sourced_read_model(None,|snapshot|{
   STAGE.set(snap::stage_status(snapshot));trace("Render".into());
   if c.fault=="stage-early"{snap::break_stage(snapshot);}
   meter::begin_replay();
   let result=render::journal_transcript_from_source(snapshot,(c.shape=="live").then_some(TURN));
   meter::end_replay();
   if c.fault=="stage-late"{snap::break_stage(snapshot);}
   result
  });
  let measure=meter::take();
  let route_trace=EVENTS.with(|e|e.borrow().clone());
  let stage=STAGE.get();let projected=c.route=="projected";let staged=c.route!="unstaged";
  if c.shape=="duplicate" || matches!(c.fault,"wrong-page"|"initial-wrong-session"){
   assert_eq!(stage,(0,0,false));
   assert!(!route_trace.iter().any(|e|e=="Render"));
  }else if staged{
   assert_eq!(stage.0,records.len());assert_eq!(stage.2,matches!(c.shape,"causal"|"embedded"));assert!(stage.1>c.n as u64);
  }else {assert_eq!(stage,(0,0,false));}
  assert_eq!(route_trace.iter().any(|e|e=="OpenDisplaySnapshot"),c.route!="unstaged");
  assert!(route_trace.iter().any(|e|if projected{e=="ReadDisplayRecords 0"}else{e=="ReadRecords 0"}) || c.shape=="duplicate" || c.fault=="initial-wrong-session");
  let (result,rows,tool_cap,ownership)=match out{
   Ok((src,model))=>{
    assert!(!matches!(c.fault,"stage-early"|"stage-late"));
    assert_ne!(c.shape,"duplicate");
    assert_eq!(src.revision().as_deref(),Some(planned.as_str()));
    assert_eq!(model.conversation.revision,revision);
    assert_eq!(model.conversation.messages.len(),if c.shape=="embedded"{2}else{usize::from(c.shape!="reset")});
    assert!(model.transcript.iter().all(|r|r.tool.as_ref().is_none_or(|t|t.call_id!="detached")));
    let tools:Vec<_>=model.transcript.iter().filter_map(|r|r.tool.as_ref().map(|t|(r,t))).collect();
    let cap=if matches!(c.shape,"live"|"causal"){assert!(tools.is_empty());0}else{
     assert_eq!(tools.len(),1);
     let (row,t)=tools[0];
     let want=if c.shape=="effect-only"{"raw effect only".into()}else{witness.text_or_status()};
     assert_eq!(t.call_id,"call-visible");assert_eq!(t.result.as_deref(),Some(want.as_str()));
     assert_eq!(t.status,if witness.ok{"done"}else{"failed"});
     assert_eq!(t.metadata["extra"],witness.metadata["extra"]);
     assert_eq!(t.metadata["stage"],if c.shape=="effect-only"{"effect"}else{"final"});
     assert_eq!(t.terminal.is_none(),c.shape=="structured");
     assert_eq!(row.timestamp_ms,Some(date));
     assert_eq!(t.name,if matches!(c.shape,"reset"|"embedded"){"tool"}else{"fixture-tool"});
     if c.shape=="subagent"{assert_eq!(t.metadata["child_thread_id"],json!(Uuid::from_u128(950)));assert_eq!(t.metadata["subagent_session"]["session_dir"],"/fixture/child");}
     let text=t.result.as_ref().unwrap();
     assert_eq!(text.len(),want.len());text.capacity()
    };
    let output=sha(&bytes(&model.transcript));let rendered=model.transcript.len();
    let cache_read=store.saved_transcript(&planned);
    let named=!matches!(c.fault,"page"|"named-write");
    assert_eq!(cache_read.is_some(),named);
    if let Some(rows)=cache_read{assert_eq!(sha(&bytes(&rows)),output);}
    (output,rendered,cap,owning_caps(&model.transcript))
   }
   Err(e)=>{
    let text=format!("{e:#}");
    assert!(text.contains(match (c.shape,c.fault){("duplicate",_)=>"duplicate tool result",(_,"wrong-page")=>"storage changed the fixed snapshot while paging",(_,"initial-wrong-session")=>"storage snapshot belongs to another session",_=>"transcript staging record count changed"}),"{text}");
    assert!(!route_trace.iter().any(|e|e.starts_with("WriteCache")));
    (text,0,0,String::new())
   }
  };
  let (header,pages,docs_n)=store.cache_proof();
  let eq=(result,rows,tool_cap,ownership,route_trace,stage,sha(&bytes(&header)),pages,docs_n);
  if let Some(old)=&prev{assert_eq!(old,&eq,"route parity {:?} {} {}",c.route,c.shape,c.fault);}else{prev=Some(eq);}
  report.push(measure);
 }
 let (result,rows,tool_cap,ownership,trace,stage,head,pages,n_docs)=prev.unwrap();
 println!("{}",json!({"n":c.n,"route":c.route,"shape":c.shape,"fault":c.fault,"result":result,"rows":rows,"capacity":tool_cap,"ownership_capacities_sha256":ownership,"stage":{"records":stage.0,"bytes":stage.1,"causal":stage.2},"trace":trace,"headers_sha256":head,"pages_sha256":pages,"page_docs":n_docs,"meters":{"stock":report.remove(0),"candidate":report.remove(0)}}));
}
fn main(){
 let mode=std::env::args().nth(1).expect("projected, fallback, unstaged or controls");
 if mode!="controls"{
  let route=match mode.as_str(){"projected"=>"projected","fallback"=>"fallback","unstaged"=>"unstaged",_=>panic!("invalid mode")};
  for n in [1<<20,4<<20,8<<20]{for shape in ["output","error"]{run_case(Case{n,route,shape,fault:"ok"});}}
  return;
 }
 for route in ["projected","fallback","unstaged"]{
  for shape in ["output","error","both","whitespace-error","whitespace-output","empty-error","structured","status-ok","status-fail","denied","reset","live","effect-final","effect-only","duplicate","causal","embedded","subagent"]{
    run_case(Case{n:89,route,shape,fault:"ok"});
  }
  if route=="unstaged"{run_case(Case{n:1024,route,shape:"loose",fault:"ok"});}
  for fault in ["page","prefix","named-write","head"]{run_case(Case{n:89,route,shape:"output",fault});}
  run_case(Case{n:89,route,shape:"output",fault:"wrong-page"});
  if route!="projected"{run_case(Case{n:89,route,shape:"output",fault:"initial-wrong-session"});}
  if route!="unstaged"{for fault in ["stage-early","stage-late"]{run_case(Case{n:89,route,shape:"output",fault});}}
 }
 supplement::supplement();
}
