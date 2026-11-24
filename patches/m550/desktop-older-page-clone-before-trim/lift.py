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
      +'\nmod cache;\npub use cache::window_changes;\n')
    (dst/'transcript.rs').write_text(text.replace('        #[cfg(test)]\n        self.text_work.clone_from(&live.text_work);\n','')+'''
#[cfg(test)]
impl Transcript {
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
    (dst/'transcript/cache.rs').write_text(cache.replace(key,key+'\n        #[cfg(test)] crate::meter::charge_visit();'))
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
       +between(hist,'const PAGE_ROWS:','\nimpl Chat {')+context+'#[cfg(test)] mod tests;\n#[cfg(test)] mod exercise;\n')
    (dst/'history.rs').write_text(history)
    (dst/'history').mkdir(exist_ok=True)
    tests=sources['src/ui/chat/history/tests.rs'].split('#[test]')
    (dst/'history/tests.rs').write_text(tests[0]+''.join('#[test]'+seg for seg in tests[1:] if 'gpui_kit::' not in seg))
    (dst/'history/exercise.rs').write_bytes((packet/'exercise.rs').read_bytes())
    (dst/'meter.rs').write_bytes((packet/'meter.rs').read_bytes())
    (dst/'lib.rs').write_text('#![allow(dead_code,unused_imports)]\nextern crate self as proteus_contracts;\nmod app_protocol;mod domain;mod contracts;mod model_standard;mod transcript;mod scroller;mod history;\n#[cfg(test)] mod meter;')
