"""Native data-only projection of short stock grep records; full tool never invoked."""
from pathlib import Path
import argparse,tempfile,subprocess
p=argparse.ArgumentParser();p.add_argument('--desktop',type=Path,required=True);p.add_argument('--rlib',type=Path,required=True);p.add_argument('--rustc',default='rustc');a=p.parse_args()
h=Path(__file__).resolve().parent;r=h.parent/'refs'
def block(s,k):
 i=s.index(k);b=s.index('{',i);j=b+1;d=1
 while d:d+=(s[j]=='{')-(s[j]=='}');j+=1
 return s[i:j]
d=(a.desktop/'src/tool_display/mod.rs').read_text();ui=(a.desktop/'src/ui/chat/tool_row.rs').read_text()
assert '"find_files" | "grep" => "pattern"' in d
head=d[d.index('    let key = match known {'):d.index('/// Arguments not already shown')].strip()
idx=ui.index('    fn block(');fold=ui[ui.index('        let lines = text.lines().count();',idx):ui.index('        let full = self.full.get(part)',idx)]
assert head.rstrip().endswith('}') # remove enclosing fn closure; synthetic prefix restricts the test to the known grep name
parts={'FUNCS':'\n'.join(block(d,k) for k in ['pub fn other_args(','fn subject_text(','fn limit(','fn arg_preview(','fn single_line(']),'HEAD':head.rstrip().removesuffix('}'),'FOLD':fold,'DETAILS':block(ui,'fn argument_details(')}
s=(h/'replay.rs.in').read_text()
for k,x in parts.items():s=s.replace('/*'+k+'*/',x)
with tempfile.TemporaryDirectory() as tmp:
 t=Path(tmp);src=t/'r.rs';out=t/'test';src.write_text(s);subprocess.run([a.rustc,'--edition=2024','-Awarnings','-L','dependency='+str(a.rlib.parent),'--extern','serde_json='+str(a.rlib),src,'-o',out],check=True);subprocess.run([out],check=True)
