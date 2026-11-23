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
def generate(src,changed,out,composition=None):
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
    src_types+='#[derive(Serialize)]\n'+next(l+'\n' for l in storage.splitlines() if l.startswith('#[serde(tag = "result"'))+'pub enum Response {\n'+sec(storage,'    Metadata {','    Blob {')+'    Done,\n}\n'
    fix=read(FIX)
    shape=sec(fix,'                format!(', '\n            )').strip().rstrip(',')
    src_types+='pub fn fixture_text(i:usize,repeats:usize)->String{'+shape+'}\n'
    cp=read(C+'model_standard/content_part.rs')
    for tag in ('enum MessageRole','struct CanonicalMessage','enum PartScope','enum PartProvenance','struct CanonicalPart'):
        src_types+=decl(cp,'pub '+tag+' {')
    ct=cp.index('pub enum ContentPart {')
    src_types+=cp[cp.rindex('#[derive(',0,ct):ct]+'pub enum ContentPart {\n'+sec(cp[ct:],'    Text {','    Context {')+'}\n'
    src_types+=decl(read(WF),'pub enum ModelContextObservation {')+decl(view,'pub(crate) struct SessionReadView {')
    emit(out,'model.rs',src_types.replace('fn matches(&self, store: &RemoteSessionStore)','fn matches(&self, store: &MemoryStore)'));emit(out,'value_hash.rs',read(HASH))
    pre=read(PREFIX)
    emit(out,'prefix.rs','use super::*;\nuse std::collections::HashSet;\nmod packed;\n'+decl(pre,'pub(crate) struct PrefixIdentities {'))
    emit(out,'prefix/packed.rs',read(PACKED).replace('pub(in crate::core::session_store::remote::view)','pub(crate)').split('#[cfg(test)]')[0])
    emit(out,'core/session_store/json_size.rs',read(JS).replace('pub(super) fn encoded_len','pub(crate) fn encoded_len'))
    # Both wrappers exist upstream and are called from the lifted prepare/project route.
    for name,root in [('stock',src),('candidate',changed),('baseline',composition.parent/'composition_base' if composition else src),('composed',composition or changed)]:
        s=(root/CACHE).read_text()
        v=(root/VIEW).read_text() if (root/VIEW).is_file() else view
        prep=read(PREPARED)
        m='use super::*;\nmod pages;\nuse pages::{Section,valid_section,write_transcript,write_section,read_section,visit_section};\n'
        m+=sec(s,'const FORMAT:', 'mod pages;')+sec(s,'#[derive(Debug, Clone, Serialize, Deserialize)]','pub(super) fn load_model(')
        m+=sec(s,'pub(super) fn load_saved_view(','pub(super) fn summary(')
        # Test probes only: immutable reference immediately after header validation; no owner moved or cloned.
        assert m.count('let previous = header(store)') == 1
        m=m.replace('let previous = header(store)','let previous = header(store).inspect(observe_header)')
        entry='    for row in rows {'
        i=m.index('pub(super) fn update_tools(')
        assert m[i:].count(entry)==1
        m=m[:i]+m[i:].replace(entry,'    meter::checkpoint(2, 0, 0);\n'+entry)
        m+='pub(crate) struct RemoteSessionStore(std::rc::Rc<MemoryStore>);\n'+(H/'route.rs').read_text()+'\nimpl RemoteSessionStore {\n'
        for meth in ('project_validated_view','saved_read_view','save_read_model','saved_transcript_page'):
            m+=method(v,'    pub(crate) fn '+meth+'(')
        m+='}\nmod cache {pub(super) use super::{load_saved_view,save_model,transcript_page};}\n'
        m+='mod prepared {use super::*;\n'+sec(prep,'pub(crate) struct PreparedSession {','fn order_startup_candidates(')+'}\n'
        m+='const IS_STOCK:bool='+('true' if name in ('stock','baseline') else 'false')+';\n'+(H/'cases.rs').read_text()
        emit(out,name+'/mod.rs',m)
        ps=read(PAGES).replace('pub(in crate::core::session_store::remote::view)','pub(crate)')
        needle='        pending.push(store, source, section, value, section.rows <= pack_before)'
        assert ps.count(needle)==1
        ps=ps.replace(needle,'        if crate::meter::active(){crate::meter::checkpoint(1, crate::value_heap_lower_bound(&value), bytes);}\n'+needle)
        emit(out,name+'/pages.rs',ps+"\npub(super) fn observe(s:&Section,group:u8){crate::meter::vec(&s.pages,group);crate::meter::vec(&s.packs,group); for p in &s.pages {crate::meter::string(&p.hash, group)} for p in &s.packs {crate::meter::string(&p.hash, group)} }\n")
        packs=read(PACKS)
        marker='        self.frames.push(frame);'
        assert packs.count(marker)==1
        packs=packs.replace(marker,marker+'''
        if self.frames.len()==1 && crate::meter::active(){
            let held=self.frames.capacity()*std::mem::size_of::<String>()+self.frames.iter().map(String::capacity).sum::<usize>()
                +self.first_body.as_ref().map_or(0,crate::value_heap_lower_bound);
            crate::meter::pack_checkpoint(held);
        }
''')
        emit(out,name+'/pages/packs.rs',packs)
    for f in ['exercise.rs','meter.rs']:
        shutil.copyfile(H/f,out/('main.rs' if f=='exercise.rs' else f))
