"""Generate fixed Core cache+renderer route from exact pinned files, using genuine contracts and semantics."""
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
PATHS=[FIX,READ,S+'context_summary.rs',S+'json_size.rs',R+'mod.rs',R+'snapshot.rs',R+'snapshot/display_records.rs',R+'view.rs',R+'view/prefix.rs',R+'view/prefix/packed.rs',R+'view/cache.rs',R+'view/cache/pages.rs',R+'view/cache/pages/packs.rs',R+'view/cache/preview.rs',*(T+x+'.rs' for x in ('','/rows','/journal','/journal/timestamps','/journal/source'))]
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
 stock=r(S+'context_summary.rs')
 candidate=changed.read_bytes()
 assert blob(candidate)==pins['candidate'],'unexpected changed read_model blob'
 for n,body in [('stock',r(READ)),('candidate',candidate.decode())]:
  read=section(body,'/// Read a complete named display revision.','/// Cold HTTP reads share')
  w(n+'.rs','use super::*;\nuse crate::RemoteSessionStore as SessionStore;\nuse crate::render::journal_transcript_from_source;\n'+read)
 w('meter.rs',meter.read_text())
 cp='core/session_store/'
 snap=r(R+'snapshot.rs')
 # The unchanged cold open/strict validation path is executed; auxiliary changed cursor is excluded.
 snap=section(snap,'#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]','    pub(crate) fn open_for_display_if_changed(')+section(snap,'    pub(crate) fn open_with_cursor(')
 render_hook='    pub(crate) fn scan_display('
 snap=snap.replace(render_hook,render_hook,1)
 w('snap.rs','use super::*;\n'+snap+'''
pub(super) fn corrupt(s:&mut RemoteJournalSnapshot){s.display_records.as_mut().unwrap().fixture_corrupt();}
pub(super) fn stage_status(s:&RemoteJournalSnapshot)->(usize,u64,bool){
    s.display_records.as_ref().map(|v|v.stage_status()).unwrap_or((0,0,false))
}
''')
 w('stage.rs',r(R+'snapshot/display_records.rs').replace('pub(in crate::core::session_store::remote)','pub(super)')+'\nimpl DisplayRecords {pub(super) fn fixture_corrupt(&mut self){self.count+=1;} pub(super) fn stage_status(&self)->(usize,u64,bool){(self.count,self.file.metadata().unwrap().len(),self.causal_roots.is_some())}}\n')
 tr=section(r(T+'.rs'),'fn append_transcript_parts', '#[cfg(test)]\nmod tests {')
 rows=section(r(T+'/rows.rs'),'#[derive(Default)]').replace('#[cfg(test)]\nmod tests;','')
 jr=section(r(T+'/journal.rs'),'struct TranscriptReplay {','#[cfg(test)]\nmod tests;')
 ts=section(r(T+'/journal/timestamps.rs'),'#[derive(Clone, Copy, Default)]','#[cfg(test)]\nmod tests;')
 f=section(r(T+'/journal/source.rs'),'pub(crate) fn journal_transcript_from_source', '#[cfg(test)]\npub(super) fn from_records'); mark='    if let Some(root_threads) = source.take_staged_causal_roots()'; assert f.count(mark)==1; f=f.replace(mark,'    crate::observe_render(source);\n'+mark,1)
 w('render.rs','use super::*;\n'+rows+tr+'\nmod journal {use super::*;use std::{hash::Hash,num::NonZeroU64};\n'+ts+jr+'\nmod source {use super::*;\n'+f+'}\npub(crate) use source::journal_transcript_from_source;\n}\npub(super) use journal::journal_transcript_from_source;\n')
 w('core.rs','pub(crate) mod session_store;pub use proteus_contracts::storage::journal::*;pub use proteus_session_semantics::history_message_sha256;\npub(crate) use session_store::summarize_context_history; pub(crate) mod session_read_cache{pub(crate) use super::session_store::remote::view::RemoteCacheSource as SourceFingerprint;}\n')
 w(cp+'mod.rs','pub(crate) mod remote;mod summary; pub(crate) mod json_size;pub(crate) use summary::summarize_context_history;\n')
 for n,t in [('summary',stock),('json_size',r(S+'json_size.rs'))]: w(cp+n+'.rs',t.replace('pub(super) fn encoded_len','pub(crate) fn encoded_len').replace('pub(super) fn summarize_context_history','pub(crate) fn summarize_context_history'))
 w(cp+'remote/mod.rs','pub(crate) use crate::RemoteSessionStore; pub(crate) mod view; pub(crate) mod snapshot{pub(crate) use crate::snap::*;}\n')
 base=cp+'remote/view'
 v=r(R+'view.rs')
 defs=section(v,'#[derive(Debug, Serialize, Deserialize)]','#[derive(Debug)]\npub(crate) struct SessionTranscriptAppend').replace('pub(super) prefix','pub(crate) prefix')
 model=section(v,'impl SessionReadModel','impl RemoteSessionStore')
 m=method(v,'    pub(crate) fn project_sourced_read_model(')
 m=m.replace('        let read = RemoteValidatedRead','        crate::meter::begin_project();\n        let read = RemoteValidatedRead',1).replace('        Ok((source, model))','        crate::meter::capture(&model);\n        crate::ready_for_final();\n        Ok((source, model))',1)
 methods='impl RemoteSessionStore {\n'+m+''.join(method(v,s) for s in ('    pub(crate) fn save_read_model(', '    pub(crate) fn fresh_context_summary(', '    pub(crate) fn saved_transcript_page(', '    pub(crate) fn saved_transcript('))+'}\n'
 methods+='impl RemoteSessionStore {\n'+''.join(method(r(R+'mod.rs'),s) for s in ('    pub fn session_dir(', '    pub fn session_id(', '    pub fn parent_session_id(', '    pub fn workspace_path(', '    pub fn journal_snapshot(','    pub(crate) fn request(','    pub(crate) fn snapshot('))+'}\n'
 w(base+'/mod.rs','use crate::*;\nuse super::{RemoteSessionStore,snapshot};mod cache;mod prefix;use prefix::PrefixIdentities;pub(crate) use cache::RemoteCacheSource;\n'+defs+model+methods+section(v,'fn display_prefix(').replace('    let mut prefix =', '    if crate::fault_is("late-prefix"){crate::snap::corrupt(snapshot); }\n    let mut prefix =',1)+(HERE/'view_fixture.rs').read_text())
 for path in ('cache.rs','cache/pages.rs','cache/pages/packs.rs','cache/preview.rs','prefix.rs','prefix/packed.rs'):
  needed=r(R+'view/'+path)
  if path=='prefix.rs':
   for field in ['history','turns','exchanges','messages','parts','calls']:
    needed=needed.replace('    pub(super) '+field+':','    '+field+':',1).replace('    '+field+':','    pub(crate) '+field+':',1)
  w(base+'/'+path,needed)
 f=section(r(FIX),'    let messages: Vec<_> = (0..rows)','    let thread_id = new_thread_id();')
 w('main.rs',(HERE/'route.rs').read_text()+'\n'+(HERE/'adapter.rs').read_text()+'\nfn seed(rows:usize,repeats:usize)->Vec<CanonicalMessage>{\n'+f+'messages\n}\n')
if __name__=='__main__':generate(*(Path(p) for p in sys.argv[1:]))
