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
EDIT={'read_model':READ,'sessions':HTTP,'view':R+'view.rs','cache':R+'view/cache.rs'}
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
 read=section(cand['read_model'],'/// Read a complete named display revision.','pub(super) fn project_committed_transcript')
 assert section(read,'/// Cold HTTP reads share','/// Read the current full transcript')==section(r(READ),'/// Cold HTTP reads share','pub(super) fn project_committed_transcript')
 w('read.rs','use super::*;\nuse crate::RemoteSessionStore as SessionStore;\nuse crate::core::session_store::remote::view::SessionReadModel;\nuse crate::render::journal_transcript_from_source;\n'+read)
 for n,http in [('stock',r(HTTP)),('candidate',cand['sessions'])]:
  body=section(section(http,'pub(super) async fn history_json','pub(super) async fn context_map_json'),'        let store = SessionStore::open(storage, session_dir)?;','    })')
  w('http_'+n+'.rs','use super::*;\nuse crate::RemoteSessionStore as SessionStore;\nuse crate::read as read_model;\npub(crate) fn restore(storage:Service, session_dir:PathBuf)->Result<Vec<AppTranscriptMessage>> {\n'+body.replace('crate::app_server::read_model::','read_model::')+'}\n')
 w('meter.rs',meter.read_text())
 cp='core/session_store/'
 snap=r(R+'snapshot.rs')
 # The unchanged cold open/strict validation path is executed; auxiliary changed cursor is excluded.
 snap=section(snap,'#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]','    pub(crate) fn open_for_display_if_changed(')+section(snap,'    pub(crate) fn open_with_cursor(')
 w('snap.rs','use super::*;\n'+snap+'''
pub(super) fn stage_status(s:&RemoteJournalSnapshot)->(usize,u64,bool){
    s.display_records.as_ref().map(|v|v.stage_status()).unwrap_or((0,0,false))
}
''')
 w('stage.rs',r(R+'snapshot/display_records.rs').replace('pub(in crate::core::session_store::remote)','pub(super)')+'\nimpl DisplayRecords {pub(super) fn stage_status(&self)->(usize,u64,bool){(self.count,self.file.metadata().unwrap().len(),self.causal_roots.is_some())}}\n')
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
 vnew=cand['view']
 defs=section(v,'#[derive(Debug, Serialize, Deserialize)]','#[derive(Debug)]\npub(crate) struct SessionTranscriptAppend').replace('pub(super) prefix','pub(crate) prefix')
 model=section(vnew,'impl SessionReadModel','impl RemoteSessionStore')
 legacy_matches=method(v,'    pub(crate) fn matches(').replace('fn matches(', 'fn matches_stock(',1)
 model=model.rsplit('}',1)[0]+legacy_matches+'}\n'
 m=method(v,'    pub(crate) fn fresh_read_model(')
 m=m.replace('        cache::load_model(self)','        crate::meter::begin_cache_load();\n        let model=if crate::CHANGED.get(){cache::load_model(self)}else{cache::load_model_stock(self)};\n        crate::meter::end_cache_load();\n        model',1)
 t=method(vnew,'    pub(crate) fn fresh_read_transcript(')
 t=t.replace('        cache::load_transcript(self)','        crate::meter::begin_cache_load();\n        let transcript=cache::load_transcript(self);\n        crate::meter::end_cache_load();\n        transcript',1)
 methods='impl RemoteSessionStore {\n'+m+t+''.join(method(v,s) for s in ('    pub(crate) fn project_read_model(', '    pub(crate) fn project_sourced_read_model(', '    pub(crate) fn save_read_model(', '    pub(crate) fn saved_transcript_page(', '    pub(crate) fn saved_transcript('))+'}\n'
 methods+='impl RemoteSessionStore {\n'+''.join(method(r(R+'mod.rs'),s) for s in ('    pub fn session_dir(', '    pub fn session_id(', '    pub fn parent_session_id(', '    pub fn workspace_path(', '    pub fn journal_snapshot(','    pub(crate) fn request(','    pub(crate) fn snapshot(','    pub fn open('))+'}\n'
 methods=methods.replace('service: StorageService','service: crate::Service')
 w(base+'/mod.rs','use crate::*;\nuse super::{RemoteSessionStore,snapshot};mod cache;mod prefix;use prefix::PrefixIdentities;pub(crate) use cache::RemoteCacheSource;\n'+defs+model+methods+section(v,'fn display_prefix(')+(HERE/'view_fixture.rs').read_text())
 for path in ('cache.rs','cache/pages.rs','cache/pages/packs.rs','cache/preview.rs','prefix.rs','prefix/packed.rs'):
  needed=r(R+'view/'+path)
  if path=='cache.rs':
   stock_load=section(needed,'pub(super) fn load_model(','pub(super) fn load_view(').replace('fn load_model(','fn load_model_stock(',1).replace('model.matches(store)','model.matches_stock(store)',1).replace('RemoteCacheSource::read(store)','crate::at_final_recheck(store)',1)
   needed=cand['cache'].replace('&& RemoteCacheSource::read(store).as_ref() == Some(&header.source)','&& crate::at_final_recheck(store).as_ref() == Some(&header.source)',1)
   needed=needed.replace('pub(super) fn load_view(',stock_load+'pub(super) fn load_view(',1)
  if path=='cache/pages.rs':
   needed=needed.replace('fn read_section<T: DeserializeOwned>','fn read_section<T: DeserializeOwned + \'static>',1).replace('fn visit_section<T: DeserializeOwned>','fn visit_section<T: DeserializeOwned + \'static>',1)
   needed=needed.replace('            .push(row);','            .push(row);\n        crate::meter::aggregate(result.as_ref().unwrap());',1)
   needed=needed.replace('    if start > end || end > section.rows','    crate::meter::before_section::<T>();\n    if start > end || end > section.rows',1)
   needed=needed.replace('                    let rows: Vec<T> = serde_json::from_value(body).ok()?;','                    crate::decode_mark::<T>(0);\n                    let rows: Vec<T> = serde_json::from_value(body).ok()?;\n                    crate::decode_mark::<T>(if rows.len()==page.rows {1}else{2});',1)
   needed=needed.replace('                    let first = start.saturating_sub(offset);','                    crate::meter::after_leaf(&rows);\n                    let first = start.saturating_sub(offset);',1)
   needed=needed.replace('                        visit(value)?;','                        crate::meter::accept(&value);\n                        visit(value)?;',1)
  w(base+'/'+path,needed)
 f=section(r(FIX),'    let messages: Vec<_> = (0..rows)','    let thread_id = new_thread_id();')
 w('main.rs',(HERE/'route.rs').read_text()+'\n'+(HERE/'adapter.rs').read_text()+'\nfn seed(rows:usize,repeats:usize)->Vec<CanonicalMessage>{\n'+f+'messages\n}\n')
if __name__=='__main__':generate(*(Path(p) for p in sys.argv[1:]))
