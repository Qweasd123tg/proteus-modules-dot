use proteus_contracts::{contracts::*,domain::*,model_standard::*,storage::journal::*};
use proteus_session_semantics::{JournalValidationState,ModelContextProjection,UsageProjection};
use proteus_session_semantics::journal::proof_bridge::{self as proof,Observer};
use serde::Serialize;
use serde_json::json;
use std::{io::{BufRead,BufReader,BufWriter,Seek,Write},path::PathBuf};
use uuid::Uuid;
mod meter;
const SESSION:Uuid=Uuid::from_u128(1);const THREAD:Uuid=Uuid::from_u128(2);
const TURN:Uuid=Uuid::from_u128(3);const NESTED:Uuid=Uuid::from_u128(5);
const EXEC:ExecutionId=ExecutionId::from_uuid(Uuid::from_u128(4));
const DETACHED:ExecutionId=ExecutionId::from_uuid(Uuid::from_u128(14));
const PREV_TURN:TurnId=Uuid::from_u128(20);const PREV_EXEC:ExecutionId=ExecutionId::from_uuid(Uuid::from_u128(21));
const OBS:Observer=Observer{
 begin_pending:meter::begin_pending,after_map_clone:meter::after_map_clone,end_pending_prepare:meter::end_pending_prepare,
 visit:meter::visit,after_capture:meter::after_capture,finish_pending:meter::finish_pending,
};
fn digest(v:&impl Serialize)->String{
 use ring::digest::{Context,SHA256};use std::io::{Result,Write};
 struct W(Context);impl Write for W{fn write(&mut self,b:&[u8])->Result<usize>{self.0.update(b);Ok(b.len())}fn flush(&mut self)->Result<()>{Ok(())}}
 let mut w=W(Context::new(&SHA256));serde_json::to_writer(&mut w,v).unwrap();
 w.0.finish().as_ref().iter().map(|v|format!("{v:02x}")).collect()
}
fn record(seq:u64,entry:JournalEntry,which:&str)->JournalRecord{
 let physical=matches!(entry,JournalEntry::TurnOpened(_)|JournalEntry::ToolCallRecorded(_)|JournalEntry::ToolEffectRecorded(_)|JournalEntry::ToolResultRecorded(_)|JournalEntry::ModelRequestRecorded(_));
 JournalRecord{schema_version:JOURNAL_SCHEMA_VERSION,record_id:Uuid::from_u128(1000+seq as u128),session_seq:seq,timestamp_ms:91+seq as i64,
  session_id:SESSION,execution_id:physical.then_some(match which{"detached"=>DETACHED,"previous"=>PREV_EXEC,_=>EXEC}),
  thread_id:if which=="detached"{None}else{Some(if which=="nested"{NESTED}else{THREAD})},
  turn_id:(which!="detached").then_some(if which=="previous"{PREV_TURN}else{TURN}),entry}
}
fn push(v:&mut Vec<JournalRecord>,entry:JournalEntry,which:&str){v.push(record(v.len() as u64+1,entry,which));}
fn effect(id:&str,n:usize,shape:&str)->ToolResult{
 let output=if shape=="mixed"{
  let token="эффект 🐢\n";let mut s=token.repeat(n/token.len());s.extend(std::iter::repeat_n('q',n-s.len()));s
 }else{"x".repeat(n)};
 let mut v=ToolResult::ok(id.into(),output);
 if shape=="mixed"{
   v.ok=false;v.error=Some("fixture error".into());
   v.content=vec![ToolContent::Text{text:"joined".into()},ToolContent::Json{value:json!({"nested":[false,{"x":"🧪"}]})},
     ToolContent::Image{mime_type:"image/png".into(),data:"AA==".into()},ToolContent::Binary{mime_type:"application/octet-stream".into(),data:"AA==".into()}];
 }
 v.with_metadata(json!({"call":id,"score":3,"unicode":"факт"}))
}
#[derive(Clone,Copy)]struct Case{n:usize,mode:&'static str,shape:&'static str,status:&'static str}
struct Fixture{history:Vec<CanonicalMessage>,bindings:Vec<WorkflowToolResultBinding>,ledger:Vec<(ToolCall,&'static str,ToolResult,bool)>,records:Vec<JournalRecord>}
fn fixture(c:Case)->Fixture{
 let mut records=Vec::new();
 if c.mode=="previous-turn"{
  let call=ToolCall::new("previous","fixture-tool",json!({}));
  push(&mut records,JournalEntry::TurnOpened(TurnOpened{task:AgentTask::new("previous",PathBuf::from("/fixture")),
   intent:None,base_history_revision:0,module_epoch:0,config_snapshot:json!({})}),"previous");
  push(&mut records,JournalEntry::ToolCallRecorded(ToolCallRecorded{call:call.clone(),phase:ToolCallRecordPhase::Requested{owner:OperationOwner::Workflow}}),"previous");
  push(&mut records,JournalEntry::ToolCallRecorded(ToolCallRecorded{call,phase:ToolCallRecordPhase::Resolved{resolution:ToolCallResolution::Allowed}}),"previous");
  push(&mut records,JournalEntry::ToolEffectRecorded(ToolResultRecorded{result:effect("previous",c.n,c.shape)}),"previous");
  push(&mut records,JournalEntry::TurnSettled(TurnSettled{status:TurnSettlementStatus::Success,output:None,error:None}),"previous");
 }

 push(&mut records,JournalEntry::TurnOpened(TurnOpened{
  task:AgentTask::new("fixture observation",PathBuf::from("/fixture")),intent:None,base_history_revision:0,module_epoch:0,config_snapshot:json!({})
 }),"root");
 let spec:Vec<(&str,&str,bool,bool)>=match c.mode{
  "only-unbound"=>vec![("u","root",false,false)],
  "owner-bypass"=>vec![("u","root",false,false)],
  "nested-detached"=>vec![("a","root",true,false),("n","nested",false,false),("d","detached",false,false)],
  "no-effects"=>vec![("a","root",true,false)],
  "only-final"=>vec![("a","root",true,true)],
  "mixed-final"=>vec![("a","root",true,false),("b","root",true,true),("u","root",false,false)],
  "multiple"|"late-part"|"late-active"=>vec![("a","root",true,false),("b","root",true,false),("u","root",false,false)],
  _=>vec![("a","root",true,false)]
 };
 let mut bindings=Vec::new();let mut ledger=Vec::new();let mut parts=Vec::new();
 for (i,(id,which,bound,finalized)) in spec.into_iter().enumerate(){
  let call=ToolCall::new(id,"fixture-tool",json!({"argument":id}));
  if bound{
   let mut b=WorkflowToolResultBinding::new(call.clone());b.message_id=Uuid::from_u128(9000+i as u128);b.part_id=Uuid::from_u128(9100+i as u128);
   bindings.push(b);parts.push(ContentPart::ToolCall{call:call.clone()});
  }
  let payload=effect(id,c.n,c.shape);
  ledger.push((call,which,payload,finalized));
 }
 let mut u=CanonicalMessage::text(MessageRole::User,"synthetic fixture prompt");
 u.id=Uuid::from_u128(7650);u.parts[0].part_id=Uuid::from_u128(7651);
 let mut history=vec![u];
 if !parts.is_empty(){
  let mut m=CanonicalMessage::new(MessageRole::Assistant,parts);m.id=Uuid::from_u128(7700);
  for (i,p) in m.parts.iter_mut().enumerate(){p.part_id=Uuid::from_u128(7800+i as u128);}
  history.push(m);
 }
 let report=(c.mode=="context").then(||{
  let mut r=HistoryCompactionReport::unchanged(0,Some("typed context marker".into()));r.changed=true;r.output_messages=history.len();r
 });
 push(&mut records,JournalEntry::HistoryMutated(HistoryMutated{
  previous_revision:0,new_revision:1,mutation:if c.mode=="owner-bypass"{HistoryMutationKind::Append}else{HistoryMutationKind::Checkpoint},
  messages:history.clone(),compaction:report,tool_results:bindings.clone()
 }),"root");
 for (call,which,payload,finalized) in &ledger{
  push(&mut records,JournalEntry::ToolCallRecorded(ToolCallRecorded{call:call.clone(),phase:ToolCallRecordPhase::Requested{owner:OperationOwner::Workflow}}),which);
  push(&mut records,JournalEntry::ToolCallRecorded(ToolCallRecorded{call:call.clone(),phase:ToolCallRecordPhase::Resolved{resolution:ToolCallResolution::Allowed}}),which);
  if c.mode!="no-effects"{
   push(&mut records,JournalEntry::ToolEffectRecorded(ToolResultRecorded{result:payload.clone()}),which);
  }
  if *finalized{
   // The fact checker validates matching ok/error/content. The final may
   // deliberately differ in presentation output.
   let mut final_value=payload.clone();final_value.output="final precedence".into();final_value.metadata["finished"]=json!(true);
   push(&mut records,JournalEntry::ToolResultRecorded(ToolResultRecorded{result:final_value}),which);
  }
 }
 Fixture{history,bindings,ledger,records}
}
fn settle(seq:u64,status:&str)->JournalRecord{
 let status=match status{"canceled"=>TurnSettlementStatus::Canceled,"failed"=>TurnSettlementStatus::Error,_=>TurnSettlementStatus::Success};
 record(seq,JournalEntry::TurnSettled(TurnSettled{status,output:None,error:(status==TurnSettlementStatus::Error).then(||"fixture failed".into())}),"root")
}
fn strict_seed(records:&[JournalRecord])->(JournalValidationState,ModelContextProjection,UsageProjection,u64,u64){
 let mut file=tempfile::tempfile().unwrap();
 {
  let mut out=BufWriter::new(&mut file);
  for r in records{serde_json::to_writer(&mut out,r).unwrap();out.write_all(b"\n").unwrap();}
  out.flush().unwrap();
 }
 let file_bytes=file.metadata().unwrap().len();file.rewind().unwrap();
 let mut in_=BufReader::new(file);let mut line=Vec::new();
 let mut canonical=JournalValidationState::default();let mut context=ModelContextProjection::default();let mut usage=UsageProjection::default();let mut seq=1;
 for expected in records{
  assert!(in_.read_until(b'\n',&mut line).unwrap()>0 && line.ends_with(b"\n"));
  let actual:JournalRecord=serde_json::from_slice(&line).unwrap();assert_eq!(&actual,expected);
  canonical.apply_sequenced(SESSION,&actual,&mut seq).unwrap();usage.apply(&actual);context.apply(&actual);line.clear();
 }
 assert_eq!(in_.read_until(b'\n',&mut line).unwrap(),0);
 (canonical,context,usage,seq,file_bytes)
}
fn one(c:Case){
 let fx=fixture(c);proof::configure(false,None);
 let (mut base,mut context,mut usage,mut seq,physical)=strict_seed(&fx.records);
 let mut extra_facts=Vec::new();
 let mut target=settle(seq,c.status);
 let mut originally=proof::pending_ids(&base,&target);
 let mut culprit=None;
 let mut before_failure=0usize;
 if matches!(c.mode,"late-part"|"late-active"){
   let bound_order=originally.iter().filter(|id|fx.bindings.iter().any(|b|&b.call_id==*id)).collect::<Vec<_>>();
   assert_eq!(bound_order.len(),2);
   let b=fx.bindings.iter().find(|b|&b.call_id==bound_order[1]).unwrap();
   culprit=Some(b.call_id.clone());
   before_failure=originally.iter().position(|id|id==&b.call_id).unwrap();
   if c.mode=="late-part"{
    let mut conflict=b.message(effect(&b.call_id,0,c.shape));
    conflict.parts[0].payload=ContentPart::Text{text:"conflicting trace".into()};
    let req=record(seq,JournalEntry::ModelRequestRecorded(ModelRequestRecorded{
     exchange_id:Uuid::from_u128(8700),origin:ModelCallOrigin::Direct,owner:OperationOwner::Workflow,
     request:CanonicalModelRequest::new(ModelRef::new("fixture","fixture"),vec![conflict])
    }),"root");
    base.apply_sequenced(SESSION,&req,&mut seq).unwrap();context.apply(&req);usage.apply(&req);extra_facts.push(req);
   }else{
    let mut extra=CanonicalMessage::text(MessageRole::User,"active collision");extra.id=b.message_id;
    extra.parts[0].part_id=Uuid::from_u128(8110);
    let current=base.history_revision();
    let rec=record(seq,JournalEntry::HistoryMutated(HistoryMutated{previous_revision:current,new_revision:current+1,
      mutation:HistoryMutationKind::Append,messages:vec![extra],compaction:None,tool_results:vec![]}),"root");
    base.apply_sequenced(SESSION,&rec,&mut seq).unwrap();context.apply(&rec);usage.apply(&rec);extra_facts.push(rec);
   }
   target=settle(seq,c.status);assert_eq!(originally,proof::pending_ids(&base,&target));
 }
 if c.mode=="saturated"{proof::set_revision_for_boundary_control(&mut base,u64::MAX);}
 if c.mode=="already-settled"{
  base.apply_sequenced(SESSION,&target,&mut seq).unwrap();context.apply(&target);usage.apply(&target);extra_facts.push(target);
  target=settle(seq,c.status);originally=proof::pending_ids(&base,&target);
 }
 if c.mode=="bad-seq"{target.session_seq+=1;}
 if c.mode=="bad-session"{target.session_id=Uuid::from_u128(201);}
 if c.mode=="bad-schema"{target.schema_version+=1;}
 // Seam only round-trips typed settlement JSON, without touching sequence or authority.
 let target:JournalRecord=serde_json::from_slice(&serde_json::to_vec(&target).unwrap()).unwrap();
 let prior_rev=base.history_revision();
 let prior_len=base.history().len();
 let prior_capture=proof::capture_open(&base);
 let original_cert=digest(&base.history());
 let original_ctx=context.snapshot();
 if c.mode=="context"{assert_eq!(original_ctx,[ModelContextObservation::HistoryCompacted]);}
 let mut result_states=Vec::new();let mut receipts=Vec::new();let mut output=None;
 let envelope_error=matches!(c.mode,"bad-seq"|"bad-session"|"bad-schema"|"already-settled");
 let late=culprit.is_some();
 let want=if envelope_error||c.mode=="owner-bypass"{vec![]}
 else if late{originally[..=before_failure].to_vec()}else{originally.clone()};
 for candidate in [false,true]{
  let mut state=base.clone();let mut nseq=seq;
  let mut md=ModelContextProjection::default();let mut u=UsageProjection::default();
  for fact in fx.records.iter().chain(&extra_facts){md.apply(fact);u.apply(fact);}
  assert_eq!(md.snapshot(),original_ctx);assert_eq!(digest(&u.snapshot(SESSION)),digest(&usage.snapshot(SESSION)));
  proof::configure(candidate,Some(OBS));meter::start();
  let got=state.apply_sequenced(SESSION,&target,&mut nseq);
  let stats=meter::take();proof::configure(false,None);
  assert_eq!(got.is_err(),envelope_error||late);
  if got.is_ok(){md.apply(&target);u.apply(&target);}
  assert_eq!(md.snapshot(),original_ctx);
  let accepted=want.iter().filter(|id|fx.bindings.iter().any(|b|&b.call_id==*id)).count();
  assert_eq!(state.history_revision(),prior_rev.saturating_add(accepted as u64));
  assert_eq!(state.history().len(),prior_len+accepted);
  assert_eq!(nseq,seq+u64::from(got.is_ok()));
  assert_eq!(proof::capture_open(&state),prior_capture&&got.is_err());
  let interrupts=state.interrupted_turns();
  if got.is_ok() && c.status=="canceled" {
   assert_eq!(interrupts.len(),1);assert_eq!(interrupts[0].after_message_id,state.history().last().unwrap().id);
  }else{assert_eq!(interrupts,base.interrupted_turns());}
  for (call,_,_,finalized) in &fx.ledger{
   assert_eq!(proof::final_ledger(&state,&call.id),(*finalized,!*finalized&&c.mode!="no-effects"));
  }
  if c.mode=="previous-turn"{assert_eq!(proof::final_ledger(&state,"previous"),(false,true));assert_eq!(want,["a"]);}
  if !late && !envelope_error{
   let expected=fx.bindings.iter().filter_map(|b|fx.ledger.iter().find(|(c,_,_,_)|c.id==b.call_id).and_then(|(_,_,v,f)|{
    if !*f&&!want.contains(&b.call_id){return None}
    let mut v=v.clone();
    if *f {v.output="final precedence".into();v.metadata["finished"]=json!(true);}
    Some(b.message(v))
   })).collect::<Vec<_>>();
   assert_eq!(state.history(),[fx.history.as_slice(),&expected].concat());
  }
  assert_eq!(digest(&base.history()),original_cert);assert_eq!(base.history_revision(),prior_rev);
  proof::verify_ledger_shared(&base,&state);
  let e=got.err().map(|e|e.to_string());
  if let Some(err)=&e{
   let expected=match c.mode{
    "late-part"=>"changed after it was recorded","late-active"=>"active history contains duplicate message",
    "bad-schema"=>"unsupported journal schema_version","bad-session"=>"belongs to session","bad-seq"=>"journal sequence mismatch","already-settled"=>"was already settled",
    _=>unreachable!()
   };
   assert!(err.contains(expected),"{err}");
   if late{let distinct=if c.mode=="late-active"{!proof::active_valid(&state)}else{proof::active_valid(&state)};assert!(distinct);}
  }else{assert!(proof::active_valid(&state));}
  let state_info=json!({"error":e,"source_seq":seq,"next_seq":nseq,"before_rev":prior_rev,"revision":state.history_revision(),
     "before_rows":prior_len,"rows":state.history().len(),"history_sha256":digest(&state.history()),"bound_before":prior_capture,
     "bound_after":proof::capture_open(&state),"known_rows":proof::known_rows(&state),"interruptions":interrupts,
     "usage":u.snapshot(SESSION),"context":md.snapshot(),"original_ledger_alive":true});
  if let Some(old)=&output{assert_eq!(old,&state_info)}else{output=Some(state_info);}
  result_states.push(state);receipts.push(stats);
 }
 proof::compare(&result_states[0],&result_states[1]);
 println!("{}",json!({"n":c.n,"mode":c.mode,"shape":c.shape,"status":c.status,"physical_bytes":physical,
   "order":originally,"visited":want,"culprit":culprit,"state":output.unwrap(),"meters":{"stock":receipts.remove(0),"candidate":receipts.remove(0)}}));
}
fn main(){
 let run=std::env::args().nth(1).expect("full or controls");
 if run=="full"{
  for n in [1<<20,4<<20,8<<20]{
   for (mode,shape,status) in [("bound","plain","canceled"),("multiple","mixed","success"),("only-unbound","mixed","failed")]{
    one(Case{n,mode,shape,status});
   }
  }
  return;
 }
 assert_eq!(run,"controls");
 for (mode,status) in [("bound","success"),("bound","failed"),("bound","canceled"),
   ("multiple","canceled"),("only-unbound","success"),("owner-bypass","success"),("nested-detached","canceled"),
   ("no-effects","success"),("previous-turn","success"),("only-final","canceled"),("mixed-final","failed"),("late-part","success"),
   ("late-active","canceled"),("saturated","success"),("context","canceled"),("already-settled","success"),
   ("bad-seq","success"),("bad-session","success"),("bad-schema","success")]{
  for shape in ["plain","mixed"]{one(Case{n:137,mode,shape,status});}
 }
 one(Case{n:0,mode:"bound",shape:"plain",status:"success"});
}
