"""Native projected changes-tree interactions; only synthetic values, no Git subprocess, repository or filesystem listing."""
from pathlib import Path
import argparse,subprocess,tempfile
p=argparse.ArgumentParser();p.add_argument('desktop_file',type=Path);p.add_argument('phase',choices=['baseline','guard','final']);p.add_argument('deps',type=Path);p.add_argument('--rustc',default='rustc');p.add_argument('--extensions',type=Path);p.add_argument('--desktop-schema',type=Path);p.add_argument('--extra-method',action='append',default=[]);a=p.parse_args()
d=Path(__file__).resolve().parent;frags=d.parent/'source'
def block(s,n):
 i=s.index(n);b=s.index('{',i);j=b+1;depth=1
 while depth:depth+=int(s[j]=='{')-int(s[j]=='}');j+=1
 return s[i:j]
def between(s,left,right):return s[s.index(left):s.index(right,s.index(left))]
def src(name,path):return ((a.extensions/path) if a.extensions else (frags/(name+'.rs'))).read_text()
panel=src('change_rows','packages/git/src/panel.rs');helpers=src('panel_helpers','packages/git/src/panel.rs');model=src('model','packages/git/src/model.rs');handler=src('header_event','packages/git/src/list.rs');sdk=src('tree_sdk','sdk/src/ui.rs')
t=a.desktop_file.read_text();rawset=between(t,'let previous = self.rows.get(self.cursor)','        for fold in folds')
keys=block(t,'fn step(')+'\n'+block(t,'fn key(')+'\n'+'\n'.join(block(t,'fn '+n+'(') for n in a.extra_method)
for n in ['tree','tree_header','stats']:assert block(sdk,'pub fn '+n+'(')
evt=block(handler,'if let Some(section) = identity.strip_prefix("section:")')
evt=evt.replace('"check" => return self.check_section(host, section, entries),','"check" => unreachable!("this pure header interaction never uses checkbox data"),')
body=(d/'frame.rs.in').read_text()
subs={'ACT':block(t,'fn act('),'VALUE':src('value','sdk/src/value.rs'),'HEADER':'\n'.join(block(sdk,'pub fn '+n+'(') for n in ['tree','tree_header','stats']),'MODEL':between(model,'#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]','/// Counts behind the panel'),'HELPERS':'\n'.join(block(helpers,n) for n in ['pub fn status_label(','pub fn status_icon(','fn row_id(']),'CHANGE_ROWS':block(panel,'pub fn change_rows('),'HANDLER':evt,'ISHEADER':block((a.desktop_schema or frags/'is_header.rs').read_text(),'pub fn header('),'NEW':between(t,'tree.cursor = tree.rows.iter().position','        tree\n'),'RECONCILE':rawset,'KEYS':keys}
for name,s in subs.items():body=body.replace('/*'+name+'*/',s)
body='const PHASE:&str="'+a.phase+'";\n'+body.replace('#![allow(dead_code)]','')
with tempfile.TemporaryDirectory() as tmp:
 f=Path(tmp)/'probe.rs';f.write_text(body);exe=f.with_suffix('');rl=next(a.deps.glob('libserde_json-*.rlib'))
 subprocess.run([a.rustc,'--edition=2024','-Awarnings','-L','dependency='+str(a.deps),'--extern','serde_json='+str(rl),f,'-o',exe],check=True);subprocess.run([exe],check=True)
