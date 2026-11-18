"""Core declarations only, two pure Extension display modules and offline fixture. Run in scratch; no service calls."""
from pathlib import Path
import subprocess,hashlib,sys,tempfile,itertools,shutil
here=Path(__file__).resolve().parent
base,new,old,serde,js=map(lambda p:Path(p).resolve(),sys.argv[1:6]);rust=sys.argv[6] if len(sys.argv)>6 else 'rustc'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
assert sha(new)=='57fadeac6a94f314d1fa4bdb1272026a57222f146baf63b9b7f1ff160bd1c0a6' and sha(old)=='1a5ac591b780c8018d50242f15a3b0bda7ac692066283eead76b959abf90f4d0'
if len(sys.argv)>7:
 with (Path(sys.argv[7])/'crates/proteus-contracts/src/contracts/model_quota.rs').open()as f:assert ''.join(itertools.islice(f,1,61)).strip()==(here/'quota-dto.frag').read_text().strip()
files=['packages/quota/src/'+n+'.rs' for n in ('view','describe')]
runs={};combined={}
with tempfile.TemporaryDirectory()as td:
 for phase,patches in [('base',[]),('mark',[new]),('191',[old]),('191mark',[old,new]),('mark191',[new,old])]:
  wd=Path(td)/phase;wd.mkdir()
  for f in files:
   (wd/f).parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(base/f,wd/f)
  for p in patches:subprocess.run(['git','apply','--check',str(p)],cwd=wd,check=True);subprocess.run(['git','apply',str(p)],cwd=wd,check=True)
  for f in files:(wd/Path(f).name).write_text((wd/f).read_text().split('#[cfg(test)]')[0])
  src=(here/'gate.rs.in').read_text().replace('/*DTO*/',(here/'quota-dto.frag').read_text())
  (wd/'main.rs').write_text(src);subprocess.run([rust,'--edition=2024','-Awarnings',str(wd/'main.rs'),'-L','dependency='+str(js.parent),'--extern','serde='+str(serde),'--extern','serde_json='+str(js),'-o',str(wd/'gate')],check=True)
  data=subprocess.check_output([str(wd/'gate'),phase]);runs[phase]=data
  if len(patches)==2:combined[phase]=[sha(wd/f) for f in files]
  print(phase, len(data.splitlines()), hashlib.sha256(data).hexdigest(), data.splitlines()[-3:])
assert runs['base']==runs['mark'] and runs['191']==runs['191mark']==runs['mark191'] and combined['191mark']==combined['mark191']
print('GO: exact marker count, correct typed limiting minimum (including None), byte-identical remaining visual/text traces after stripping only the approved annotations; either patch order gives identical source.')
