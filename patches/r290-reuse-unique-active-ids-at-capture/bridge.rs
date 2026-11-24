// Test bridge only. Exposes observation, not substituted validation logic.
use super::*;
use std::cell::Cell;
#[derive(Clone,Copy)]
pub struct Observer{
 pub active_begin:fn(usize,usize,bool,bool),
 pub active_fast:fn(),
 pub rebuild_rows:fn(usize,usize),
 pub active_finish:fn(usize,bool,bool),
}
thread_local!{
 static CANDIDATE:Cell<bool>=const{Cell::new(false)};
 static OBS:Cell<Option<Observer>>=const{Cell::new(None)};
 static COUNTS:Cell<Option<(usize,usize,bool)>>=const{Cell::new(None)};
}
pub fn configure(candidate:bool,o:Option<Observer>){CANDIDATE.set(candidate);OBS.set(o);assert!(COUNTS.get().is_none());}
pub(super) fn is_candidate()->bool{CANDIDATE.get()}
pub(super) fn active_begin(i:usize,n:usize,u:bool,p:bool){
 if let Some(o)=OBS.get(){assert!(COUNTS.replace(Some((0,0,false))).is_none());(o.active_begin)(i,n,u,p);}
}
pub(super) fn active_fast(){
 if let Some(o)=OBS.get(){let (r,p,s)=COUNTS.get().unwrap();assert_eq!((r,p,s),(0,0,false));COUNTS.set(Some((r,p,true)));(o.active_fast)();}
}
pub(super) fn scan_row(){if let Some((r,p,s))=COUNTS.get(){COUNTS.set(Some((r+1,p,s)));}}
pub(super) fn scan_part(){if let Some((r,p,s))=COUNTS.get(){COUNTS.set(Some((r,p+1,s)));}}
pub(super) fn active_finish(i:usize,ok:bool)->bool{
 let Some(o)=OBS.get() else{return false};
 let (r,p,fast)=COUNTS.replace(None).unwrap();if !fast{(o.rebuild_rows)(r,p);}else{assert_eq!((r,p),(0,0));}(o.active_finish)(i,fast,ok);fast
}
pub fn is_unique(s:&JournalValidationState)->bool{s.active_ids.as_ref().is_some_and(|x|Arc::strong_count(x)==1 && Arc::weak_count(x)==0)}
pub fn same_tool_nodes(a:&JournalValidationState,b:&JournalValidationState)->bool{
 a.tool_calls.len()==b.tool_calls.len() && a.tool_calls.iter().all(|(k,v)|b.tool_calls.get(k).is_some_and(|other|Arc::ptr_eq(v,other)))
}
pub fn reorder_before_capture_for_private_case(s:&mut JournalValidationState){
    let h=Arc::make_mut(&mut s.history);let last=h.len()-1;h.swap(0,last);
}
pub fn check_exact_current_memberships(s:&JournalValidationState){
 if let Some((m,p))=s.proof_memberships(){
  let mut expected=s.history.iter().map(|m|m.id).collect::<Vec<_>>();
  let mut parts=s.history.iter().flat_map(|m|m.parts.iter().map(|p|p.part_id)).collect::<Vec<_>>();
  expected.sort_unstable();parts.sort_unstable();assert_eq!(m,expected);assert_eq!(p,parts);
 }
}
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
 assert_eq!(a.proof_memberships(),b.proof_memberships());
 assert_eq!(a.known_parts,b.known_parts);
 assert_eq!(a.record_ids,b.record_ids);
 assert_eq!(a.opened_turns,b.opened_turns);
 assert_eq!(a.execution_turns,b.execution_turns);
 assert_eq!(a.detached_executions,b.detached_executions);
 assert_eq!(a.settled_turns,b.settled_turns);
 assert_eq!(a.model_requests,b.model_requests);
 assert_eq!(a.model_responses,b.model_responses);
 assert_eq!(format!("{:?}",a.context),format!("{:?}",b.context));
 for (k,x) in &a.tool_calls{let y=b.tool_calls.get(k).unwrap();assert_eq!(format!("{x:?}"),format!("{y:?}"));}
}
pub fn capture_open(s:&JournalValidationState)->bool{s.capture_owner.is_some()}
pub fn active_valid(s:&JournalValidationState)->bool{s.active_ids.is_some()}
pub fn known_rows(s:&JournalValidationState)->usize{s.history.iter().flat_map(|m|&m.parts)
 .filter(|p|s.known_parts.get(&p.part_id).is_some_and(|id|id.matches(p))).count()}
pub fn final_ledger(s:&JournalValidationState,id:&str)->(bool,bool){
 let life=s.tool_calls.get(id).unwrap();(life.result,life.effect.is_some())
}

pub fn truncate_for_private_loss(s:&mut JournalValidationState){Arc::make_mut(&mut s.history).pop().unwrap();}

pub fn direct_check(s:&mut JournalValidationState,index:usize,candidate:bool)->Result<()>{s.observe_captured_active_ids(index,candidate)}
pub fn push_for_private_shape(s:&mut JournalValidationState,row:CanonicalMessage)->usize{
    let history=Arc::make_mut(&mut s.history);let index=history.len();history.push(row);index
}
pub fn weak_guard(s:&JournalValidationState)->impl Drop+use<> {Arc::downgrade(s.active_ids.as_ref().unwrap())}
