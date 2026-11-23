"""Lift pinned code, not a reimplementation of indexing. See README for boundaries."""
from pathlib import Path
import shutil
H=Path(__file__).resolve().parent
SS='crates/proteus-core/src/core/session_store/'
C='crates/proteus-contracts/src/'
CACHE=SS+'remote/view/cache.rs'
PAGES=CACHE[:-3]+'/pages.rs'
PACKS=PAGES[:-3]+'/packs.rs'
INC=SS+'remote/view/incremental.rs'
VIEW=SS+'remote/view.rs'
HASH=C+'contracts/session_storage/value_hash.rs'
JS=SS+'json_size.rs'
CONTEXT=C+'app_protocol/context.rs'
FIX='crates/proteus-core/examples/session_index_fixture.rs'
TYPES={
'domain/image':['struct ImageRef'],
'contracts/tool_terminal':['struct ToolTerminalRef'],
'contracts/session_storage':['struct SessionLocator','struct StorageRevision','struct StorageSnapshot','struct StorageSessionDescriptor','struct StorageMetadataDocument'],
'model_standard/content_part':['enum MessagePhase'], 'domain/usage':['struct SessionUsageSnapshot','struct ModelRequestUsage','enum ModelUsageStatus'],
'contracts/execution_recorder':['enum ModelCallOrigin'],'domain/model':['struct ModelRef'],
'model_standard/canonical_response':['enum FinishReason','struct TokenUsage'],
'contracts/conversation':['struct ConversationSnapshot'],
}
SOURCES=['Cargo.lock',CACHE,PAGES,PACKS,JS,HASH,VIEW,INC,SS+'remote/snapshot.rs',C+'domain/ids.rs',C+'app_protocol/session.rs',C+'app_protocol/transcript.rs',CONTEXT,FIX,*[C+key+'.rs' for key in TYPES]]
def decl(s,label):
    i=s.index(label)
    return s[s.rindex('#[derive(',0,i):s.index('\n}',i)+2]+'\n'
def sec(s,a,b):
    i=s.index(a);return s[i:s.index(b,i+len(a))]
def emit(dest,p,s):
    f=dest/p;f.parent.mkdir(parents=True,exist_ok=True);f.write_text(s)
def generate(src,changed,out):
    read=lambda p:(src/p).read_text()
    storage=read(C+'contracts/session_storage.rs')
    src_types='use super::*;\n'+sec(read(C+'domain/ids.rs'),'#[derive(', 'pub fn new_session_id')
    for path,types in TYPES.items():
        for d in types:src_types+=decl(read(C+path+'.rs'),'pub '+d+' {')
    src_types+=read(C+'app_protocol/transcript.rs')[read(C+'app_protocol/transcript.rs').index('/// A page'): ]
    sess=read(C+'app_protocol/session.rs')
    src_types+=sec(sess,'/// Canonical summary', '#[cfg(test)]')
    context=read(CONTEXT)
    src_types+=decl(context,'pub struct AppContextHistorySummary {')
    src_types+=decl(read(SS+'remote/snapshot.rs'),'pub(crate) struct RemoteJournalCursor {')
    view=read(VIEW)
    src_types+=decl(view,'pub(crate) struct SessionReadModel {').replace('pub(super) prefix','pub(crate) prefix')+'impl SessionReadModel {\n'+sec(view,'    pub(crate) fn matches(&self, store:','\n}\n')+'\n}\n'
    src_types+=next(l+'\n' for l in storage.splitlines() if l.startswith('pub const SESSION_STORAGE_MAX_CACHE_BYTES'))
    src_types+='#[derive(Serialize)] #[serde(tag="operation", rename_all="snake_case")] pub enum Request {\n'+sec(storage,'    ReadCache {','    CompareExchangeMetadata {')+'}\n'
    src_types+='pub enum Response {\n'+sec(storage,'    Metadata {','    Blob {')+'    Done,\n}\n'
    fix=read(FIX)
    shape=sec(fix,'                format!(', '\n            )').strip().rstrip(',')
    src_types+='pub fn fixture_text(i:usize,repeats:usize)->String{'+shape+'}\n'
    emit(out,'model.rs',src_types);emit(out,'value_hash.rs',read(HASH))
    emit(out,'core/session_store/json_size.rs',read(JS).replace('pub(super) fn encoded_len','pub(crate) fn encoded_len'))
    # Cold save and committed suffix callers invoke the exact function below, before publication.
    assert 'update_tools(store, source, &mut tools, &model.transcript)?;' in read(CACHE)
    assert 'cache::update_tools(self, &source, &mut next.tools, &suffix.transcript)?;\n                cache::publish(self, &next)?;' in read(INC)
    for name,root in [('stock',src),('candidate',changed)]:
        s=(root/CACHE).read_text()
        m='use super::*;\nmod pages;\nuse pages::{Section,valid_section,write_transcript,write_section,read_section,visit_section};\n'
        m+=sec(s,'const FORMAT:', 'mod pages;')+sec(s,'#[derive(Debug, Clone, Serialize, Deserialize)]','pub(super) fn read_prefix(')
        m+=sec(s,'fn bounded_value(','pub(super) fn header_at_revision(')+sec(s,'pub(super) fn fresh_header(','pub(super) fn load_model(')
        m+=sec(s,'pub(super) fn save_model(','pub(super) fn summary(')
        m+='fn write_prefix(_: &RemoteSessionStore, _: &RemoteCacheSource,_:&PrefixIdentities)->Option<String>{panic!("unexpected prefix fixture")}\n'
        m+=(H/'cases.rs').read_text()
        emit(out,name+'/mod.rs',m)
        emit(out,name+'/pages.rs',read(PAGES).replace('pub(in crate::core::session_store::remote::view)','pub(crate)'))
        emit(out,name+'/pages/packs.rs',read(PACKS))
    for f in ['exercise.rs','meter.rs']:
        shutil.copyfile(H/f,out/('main.rs' if f=='exercise.rs' else f))
