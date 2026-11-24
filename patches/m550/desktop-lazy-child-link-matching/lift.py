from pathlib import Path
def between(s,a,b):
    assert s.count(a)==1,a
    i=s.index(a)
    return s[i:s.index(b,i)]
def lift(sources,dst,packet):
    dst.mkdir(parents=True,exist_ok=True)
    t=sources['src/transcript/mod.rs']; text=(
      t[t.index('use std::'):t.index('use proteus_contracts')]
      +'use crate::app_protocol::{AppTranscriptMessage,AppTranscriptSubagent,AppTranscriptTool};\nuse crate::domain::{ImageRef,MessageId,ThreadId};\n'
      +between(t,'#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash)]\npub enum Role','    /// Records `at` (Unix milliseconds)').replace('    #[cfg(test)]\n    text_work: text_run::TextWork,\n','')
      +between(t,'    fn stop_streaming(','fn delta_keep(')
      +between(t,'/// Whether a row renders the same','\nmod cache;')
      +'\nmod cache;mod chains;pub mod subagent;\npub use cache::window_changes;pub use chains::{tool_chain,affected_rows};pub(crate) use chains::tool_run;\n')
    (dst/'transcript.rs').write_text(text.replace('        #[cfg(test)]\n        self.text_work.clone_from(&live.text_work);\n','')+'''
#[cfg(test)]
impl Transcript {
    pub(crate) fn proof_slots(&self) -> (usize, usize, usize) {
        (self.entries.len(), self.entries.capacity(), self.entries.as_ptr() as usize)
    }
    pub(crate) fn proof_reserve_to(&mut self, capacity: usize) {
        self.entries.reserve_exact(capacity - self.entries.len());
    }
    pub(crate) fn proof_window_state_matches(&self, live: &Self) -> bool {
        Arc::ptr_eq(&self.next_key, &live.next_key)
            && self.turn_thread == live.turn_thread
            && self.snapshot_root_known == live.snapshot_root_known
            && self.external_ids == live.external_ids
    }
}
''')
    (dst/'transcript').mkdir(exist_ok=True)
    cache=sources['src/transcript/cache.rs']
    key='    pub fn retained_bytes(&self) -> usize {'
    assert cache.count(key)==1
    (dst/'transcript/cache.rs').write_text(cache.replace(key,key+'\n        #[cfg(test)] crate::meter::charge_visit();').replace('fn value_bytes(value: &Value) -> usize {','fn value_bytes(value: &Value) -> usize {\n    #[cfg(test)] crate::meter::value_visit();'))
    base='crates/proteus-contracts/src/'
    def read(f):return sources[base+f]
    def typ(f,token):
        raw=read(f);i=raw.index(token)
        return raw[raw.rindex('#[derive(',0,i):raw.index('\n}',i)+2]
    (dst/'app_protocol.rs').write_text(read('app_protocol/transcript.rs')+'\nmod live {use super::*; use crate::domain::SessionId; use serde::{Serialize,Deserialize};\n'+read('app_protocol/live.rs').split('/// Session subscription baseline',1)[1].join(['/// Session subscription baseline',''])+'\n}\npub use live::*;\n')
    (dst/'domain.rs').write_text('use std::path::PathBuf;use serde::{Deserialize,Serialize};use uuid::Uuid;\n'+''.join(between(read('domain/ids.rs'),f'pub type {n} = ','\n')+'\n' for n in ('MessageId','ThreadId','SessionId'))+typ('domain/image.rs','pub struct ImageRef')+'\n'+typ('domain/run_options.rs','pub struct RunOptions')+'\n'+typ('domain/tool.rs','pub enum PermissionMode'))
    (dst/'contracts.rs').write_text('use serde::{Deserialize,Serialize};use uuid::Uuid;\n'+typ('contracts/tool_terminal.rs','pub struct ToolTerminalRef'))
    (dst/'model_standard.rs').write_text('use serde::{Deserialize,Serialize};\n'+typ('model_standard/content_part.rs','pub enum MessagePhase'))
    scroll=sources['src/ui/chat/scroller/scrollbar.rs']
    (dst/'scroller.rs').write_text(between(scroll,'#[derive(Clone, Copy, Debug, PartialEq, Eq)]\npub(crate) struct HistoryRange','#[derive(Clone, Copy, Default)]\nstruct State'))
    raw=sources['src/ui/chat/history/context.rs']
    context=(between(raw,'pub(super) struct ContextSeek','#[derive(Debug, PartialEq)]')+between(raw,'impl ContextSeek {','    fn step(')+'}\n'
        +'impl History {\n'+between(raw,'    pub(super) fn context_visible(','\n}\n\nimpl Chat')+'\n}\n')
    hist=sources['src/ui/chat/history.rs']
    history=('use std::ops::Range;\nuse crate::{app_protocol::{AppTranscriptMessage,AppTranscriptPage,AppTranscriptCursor},transcript::{Change,Transcript,window_changes},scroller::{HistoryRange,ScrollTarget}};\n'
       +between(hist,'const PAGE_ROWS:','\nimpl Chat {')+context+'#[cfg(test)] mod tests;\n')
    (dst/'history.rs').write_text(history)
    (dst/'history').mkdir(exist_ok=True)
    tests=sources['src/ui/chat/history/tests.rs'].split('#[test]')
    (dst/'history/tests.rs').write_text(tests[0]+''.join('#[test]'+seg for seg in tests[1:] if 'gpui_kit::' not in seg))
    (dst/'exercise.rs').write_bytes((packet/'exercise.rs').read_bytes())
    (dst/'meter.rs').write_bytes((packet/'meter.rs').read_bytes())
    (dst/'transcript/chains.rs').write_text(sources['src/transcript/chains.rs'])
    sa=sources['src/transcript/subagent.rs']
    mark='let session = AppSubagentSession::deserialize'
    assert sa.count(mark)==1
    sa=sa.replace(mark,'#[cfg(test)] crate::meter::decode_visit();\n    '+mark)
    (dst/'transcript/subagent.rs').write_text(sa)
    st=sources['src/ui/chat/stamp.rs'];st_tests=st.split('    fn transcript(roles:',1)[1]
    (dst/'stamp.rs').write_text('use crate::transcript::{Entry,Role};\n'
     +between(st,'pub(super) fn hidden','/// The time of row')
     +'#[cfg(test)] mod tests {\n    fn transcript(roles:'+st_tests)
    (dst/'row_layout.rs').write_text(sources['src/ui/chat/row_layout.rs'])
    dom=dst/'domain.rs'
    tools=read('domain/tool.rs')
    tool_call=between(tools,'#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]\n#[serde(deny_unknown_fields)]\n#[non_exhaustive]\npub struct ToolCall {','/// Canonical pre-invocation resolution')
    tool_more=between(tools,'#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq, Default)]\n#[serde(rename_all = "snake_case")]\n#[non_exhaustive]\npub enum ToolCallSurface {','#[cfg(test)]')
    dom.write_text(dom.read_text()+'\n'+between(read('domain/ids.rs'),'pub type CallId = ','\n')+'\n'+tool_call+tool_more+'\n'+typ('domain/subagent.rs','pub struct SubagentSessionBinding'))
    cb='crates/proteus-core/src/app_server/'
    core=sources[cb+'transcript.rs']
    raw=sources[cb+'transcript/journal.rs']
    finish=between(raw,'    fn finish(mut self) -> Vec<AppTranscriptMessage>','\n}\n\n#[derive(Default)]\nstruct TranscriptVisibility')
    rows=sources[cb+'transcript/rows.rs']
    (dst/'core_projection').mkdir(exist_ok=True)
    (dst/'core_projection/rows.rs').write_text(rows.replace('#[cfg(test)]\nmod tests;',''))
    (dst/'core_projection.rs').write_text('''use std::collections::HashMap;
use serde_json::Value;
use crate::{app_protocol::{AppTranscriptMessage,AppTranscriptTool,AppTranscriptPage},
domain::{CallId,ToolCall,ToolResult,SubagentSessionBinding}};
mod rows;use rows::TranscriptRows;
#[derive(Default)] struct State {transcript: TranscriptRows}
#[derive(Default)] pub(crate) struct JournalProof {
    state: State,
    subagent_bindings: HashMap<CallId, SubagentSessionBinding>,
}
impl JournalProof {
    pub(crate) fn push(&mut self,row:AppTranscriptMessage){self.state.transcript.push(row);}
    pub(crate) fn record(&mut self,call:ToolCall,result:ToolResult,binding:SubagentSessionBinding){
        append_transcript_tool_call(&mut self.state.transcript,&call);
        append_transcript_tool_result(&mut self.state.transcript,&result);
        self.subagent_bindings.insert(binding.source_call_id.clone(),binding);
    }
    pub(crate) fn page(self)->AppTranscriptPage{
        let messages=self.finish();
        let revision="synthetic-readonly".to_owned();
        let total=messages.len();
        let end=total;
'''
      +between(sources[cb+'read_model.rs'],'    let start = end.saturating_sub(50);','\n}\n\n#[cfg(unix)]')
      .replace('Ok(proteus_contracts::app_protocol::AppTranscriptPage {','AppTranscriptPage {').replace('    })','    }')
      +'\n}\n'+finish+'\n}\n'
      +between(core,'fn append_transcript_tool_call','fn append_hosted_tool_activity')
      +between(core,'fn append_transcript_tool_result','fn transcript_role'))
    (dst/'lib.rs').write_text('#![allow(dead_code,unused_imports)]\nextern crate self as proteus_contracts;\nmod app_protocol;mod domain;mod contracts;mod model_standard;mod transcript;mod scroller;mod history;mod stamp;mod row_layout;mod core_projection;\n#[cfg(test)] mod meter;#[cfg(test)] mod exercise;')
    (dst/'history.rs').write_text((dst/'history.rs').read_text()+'''
#[cfg(test)]
pub(crate) fn present_page(page: AppTranscriptPage) -> (Transcript, HistoryRange, Vec<Change>) {
    assert_eq!(page.start+page.messages.len(),page.total);
    let cursor = AppTranscriptCursor { revision: page.revision, before: page.start, base: page.base };
    let mut history=History::default();
    let mut transcript=Transcript::default();
    let (_, changes)=history.apply(&mut transcript,page.messages,Some(cursor));
    let range=history.range(&transcript).unwrap();
    (transcript, range, changes)
}
''')
