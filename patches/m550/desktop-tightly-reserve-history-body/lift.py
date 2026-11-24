from pathlib import Path

def between(s,a,b):
    assert s.count(a)==1,a
    i=s.index(a)
    return s[i:s.index(b,i)]
def lift(s,dst,packet):
    dst.mkdir(parents=True,exist_ok=True)
    api=s['src/api/mod.rs']
    imports=api[:api.index('use anyhow::')]
    struct=between(api,'#[derive(Clone)]\npub struct Api','impl Api {')
    reads=between(api,'    pub fn history_page(','    pub fn resume(')
    get=between(api,'    fn get<T: DeserializeOwned>','    fn command<B: Serialize')
    get=get.replace('        let _trace = crate::startup_trace::span(path);\n','') # unchanged trace I/O boundary, not under measurement
    mark='        Ok(serde_json::from_str(&body)?)'
    assert get.count(mark)==1
    get=get.replace(mark,'        #[cfg(test)] crate::meter::body(body.len(),body.capacity());\n'+mark)
    helper=between(api,'/// For a fixed-length Core history page,','fn request_id(') if 'fn read_history_body(' in api else ''
    if helper:
        k='        bytes.reserve_exact(size + 1 - bytes.len());'
        helper=helper.replace(k,'        #[cfg(test)] crate::meter::tight_hint(bytes.len()+received,bytes.capacity(),size+1);\n'+k)
    proxy=s['src/api/proxy.rs']
    agent=between(proxy.split('#[cfg(test)]',1)[0],'    let config = ureq::Agent::config_builder()','\n}\n\n')
    agent=agent.replace('super::transport::','transport::')
    (dst/'api.rs').write_text(imports+'''use anyhow::{Result,bail};
use serde::de::DeserializeOwned;
mod transport;
'''+struct+'''impl Api {
    pub(crate) fn local_test(origin: &str) -> Self {
        let timeout=Duration::from_secs(30);
        let proxy=None;
        let agent=(|| {
'''+agent+'''
        })();
        Self {connection_id:1,agent,origin:origin.into(),token:"history-proof".into()}
    }
    #[cfg(test)]
    pub(crate) fn control_get(&self, path: &str) -> Result<crate::app_protocol::AppTranscriptPage> {
        self.get(path,None)
    }
'''+reads+get+'}\n'+helper)
    transport=dst/'api'; transport.mkdir(exist_ok=True)
    (transport/'transport.rs').write_text(s['src/api/transport.rs'])
    base='crates/proteus-contracts/src/'
    def read(f):return s[base+f]
    def typ(f,token):
        raw=read(f);i=raw.index(token)
        return raw[raw.rindex('#[derive(',0,i):raw.index('\n}',i)+2]
    (dst/'app_protocol.rs').write_text(read('app_protocol/transcript.rs'))
    (dst/'domain.rs').write_text('use std::path::PathBuf;use serde::{Deserialize,Serialize};use uuid::Uuid;\n'+''.join(between(read('domain/ids.rs'),f'pub type {n} = ','\n')+'\n' for n in ('MessageId','SessionId'))+typ('domain/image.rs','pub struct ImageRef'))
    (dst/'contracts.rs').write_text('use serde::{Deserialize,Serialize};use uuid::Uuid;\n'+typ('contracts/tool_terminal.rs','pub struct ToolTerminalRef'))
    (dst/'model_standard.rs').write_text('use serde::{Deserialize,Serialize};\n'+typ('model_standard/content_part.rs','pub enum MessagePhase'))
    cm=s['crates/proteus-core/src/app_server/read_model.rs']
    cut=between(cm,'    let start = end.saturating_sub(50);','\n}\n\n#[cfg(unix)]')
    cut=cut.replace('Ok(proteus_contracts::app_protocol::AppTranscriptPage {','AppTranscriptPage {').replace('    })','    }')
    (dst/'core_page.rs').write_text('''use crate::app_protocol::{AppTranscriptPage,AppTranscriptMessage};
pub(crate) fn page(messages:Vec<AppTranscriptMessage>,revision:String,end:usize)->AppTranscriptPage {
    let total=messages.len();
    assert!(end<=total);
'''+cut+'\n}\n')
    for n in ('exercise.rs','meter.rs'):(dst/n).write_bytes((packet/n).read_bytes())
    (dst/'lib.rs').write_text('#![allow(dead_code,unused_imports)]\nextern crate self as proteus_contracts;\nmod api;mod app_protocol;mod domain;mod contracts;mod model_standard;mod core_page;\n#[cfg(test)]mod exercise;\n#[cfg(test)]mod meter;\n')
