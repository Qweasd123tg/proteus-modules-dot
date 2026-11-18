#!/usr/bin/env python3
"""Read static files only. Accept source checkout, matching serde rlibs and compiler. No repo/GUI startup."""
import argparse,hashlib,subprocess,tempfile
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('desktop',type=Path);p.add_argument('core',type=Path);p.add_argument('patch',type=Path)
p.add_argument('serde',type=Path);p.add_argument('serde_json',type=Path);p.add_argument('--rustc',default='rustc');a=p.parse_args()
def digest(s): return hashlib.sha256(s).hexdigest()
def cut(s,k):
 i=s.index(k); j=s.index('{',i);d=1
 while d:j+=1;d+=(s[j]=='{')-(s[j]=='}')
 return s[i:j+1]
root=Path(__file__).parent
patch=a.patch.resolve(); assert digest(patch.read_bytes())=='1f8c33475c0686b912227ed1bdfd99c4fb36af4fb31cf2d34666d55f1a8b6000'
# Only declaration lines 1-76 are read. Validators and all other contract code are outside this check.
import itertools
cp=a.core/'crates/proteus-contracts/src/domain/config_schema.rs'
with cp.open() as src: core=''.join(itertools.islice(src,76))
def lines(p,start,count):
 with p.open() as f:return ''.join(itertools.islice(f,start-1,start-1+count))
sch=lines(a.desktop/'src/settings/schema.rs',40,80).split('pub fn choice_title')[0]
tag=lines(a.desktop/'src/ui/settings/tags.rs',21,12)
for body,name in [(core,'domain'),(sch,'route'),(tag,'tags')]:
 assert digest(body.strip().encode())=={'domain': 'bf371b48a9cb6065d66eefe4d38d83afbd1df2be61a08dfff8ea031b0d56ea1f', 'route': '580bce7ca784b20f909d9e0d4bd2f6ad9c76948103147483d1a0014b97caabe3', 'tags': 'dc321355d7c648f7008d4f51c2bbcff2dadac3440f32fdd38ac3a6d179505646'}[name],name
target='src/ui/settings/fields.rs';orig=(a.desktop/target).read_bytes();assert hashlib.sha1(b'blob '+str(len(orig)).encode()+b'\0'+orig).hexdigest()=='e038818a96da61e8ce5e52a8b66ce513cbf37e20'
source=orig.decode(); assert 'if tagged {\n            self.string_tags' in source and 'FieldKind::MultiChoice(options) => multi_choice(&spec, options)' in source
with tempfile.TemporaryDirectory()as tmp:
 t=Path(tmp);f=t/target;f.parent.mkdir(parents=True);f.write_bytes(orig);metrics=[]
 for name in ('base','patched'):
  if name=='patched':subprocess.run(['patch','--batch','--fuzz=0','-s','-p1','-i',str(patch)],cwd=t,check=True)
  s=f.read_text();frame=(root/'frame.rs.in').read_text()
  for token,body in [('CORE_DTOS',core),('ROUTE',sch),('TAGS',tag),('EFFECTIVE',cut(s,'pub(super) fn effective(').replace('pub(super) ','')),('MULTI',cut(s,'fn multi_choice('))]:frame=frame.replace('/*'+token+'*/',body)
  main=t/'main.rs';main.write_text(frame);exe=t/'check'
  subprocess.run([a.rustc,'--edition=2024','-C','opt-level=1',str(main),'-o',str(exe),'-L','dependency='+str(a.serde.resolve().parent),'--extern','serde='+str(a.serde.resolve()),'--extern','serde_json='+str(a.serde_json.resolve())],check=True)
  out=subprocess.check_output([str(exe)],text=True);print(name+'\n'+out,end='');metrics.append((out.splitlines()[0],[list(map(int,row.split())) for row in out.splitlines()[2:]]))
 assert metrics[0][0]==metrics[1][0]
 for b,c in zip(metrics[0][1],metrics[1][1]):
  assert b[0]==c[0] and all(x>y for x,y in zip(b[1:],c[1:]))
 assert metrics[0][1][-1][3]>50*metrics[1][1][-1][3]
