"""Pinned, actual Core cold prefix path, typed providers and allocator observers."""
import json,sys
from pathlib import Path
import hashlib
HERE=Path(__file__).resolve().parent
C='crates/proteus-core/src/'
S=C+'core/session_store/'
R=S+'remote/'
T=C+'app_server/transcript'
FIX='crates/proteus-core/examples/session_index_fixture.rs'
READ=C+'app_server/read_model.rs'
PREP=R+'prepared.rs'
PATHS=[FIX,READ,PREP,S+'context_summary.rs',S+'json_size.rs',R+'mod.rs',R+'snapshot.rs',R+'snapshot/display_records.rs',R+'view.rs',R+'view/prefix.rs',R+'view/prefix/packed.rs',R+'view/cache.rs',R+'view/cache/pages.rs',R+'view/cache/pages/packs.rs',R+'view/cache/preview.rs',*(T+x+'.rs' for x in ('','/rows','/journal','/journal/timestamps','/journal/source'))]
def section(s,a,b=None):
 i=s.index(a);return s[i:] if b is None else s[i:s.index(b,i+len(a))]
def method(s,sig):
 i=s.index(sig);return s[i:s.index('\n    }',i)+6]+'\n'
def blob(b):return hashlib.sha1(b'blob '+str(len(b)).encode()+b'\0'+b).hexdigest()
def replace(s,a,b):
 assert s.count(a)==1,a
 return s.replace(a,b,1)
def generate(src,changed_view,changed_prefix,meter,out):
 pins=json.loads((HERE/'route-pins.json').read_text())
 def r(p):
  b=(src/p).read_bytes();assert blob(b)==pins[p],p;return b.decode()
 def w(p,s):
  q=out/p;q.parent.mkdir(parents=True,exist_ok=True);q.write_text(s)
 view=changed_view.read_bytes(); prefix=changed_prefix.read_bytes()
 assert blob(view)==pins['candidate-view'] and blob(prefix)==pins['candidate-prefix']
 read=section(r(READ),'/// Read a complete named display revision.','/// Cold HTTP reads share')
 w('read.rs','use super::*;\nuse crate::RemoteSessionStore as SessionStore;\nuse crate::render::journal_transcript_from_source;\n'+read)
 prep=section(r(PREP),'pub(crate) struct PreparedSession','fn order_startup_candidates')
 w('prepared.rs','use super::*;\nuse crate::core::session_store::remote::view::{SessionReadView,RemoteCacheSource};\nuse crate::Service as StorageService;\n'+prep)
 w('meter.rs',meter.read_text())
 cp='core/session_store/'
 snap=r(R+'snapshot.rs')
 snap=section(snap,'#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]','    pub(crate) fn open_for_display_if_changed(')+section(snap,'    pub(crate) fn open_with_cursor(')
 snap=snap.replace('            let response = self.store.request(request)?;','            crate::meter::begin_decode();\n            let response = self.store.request(request)?;',1)
 snap=replace(snap,'                    consume(record)?;','                    consume(record)?;\n                    crate::meter::finish_record();')
 w('snap.rs','use super::*;\n'+snap+'''
pub(super) fn stage_status(s:&RemoteJournalSnapshot)->(usize,u64,bool){
    s.display_records.as_ref().map(|v|v.stage_status()).unwrap_or((0,0,false))
}
pub(super) fn break_prefix(s:&mut RemoteJournalSnapshot){
    if let Some(stage)=&mut s.display_records{stage.break_prefix(crate::F.get());}
}
''')
 stage=r(R+'snapshot/display_records.rs').replace('pub(in crate::core::session_store::remote)','pub(super)')
 stage=stage.replace('        Some(Self {\n            writer: Some','        if crate::UNSTAGED.get(){return None;}\n        Some(Self {\n            writer: Some',1)
 stage=replace(stage,'            consume(serde_json::from_slice(&line)?)?;','            crate::meter::begin_decode();\n            consume(serde_json::from_slice(&line)?)?;\n            crate::meter::finish_record();')
 w('stage.rs',stage+r'''
impl DisplayRecords {
 pub(super) fn stage_status(&self)->(usize,u64,bool){(self.count,self.file.metadata().unwrap().len(),self.causal_roots.is_some())}
 pub(super) fn break_prefix(&mut self,fault:&str){
    use std::io::SeekFrom;
    match fault{
      "late-count"=>{self.count+=1;}
      "late-lf"|"late-decode"=>{
        self.file.seek(SeekFrom::End(0)).unwrap();
        self.file.write_all(if fault=="late-lf"{b"invalid"}else{b"{{\n"}).unwrap();
      }
      _=>()
    }
 }
}
''')
 tr=section(r(T+'.rs'),'fn append_transcript_parts', '#[cfg(test)]\nmod tests {')
 rows=section(r(T+'/rows.rs'),'#[derive(Default)]').replace('#[cfg(test)]\nmod tests;','')
 jr=section(r(T+'/journal.rs'),'struct TranscriptReplay {','#[cfg(test)]\nmod tests;')
 ts=section(r(T+'/journal/timestamps.rs'),'#[derive(Clone, Copy, Default)]','#[cfg(test)]\nmod tests;')
 f=section(r(T+'/journal/source.rs'),'pub(crate) fn journal_transcript_from_source', '#[cfg(test)]\npub(super) fn from_records')
 mark='    if let Some(root_threads) = source.take_staged_causal_roots()'
 f=replace(f,mark,'    crate::observe_render(source);\n'+mark)
 w('render.rs','use super::*;\n'+rows+tr+'\nmod journal {use super::*;use std::{hash::Hash,num::NonZeroU64};\n'+ts+jr+'\nmod source {use super::*;\n'+f+'}\npub(crate) use source::journal_transcript_from_source;\n}\npub(super) use journal::journal_transcript_from_source;\n')
 w('core.rs','pub(crate) mod session_store;pub use proteus_contracts::storage::journal::*;pub use proteus_session_semantics::history_message_sha256;\npub(crate) use session_store::summarize_context_history; pub(crate) mod session_read_cache{pub(crate) use super::session_store::remote::view::RemoteCacheSource as SourceFingerprint;}\n')
 w(cp+'mod.rs','pub(crate) mod remote;mod summary; pub(crate) mod json_size;pub(crate) use summary::summarize_context_history;\n')
 for n,t in [('summary',r(S+'context_summary.rs')),('json_size',r(S+'json_size.rs'))]:
  w(cp+n+'.rs',t.replace('pub(super) fn encoded_len','pub(crate) fn encoded_len').replace('pub(super) fn summarize_context_history','pub(crate) fn summarize_context_history'))
 w(cp+'remote/mod.rs','pub(crate) use crate::RemoteSessionStore; pub(crate) mod view; pub(crate) mod snapshot{pub(crate) use crate::snap::*;}\n')
 base=cp+'remote/view'
 v=r(R+'view.rs')
 defs=section(v,'#[derive(Debug, Serialize, Deserialize)]','#[derive(Debug)]\npub(crate) struct SessionTranscriptAppend')
 model=section(v,'impl SessionReadModel','impl RemoteSessionStore')
 m=method(v,'    pub(crate) fn project_sourced_read_model(')
 m=replace(m,'        Ok((source, model))','        crate::ready_for_final();\n        Ok((source, model))')
 methods='impl RemoteSessionStore {\n'+m+''.join(method(v,s) for s in (
  '    pub(crate) fn project_validated_view(', '    pub(crate) fn saved_read_view(',
  '    pub(crate) fn save_read_model(', '    pub(crate) fn saved_transcript_page(', '    pub(crate) fn saved_transcript('))+'}\n'
 methods+='impl RemoteSessionStore {\n'+''.join(method(r(R+'mod.rs'),s) for s in (
  '    pub fn session_dir(', '    pub fn session_id(', '    pub fn parent_session_id(',
  '    pub fn workspace_path(', '    pub fn journal_snapshot(','    pub(crate) fn request(',
  '    pub(crate) fn snapshot(','    pub fn open('))+'}\n'
 methods=methods.replace('service: StorageService','service: crate::Service')
 dispatch='''
fn display_prefix(snapshot:&mut RemoteJournalSnapshot,history:&[crate::CanonicalMessage])->Result<PrefixIdentities>{
    if crate::CHANGED.get(){display_prefix_candidate(snapshot,history)}else{display_prefix_stock(snapshot,history)}
}
'''
 for name,src_v in [('stock',v),('candidate',view.decode())]:
  before=section(src_v,'fn display_prefix(')
  before=replace(before,'fn display_prefix(',f'fn display_prefix_{name}(')
  before=replace(before,'    snapshot.scan_display(|record| {','    crate::snap::break_prefix(snapshot);\n    crate::PREFIXING.set(true);\n    crate::meter::begin_scan();\n    let scanned = snapshot.scan_display(|record| {\n        crate::meter::begin_record(&record);')
  before=replace(before,'    })?;\n    prefix.history =','    });\n    crate::meter::end_scan();\n    crate::PREFIXING.set(false);\n    scanned?;\n    crate::trace("Digest".into());\n    prefix.history =')
  dispatch+=before
 w(base+'/semantic.rs',meter.with_name('semantic.rs').read_text())
 w(base+'/mod.rs','mod semantic;pub(crate) use semantic::semantic_test;\nuse crate::*;\nuse super::{RemoteSessionStore,snapshot};mod cache;mod prefix;pub(crate) use prefix::PrefixIdentities;pub(crate) use cache::RemoteCacheSource;\n'+defs+model+methods+dispatch+(HERE/'view_fixture.rs').read_text())
 for path in ('cache.rs','cache/pages.rs','cache/pages/packs.rs','cache/preview.rs','prefix.rs','prefix/packed.rs'):
  needed=r(R+'view/'+path)
  if path=='prefix.rs':
   stock_visit=section(needed,'    pub(crate) fn visit(','    fn message(')
   stock_visit=replace(stock_visit,'                for message in &mutation.messages {','                for message in &mutation.messages {\n                    if !suffix{crate::meter::mid_row(message);}')
   candidate_impl=section(prefix.decode(),'    pub(crate) fn visit(','    fn message(')
   candidate_impl=replace(candidate_impl,'pub(crate) fn visit(','pub(crate) fn visit_candidate(')
   candidate_impl=replace(candidate_impl,'self.visit(&record, false);','self.visit_candidate(&record, false);')
   candidate_impl=replace(candidate_impl,'            for message in mutation.messages {','            for message in mutation.messages {\n                crate::meter::mid_row(&message);')
   assert section(needed,'    fn message(')==section(prefix.decode(),'    fn message(')
   needed=section(needed,'//! Compact identities','    pub(crate) fn visit(')+stock_visit+candidate_impl+section(needed,'    fn message(')
   for field in ['history','turns','exchanges','messages','parts','calls']:
    needed=needed.replace('    pub(super) '+field+':','    '+field+':',1).replace('    '+field+':','    pub(crate) '+field+':',1)
  w(base+'/'+path,needed)
 f=section(r(FIX),'    let messages: Vec<_> = (0..rows)','    let thread_id = new_thread_id();')
 w('main.rs',(HERE/'route.rs').read_text()+'\n'+(HERE/'adapter.rs').read_text()+'\nfn seed(rows:usize,repeats:usize)->Vec<CanonicalMessage>{\n'+f+'messages\n}\n')
if __name__=='__main__':generate(*(Path(p) for p in sys.argv[1:]))
