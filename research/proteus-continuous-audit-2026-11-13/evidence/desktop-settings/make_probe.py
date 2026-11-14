from pathlib import Path
import hashlib
root=Path(__file__).resolve().parents[1]
out=root/'audit-state-edges/probe'
mod=root/'src/ui/settings/mod.rs'
save=root/'src/ui/settings/save.rs'
extracted=[]
def method(file,name):
 s=file.read_text(); start=s.index('    ', s.index('\n',s.index('impl SettingsView'))+1) if False else 0
 import re
 m=re.search(r'    (?:pub\([^)]*\) )?fn '+name+r'\(',s); assert m,name
 start=m.start(); brace=s.index('{',m.end()); n=1; i=brace+1
 while n:
  if s[i]=='{': n+=1
  if s[i]=='}': n-=1
  i+=1
 chunk=s[start:i]
 extracted.append(f'{file.relative_to(root)}:{s[:start].count(chr(10))+1}-{s[:i].count(chr(10))+1} {hashlib.sha256(chunk.encode()).hexdigest()}')
 return chunk
methods='\n\n'.join(method(mod,n) for n in ['accept','snapshot','dirty','has_unsaved_changes','can_save','has_errors','update_draft','replace_draft','discard','forget_editors','clear_feedback'])+'\n\n'+method(save,'accept_save')
s=mod.read_text(); start=s.index('                this.reloading = false;'); end=s.index('\n            })',start)
callback=s[start:end]
extracted.append(f'src/ui/settings/mod.rs:{s[:start].count(chr(10))+1}-{s[:end].count(chr(10))+1} {hashlib.sha256(callback.encode()).hexdigest()}')
header='''#![allow(dead_code)]
mod probe {
use std::collections::HashSet;
use std::marker::PhantomData;
use proteus_contracts::app_protocol::{config_builder::ConfigBuilderSnapshot, addons::AppAddonsSnapshot};
use settings::draft::Draft;
use settings::mcp::mcp_problems;
pub mod settings {
'''
for n in ['mcp','draft','addons']:
 header+=f'    #[path = "{root}/src/settings/{n}.rs"] pub mod {n};\n'
header+='''}
#[derive(Default)] struct Context<T>(PhantomData<T>);
impl<T> Context<T> { fn notify(&mut self) {} }
#[derive(Default)] struct Editors { error: bool }
impl Editors { fn has_errors(&self)->bool {self.error} }
#[derive(Default)] struct Catalogs {busy:bool}
#[derive(Default)] enum LoadState { #[default] Unavailable, Loading, Failed(String), Ready(Box<ConfigBuilderSnapshot>) }
#[derive(Default)] struct SettingsView {
 state: LoadState, baseline: Draft, draft: Draft, editors: Editors, catalogs: Catalogs,
 saving:bool, reloading:bool, edit_revision:u64, catalog_conflict:Option<String>,
 json:HashSet<(String,String)>, feedback:Option<String>, feedback_timer:Option<()>
}
impl SettingsView {
 fn addons(&self)->Option<&AppAddonsSnapshot>{None}
 fn show_feedback(&mut self,text:impl Into<String>,_:bool,_:&mut Context<Self>){self.feedback=Some(text.into());}
'''
footer='''
 fn complete_reload(&mut self, result:anyhow::Result<ConfigBuilderSnapshot>, cx:&mut Context<Self>) {
  let this=self;
'''+callback+'''
 }
}
#[cfg(test)] #[path="/workspace/shared/desktop-state-edges-audit/audit-state-edges/probe/src/tests.rs"] mod tests;
}
'''
(out/'src/lib.rs').write_text(header+methods+footer)
(out/'Cargo.toml').write_text('''[package]
name="desktop-state-edges-probe"
version="0.0.0"
edition="2024"
[workspace]
[dependencies]
proteus-contracts={path="/workspace/shared/proteus-toolchain/cargo/git/checkouts/proteus-core-7355afd4bdf4a66a/5e8b6ae/crates/proteus-contracts"}
serde_json="1"
anyhow="1"
[profile.dev]
debug=0
''')
(root/'audit-state-edges/extraction.txt').write_text('\n'.join(extracted)+'\n')
