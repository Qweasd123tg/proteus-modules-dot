// Test bridge only. Exposes observation, not substituted validation logic.
use super::*;
use proteus_contracts::domain::ToolResult;
use std::cell::Cell;
#[derive(Clone,Copy)]
pub struct Observer{
 pub begin_pending:fn(),
 pub after_map_clone:fn(),
 pub end_pending_prepare:fn(),
 pub visit:fn(&ToolResult,&ToolResult),
 pub after_capture:fn(&ToolResult,Option<&CanonicalMessage>),
 pub finish_pending:fn(),
}
thread_local!{
 static CANDIDATE:Cell<bool>=const{Cell::new(false)};
 static OBS:Cell<Option<Observer>>=const{Cell::new(None)};
}
pub fn configure(candidate:bool,o:Option<Observer>){CANDIDATE.set(candidate);OBS.set(o);}
pub(super) fn is_candidate()->bool{CANDIDATE.get()}
pub(super) struct Guard;
impl Drop for Guard{fn drop(&mut self){if let Some(o)=OBS.get(){(o.finish_pending)();}}}
pub(super) fn begin_pending()->Guard{if let Some(o)=OBS.get(){(o.begin_pending)();}Guard}
pub(super) fn after_map_clone(){if let Some(o)=OBS.get(){(o.after_map_clone)();}}
pub(super) fn end_pending_prepare(){if let Some(o)=OBS.get(){(o.end_pending_prepare)();}}
pub(super) fn visit(r:&ToolResult,original:&ToolResult){if let Some(o)=OBS.get(){(o.visit)(r,original);}}
pub(super) fn after_capture(r:&ToolResult, row:Option<&CanonicalMessage>){if let Some(o)=OBS.get(){(o.after_capture)(r,row);}}
pub fn pending_ids(s:&JournalValidationState,r:&JournalRecord)->Vec<String>{
 let cloned=s.tool_calls.clone();
 let collect=|m:&SharedMap<CallId,Arc<ToolLifecycle>>|m.values()
    .filter(|c|!c.result&&c.owner.is_some_and(|x|x.thread_id==r.thread_id&&x.turn_id==r.turn_id))
    .filter_map(|c|c.effect.as_ref().map(|e|e.call_id.clone())).collect::<Vec<_>>();
 let actual=collect(&cloned);
 assert_eq!(actual,collect(&s.tool_calls));
 for k in &actual{
  assert!(Arc::ptr_eq(cloned.get(k).unwrap(),s.tool_calls.get(k).unwrap()));
 }
 actual
}
pub fn set_revision_for_boundary_control(s:&mut JournalValidationState,n:u64){s.history_revision=n;}
pub fn verify_ledger_shared(old:&JournalValidationState,new:&JournalValidationState){
 assert_eq!(old.tool_calls.len(),new.tool_calls.len());
 for (k,v) in &old.tool_calls{
   let w=new.tool_calls.get(k).unwrap();assert!(Arc::ptr_eq(v,w));
 }
}
pub fn compare(a:&JournalValidationState,b:&JournalValidationState){
 assert_eq!(a.history,b.history);
 assert_eq!(a.history_revision,b.history_revision);
 assert_eq!(a.last_history_turn(),b.last_history_turn());
 assert_eq!(a.interrupted_turns,b.interrupted_turns);
 assert_eq!(a.capture_owner,b.capture_owner);
 assert_eq!(format!("{:?}",a.capture),format!("{:?}",b.capture));
 assert_eq!(a.active_ids.is_some(),b.active_ids.is_some());
 assert_eq!(a.known_parts,b.known_parts);
 assert_eq!(a.record_ids,b.record_ids);
 assert_eq!(a.opened_turns,b.opened_turns);
 assert_eq!(a.execution_turns,b.execution_turns);
 assert_eq!(a.detached_executions,b.detached_executions);
 assert_eq!(a.settled_turns,b.settled_turns);
 assert_eq!(a.model_requests,b.model_requests);
 assert_eq!(a.model_responses,b.model_responses);
 assert_eq!(format!("{:?}",a.context),format!("{:?}",b.context));
 verify_ledger_shared(a,b);
}
pub fn capture_open(s:&JournalValidationState)->bool{s.capture_owner.is_some()}
pub fn active_valid(s:&JournalValidationState)->bool{s.active_ids.is_some()}
pub fn known_rows(s:&JournalValidationState)->usize{s.history.iter().flat_map(|m|&m.parts)
 .filter(|p|s.known_parts.get(&p.part_id).is_some_and(|id|id.matches(p))).count()}
pub fn final_ledger(s:&JournalValidationState,id:&str)->(bool,bool){
 let life=s.tool_calls.get(id).unwrap();(life.result,life.effect.is_some())
}
