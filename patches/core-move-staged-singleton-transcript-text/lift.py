"""Compile source-bound renderer and locked wire DTOs; only JournalEntry's irrelevant
hook, request and context variants are removed, not their exercised dependencies."""
from pathlib import Path

APP='crates/proteus-core/src/app_server/'
C='crates/proteus-contracts/src/'
STAGE='crates/proteus-core/src/core/session_store/remote/snapshot/display_records.rs'

def section(s,a,b=None):
    i=s.index(a)
    return s[i:] if b is None else s[i:s.index(b,i+len(a))]
def decl(s,signature):
    i=s.index(signature)
    return s[s.rindex('#[derive(',0,i):s.index('\n}',i)+2]+'\n'

def generate(orig,changed,out):
    def read(x):return (orig/x).read_text()
    def source(x):return read(C+x+'.rs')
    def d(f,*types):
        s=source(f)
        return ''.join(decl(s,'pub '+t+' {') for t in types)
    s=source('domain/ids')
    types=section(s,'#[derive(', 'pub fn new_session_id')
    types+=section(source('domain/hosted_tool'),'#[derive(')
    types+=section(source('domain/tool'),'#[derive(','#[cfg(test)]')
    types+=section(source('domain/compaction'),'#[derive(')
    types+=d('domain/context','enum ContextRenderMode','struct ContextChunk')
    types+=d('domain/image','struct ImageRef')+d('domain/patch','struct Patch')+d('domain/subagent','struct SubagentSessionBinding')
    types+=d('domain/task','struct AgentTask')+d('domain/output','struct AgentOutput')
    types+=d('contracts/tool_terminal','struct ToolTerminalRef')+d('contracts/operation','enum OperationOwner')
    types+=d('contracts/workflow_checkpoint','struct WorkflowToolResultBinding')
    types+=d('model_standard/content_part','enum MessageRole','enum MessagePhase','struct CanonicalMessage','enum PartScope','enum PartProvenance','struct CanonicalPart','enum ContentPart')
    types+=d('model_standard/canonical_response','struct CanonicalModelResponse','enum FinishReason','struct TokenUsage')
    types+=d('model_standard/failure','enum ModelFailureKind','struct ModelFailure')
    types+=d('storage/journal','struct JournalRecord','struct TurnOpened','struct HistoryMutated','enum HistoryMutationKind','struct ModelMessageRecorded','enum ModelResponseOutcome','struct ModelResponseRecorded','struct TurnSettled','enum TurnSettlementStatus','enum ToolCallRecordPhase','struct ToolCallRecorded','struct ToolResultRecorded')
    entry=d('storage/journal','enum JournalEntry')
    omitted=('HookInvoked(','ContextRequestRecorded(','ContextResponseRecorded(','ModelRequestRecorded(')
    types+='\n'.join(x for x in entry.splitlines() if not x.strip().startswith(omitted))+'\n'
    types+=d('app_protocol/transcript','struct AppTranscriptMessage','struct AppTranscriptTool','struct AppTranscriptSubagent','struct AppSubagentSession')
    header='''#![allow(dead_code,unused_imports,unreachable_patterns)]
use serde::{Serialize,Deserialize};
use serde_json::Value;
use uuid::Uuid;
use std::{fmt,borrow::Cow,path::PathBuf,collections::{HashMap,HashSet},io::{BufRead,BufReader,Seek,Write},fs::File};
type Result<T> = std::result::Result<T,Box<dyn std::error::Error>>;
mod domain {pub use super::*;}
mod contracts {pub use super::*;}
mod model_standard {pub use super::*;}
mod core {pub use super::*;}
macro_rules! ensure {($expr:expr,$msg:literal)=>{if !$expr {return Err($msg.into());}};}
'''
    stage=read(STAGE)
    header+=types+section(stage,'const MAX_STAGED_ROOTS','pub(crate) fn is_display_kind')
    header+='struct DisplayRecords { file:File,count:usize }\nimpl DisplayRecords {\n'+section(stage,'    pub(crate) fn scan(').replace('anyhow::ensure!','ensure!')
    out.mkdir(parents=True,exist_ok=True)
    for tag,root in [('stock',orig),('candidate',changed)]:
        def app(f):return (root/(APP+f+'.rs')).read_text()
        tr=section(app('transcript'),'fn append_transcript_parts', '#[cfg(test)]\nmod tests {')
        rows=section(app('transcript/rows'),'#[derive(Default)]').replace('#[cfg(test)]\nmod tests;','')
        j=section(app('transcript/journal'),'struct TranscriptReplay {','#[cfg(test)]\nmod tests;')
        t=section(app('transcript/journal/timestamps'),'#[derive(Clone, Copy, Default)]','#[cfg(test)]\nmod tests;')
        u=section(app('transcript/journal/source'),'pub(super) fn transcript_from_scan','#[cfg(test)]\npub(super) fn from_records')
        out.joinpath(tag+'.rs').write_text('use super::*;\n'+rows+tr+'\nmod journal {use super::*;use std::{hash::Hash,num::NonZeroU64};\n'+t+j+'\nmod src {use super::*;\n'+u+
         '''pub(in super::super) fn drive(stage:&mut DisplayRecords,roots:HashMap<TurnId,ThreadId>,live:Option<TurnId>,general:bool,observer:&mut dyn FnMut(&mut JournalRecord)) -> Result<Vec<AppTranscriptMessage>>{
         let mut scan=|visit:&mut dyn FnMut(JournalRecord)->Result<()>| {stage.scan(|mut record|{observer(&mut record);if TIMED.get(){let before=cpu();let out=visit(record);INNER.set(INNER.get()+cpu()-before);out}else{visit(record)}})?;if LATE.get(){return Err("injected late scan error".into());} Ok(())};
         if general {transcript_from_scan(scan,live)} else {render_causal(&mut scan,live,TranscriptVisibility{root_threads:roots,certified_text_responses:true,..Default::default()})}
         }
}
pub(super) use src::drive;
}
pub(super) fn run(stage:&mut DisplayRecords,roots:HashMap<TurnId,ThreadId>,live:Option<TurnId>,general:bool,observer:&mut dyn FnMut(&mut JournalRecord))->Result<Vec<AppTranscriptMessage>>{journal::drive(stage,roots,live,general,observer)}
''')
    (out/'main.rs').write_text(header+'\nmod stock; mod candidate;\n'+(Path(__file__).parent/'exercise.rs').read_text())
