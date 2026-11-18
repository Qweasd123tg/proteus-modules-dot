"""Native source gate. Inputs are Core and Desktop checkouts, plus pinned serde/serde_json rlibs with their dependency directory available. Does not build Desktop or access a clipboard."""
import argparse,subprocess,tempfile
from pathlib import Path
p=argparse.ArgumentParser()
for a in ['core','desktop','serde','serde_json']:p.add_argument(a,type=Path)
p.add_argument('--rustc',default='rustc');p.add_argument('--expect',choices=['before','after'],required=True);a=p.parse_args()
def fun(s,k):
 i=s.index(k);start=s.index('{',i);d=1;j=start
 while d:j+=1;d+=(s[j]=='{')-(s[j]=='}')
 return s[i:j+1]
co=(a.core/'crates/proteus-contracts/src/domain/config_schema.rs').read_text().split('impl ModuleConfigSchema {',1)[0];d=a.desktop;ss=(d/'src/settings/schema.rs').read_text();tags=(d/'src/ui/settings/tags.rs').read_text()
s='\n'.join([ss[ss.index('#[derive(Clone, Copy, Debug, PartialEq, Eq)]'):ss.index('pub fn choice_title')], fun(ss,'pub fn format_value('),fun(ss,'pub fn parse_text('),fun(tags,'pub(super) fn is_tag_field(').replace('pub(super) ','',1),fun(tags,'fn added_value(')])
ff=(d/'src/ui/settings/fields.rs').read_text();ed=(d/'src/ui/settings/editors.rs').read_text();inputstate=(d/'vendor/gpui-base/src/input/base/state.rs').read_text()
assert 'let tagged = super::tags::is_tag_field(field);' in ff and 'if tagged {\n            self.string_tags' in ff
assert 'if super::tags::is_tag_field(field)' in ed and 'tags: Some(field.clone())' in ed and 'InputState::new(window, cx).placeholder("Добавить' in ed and 'TextInput::Line(state)' in ed and 'else if format.is_multiline()' in ed and 'TextareaState::new(window, cx)' in ed
assert 'if !self.is_multi_line() {' in inputstate
conversion=next(x.strip() for x in inputstate.splitlines() if "new_text = new_text.replace('\\n'," in x)
spec=(Path(__file__).with_name('matrix.rs.in').read_text().replace('/*CORE*/',co).replace('/*DESKTOP*/',s).replace('/*ONE-LINE*/',conversion))
with tempfile.TemporaryDirectory() as temp:
 t=Path(temp);f=t/'main.rs';f.write_text(spec)
 subprocess.run([a.rustc,'--edition=2024','--cfg',a.expect,'-A','dead_code',str(f),'--extern','serde='+str(a.serde.resolve()),'--extern','serde_json='+str(a.serde_json.resolve()),'-L','dependency='+str(a.serde.resolve().parent),'-o',str(t/'check')],check=True)
 subprocess.run([str(t/'check')],check=True)
