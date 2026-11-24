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
PREFIX=SS+'remote/view/prefix.rs'
PACKED=PREFIX[:-3]+'/packed.rs'
PREPARED=SS+'remote/prepared.rs'
WF=C+'contracts/workflow_context.rs'
SOURCES+= [PREFIX,PACKED,PREPARED,WF]
def method(s,sig):
    at=s.index(sig)
    return s[at:s.index('\n    }',at)+6]+'\n'
CATALOG=SS+'remote/catalog.rs'
SOURCES += [CATALOG]
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
    src_types+=next(l+'\n' for l in storage.splitlines() if l.startswith('#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]'))+next(l+'\n' for l in storage.splitlines() if l.startswith('#[serde(tag = "operation"'))+'pub enum Request {\n'+sec(storage,'    ListCandidates {','    AcquireWriter {')+sec(storage,'    ReadCache {','    CompareExchangeMetadata {')+'}\n'
    src_types+='#[derive(Serialize,Deserialize)]\n'+next(l+'\n' for l in storage.splitlines() if l.startswith('#[serde(tag = "result"'))+'pub enum Response {\n'+sec(storage,'    Candidates {','    Sessions {')+sec(storage,'    Metadata {','    Blob {')+'    Done,\n}\n'
    fix=read(FIX)
    shape=sec(fix,'                format!(', '\n            )').strip().rstrip(',')
    src_types+='pub fn fixture_text(i:usize,repeats:usize)->String{'+shape+'}\n'
    cp=read(C+'model_standard/content_part.rs')
    for tag in ('enum MessageRole','struct CanonicalMessage','enum PartScope','enum PartProvenance','struct CanonicalPart'):
        src_types+=decl(cp,'pub '+tag+' {')
    ct=cp.index('pub enum ContentPart {')
    src_types+=cp[cp.rindex('#[derive(',0,ct):ct]+'pub enum ContentPart {\n'+sec(cp[ct:],'    Text {','    Context {')+'}\n'
    src_types+=decl(read(WF),'pub enum ModelContextObservation {')+decl(view,'pub(crate) struct SessionReadView {')
    emit(out,'model.rs',src_types.replace('fn matches(&self, store: &RemoteSessionStore)','fn matches(&self, store: &Opened)'));emit(out,'value_hash.rs',read(HASH))
    pre=read(PREFIX)
    emit(out,'prefix.rs','use super::*;\nuse std::collections::HashSet;\nmod packed;\n'+decl(pre,'pub(crate) struct PrefixIdentities {'))
    emit(out,'prefix/packed.rs',read(PACKED).replace('pub(in crate::core::session_store::remote::view)','pub(crate)').split('#[cfg(test)]')[0])
    emit(out,'core/session_store/json_size.rs',read(JS).replace('pub(super) fn encoded_len','pub(crate) fn encoded_len'))
    for name,root in [('stock',src),('candidate',changed)]:
        s=read(CACHE); v=view
        prep=(root/PREPARED).read_text()
        m='use super::*;\nmod pages;\nuse pages::{Section,valid_section,write_transcript,write_section,read_section,visit_section};\n'
        m+=sec(s,'const FORMAT:', 'mod pages;')+sec(s,'#[derive(Debug, Clone, Serialize, Deserialize)]','pub(super) fn load_model(')
        m+=sec(s,'pub(super) fn load_saved_view(','pub(super) fn summary(')
        m+=(H/'route.rs').read_text()+'\nimpl RemoteSessionStore {\n'
        for meth in ('project_validated_view','saved_read_view','save_read_model','saved_transcript_page'):
            m+=method(v,'    pub(crate) fn '+meth+'(')
        m+='}\nmod cache {pub(super) use super::{load_saved_view,save_model,transcript_page};}\n'
        c=sec(read(CATALOG),'/// Provisional display discovery.','fn updates()')
        m+='mod catalog {use super::*;\n'+c+'}\n'
        # Monitoring adds nonallocating checkpoints; production source bodies otherwise unchanged.
        probe='    order_startup_candidates(&mut candidates);'
        assert prep.count(probe)==1
        prep=prep.replace(probe,'    meter::sorted_capacity(crate::vec_bytes(&candidates));\n    meter::checkpoint(2);\n'+probe+'\n    meter::checkpoint(3);')
        prep=prep.replace('    use std::cmp::Ordering;', '    use std::cmp::Ordering;\n    meter::sort_entry(candidates.len());')
        prep=prep.replace('    candidates.sort_by(order);','    meter::did_sort();\n    candidates.sort_by(order);')
        m+='mod snapshot {pub(super) use super::{RemoteJournalSnapshot,RemoteValidatedRead};}\nmod view {pub(super) use super::{RemoteCacheSource,SessionReadView};}\nmod prepared {\n'+prep.replace('use anyhow::Result;', 'use anyhow::Result;\nuse crate::meter;')+'}\n'+(H/'cases.rs').read_text()
        emit(out,name+'/mod.rs',m)
        emit(out,name+'/pages.rs',read(PAGES).replace('pub(in crate::core::session_store::remote::view)','pub(crate)'))
        emit(out,name+'/pages/packs.rs',read(PACKS))
    for f in ['exercise.rs','meter.rs']:
        shutil.copyfile(H/f,out/('main.rs' if f=='exercise.rs' else f))
