"""Extract pinned Core projection bodies, owning DTOs and real hash logic."""
from pathlib import Path

CR = 'crates/proteus-contracts/src/'
REM = 'crates/proteus-core/src/core/session_store/remote/'
VIEW = REM+'view.rs'
HASH = CR+'contracts/session_storage/value_hash.rs'
HISTORY = 'crates/proteus-session-semantics/src/journal/message_hash.rs'
TYPES = {
    'domain/context': ['enum ContextRenderMode','struct ContextChunk'],
    'domain/image': ['struct ImageRef'], 'domain/patch': ['struct Patch'],
    'domain/subagent': ['struct SubagentSessionBinding'], 'domain/task': ['struct AgentTask'],
    'domain/output': ['struct AgentOutput'], 'domain/model': ['struct ModelRef'],
    'domain/usage': ['struct SessionUsageSnapshot','struct ModelRequestUsage','enum ModelUsageStatus'],
    'contracts/tool_terminal': ['struct ToolTerminalRef'],
    'contracts/operation': ['enum OperationOwner'],
    'contracts/workflow_checkpoint': ['struct WorkflowToolResultBinding'],
    'contracts/execution_recorder': ['enum ModelCallOrigin'],
    'contracts/workflow_context': ['enum ModelContextObservation'],
    'contracts/conversation': ['struct ConversationSnapshot'],
    'contracts/session_storage': ['struct SessionLocator','struct StorageRevision','struct StorageSnapshot'],
    'model_standard/content_part': ['enum MessageRole','enum MessagePhase','struct CanonicalMessage','enum PartScope','enum PartProvenance','struct CanonicalPart','enum ContentPart'],
    'model_standard/canonical_response': ['struct CanonicalModelResponse','enum FinishReason','struct TokenUsage'],
    'model_standard/failure': ['enum ModelFailureKind','struct ModelFailure'],
    'storage/journal': ['struct JournalRecord','struct TurnOpened','struct HistoryMutated','enum HistoryMutationKind','struct ModelMessageRecorded','enum ModelResponseOutcome','struct ModelResponseRecorded','struct TurnSettled','enum TurnSettlementStatus','enum ToolCallRecordPhase','struct ToolCallRecorded','struct ToolResultRecorded'],
    'app_protocol/transcript': ['struct AppTranscriptPage','struct AppTranscriptCursor','struct AppTranscriptBase','struct AppTranscriptMessage','struct AppTranscriptTool','struct AppTranscriptSubagent','struct AppSubagentSession'],
    'app_protocol/session': ['struct AppSessionSummary','struct AppSessionActivity','enum AppSessionActivityStatus'],
}
INPUTS = [VIEW, REM+'snapshot.rs', REM+'view/cache.rs',REM+'view/prefix.rs', HASH, HISTORY, 'Cargo.lock',
          'crates/proteus-core/examples/session_index_fixture.rs',
          *(CR+f+'.rs' for f in TYPES),
          *(CR+f+'.rs' for f in ('domain/ids','domain/hosted_tool','domain/tool','domain/compaction'))]

def section(text,start,end=None):
    at=text.index(start)
    return text[at:] if end is None else text[at:text.index(end,at+len(start))]
def decl(text,sig):
    at=text.index(sig)
    return text[text.rindex('#[derive(',0,at):text.index('\n}',at)+2]+'\n'
def method(text,sig):
    at=text.index(sig)
    return text[at:text.index('\n    }',at)+6]+'\n'

def generate(orig, changed, dest):
    def read(path): return (orig/path).read_text()
    def source(key): return read(CR+key+'.rs')
    view=read(VIEW)
    support=section(source('domain/ids'),'#[derive(', 'pub fn new_session_id')
    support+=section(source('domain/hosted_tool'),'#[derive(')
    support+=section(source('domain/tool'),'#[derive(','#[cfg(test)]')
    support+=section(source('domain/compaction'),'#[derive(')
    support+=''.join(decl(source(file),'pub '+ty+' {') for file, types in TYPES.items() for ty in types)
    entry=decl(source('storage/journal'),'pub enum JournalEntry {')
    omitted=('HookInvoked(','ContextRequestRecorded(','ContextResponseRecorded(','ModelRequestRecorded(')
    support+='\n'.join(l for l in entry.splitlines() if not l.strip().startswith(omitted))+'\n'
    support+=decl(read(REM+'snapshot.rs'),'pub(crate) struct RemoteJournalCursor {')
    support+=decl(view,'pub(crate) struct SessionReadModel {').replace('pub(super) prefix','pub(crate) prefix')+decl(view,'pub(crate) struct SessionReadView {')
    pre=read(REM+'view/prefix.rs')
    pre=pre.replace('mod packed;\n','')
    cache=read(REM+'view/cache.rs')
    core_prefix=section(view,'fn display_prefix(')
    dest.mkdir(parents=True,exist_ok=True)
    (dest/'value_hash.rs').write_text(read(HASH))
    (dest/'message_hash.rs').write_text(read(HISTORY))
    (dest/'prefix.rs').write_text(pre+'''
impl PrefixIdentities {
    pub(super) fn observe_for_proof(&self, w: &mut Vec<crate::Watch>) {
        use crate::{Kind, add_vec, add};
        add_vec(w, &self.history, Kind::Hashes);
        for set in [&self.turns,&self.exchanges,&self.messages,&self.parts,&self.explicit_committed_parts] {
            if let Some(member) = set.iter().next() {
                add(w, std::ptr::from_ref(member).addr(), Kind::Sets, None);
            }
        }
        assert!(self.calls.is_empty(), "fixture call table not part of this proof");
    }
}
''')
    for label, src in [('stock',orig),('candidate',changed)]:
        h=method((src/VIEW).read_text(),'    pub(crate) fn project_validated_view(')
        # Preserve the original &self body verbatim in two isolated receiver wrappers.
        (dest/(label+'.rs')).write_text("use super::*;\nstruct Arm<'a>(&'a RemoteSessionStore);\nimpl std::ops::Deref for Arm<'_> {type Target=RemoteSessionStore;fn deref(&self)->&Self::Target{self.0}}\nimpl Arm<'_> {\n"+h+"}\npub(super) fn project(store:&RemoteSessionStore,read:RemoteValidatedRead,paged:bool,render:impl FnOnce(&mut RemoteJournalSnapshot)->Result<Vec<AppTranscriptMessage>>)->Result<SessionReadView>{\nArm(store).project_validated_view(read,paged,render)\n}\n")
    app='''#![allow(dead_code, unused_imports, unreachable_patterns)]
use anyhow::Result;
use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::{fmt, borrow::Cow, path::PathBuf};
use uuid::Uuid;
mod stock;
mod candidate;
mod prefix;
mod message_hash;
mod value_hash;
use prefix::PrefixIdentities;
mod domain {pub use super::*;}
mod contracts {pub use super::*;}
mod model_standard {pub use super::*;}
mod core {pub use super::*; pub use super::message_hash::history_message_sha256;}
'''+ support + '\nimpl SessionReadModel {\n'+method(view,'    pub(crate) fn from_validated(')+'}\n'+core_prefix+'''\nimpl RemoteSessionStore {
'''+method(view,'    pub(crate) fn save_read_model(')+method(view,'    pub(crate) fn saved_transcript_page(')+'''}
'''+decl(cache,'pub(crate) struct RemoteCacheSource {')+'\nimpl RemoteCacheSource {\n'+method(cache,'    pub(crate) fn from_cursor(')+method(cache,'    pub(crate) fn revision(')+'}\n'
    app+=next(l+'\n' for l in cache.splitlines() if l.startswith('const FORMAT:'))+next(l.replace('pub(super) ','')+'\n' for l in cache.splitlines() if l.startswith('pub(super) const PAGE_ROWS:'))
    app+=section(cache,'fn hash(value:', 'fn read_value(').replace('proteus_contracts::contracts::','value_hash::')
    fixture=read('crates/proteus-core/examples/session_index_fixture.rs')
    sentence=next(l.strip()[:-len('.repeat(repeats)')] for l in fixture.splitlines() if 'Синтетический текст' in l)
    app+='const SEED: &str = '+sentence+';\n'
    app+=(Path(__file__).parent/'exercise.rs').read_text()
    (dest/'main.rs').write_text(app)
