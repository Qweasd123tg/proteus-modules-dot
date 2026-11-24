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
HTTP=C+'app_server/http/sessions.rs'
EDIT={'transcript':T+'.rs','journal':T+'/journal.rs','source':T+'/journal/source.rs'}
PATHS=[FIX,HTTP,READ,S+'context_summary.rs',S+'json_size.rs',R+'mod.rs',R+'snapshot.rs',R+'snapshot/display_records.rs',R+'view.rs',R+'view/prefix.rs',R+'view/prefix/packed.rs',R+'view/cache.rs',R+'view/cache/pages.rs',R+'view/cache/pages/packs.rs',R+'view/cache/preview.rs',*(T+x+'.rs' for x in ('','/rows','/journal','/journal/timestamps','/journal/source'))]
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
 cand={}
 for name,path in EDIT.items():
  b=(changed/path).read_bytes();assert blob(b)==pins['candidate-'+name]
  cand[name]=b.decode()
 w('meter.rs',meter.read_text())
 w('supplement.rs',meter.with_name('supplement.rs').read_text())
 cp='core/session_store/'
 snap=r(R+'snapshot.rs')
 # The unchanged cold open/strict validation path is executed; auxiliary changed cursor is excluded.
 snap=section(snap,'#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]','    pub(crate) fn open_for_display_if_changed(')+section(snap,'    pub(crate) fn open_with_cursor(')
 w('snap.rs','use super::*;\n'+snap+'''
pub(super) fn break_stage(s:&mut RemoteJournalSnapshot){if let Some(x)=&mut s.display_records{x.fault();}}\npub(super) fn stage_status(s:&RemoteJournalSnapshot)->(usize,u64,bool){
    s.display_records.as_ref().map(|v|v.stage_status()).unwrap_or((0,0,false))
}
''')
 stage=r(R+'snapshot/display_records.rs').replace('pub(in crate::core::session_store::remote)','pub(super)')
 stage=stage.replace('        Some(Self {\n            writer: Some','        if crate::UNSTAGED.get(){return None;}\n        Some(Self {\n            writer: Some',1)
 w('stage.rs',stage+'\nimpl DisplayRecords {pub(super) fn fault(&mut self){self.count+=1;} pub(super) fn stage_status(&self)->(usize,u64,bool){(self.count,self.file.metadata().unwrap().len(),self.causal_roots.is_some())}}\n')
 rows=section(r(T+'/rows.rs'),'#[derive(Default)]').replace('#[cfg(test)]\nmod tests;','')
 ts=section(r(T+'/journal/timestamps.rs'),'#[derive(Clone, Copy, Default)]','#[cfg(test)]\nmod tests;')
 for arm in ('stock','candidate'):
  body={k:r(v) for k,v in EDIT.items()} if arm=='stock' else cand
  tr=section(body['transcript'],'fn append_transcript_parts', '#[cfg(test)]\nmod tests {')
  jr=section(body['journal'],'struct TranscriptReplay {','#[cfg(test)]\nmod tests;')
  jr=jr.replace('fn append_tool_result(&mut self, result: &crate::domain::ToolResult) {','fn append_tool_result(&mut self, result: &crate::domain::ToolResult) {\n        crate::meter::accepted(result);',1)
  jr=jr.replace('fn append_owned_tool_result(&mut self, result: &mut crate::domain::ToolResult) {','fn append_owned_tool_result(&mut self, result: &mut crate::domain::ToolResult) {\n        crate::meter::accepted(result);',1)
  f=section(body['source'],'pub(crate) fn journal_transcript_from_source', '#[cfg(test)]\npub(super) fn from_records')
  p='        if record.session_seq >= start {\n            replay.'
  mark=p+('render_record(&record, live_turn_id);' if arm=='stock' else 'render_final_record(&mut record, live_turn_id);')
  assert f.count(mark)==1
  end='''
            let tool = if let JournalEntry::ToolResultRecorded(r)=&record.entry {
                replay.state.transcript.rows.iter().rev().filter_map(|v|v.tool.as_ref()).find(|t|t.call_id==r.result.call_id)
            }else{None};
            crate::meter::end_record(tool);
            drop(record);
            crate::meter::finish_record();'''
  f=f.replace(mark,'        if record.session_seq >= start {\n            crate::meter::begin_record(&record);\n            replay.'+mark.split('replay.',1)[1]+end,1)
  f=f.replace('pub(super) fn transcript_from_scan','pub(crate) fn transcript_from_scan',1)
  w('render_'+arm+'.rs','use super::*;\n'+rows+tr+'\nmod journal {use super::*;use std::{hash::Hash,num::NonZeroU64};\n'+ts+jr+'\nmod source {use super::*;\n'+f+'}\npub(crate) use source::{journal_transcript_from_source,transcript_from_scan};\n}\npub(crate) use journal::{journal_transcript_from_source,transcript_from_scan};\n')
 w('render.rs','use super::*;\npub(crate) fn transcript_from_scan(scan:impl FnMut(&mut dyn FnMut(JournalRecord)->Result<()>) -> Result<()>,live:Option<TurnId>)->Result<Vec<AppTranscriptMessage>>{ if CHANGED.get(){render_candidate::transcript_from_scan(scan,live)}else{render_stock::transcript_from_scan(scan,live)}}\npub(crate) fn journal_transcript_from_source(s:&mut RemoteJournalSnapshot,l:Option<TurnId>)->Result<Vec<AppTranscriptMessage>>{if CHANGED.get(){render_candidate::journal_transcript_from_source(s,l)}else{render_stock::journal_transcript_from_source(s,l)}}')
 w('core.rs','pub(crate) mod session_store;pub use proteus_contracts::storage::journal::*;pub use proteus_session_semantics::history_message_sha256;\npub(crate) use session_store::summarize_context_history; pub(crate) mod session_read_cache{pub(crate) use super::session_store::remote::view::RemoteCacheSource as SourceFingerprint;}\n')
 w(cp+'mod.rs','pub(crate) mod remote;mod summary; pub(crate) mod json_size;pub(crate) use summary::summarize_context_history;\n')
 for n,t in [('summary',stock),('json_size',r(S+'json_size.rs'))]: w(cp+n+'.rs',t.replace('pub(super) fn encoded_len','pub(crate) fn encoded_len').replace('pub(super) fn summarize_context_history','pub(crate) fn summarize_context_history'))
 w(cp+'remote/mod.rs','pub(crate) use crate::RemoteSessionStore; pub(crate) mod view; pub(crate) mod snapshot{pub(crate) use crate::snap::*;}\n')
 base=cp+'remote/view'
 v=r(R+'view.rs')
 defs=section(v,'#[derive(Debug, Serialize, Deserialize)]','#[derive(Debug)]\npub(crate) struct SessionTranscriptAppend')
 model=section(v,'impl SessionReadModel','impl RemoteSessionStore')
 methods='impl RemoteSessionStore {\n'+''.join(method(v,s) for s in ('    pub(crate) fn project_sourced_read_model(', '    pub(crate) fn save_read_model(', '    pub(crate) fn saved_transcript_page(', '    pub(crate) fn saved_transcript('))+'}\n'
 methods+='impl RemoteSessionStore {\n'+''.join(method(r(R+'mod.rs'),s) for s in ('    pub fn session_dir(', '    pub fn session_id(', '    pub fn parent_session_id(', '    pub fn workspace_path(', '    pub fn journal_snapshot(','    pub(crate) fn request(','    pub(crate) fn snapshot('))+'}\n'
 w(base+'/mod.rs','use crate::*;\nuse super::{RemoteSessionStore,snapshot};mod cache;mod prefix;use prefix::PrefixIdentities;pub(crate) use cache::RemoteCacheSource;\n'+defs+model+methods+section(v,'fn display_prefix(')+(HERE/'view_fixture.rs').read_text())
 for path in ('cache.rs','cache/pages.rs','cache/pages/packs.rs','cache/preview.rs','prefix.rs','prefix/packed.rs'):
  w(base+'/'+path,r(R+'view/'+path))
 f=section(r(FIX),'    let messages: Vec<_> = (0..rows)','    let thread_id = new_thread_id();')
 w('main.rs',(HERE/'route.rs').read_text()+'\n'+(HERE/'adapter.rs').read_text()+'\nfn seed(rows:usize,repeats:usize)->Vec<CanonicalMessage>{\n'+f+'messages\n}\n')
if __name__=='__main__':generate(*(Path(p) for p in sys.argv[1:]))
