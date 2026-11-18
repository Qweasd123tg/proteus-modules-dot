"""Independent, dependency-local static schema/UI-routing replay. Supply Desktop checkout, exact patch, serde_json rlib, rustc."""
from pathlib import Path
import sys,hashlib,subprocess,shutil,tempfile
root,pch,lib=map(lambda s:Path(s).resolve(),sys.argv[1:4])
rust=sys.argv[4] if len(sys.argv)>4 else 'rustc'
assert hashlib.sha256(pch.read_bytes()).hexdigest()=='f306743af95285977a21584dd9143860f244c9d7187658e4e01149bac70ec851'
def blob(p):
    b=p.read_bytes();return hashlib.sha1(b'blob '+str(len(b)).encode()+b'\0'+b).hexdigest()
assert blob(root/'src/settings/schema.rs')=='1a799115bf45e9854defbc3b0c4f4cc6645e4a2c'
assert blob(root/'src/ui/settings/tags.rs')=='3e1fab04d2771d9129ba2df139682bfdeda3b401'
def cut(s,a,b): return s[s.index(a):s.index(b,s.index(a))]
def fn(s,query):
    i=s.index(query);j=s.index('{',i);n=1
    for k in range(j+1,len(s)):
        n+=(s[k]=='{')-(s[k]=='}')
        if n==0:return s[i:k+1]
    assert False
drivers=Path(__file__).with_name('matrix.rs.in').read_text()
with tempfile.TemporaryDirectory() as t:
    tmp=Path(t)
    for f in ['src/ui/settings/tags.rs','src/ui/settings/tags/tests.rs','src/settings/schema.rs','README.md']:
        (tmp/f).parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(root/f,tmp/f)
    subprocess.run(['patch','--fuzz=0','--batch','-p1','-i',str(pch)],cwd=tmp,stdout=subprocess.DEVNULL,check=True)
    for place,ver in [(root,'before'),(tmp,'after')]:
        schema=(place/'src/settings/schema.rs').read_text();tags=(place/'src/ui/settings/tags.rs').read_text()
        disp=cut(schema,'#[derive(Clone, Copy, Debug, PartialEq, Eq)]\npub enum TextFormat','pub fn choice_title')
        routines=fn(schema,'pub fn format_value(')+'\n'+fn(schema,'pub fn parse_text(')
        tag=fn(tags,'pub(super) fn is_tag_field(').replace('pub(super) fn','fn',1)
        src=drivers.replace('@@routines@@',disp+'\n'+routines+'\n'+tag)
        (tmp/'gate.rs').write_text(src)
        subprocess.run([rust,'--edition=2024','-Awarnings',str(tmp/'gate.rs'),'--extern','serde_json='+str(lib),'-L','dependency='+str(lib.parent),'-o',str(tmp/'gate')],check=True)
        subprocess.run([str(tmp/'gate'),ver],check=True)
