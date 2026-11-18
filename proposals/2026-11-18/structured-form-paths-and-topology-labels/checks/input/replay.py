"""Native projected form and one-line normalization; offline code/data only."""
from pathlib import Path
import argparse,subprocess,tempfile
p=argparse.ArgumentParser()
for key in ['desktop-fields','desktop-render','desktop-input-state','sdk-ui','serde-json']:p.add_argument('--'+key,type=Path,required=True)
p.add_argument('--rustc',default='rustc');a=p.parse_args()
def block(s,k):
 i=s.index(k);b=s.index('{',i);j=b+1;d=1
 while d:d+=int(s[j]=='{')-int(s[j]=='}');j+=1
 return s[i:j]
fields=a.desktop_fields.read_text();rend=a.desktop_render.read_text();sdk=a.sdk_ui.read_text();state=a.desktop_input_state.read_text()
# Ground the pure method in the actual programmatic set_value path for a fresh editor (not replaying undo).
for name,callees in [('pub fn set_value(',['self.replace_text(', 'self.reset_selection();','self.undo_manager.clear();']),('fn replace_text(',['this.replace_text_in_range_silent(']),('pub(crate) fn replace_text_in_range_silent(',['self.replace_text_in_range(']),('fn replace_text_in_range(',['self.normalize_input(new_text)'])]:
 s=block(state,name);assert all(c in s for c in callees)
idx=fields.index('            Node::Input {\n                id,\n                value,');arm=fields[idx:fields.index('            Node::Code {\n',idx)]
r=rend.index('            Node::Input {\n                id,\n                search: true,');search=rend[r:rend.index('            Node::Input {',r+20)]
assert 'super::fields::Text::Area(_) => None' in search and 'kit::input(state)' in rend and 'super::fields::textarea::render(' in rend
search=search.replace('crate::ui::search::','crate::fake_ui::search::')
prune=block(fields,'pub(super) fn prune_fields(')
ib=prune.index('Node::Input { id, .. } => {');ie=prune.index('\n            }',ib)+14
ids=prune[ib:ie]
ret=prune.index('self.fields\n            .inputs\n            .retain(');retain=prune[ret:prune.index(';',ret)+1]
props=block(fields,'pub(super) struct TextInput {').split('{',1)[1].rsplit('}',1)[0]
parts={'IDS':ids,'RETAIN':retain,'SEARCH':search,'SDK':'\n'.join(block(sdk,n) for n in ['pub trait Node','impl Node for Value','pub fn input(','pub fn search(']),'NORMALIZE':block(state,"fn normalize_input<'a>("),'ARM':arm,'INPUT_PROPS':props}
s=Path(__file__).with_name('frame.rs.in').read_text()
for k,v in parts.items():s=s.replace('/*'+k+'*/',v)
with tempfile.TemporaryDirectory() as tmp:
 t=Path(tmp);src=t/'probe.rs';src.write_text(s);exe=t/'probe'
 subprocess.run([a.rustc,'--edition=2024','-Awarnings',src,'--extern','serde_json='+str(a.serde_json),'-L','dependency='+str(a.serde_json.parent),'-o',exe],check=True)
 subprocess.run([exe],check=True)
