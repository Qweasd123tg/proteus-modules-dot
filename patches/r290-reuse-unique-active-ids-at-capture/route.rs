use proteus_contracts::{contracts::*,domain::*,model_standard::*,storage::journal::*};
use proteus_session_semantics::{JournalValidationState,ModelContextProjection,UsageProjection};
use proteus_session_semantics::journal::proof_bridge::{self as proof,Observer};
use serde::Serialize;
use serde_json::json;
use std::{io::{BufRead,BufReader,BufWriter,Seek,Write},path::PathBuf};
use uuid::Uuid;
mod meter;mod edge;
const SESSION:Uuid=Uuid::from_u128(1);const THREAD:Uuid=Uuid::from_u128(2);
const TURN:Uuid=Uuid::from_u128(3);const NESTED:Uuid=Uuid::from_u128(5);
const EXEC:ExecutionId=ExecutionId::from_uuid(Uuid::from_u128(4));
const DETACHED:ExecutionId=ExecutionId::from_uuid(Uuid::from_u128(14));
const PREV_TURN:TurnId=Uuid::from_u128(20);const PREV_EXEC:ExecutionId=ExecutionId::from_uuid(Uuid::from_u128(21));
const OBS:Observer=Observer{
 active_begin:meter::active_begin,active_fast:meter::active_fast,
 rebuild_rows:meter::rebuild_rows,active_finish:meter::active_finish,
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
  "unbound-final"|"no-owner-settle"=>vec![("u","root",false,false)],
  "settle-unique"|"settle-shared"|"settle-late"|"none-followup"=>vec![("a","root",true,false),("b","root",true,false),("u","root",false,false)],
  "settle-nested"=>vec![("a","root",true,false),("n","nested",false,false),("d","detached",false,false)],
  _=>vec![("a","root",true,false)]
 };
 let mut bindings=Vec::new();let mut ledger=Vec::new();let mut parts=Vec::new();
 for (i,(id,which,bound,finalized)) in spec.into_iter().enumerate(){
  let call=ToolCall::new(id,"fixture-tool",json!({"argument":id}));
  if bound{
   let mut b=WorkflowToolResultBinding::new(call.clone());b.message_id=Uuid::from_u128(9000+i as u128);b.part_id=Uuid::from_u128(9100+i as u128);
   bindings.push(b);parts.push(ContentPart::ToolCall{call:call.clone()});
  }
  let payload=effect(id,73,c.shape);
  ledger.push((call,which,payload,finalized));
 }
 let mut u=CanonicalMessage::text(MessageRole::User,"synthetic fixture prompt");
 u.id=Uuid::from_u128(7650);u.parts[0].part_id=Uuid::from_u128(7651);
 let mut history=public_rows(c.n,4);
 for (i,m) in history.iter_mut().enumerate(){m.id=Uuid::from_u128(1000000+i as u128);m.parts[0].part_id=Uuid::from_u128(2000000+i as u128);}
 history.push(u);
 if !parts.is_empty(){
  let mut m=CanonicalMessage::new(MessageRole::Assistant,parts);m.id=Uuid::from_u128(7700);
  for (i,p) in m.parts.iter_mut().enumerate(){p.part_id=Uuid::from_u128(7800+i as u128);}
  history.push(m);
 }
 let report=(c.mode=="context").then(||{
  let mut r=HistoryCompactionReport::unchanged(0,Some("typed context marker".into()));r.changed=true;r.output_messages=history.len();r
 });
 push(&mut records,JournalEntry::HistoryMutated(HistoryMutated{
  previous_revision:0,new_revision:1,mutation:if c.mode=="no-owner-settle"{HistoryMutationKind::Append}else{HistoryMutationKind::Checkpoint},
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
fn append(seq:u64,revision:u64,m:CanonicalMessage)->JournalRecord{
 record(seq,JournalEntry::HistoryMutated(HistoryMutated{previous_revision:revision,new_revision:revision+1,
  mutation:HistoryMutationKind::Append,messages:vec![m],compaction:None,tool_results:vec![]}),"root")
}
fn late_row()->CanonicalMessage{
 let mut m=CanonicalMessage::text(MessageRole::User,"actual row appended after checkpoint");
 m.id=Uuid::from_u128(8109);m.parts[0].part_id=Uuid::from_u128(8110);m
}
fn final_fact(seq:u64,v:&ToolResult)->JournalRecord{
 let mut v=v.clone();
 v.output="final receipt semantics".into();v.metadata["final"]=json!(true);
 record(seq,JournalEntry::ToolResultRecorded(ToolResultRecorded{result:v}),"root")
}
fn one(c:Case){
 let fx=fixture(c);proof::configure(false,None);
 let (mut base,_,_,mut sequence,physical)=strict_seed(&fx.records);
 assert_eq!(base.history(),fx.history);
 let mode=c.mode;
 let is_settle=c.mode.starts_with("settle")||matches!(mode,"no-owner-settle"|"context");
 let collision=mode.starts_with("collision-")||matches!(mode,"both-conflicts"|"none-followup");
 let known=matches!(mode,"known-after"|"settle-late");
 let private=mode.contains("before")||matches!(mode,"none-followup"|"lost-final"|"saturated");
 let mut extra=Vec::<JournalRecord>::new();
 let false_scope=matches!(mode,"unbound-final"|"no-owner-settle"|"bad-seq"|"duplicate-final"|"lost-final");
 let origin=digest(&base.history());
 let mut expected_pre=Vec::new();let mut observed=Vec::new();let mut out_states=Vec::new();let mut summary=None;
 let b_a=fx.bindings.first();
 let a=fx.ledger.first().unwrap().2.clone();
 let candidates=proof::pending_ids(&base,&settle(sequence,c.status));
 let known_call=if mode=="settle-late"{
  Some(candidates.iter().filter(|id|fx.bindings.iter().any(|b|&b.call_id==*id)).nth(1).unwrap().clone())
 }else if known{Some(a.call_id.clone())}else{None};
 // Add trace-only IDs before cloning both arms: ordinary strict facts with no duplicate active id.
 if let Some(ref picked)=known_call{
  let b=fx.bindings.iter().find(|b|b.call_id==*picked).unwrap();
  let mut trace=b.message(effect(picked,0,c.shape));
  trace.parts[0].payload=ContentPart::Text{text:"already-known incompatible trace part".into()};
  let r=record(sequence,JournalEntry::ModelRequestRecorded(ModelRequestRecorded{
   exchange_id:Uuid::from_u128(8700),origin:ModelCallOrigin::Direct,owner:OperationOwner::Workflow,
   request:CanonicalModelRequest::new(ModelRef::new("fixture","fixture"),vec![trace])
  }),"root");
  base.apply_sequenced(SESSION,&r,&mut sequence).unwrap();extra.push(r);
 }
 assert_eq!(origin,digest(&base.history()));
 let original_rev=base.history_revision();
 // Keeping the original alive gives genuine shared COW indexes before additional normal facts.
 for changed in [false,true]{
  let mut state=base.clone();let mut seq=sequence;let mut extras=extra.clone();
  assert!(proof::same_tool_nodes(&state,&base));
  let shared=matches!(mode,"final-shared"|"settle-shared");
  if mode=="final-tail"{
   // The same valid checkpoint with the same bindings forces a new exact
   // active index without mutating the shared tool map or moving insertion off-tail.
   let rev=state.history_revision();
   let r=record(seq,JournalEntry::HistoryMutated(HistoryMutated{
    previous_revision:rev,new_revision:rev+1,mutation:HistoryMutationKind::Checkpoint,
    messages:state.history().to_vec(),compaction:None,tool_results:fx.bindings.clone()
   }),"root");
   state.apply_sequenced(SESSION,&r,&mut seq).unwrap();extras.push(r);
  }else if !shared && !matches!(mode,"no-owner-settle"|"lost-final"){
   let mut m=late_row();
   if collision{
    let b=b_a.unwrap();
    if mode.ends_with("message") || mode=="both-conflicts"{m.id=b.message_id;}
    if !mode.ends_with("message") || mode=="both-conflicts"{m.parts[0].part_id=b.part_id;}
   }
   let r=append(seq,state.history_revision(),m);
   state.apply_sequenced(SESSION,&r,&mut seq).unwrap();extras.push(r);
  }
  if mode.starts_with("collision-before"){proof::reorder_before_capture_for_private_case(&mut state);}
  if mode=="lost-final"{proof::truncate_for_private_loss(&mut state);}
  if mode=="duplicate-final"{
   let r=final_fact(seq,&a);state.apply_sequenced(SESSION,&r,&mut seq).unwrap();extras.push(r);
  }
  if mode=="saturated"{proof::set_revision_for_boundary_control(&mut state,u64::MAX);}
  let mut result_pick=a.clone();
  if mode=="none-followup"{
   let r=final_fact(seq,&a);
   assert!(state.apply_sequenced(SESSION,&r,&mut seq).unwrap_err().to_string().contains("active history contains duplicate part"));
   assert!(!proof::active_valid(&state));
   result_pick=fx.ledger[1].2.clone();
  }
  let mut target=if is_settle{settle(seq,c.status)}else{final_fact(seq,&result_pick)};
  if mode=="bad-seq"{target.session_seq+=1;}
  if mode=="none-followup"{target.record_id=Uuid::from_u128(999000);}
  let target:JournalRecord=serde_json::from_slice(&serde_json::to_vec(&target).unwrap()).unwrap();
  let before_revision=state.history_revision();
  let before_rows=state.history().len();
  let before_unique=proof::is_unique(&state);
  let before_present=proof::active_valid(&state);
  if !shared && !matches!(mode,"none-followup"|"lost-final"|"no-owner-settle"){assert!(before_unique);}
  if shared{assert!(!before_unique && before_present);}
  if mode=="none-followup"{assert!(!before_present);}
  let bind_ids=fx.bindings.iter().map(|b|b.call_id.clone()).collect::<Vec<_>>();
  let expected_order=if is_settle{
   if mode=="no-owner-settle"{vec![]}else{let order=proof::pending_ids(&state,&target);assert_eq!(order,candidates);order}
  }else if false_scope{vec![]}else{vec![result_pick.call_id.clone()]};
  let want=if mode=="settle-late"{
    let k=expected_order.iter().position(|id|Some(id)==known_call.as_ref()).unwrap();
    expected_order[..=k].to_vec()
  }else{expected_order.clone()};
  let captures=want.iter().filter(|id|bind_ids.contains(*id)).cloned().collect::<Vec<_>>();
  let before_history=digest(&state.history());
  expected_pre.push(before_history.clone());
  let error_expected=collision||known||matches!(mode,"duplicate-final"|"lost-final"|"bad-seq");
  let mut md=ModelContextProjection::default();let mut usage=UsageProjection::default();
  for fact in fx.records.iter().chain(&extras){md.apply(fact);usage.apply(fact);}
  if mode=="context"{assert_eq!(md.snapshot(),[ModelContextObservation::HistoryCompacted]);}
  let mut next=seq;
  proof::configure(changed,Some(OBS));meter::start();
  let got=state.apply_sequenced(SESSION,&target,&mut next);
  let receipt=meter::take();proof::configure(false,None);
  assert_eq!(got.is_err(),error_expected);
  if got.is_ok(){md.apply(&target);usage.apply(&target);}
  assert_eq!(state.history_revision(),before_revision.saturating_add(captures.len() as u64));
  assert_eq!(state.history().len(),before_rows+captures.len());
  assert_eq!(next,seq+u64::from(!error_expected));
  let error=got.err().map(|x|x.to_string());
  if let Some(ref e)=error{
   let check=if mode=="duplicate-final"{"duplicate tool result".to_owned()}else if mode=="lost-final"{"checkpoint history suffix was lost".into()}
     else if mode=="bad-seq"{"journal sequence mismatch".into()}
     else if known{"changed after it was recorded".into()}
     else if mode.ends_with("message") || mode=="both-conflicts"{format!("duplicate message id {}",b_a.unwrap().message_id)}
     else {
      let old_id=if mode=="collision-before-part"{b_a.unwrap().message_id}else{late_row().id};
      format!("duplicate part id {} at message {}",b_a.unwrap().part_id,old_id)
     };
   assert!(e.contains(&check),"{mode}: missing {check}; got {e}");
  }
  if collision{assert!(!proof::active_valid(&state));}
  if known{assert!(proof::active_valid(&state));}
  if mode!="lost-final"{proof::check_exact_current_memberships(&state);}
  if !is_settle && !false_scope && !error_expected{
   let b=fx.bindings.iter().find(|x|x.call_id==result_pick.call_id).unwrap();
   let JournalEntry::ToolResultRecorded(r)=&target.entry else{unreachable!()};
   let row=state.history().iter().find(|m|m.id==b.message_id).unwrap();
   assert_eq!(*row,b.message(r.result.clone()));
  }
  if is_settle && !error_expected && c.status=="canceled"{
   let interrupts=state.interrupted_turns();
   assert_eq!(interrupts.len(),1);assert_eq!(interrupts[0].after_message_id,state.history().last().unwrap().id);
  }else{assert!(state.interrupted_turns().is_empty());}
  if !error_expected && !captures.is_empty(){
    // Follow the optimized proof by a real append and replacement, both
    // post-measurement, and independently compare exact index memberships.
    let mut probe=state.clone();let mut follow_seq=next;
    let mut m=late_row();m.id=Uuid::from_u128(99901);m.parts[0].part_id=Uuid::from_u128(99902);
    if probe.history_revision()!=u64::MAX{
      let mut r=append(follow_seq,probe.history_revision(),m);r.thread_id=None;r.turn_id=None;
      probe.apply_sequenced(SESSION,&r,&mut follow_seq).unwrap();proof::check_exact_current_memberships(&probe);
      let rev=probe.history_revision();
      let mut r=record(follow_seq,JournalEntry::HistoryMutated(HistoryMutated{
       previous_revision:rev,new_revision:rev+1,mutation:HistoryMutationKind::Replace,
       messages:vec![],compaction:None,tool_results:vec![]}),"root");
      r.turn_id=None;r.thread_id=None;
      probe.apply_sequenced(SESSION,&r,&mut follow_seq).unwrap();proof::check_exact_current_memberships(&probe);
    }
  }
  assert_eq!(origin,digest(&base.history()));assert_eq!(base.history_revision(),original_rev);
  let info=json!({"before_rows":before_rows,"rows":state.history().len(),"before_revision":before_revision,"revision":state.history_revision(),
    "before_unique":before_unique,"before_present":before_present,"after_present":proof::active_valid(&state),"source_seq":seq,"next_seq":next,
    "history_sha256":digest(&state.history()),"known_rows":proof::known_rows(&state),"error":error,"context":md.snapshot(),
    "interruptions":state.interrupted_turns(),"usage":usage.snapshot(SESSION),"order":want,"captured":captures,"private_adversarial":private});
  if let Some(old)=&summary{assert_eq!(old,&info)}else{summary=Some(info);}
  out_states.push(state);observed.push(receipt);
 }
 assert_eq!(expected_pre[0],expected_pre[1]);proof::compare(&out_states[0],&out_states[1]);
 println!("{}",json!({"n":c.n,"mode":c.mode,"shape":c.shape,"status":c.status,"physical_bytes":physical,
  "state":summary.unwrap(),"meters":{"stock":observed.remove(0),"candidate":observed.remove(0)}}));
}
fn main(){
 let run=std::env::args().nth(1).expect("full or controls");
 if run=="full"{
  for n in [5000,50000]{for (mode,status) in [("final-middle","success"),("final-tail","success"),("final-shared","success"),("settle-unique","canceled"),("settle-shared","canceled")]{
   one(Case{n,mode,shape:"plain",status});
  }}
 }else{
  assert_eq!(run,"controls");
  for (mode,status) in [("final-middle","success"),("final-tail","success"),("final-shared","success"),("settle-unique","canceled"),("settle-shared","canceled"),
   ("unbound-final","success"),("no-owner-settle","failed"),("none-followup","success"),("collision-after-part","success"),("collision-before-part","success"),
   ("collision-after-message","success"),("collision-before-message","success"),("both-conflicts","success"),("known-after","success"),
   ("settle-late","failed"),("duplicate-final","success"),("lost-final","success"),("bad-seq","success"),("saturated","success"),("context","canceled"),("settle-nested","canceled")]{
   for shape in ["plain","mixed"]{one(Case{n:17,mode,shape,status});}
  }
  one(Case{n:0,mode:"final-middle",shape:"plain",status:"success"});
  edge::run();
 }
}
