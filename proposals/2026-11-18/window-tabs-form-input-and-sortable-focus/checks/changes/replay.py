"""Compile exact bounded public UI functions into a synthetic data-only Rust probe."""
from pathlib import Path
import argparse,subprocess,tempfile
p=argparse.ArgumentParser()
p.add_argument('deps',type=Path,help='existing serde_json rlib and transitive deps')
p.add_argument('--rustc',default='rustc');p.add_argument('--extensions',type=Path,required=True)
p.add_argument('--desktop-tree',type=Path,required=True);p.add_argument('--desktop-schema',type=Path,required=True)
a=p.parse_args();d=Path(__file__).resolve().parent
def block(s,n):
 i=s.index(n);b=s.index('{',i);j=b+1;dep=1
 while dep:dep+=int(s[j]=='{')-int(s[j]=='}');j+=1
 return s[i:j]
def between(s,start,end):return s[s.index(start):s.index(end,s.index(start))]
def ext(k,path):return (a.extensions/path).read_text()
panel=ext('change_rows','packages/git/src/panel.rs');helpers=ext('panel_helpers','packages/git/src/panel.rs');model=ext('model','packages/git/src/model.rs');sdk=ext('tree_sdk','sdk/src/ui.rs')
handler=ext('record_selection','packages/git/src/list.rs');handler=handler[handler.index('let path = panel::row_path(identity);'):].split('self.selected = Some(identity.to_owned());')[0]+'self.selected = Some(identity.to_owned());'
tree=a.desktop_tree.read_text()
recon=between(tree,'let previous = self.rows.get(self.cursor)','        for fold in folds')
subs={'ROWS':block(panel,'pub fn change_rows('),'HELPERS':'\n'.join(block(helpers,n) for n in ('pub fn row_path(','fn row_id(','pub fn status_label(','pub fn status_icon(')),'MODEL':between(model,'#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]','/// Counts behind the panel'),'SDK':'\n'.join(block(sdk,'pub fn '+n+'(') for n in ('tree_header','stats')),'VALUE':ext('value','sdk/src/value.rs'),'REC':handler,'RECON':recon,'HEADER':block(a.desktop_schema.read_text(),'pub fn header('),'TREE':'\n'.join(block(tree,'fn '+n+'(') for n in ('step','act','key'))}
body=(d/'frame.rs.in').read_text()
for k,val in subs.items():body=body.replace('/*'+k+'*/',val)
with tempfile.TemporaryDirectory() as t:
 t=Path(t);f=t/'probe.rs';f.write_text(body);exe=t/'probe'
 rl=next(a.deps.glob('libserde_json-*.rlib'))
 subprocess.run([a.rustc,'--edition=2024','-Awarnings','-L','dependency='+str(a.deps),'--extern','serde_json='+str(rl),f,'-o',exe],check=True)
 subprocess.run([exe],check=True)
