"""Read the actual multiselect presenter and its public choice DTO; everything else is an inert recorder."""
from pathlib import Path
import argparse,subprocess as sp,tempfile
p=argparse.ArgumentParser();p.add_argument('fields',type=Path);p.add_argument('schema',type=Path);p.add_argument('deps',type=Path);p.add_argument('--rustc',default='rustc');a=p.parse_args()
def block(text,fn):
 i=text.index(fn);n=1;j=text.index('{',i)+1
 while n:n+=int(text[j]=='{')-int(text[j]=='}');j+=1
 return text[i:j]
s=a.fields.read_text();c=a.schema.read_text();r=Path(__file__).with_name('frame.rs.in').read_text()
choice=block(c,'pub struct ConfigChoice');k=c.index(choice);choice=c[c.rindex('#[derive(',0,k):k]+choice
r=r.replace('/*CHOICE*/',choice).replace('/*BODY*/',block(s,'fn multi_choice(')).replace('/*EFFECTIVE*/',block(s,'pub(super) fn effective(').replace('pub(super) ',''))
with tempfile.TemporaryDirectory() as t:
 t=Path(t);f=t/'p.rs';f.write_text(r);cmd=[a.rustc,'--edition=2024','-O','-Awarnings',f,'-o',t/'peer','-L','dependency='+str(a.deps.resolve())]
 for name in ['serde','serde_json']:v,=a.deps.glob('lib'+name+'-*.rlib');cmd+=['--extern',name+'='+str(v.resolve())]
 sp.run(cmd,check=True);sp.run([t/'peer'],check=True)
