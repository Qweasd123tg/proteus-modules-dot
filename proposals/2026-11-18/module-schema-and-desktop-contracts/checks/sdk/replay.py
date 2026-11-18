"""Compile only the SDK UI builders, native data schema & row behavior; no GPUI or extension execution."""
from pathlib import Path
import argparse, subprocess,tempfile
p=argparse.ArgumentParser();p.add_argument('extensions',type=Path);p.add_argument('desktop',type=Path);p.add_argument('deps',type=Path);p.add_argument('--rustc',default='rustc');a=p.parse_args()
ui=(a.extensions/'sdk/src/ui.rs').read_text();la=(a.desktop/'src/declarative/lanes.rs').read_text()
ls=(a.desktop/'src/ui/extensions/declarative/list.rs').read_text();rw=(a.desktop/'src/ui/extensions/declarative/rows.rs').read_text()
def body(src,start):
 i=src.index(start);dep=1;b=src.index('{',i);j=b+1
 while dep:dep+=int(src[j]=='{')-int(src[j]=='}');j+=1
 return src[i:j]
docs=ui[ui.index('/// A row of [`lanes`]'):ui.index('pub fn lane_row(')].split('/// ```')
sample=(('\n'.join(x.removeprefix('///').removeprefix(' ') for x in docs[1].splitlines())) if len(docs)>1 else '')
old='a click or Enter sends `{id, event: "open"}`' in ui
assert old == (not sample)
assert 'this.act_at(index, K::clicked(event.click_count()), cx);' in rw
key=body(rw,'fn key(');act=body(rw,'fn act_at(')
method=body(ls,'fn clicked(')
moved=next(line.strip() for line in ls.splitlines() if 'const MOVED:' in line)
subs={'UI':'\n'.join(body(ui,n) for n in ['pub trait Node','impl Node for Value','pub fn lane_row(','pub fn lanes(','pub fn list(','pub fn list_row(']),'SAMPLE':sample+('\ncheck(&view).unwrap();' if sample else ''),'LANES':'\n'.join(x for x in la.splitlines() if not x.startswith('//!')),'OLD':str(old).lower(),'CLICK':method,'MOVED':moved,'KEY':key,'ACT':act}
s=Path(__file__).with_name('probe.rs.in').read_text()
for k,v in subs.items():s=s.replace('/*'+k+'*/',v)
with tempfile.TemporaryDirectory() as td:
 t=Path(td);f=t/'probe.rs';exe=t/'probe';f.write_text(s);cmd=[a.rustc,'--edition=2024','-Awarnings','-L','dependency='+str(a.deps)]
 for name in ['anyhow','serde','serde_json']:
  cmd+=['--extern',name+'='+str(next(a.deps.glob('lib'+name+'-*.rlib')))]
 subprocess.run(cmd+[f,'-o',exe],check=True);subprocess.run([exe],check=True)
