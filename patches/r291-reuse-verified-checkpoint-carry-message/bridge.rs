use std::cell::Cell;
use super::HistoryCapture;
use proteus_contracts::{contracts::WorkflowToolResultBinding,model_standard::CanonicalMessage};
#[derive(Clone,Copy)]
pub struct Observer{
 pub begin_carry:fn(),pub prepared:fn(&CanonicalMessage),
 pub inserted:fn(&CanonicalMessage),pub finish_carry:fn(),
}
thread_local!{
 static CAND:Cell<bool>=const{Cell::new(false)};
 static OBS:Cell<Option<Observer>>=const{Cell::new(None)};
 static CARRY:Cell<bool>=const{Cell::new(false)};
}
pub fn configure(candidate:bool,probe:Option<Observer>){CAND.set(candidate);OBS.set(probe);assert!(!CARRY.get());}
pub(super) fn candidate()->bool{CAND.get()}
pub(super) struct CarryGuard;
impl Drop for CarryGuard{
 fn drop(&mut self){
  if let Some(o)=OBS.get(){assert!(CARRY.replace(false));(o.finish_carry)();}
 }
}
pub(super) fn begin_carry()->CarryGuard{
 if let Some(o)=OBS.get(){assert!(!CARRY.replace(true));(o.begin_carry)();}
 CarryGuard
}
pub(super) fn prepared(m:&CanonicalMessage){if let Some(o)=OBS.get(){assert!(CARRY.get());(o.prepared)(m);}}
pub(super) fn inserted(m:&CanonicalMessage){if let Some(o)=OBS.get(){if CARRY.get(){(o.inserted)(m);}}}
pub fn rebase(c:&HistoryCapture,current:&[CanonicalMessage],proposed:&[CanonicalMessage],bindings:&[WorkflowToolResultBinding],compacted:bool)
 ->anyhow::Result<(HistoryCapture,Vec<CanonicalMessage>)>{c.rebase(current,proposed,bindings,compacted)}
