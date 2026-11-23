"""Compile source-bound renderer and locked wire DTOs; only JournalEntry's irrelevant
hook, request and context variants are removed, not their exercised dependencies."""
from pathlib import Path
import json

APP='crates/proteus-core/src/app_server/'
C='crates/proteus-contracts/src/'
SNAP='crates/proteus-core/src/core/session_store/remote/snapshot.rs'
STAGE=SNAP[:-3]+'/display_records.rs'
FIX='crates/proteus-core/examples/session_index_fixture.rs'
STORAGE='contracts/session_storage'
SOURCES=list(json.loads((Path(__file__).resolve().parent/'source-pins.json').read_text()))
def method(s,sig):
    at=s.index(sig)
    return s[at:s.index('\n    }',at)+6]+'\n'
def write(out,p,text):
    p=out/p
    p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(text)


def section(s,a,b=None):
    i=s.index(a)
    return s[i:] if b is None else s[i:s.index(b,i+len(a))]
def decl(s,signature):
    i=s.index(signature)
    return s[s.rindex('#[derive(',0,i):s.index('\n}',i)+2]+'\n'

def generate(orig,changed,out,composition=None):
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
    journal=source('storage/journal')
    types+=d('storage/journal','enum JournalKind')
    types+=section(journal,'impl JournalKind {','#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]')
    km=method(journal,'    pub fn kind(&self)')
    km='\n'.join(x for x in km.splitlines() if not x.strip().startswith(tuple('Self::'+v for v in omitted)))
    types+='impl JournalEntry {\n'+km+'\n}\n'
    types+=d(STORAGE,'struct SessionLocator','struct StorageRevision','struct StorageSnapshot','struct StorageRecordPage')
    fix=read(FIX)
    types+='const SCHEMA:u32='+journal.split('pub const JOURNAL_SCHEMA_VERSION: u32 = ',1)[1].split(';')[0]+';\n'
    body=section(fix,'    let messages: Vec<_> = (0..rows)','    let thread_id = new_thread_id();')
    assert 'CanonicalMessage::text' in body and '.repeat(repeats)' in body
    types+='fn published_seed_messages(rows:usize,repeats:usize)->Vec<CanonicalMessage>{\n'+body+'messages\n}\n'
    cp=source('model_standard/content_part')
    types+='impl CanonicalPart {\n'+method(cp,'    pub fn new(provenance:')+'}\n'
    types+='impl CanonicalMessage {\n'+method(cp,'    pub fn text(role:')+method(cp,'    pub fn new(role:')+method(cp,'    pub fn from_parts(role:')+'}\n'+section(cp,'fn default_part_semantics(','#[cfg(test)]')
    header='''#![allow(dead_code,unused_imports,unreachable_patterns)]
use serde::{Serialize,Deserialize};
use serde_json::Value;
use uuid::Uuid;
use std::{fmt,borrow::Cow,path::PathBuf,collections::{HashMap,HashSet},io::{BufRead,BufReader,Seek,Write},fs::File};
use anyhow::{Result,bail,ensure};
fn new_part_id()->PartId { next_id() }
fn new_message_id()->MessageId { next_id() }
mod domain {pub use super::*;}
mod contracts {pub use super::*;}
mod model_standard {pub use super::*;}
mod core {pub use super::*;}
'''
    header+=types
    parent=Path(__file__).resolve().parent
    arms=[('stock',orig),('candidate',changed),('baseline',composition.parent/'composition_base' if composition else orig),('composed',composition or changed)]
    for tag,root in arms:
        def fetch(p):
            f=root/p
            return f.read_text() if f.is_file() else read(p)
        def app(f):return fetch(APP+f+'.rs')
        st=fetch(STAGE)
        st=st.replace('pub(in crate::core::session_store::remote)', 'pub(super)')
        # Test-local instrumentation at exact callback boundary; scanner and failures untouched.
        st=st.replace('            consume(serde_json::from_slice(&line)?)?;', '            let record = serde_json::from_slice(&line)?;\n            consume(record)?;')
        marker='            consume(record)?;'
        assert st.count(marker)==1
        st=st.replace(marker,'            crate::live_checkpoint(0);\n'+marker).replace('            count += 1;','            crate::live_checkpoint(2);\n            count += 1;')
        st+=r"""
impl DisplayRecords {
    pub(super) fn replay_roots(&self)->Option<RootBindings>{self.causal_roots.clone()}
    pub(super) fn rearm_roots(&mut self,roots:Option<RootBindings>){self.causal_roots=roots;}
    pub(super) fn fail_read(&mut self){
        let tmp=tempfile::NamedTempFile::new().unwrap();
        self.file=std::fs::OpenOptions::new().write(true).open(tmp.path()).unwrap();
    }
    pub(super) fn zero_seq(&mut self,record:&JournalRecord){
        self.file.rewind().unwrap();self.file.set_len(0).unwrap();
        let mut r=record.clone();r.session_seq=0;serde_json::to_writer(&mut self.file,&r).unwrap();self.file.write_all(b"\n").unwrap();
    }
    pub(super) fn test_last(&self)->u64{self.file.metadata().unwrap().len()}
    pub(super) fn corrupt(&mut self, mode:&str, extra:&JournalRecord) {
        match mode {
            "short"=>self.file.set_len(0).unwrap(),
            "wrong-count"=>self.count+=1,
            "non-lf"|"parse"|"extra"=>{
                self.file.seek(std::io::SeekFrom::End(0)).unwrap();
                match mode {
                    "non-lf"=>self.file.write_all(b"{").unwrap(),
                    "parse"=>self.file.write_all(b"garbage\n").unwrap(),
                    "extra"=>{serde_json::to_writer(&mut self.file,extra).unwrap();self.file.write_all(b"\n").unwrap();},
                    _=>unreachable!(),
                }
            },
            _=>unreachable!()
        }
    }
}
"""
        write(out,f'{tag}/stage.rs',st)
        tr=section(app('transcript'),'fn append_transcript_parts', '#[cfg(test)]\nmod tests {')
        rows=section(app('transcript/rows'),'#[derive(Default)]').replace('#[cfg(test)]\nmod tests;','')
        j=section(app('transcript/journal'),'struct TranscriptReplay {','#[cfg(test)]\nmod tests;')
        t=section(app('transcript/journal/timestamps'),'#[derive(Clone, Copy, Default)]','#[cfg(test)]\nmod tests;')
        snap=fetch(SNAP)
        u=section(app('transcript/journal/source'),'pub(crate) fn journal_transcript_from_source', '#[cfg(test)]\npub(super) fn from_records')
        # Observe collection and rendered-row live bytes within the unchanged renderer's callback.
        tag_start=u.index('fn render_causal(')
        collect='        replay.state.timestamps.collect_record::<false>(&record);'
        assert u[tag_start:].count(collect)==1
        u=u[:tag_start]+u[tag_start:].replace(collect,collect+'\n        crate::live_checkpoint(1);')
        # Record which branch actually ran without querying the stage twice.
        if 'self.uniform_message_date = Some(at.timestamp_ms);' in t:
            t=t.replace('self.uniform_message_date = Some(at.timestamp_ms);','self.uniform_message_date = Some(at.timestamp_ms);\n            crate::hit();')
        methods=''.join(method(snap,x) for x in ('    pub(crate) fn open(store:','    pub(crate) fn scan(&mut self,','    pub(crate) fn take_staged_causal_roots(','    pub(crate) fn scan_display(','    fn scan_from('))
        snapstr=section(snap,'pub(crate) struct RemoteJournalSnapshot {','impl std::fmt::Debug')
        actual_open=method(snap,'    pub(crate) fn open_for_display(')+method(snap,'    fn open_projected_display(')
        layer=snapstr+'type JournalReadSnapshot = RemoteJournalSnapshot;\nimpl RemoteJournalSnapshot {\n'+methods+'}\n'
        layer+='struct RemoteValidatedRead {source:RemoteJournalSnapshot,resume:ResumeState,prefix_history_fingerprints:Option<Vec<[u8;32]>>}\n'
        layer+='impl RemoteValidatedRead {\n'+actual_open+(parent/'boundary.rs').read_text()+'}\n'
        write(out,f'{tag}/mod.rs','use super::*;\nmod stage;use stage::{DisplayRecordWriter,DisplayRecords,is_display_kind};\n'+layer+rows+tr+'\nmod journal {use super::*;use std::{hash::Hash,num::NonZeroU64};\n'+t+j+'\nmod src {use super::*;\n'+u+'\n}\npub(super) use src::journal_transcript_from_source;\n}\n'+(parent/'drive.rs').read_text())
    write(out,'main.rs',header+'\nmod stock;mod candidate;mod baseline;mod composed;\n'+(parent/'exercise.rs').read_text())
