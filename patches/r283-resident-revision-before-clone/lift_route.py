"""Pin all source donors. Emit the two TurnConversation implementations, genuine
Tokio writer registry/history_revision and exact snapshot dispatch/drop methods.
No static stubs for any exercised runtime method. Fixture implements SessionStorage."""
import hashlib,json,sys
from pathlib import Path
here=Path(__file__).resolve().parent
c='crates/proteus-core/src/core/'
r=c+'session_store/remote/'
conv=c+'runtime/conversation.rs'
mod=r+'mod.rs'
writer=r+'writer.rs'
snap=r+'snapshot.rs'
display=r+'snapshot/display_records.rs'
MODEL=c+'model_context.rs'
ALIAS=c+'session_store.rs'
files=[conv,mod,writer,snap,display,MODEL,ALIAS,'crates/proteus-core/examples/session_index_fixture.rs','crates/proteus-contracts/src/contracts/session_storage.rs','crates/proteus-contracts/src/contracts/session_storage/validation.rs','crates/proteus-contracts/src/contracts/conversation.rs','crates/proteus-session-semantics/src/model_context.rs']
def oid(b):return hashlib.sha1(b'blob '+str(len(b)).encode()+b'\0'+b).hexdigest()
def cut(s,a,b):
 i=s.index(a);j=s.index(b,i+len(a));return s[i:j]
def generate(core,candidate,out):
 pins=json.loads((here/'route-pins.json').read_text())
 def read(p):
  v=(core/p).read_bytes();assert oid(v)==pins[p],p
  return v.decode()
 for f in files:read(f)
 changed=candidate.read_bytes();assert oid(changed)==pins['candidate'],candidate
 orig=read(conv);rem=read(mod);wr=read(writer);sn=read(snap);dr=read(display)
 def arm(s):
  # The ancestor-facing type must be constructible by the independent outer
  # driver. Only the single visibility token is widened, never the read body.
  return cut(s,'use crate::{','impl super::AgentRuntime')+s[s.index('pub(super) struct TurnConversation'):].replace('pub(super) struct TurnConversation','pub(crate) struct TurnConversation',1)
 txt='''#![allow(dead_code,unused_imports)]
pub mod model_context {
'''+cut(read(MODEL),'pub(crate) use','pub(crate) mod recorder;')+''' }
pub mod stock {
'''+arm(orig)+''' }
pub mod candidate {
'''+arm(changed.decode())+''' }
mod remote {
use anyhow::{Result,bail,ensure};
use proteus_contracts::{contracts::{SessionStorage,SessionStorageRequest as Request,SessionStorageResponse as Response,StorageSessionDescriptor,StorageHistoryPoint,StorageSnapshot,StorageConversation,StorageRevision,StorageWriterLease},domain::SessionId,model_standard::CanonicalMessage};
use std::{path::PathBuf,sync::Arc};
use writer::RemoteWriter;
'''+cut(rem,'pub type StorageService','impl std::fmt::Debug')+'''
impl RemoteSessionStore {
'''+cut(rem,'    fn from_descriptor','    pub fn session_dir')+cut(rem,'    pub(crate) fn request','    pub fn load_messages')+''' }
mod stage_layout {
use std::{collections::HashMap,fs::File,io::BufWriter};
use proteus_contracts::domain::{TurnId,ThreadId,PartId};
'''+cut(dr,'type RootBindings','impl CausalStage')+cut(dr,'pub(in crate::core::session_store::remote) struct DisplayRecordWriter','impl DisplayRecordWriter').replace('pub(in crate::core::session_store::remote)','pub(super)')+cut(dr,'pub(crate) struct DisplayRecords','impl DisplayRecords')+''' }
mod writer {
use super::*;
use super::stage_layout::DisplayRecordWriter;
'''+cut(wr,'struct DisplayCapture','fn lease_lost')+cut(wr,'pub(super) struct RemoteWriter','    async fn acquire(')+'''
    pub(super) fn fixture_lease(&mut self,lease:StorageWriterLease){
        self.lease=Some(lease); self.revision=StorageRevision {session_seq:51,history_revision:41};
    }
}
impl RemoteSessionStore {
'''+cut(wr,'    pub(crate) async fn history_revision','    pub(crate) async fn prepare_resume_state')+''' }
}
mod snapshot {
use super::*;
use super::stage_layout::DisplayRecords;
'''+cut(sn,'pub(crate) struct RemoteJournalSnapshot','    pub(crate) fn cursor')+cut(sn,'    pub(crate) fn conversation','    pub(crate) fn scan(')+''' }
'''+cut(sn,'impl Drop for RemoteJournalSnapshot','#[derive(Debug)]')+''' }
'''+(here/'adapter.rs').read_text()+''' }
pub(crate) use remote::{TestMode,TestIo};
'''+cut(read(ALIAS),'pub use remote::RemoteSessionStore as SessionStore;', 'pub use remote::StorageService;')+'''
pub(crate) fn public_rows(rows:usize,repeats:usize)->Vec<proteus_contracts::model_standard::CanonicalMessage>{
    use proteus_contracts::model_standard::{CanonicalMessage,MessageRole};
'''+cut(read('crates/proteus-core/examples/session_index_fixture.rs'),'    let messages: Vec<_> = (0..rows)','    let thread_id = new_thread_id();')+'''    messages
}
'''
 out.mkdir(parents=True,exist_ok=True);(out/'core.rs').write_text(txt)
if __name__=='__main__':generate(*(Path(x) for x in sys.argv[1:]))
