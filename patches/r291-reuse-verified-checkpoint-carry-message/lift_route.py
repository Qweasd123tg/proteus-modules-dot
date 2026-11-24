"""Lift strict actual semantics + exact no-store live checkpoint caller."""
import hashlib,json,sys,shutil
from pathlib import Path
HERE=Path(__file__).resolve().parent
C='crates/proteus-session-semantics/src/journal/'
CAP=C+'history_capture.rs'
R='crates/proteus-core/src/core/runtime/'
CHECK=R+'checkpoint.rs'
HIST=R+'history.rs'
USER=R+'history/compacted_user.rs'
WEAVE=R+'steering/weave.rs'
STEER=R+'steering.rs'
FILES=[CAP,C+'mod.rs',C+'projection.rs',C+'projection/facts.rs',C+'projection/sequence.rs',CHECK,HIST,USER,WEAVE,STEER,
       'crates/proteus-contracts/src/contracts/workflow_checkpoint.rs','crates/proteus-contracts/src/contracts/workflow_failure.rs']
def oid(b):return hashlib.sha1(b'blob '+str(len(b)).encode()+b'\0'+b).hexdigest()
def cut(s,a,b=None):
 i=s.index(a);return s[i:] if b is None else s[i:s.index(b,i+len(a))]
def method(s,a):
 i=s.index(a);return s[i:s.index('\n    }',i)+6]+'\n'
def rep(s,a,b):assert s.count(a)==1,a;return s.replace(a,b,1)
def generate(src,candidate,meter,out):
 pins=json.loads((HERE/'route-pins.json').read_text())
 def r(p):
  v=(src/p).read_bytes();assert oid(v)==pins[p],p
  return v.decode()
 for each in FILES:r(each)
 new=candidate.read_bytes();assert oid(new)==pins['candidate-history_capture']
 def cr(name):
  d=out/'crates'/name;o=src/'crates'/name
  if d.is_symlink():
   assert name=='proteus-contracts'
   for p in o.rglob('*'):
    if p.is_file():assert (d/p.relative_to(o)).read_bytes()==p.read_bytes(),p
  else:shutil.copytree(o,d,dirs_exist_ok=True)
  return d
 cr('proteus-contracts');sem=cr('proteus-session-semantics')
 def w(p,s,root=out):
  f=root/p;f.parent.mkdir(parents=True,exist_ok=True);f.write_text(s)
 s=r(CAP);c=new.decode()
 stock=method(s,'    pub fn rebase(').replace('pub fn rebase(','fn rebase_stock(',1)
 stock=rep(stock,'''            ensure!(
                &binding.message(result.clone()) == message,
                "checkpoint result suffix was changed"
            );''','''            let _carry_probe=crate::journal::proof::begin_carry();
            let prepared=binding.message(result.clone());
            crate::journal::proof::prepared(&prepared);
            let equal=&prepared==message;
            drop(prepared);
            ensure!(equal, "checkpoint result suffix was changed");''')
 cand=method(c,'    pub fn rebase(').replace('pub fn rebase(','fn rebase_candidate(',1)
 cand=rep(cand,'            let prepared = binding.message(result.clone());','            let _carry_probe=crate::journal::proof::begin_carry();\n            let prepared = binding.message(result.clone());\n            crate::journal::proof::prepared(&prepared);')
 d=method(s,'    pub fn record_at(').replace('pub fn record_at(','fn record_at_stock(',1)
 d=rep(d,'        history.insert(position, binding.message(result.clone()));','        history.insert(position, binding.message(result.clone()));\n        crate::journal::proof::inserted(&history[position]);')
 e=method(c,'    pub fn record_at(').replace('pub fn record_at(','fn record_at_candidate(',1)
 f=method(c,'    fn record_message_at(')
 f=rep(f,'        history.insert(position, message(binding));','        history.insert(position, message(binding));\n        crate::journal::proof::inserted(&history[position]);')
 begin=cut(s,'use std::collections','    pub fn rebase(')
 middle=cut(s,'    pub fn new(','    pub fn record_at(')
 joined=begin+'''    pub fn rebase(
        &self,current:&[CanonicalMessage],proposed:&[CanonicalMessage],
        bindings:&[WorkflowToolResultBinding],compacted:bool
    )->Result<(Self,Vec<CanonicalMessage>)>{
        if crate::journal::proof::candidate(){self.rebase_candidate(current,proposed,bindings,compacted)}
        else{self.rebase_stock(current,proposed,bindings,compacted)}
    }
'''+stock+cand+middle+'''    pub fn record_at(&mut self,history:&mut Vec<CanonicalMessage>,result:&ToolResult)->Result<Option<usize>>{
       if crate::journal::proof::candidate(){self.record_at_candidate(history,result)}
       else{self.record_at_stock(history,result)}
    }
'''+d+e+f+'}\n#[cfg(test)]\nmod tests;\n'
 w('src/journal/history_capture.rs',joined,sem)
 w('src/journal/mod.rs',r(C+'mod.rs')+'\npub mod proof;\n',sem)
 w('src/journal/proof.rs',(HERE/'bridge.rs').read_text(),sem)
 k=r(CHECK)
 lead=cut(k,'use std::sync::Arc','use super::{').replace('        WorkflowHistoryRecorder,','        WorkflowHistoryRecorder,')
 lead+='use crate::steering::{SteeringModel,weave_deliveries_into_failed_history};\nuse crate::history_prepare::prepare_failed_history_update;\n'
 st=cut(k,'/// Per-invocation binding.','impl TurnHistoryRecorder').replace('pub(super)','pub(crate)')
 h=method(k,'    async fn normalize_progress(')
 ck=cut(k,'#[async_trait]\nimpl WorkflowHistoryRecorder','#[async_trait]\nimpl ToolExecutionRecorder')
 tools=cut(k,'#[async_trait]\nimpl ToolExecutionRecorder')
 w('live.rs',lead+st+'impl TurnHistoryRecorder {\n'+h+'}\n'+ck+tools)
 w('history_prepare/mod.rs',cut(r(HIST),'use std::collections::HashSet','impl super::AgentRuntime').replace(', TurnId',''))
 w('history_prepare/compacted_user.rs',cut(r(USER),'use std::collections','#[cfg(test)]'))
 weave=rep(cut(r(WEAVE),'use std::collections','#[cfg(test)]'),'use super::SteeringDeliveryRecord;\n','')
 st=cut(r(STEER),'#[derive(Debug, Clone)]\npub(crate) struct SteeringDeliveryRecord','/// Per-turn model decorator.')
 w('steering.rs',weave+'\n'+st+'''
pub(crate) struct SteeringModel;
impl SteeringModel {
    pub(crate) async fn delivery_records(&self)->Vec<SteeringDeliveryRecord>{panic!("steering is not present in the measured no-store route")}
}
''')
 w('main.rs',(HERE/'route.rs').read_text())
 w('meter.rs',meter.read_text())
 w('edge.rs',meter.with_name('edge.rs').read_text())
if __name__=='__main__':generate(*(Path(p) for p in sys.argv[1:]))
