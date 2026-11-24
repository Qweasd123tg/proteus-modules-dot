"""Generate source-pinned exact Tokio and Workflow capture mutation proof."""
import hashlib,json,sys
from pathlib import Path
HERE=Path(__file__).resolve().parent
C='crates/proteus-core/src/core/'
R=C+'session_store/remote/'
CHECK=C+'runtime/checkpoint.rs'
MOD=R+'mod.rs'
WR=R+'writer.rs'
DISPLAY=R+'snapshot/display_records.rs'
MODEL=C+'model_context.rs'
FIX='crates/proteus-core/examples/session_index_fixture.rs'
PATHS=[CHECK,MOD,WR,DISPLAY,MODEL,FIX,'crates/proteus-session-semantics/src/journal/history_capture.rs','crates/proteus-contracts/src/contracts/tool_execution_recorder.rs','crates/proteus-contracts/src/contracts/workflow_checkpoint.rs','crates/proteus-contracts/src/model_standard/content_part.rs','crates/proteus-contracts/src/domain/context.rs','crates/proteus-contracts/src/domain/hosted_tool.rs']
def section(s,a,b=None):
 i=s.index(a);return s[i:] if b is None else s[i:s.index(b,i+len(a))]
def method(s,sig):
 i=s.index(sig);return s[i:s.index('\n    }',i)+6]+'\n'
def blob(b):return hashlib.sha1(b'blob '+str(len(b)).encode()+b'\0'+b).hexdigest()
def generate(src,changed,meter,out):
 pins=json.loads((HERE/'route-pins.json').read_text())
 def r(p):
  b=(src/p).read_bytes();assert blob(b)==pins[p],p;return b.decode()
 def w(p,s):
  q=out/p;q.parent.mkdir(parents=True,exist_ok=True);q.write_text(s)
 for p in PATHS:r(p)
 new=changed.read_bytes();assert blob(new)==pins['candidate-checkpoint']
 for name,s in [('stock',r(CHECK)),('candidate',new.decode())]:
  lead=section(s,'use std::sync::Arc','use super::{')
  helper='' if name=='stock' else section(s,'fn in_memory_history_changed','/// Per-invocation binding.')
  st=section(s,'/// Per-invocation binding.','impl TurnHistoryRecorder').replace('pub(super)','pub(crate)')
  settle=method(s,'    pub(super) async fn settle_in_memory_effects').replace('pub(super)','pub(crate)').replace('        let mut history = self.history.lock().await;','        let mut history = self.history.lock().await;\n        let _meter=crate::meter::enter();',1)
  trait=section(s,'#[async_trait]\nimpl ToolExecutionRecorder')
  assert trait.count('            let mut history = self.history.lock().await;')==1
  trait=trait.replace('            let mut history = self.history.lock().await;','            let mut history = self.history.lock().await;\n            let _meter=crate::meter::enter();',1)
  w(name+'.rs',lead+'use crate::SteeringModel;\n'+helper+st+'impl TurnHistoryRecorder {\n'+settle+'}\n'+trait)
 rem=r(MOD);wr=r(WR);d=r(DISPLAY)
 st='''use crate::*;
use anyhow::{anyhow,bail,ensure};
use writer::RemoteWriter;
'''+section(rem,'pub type StorageService','impl std::fmt::Debug')+'''
impl RemoteSessionStore {
'''+section(rem,'    pub fn open(','    pub fn session_dir(')+''' }
mod stage_layout {
use std::{collections::HashMap,fs::File,io::BufWriter};
use proteus_contracts::domain::{TurnId,ThreadId,PartId};
'''+section(d,'type RootBindings','impl CausalStage')+section(d,'pub(in crate::core::session_store::remote) struct DisplayRecordWriter','impl DisplayRecordWriter').replace('pub(in crate::core::session_store::remote)','pub(super)')+''' }
mod writer {
 use super::*;
 use super::stage_layout::DisplayRecordWriter;
'''+section(wr,'struct DisplayCapture','fn lease_lost')+section(wr,'pub(super) struct RemoteWriter','    async fn acquire(')+''' }
}
'''
 w('store.rs',st)
 w('meter.rs',meter.read_text())
 w('controls.rs',meter.with_name('controls.rs').read_text())
 w('core.rs','pub(crate) use crate::store::RemoteSessionStore as SessionStore;pub(crate) mod session_journal{pub(crate) use proteus_session_semantics::journal::history_capture;}pub(crate) mod model_context{pub(crate) use proteus_session_semantics::ModelContextState;}')
 w('main.rs',(HERE/'route.rs').read_text()+'\n'+(HERE/'adapter.rs').read_text()+'''
pub(crate) fn public_rows(rows:usize,repeats:usize)->Vec<CanonicalMessage>{
'''+section(r(FIX),'    let messages: Vec<_> = (0..rows)','    let thread_id = new_thread_id();')+'messages\n}\n')
if __name__=='__main__':generate(*(Path(p) for p in sys.argv[1:]))
