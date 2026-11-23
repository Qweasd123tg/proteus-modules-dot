from pathlib import Path
from argparse import ArgumentParser
from hashlib import sha1, sha256
from tempfile import TemporaryDirectory
from subprocess import run

p=ArgumentParser()
p.add_argument("--stock", type=Path, required=True)
p.add_argument("--rustc", type=Path, required=True)
p.add_argument("--work-dir", type=Path, required=True)
args=p.parse_args()
stock=args.stock.read_bytes()
patch=Path(__file__).with_name("source.patch").read_bytes()
assert sha256(patch).hexdigest()=="e22efd547bfb48d34d48aece04c02e7b29a6c2e1eeb65a82e7aaf4dad0f22a18"
def blob(data):
    return sha1(f"blob {len(data)}\0".encode()+data).hexdigest()
assert blob(stock)=="be45f061bc36b309d70de80855f850b0a7dceb29"
parts=patch.splitlines(keepends=True)[3:]
prior=b"".join(l[1:] for l in parts if l.startswith((b" ",b"-")))
after=b"".join(l[1:] for l in parts if l.startswith((b" ",b"+")))
assert stock.count(prior)==1
candidate=stock.replace(prior,after,1)
assert blob(candidate)=="2a40f83317b1edf2b6bc6b04d28346eddfab46bf"
assert candidate.count(after)==1 and candidate.replace(after,prior,1)==stock
pre=r"""
use std::{cell::{Cell,RefCell},collections::HashMap};
mod proteus_contracts {
 pub mod domain {#[derive(Clone,Debug,PartialEq,Eq)] pub struct ToolCall {pub id:String, pub label:u8}}
 pub mod model_standard {pub enum ContentPart { ToolCall {call:super::domain::ToolCall}, Other }}
}
use proteus_contracts::{domain::ToolCall,model_standard::ContentPart};
#[derive(Clone,Debug,PartialEq,Eq)]
struct WorkflowToolResultBinding(ToolCall);
impl WorkflowToolResultBinding {fn new(c:ToolCall)->Self{Self(c)}}
struct Part { payload:ContentPart }
struct Message {parts:Vec<Part>}
struct TracedRows { rows:Vec<Message>, visits:Cell<usize> }
impl TracedRows {
 fn iter(&self)->impl Iterator<Item=&Message>{
  self.rows.iter().inspect(|_| self.visits.set(self.visits.get()+1))
 }
}
struct Pending {target:Option<String>}
#[derive(Debug,PartialEq,Eq)]
struct WorkflowHistoryCheckpoint {history:u16,tool_results:Vec<WorkflowToolResultBinding>,preparation_target:Option<String>}
struct WorkflowModuleHostMut<'a> {state:&'a RefCell<Vec<WorkflowHistoryCheckpoint>>, fail:bool}
type ProcessModuleError=&'static str;
struct TurnScaffold {persistent_messages:TracedRows, result_bindings:HashMap<String,WorkflowToolResultBinding>, pending_preparation:Option<Pending>, phase:u8}
impl TurnScaffold {
 fn history_update(&self)->Result<Option<u16>,ProcessModuleError>{match self.phase{1=>Ok(None),2=>Err("history"),x=>Ok(Some(x as u16))}}
 fn accept_checkpoint(&mut self, h:&WorkflowModuleHostMut<'_>, c:WorkflowHistoryCheckpoint)->Result<(),ProcessModuleError>{
   h.state.borrow_mut().push(c);
   if h.fail{Err("ack")}else{Ok(())}
 }
}
"""
def x(p,ns):
 s=p.decode().split('    pub(crate) fn checkpoint(',1)[1].split('    pub(crate) fn apply_compaction_report(',1)[0]
 return 'mod '+ns+' {use super::*; pub(super) fn checkpoint('+s.replace('&mut self,','this: &mut TurnScaffold,').replace('self','this')+'}\n'
test=r"""
#[test]
fn compare_trace_and_map() {
 let mut seed=751863_u64;
 let mut next=|m:usize| {seed=seed.wrapping_mul(6364136223846793005).wrapping_add(1);((seed>>32) as usize)%m};
 for _ in 0..7000 {
  let data=(0..next(45)).map(|_|(0..next(15)).map(|_|next(33)).collect::<Vec<_>>()).collect::<Vec<_>>();
  let calls=(0..next(9)).map(|j|ToolCall{id:next(29).to_string(),label:j as u8}).collect::<Vec<_>>();
  let active=(0..next(8)).map(|j|ToolCall{id:next(29).to_string(),label:(200+j) as u8}).collect::<Vec<_>>();
  let phase=next(6) as u8;let fail=next(4)==0;
  let mk=||TurnScaffold{persistent_messages:TracedRows{rows:data.iter().map(|seq|Message{parts:seq.iter().map(|n|Part{
   payload:if n%2==0{ContentPart::Other}else{ContentPart::ToolCall{call:ToolCall{id:n.to_string(),label:200}}}
  }).collect()}).collect(),visits:Cell::new(0)},result_bindings:active.iter().map(|c|(c.id.clone(),WorkflowToolResultBinding(c.clone()))).collect(),
  pending_preparation:(phase%2==0).then(||Pending{target:Some("inert".into())}),phase};
  let(mut a,mut b)=(mk(),mk());
  let (ta,tb)=(RefCell::new(vec![]),RefCell::new(vec![]));
  let ra=stock::checkpoint(&mut a,&WorkflowModuleHostMut{state:&ta,fail},&calls);
  let rb=candidate::checkpoint(&mut b,&WorkflowModuleHostMut{state:&tb,fail},&calls);
  assert_eq!(ra,rb);
  assert_eq!(a.result_bindings,b.result_bindings);
  assert_eq!(ta.into_inner(),tb.into_inner());
 }
}
"""
test += r"""
#[test]
fn empty_map_visits_and_insertion_order() {
 let mk=||TurnScaffold {
  persistent_messages:TracedRows{rows:(0..125000).map(|_|Message{parts:vec![Part{payload:ContentPart::Other}]}).collect(),visits:Cell::new(0)},
  result_bindings:HashMap::new(),pending_preparation:None,phase:0
 };
 let (mut a,mut b)=(mk(),mk());
 let (ta,tb)=(RefCell::new(vec![]),RefCell::new(vec![]));
 let ha=WorkflowModuleHostMut{state:&ta,fail:false};let hb=WorkflowModuleHostMut{state:&tb,fail:false};
 stock::checkpoint(&mut a,&ha,&[]).unwrap();
 candidate::checkpoint(&mut b,&hb,&[]).unwrap();
 assert_eq!(a.persistent_messages.visits.get(),125000);
 assert_eq!(b.persistent_messages.visits.get(),0);
 assert_eq!(*ta.borrow(),*tb.borrow());
 // Current calls must initialize the map before any shortcut.
 let call=ToolCall{id:"test".into(), label:3};
 a.persistent_messages.rows.truncate(1);b.persistent_messages.rows.truncate(1);
 for m in [&mut a,&mut b] {m.persistent_messages.rows[0].parts=vec![Part{payload:ContentPart::ToolCall{call:call.clone()}}];}
 stock::checkpoint(&mut a,&ha,std::slice::from_ref(&call)).unwrap();
 candidate::checkpoint(&mut b,&hb,std::slice::from_ref(&call)).unwrap();
 assert_eq!(*ta.borrow(),*tb.borrow());
 assert_eq!(tb.borrow()[1].tool_results,vec![WorkflowToolResultBinding(call)]);
}
"""
assert "rustc 1.95.0" in __import__("subprocess").check_output([args.rustc,"--version"],text=True)
with TemporaryDirectory(prefix="r224-lift-",dir=args.work_dir) as d:
 root=Path(d)
 source=root/"lift.rs"
 source.write_text(pre+x(stock,'stock')+x(candidate,'candidate')+test)
 for mode,opt in [("debug",[]),("optimized",["-O"])]:
  path=root/mode
  run([args.rustc,"--edition=2024","-D","warnings","--test",*opt,source,"-o",path],check=True)
  run([path],check=True)
