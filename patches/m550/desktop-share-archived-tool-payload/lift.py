from pathlib import Path
def between(s,a,b):
 assert s.count(a)==1,a
 i=s.index(a)
 return s[i:s.index(b,i)]
def lift(s,dst,packet):
 dst.mkdir(parents=True,exist_ok=True)
 for n,v in s.items():
  if n.startswith('src/transcript/'):
   f=dst/n.removeprefix('src/');f.parent.mkdir(parents=True,exist_ok=True);f.write_text(v)
 for n,v in s.items():
  if n.startswith('crates/proteus-contracts/'):
   f=dst.parent.parent/'shared'/n;f.parent.mkdir(parents=True,exist_ok=True);f.write_text(v)
 types=s['src/agents/codex/types.rs']
 (dst/'agents.rs').write_text('pub(crate) mod codex { use serde_json::Value;\n'+
   between(types,'#[derive(Clone, Debug, PartialEq)]\npub struct Item','#[derive(Clone, Debug, PartialEq)]\npub enum CatalogEvent')+'}\n')
 scroll=s['src/ui/chat/scroller/scrollbar.rs']
 (dst/'scroller.rs').write_text(between(scroll,'#[derive(Clone, Copy, Debug, PartialEq, Eq)]\npub(crate) struct HistoryRange','#[derive(Clone, Copy, Default)]\nstruct State'))
 hist=s['src/ui/chat/history.rs']
 history=('use std::ops::Range;\nuse proteus_contracts::app_protocol::{AppTranscriptMessage,AppTranscriptPage,AppTranscriptCursor};\n'
      +'use crate::transcript::{Change,Transcript,window_changes};\nuse crate::scroller::{HistoryRange,ScrollTarget};\n'
      +'mod context;use context::ContextSeek;\n'+between(hist,'const PAGE_ROWS:','\nimpl Chat {')
      +'#[cfg(test)] mod tests;\n#[cfg(test)] mod exercise;\n')
 (dst/'history.rs').write_text(history)
 (dst/'history').mkdir(exist_ok=True)
 t=s['src/ui/chat/history/tests.rs'].split('#[test]')
 (dst/'history/tests.rs').write_text(t[0]+''.join('#[test]'+seg for seg in t[1:] if 'gpui_kit::' not in seg))
 cx=s['src/ui/chat/history/context.rs'].split('\nimpl Chat {',1)[0]
 cx=cx.replace('ChargedRows, Chat, Direction','ChargedRows, Direction').replace('use gpui_kit::*;\n','')
 gui=between(cx,'    #[::core::prelude::v1::test]\n    fn accepted_remote_seek_event_starts_context_resolution','\n}\n\nimpl History')
 cx=cx.replace(gui,'')
 (dst/'history/context.rs').write_text(cx)
 (dst/'history/exercise.rs').write_bytes((packet/'exercise.rs').read_bytes())
 (dst/'meter.rs').write_bytes((packet/'meter.rs').read_bytes())
 stamp=s['src/ui/chat/stamp.rs'];st_tests=stamp.split('    fn transcript(roles:',1)[1]
 (dst/'stamp.rs').write_text('use crate::transcript::{Entry,Role};\n'
   +between(stamp,'pub(super) fn hidden','/// The time of row')
   +'#[cfg(test)] mod tests {\n    fn transcript(roles:'+st_tests)
 (dst/'row_layout.rs').write_text(s['src/ui/chat/row_layout.rs'])
 ts=s['src/ui/chat/thread.rs']
 chain=between(ts,'                    let tools = entries[chain.clone()]','                    let header =').replace('entries[chain.clone()]','entries')
 b=s['src/ui/extensions/session.rs'];cut=between(b,'pub(in crate::ui) fn entries','pub(in crate::ui) fn changed').replace('pub(in crate::ui)','pub(crate)')
 (dst/'bridge.rs').write_text('''use crate::transcript::{Transcript,Entry,Role};
use proteus_contracts::app_protocol::{AppTranscriptTool,AppTranscriptSubagent};
use std::path::Path;
pub(crate) struct Key(pub(crate) bool);
impl Key { fn proteus_dir(&self)->Option<&Path>{self.0.then(||Path::new("/synthetic"))} }
pub(crate) struct Session<'a>{pub(crate) transcript:&'a Transcript,pub(crate) key:Key}
pub(crate) mod session {
   use super::*;
   pub(crate) struct Entry {
       pub(crate) role: &'static str,
       pub(crate) tool: Option<AppTranscriptTool>,
       pub(crate) subagent: Option<AppTranscriptSubagent>,
   }
}
pub(crate) fn chain_tools(entries:&[Entry])->Vec<&AppTranscriptTool> {
'''+chain+'    tools.collect()\n}\n'+cut)
 (dst/'lib.rs').write_text('#![allow(dead_code,unused_imports)]\nmod agents;mod transcript;mod scroller;mod history;mod stamp;mod row_layout;mod bridge;\n#[cfg(test)]mod meter;')
