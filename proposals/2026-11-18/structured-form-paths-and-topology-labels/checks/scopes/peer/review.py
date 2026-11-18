"""Offline independent test of Finder -> selected spot / opened disclosures in a settled synthetic form.
Input Desktop is a pinned bare repository or worktree; in patched runs --patch is applied to a fresh partial copy.
Core read is restricted to the public declarations/builders. No module/GUI/files/profile is run."""
from pathlib import Path
import argparse, subprocess as sp, tempfile, hashlib, re
p=argparse.ArgumentParser()
for k in ('core','desktop','serde','serde_json','rustc'): p.add_argument(k,type=Path)
p.add_argument('--patch',type=Path); a=p.parse_args()
def rev(r):return '2307e9c67125bbe66f15ced51317a2dfcc437aa4' if r==a.desktop else 'c2cbadee518788f306ffb2b5271036b2658ea8cc'
def repo(r,k): return sp.check_output(['git','-C',str(r),'show',rev(r)+':'+k],text=True)
def prefix(r,k,stop):
 # Do not inspect, store, compile or execute implementation behind the public declarations.
 cmd=['git','-C',str(r),'show',rev(r)+':'+k]
 with sp.Popen(cmd,stdout=sp.PIPE,text=True) as proc:
  out=[]
  for line in proc.stdout:
   if line.startswith(stop):break
   out.append(line)
  else:raise RuntimeError('missing public declaration boundary '+stop)
  proc.stdout.close()
  return ''.join(out)
def r(x):return repo(a.desktop,x)
def interval(s,b,e):return s[s.index(b):s.index(e,s.index(b))]
def fun(s,marker):
 i=s.index(marker); j=s.index('{',i); depth=1
 while depth:j+=1;depth+=(s[j]=='{')-(s[j]=='}')
 return s[i:j+1]
def stmt(s,marker):return re.search(marker,s,re.M).group(1)
with tempfile.TemporaryDirectory() as tmp:
 t=Path(tmp)
 for f in ('src/settings/mod.rs','src/settings/schema.rs','src/ui/settings/spot.rs','src/ui/settings/search.rs','src/ui/settings/group.rs','src/ui/settings/params.rs'):
  dst=t/f;dst.parent.mkdir(parents=True,exist_ok=True);dst.write_text(r(f))
 if a.patch:
  assert hashlib.sha256(a.patch.read_bytes()).hexdigest()=='a3c44ed1f38c3a3e5c3b93f03131895116b116ed10cd804137f41143d6fc2b04'
  sp.run(['git','apply','--check',str(a.patch.resolve())],cwd=t,check=True);sp.run(['git','apply',str(a.patch.resolve())],cwd=t,check=True)
 def src(f):return (t/f).read_text()
 co=prefix(a.core,'crates/proteus-contracts/src/domain/config_schema.rs','impl ModuleConfigSchema {')
 cat=r('src/settings/catalog.rs')
 dr=r('src/settings/draft.rs');path=fun(dr,'#[derive(Clone, Debug, PartialEq, Eq, Hash, PartialOrd, Ord)]')+'\n'+fun(dr,'impl FieldPath {')
 sc=src('src/settings/schema.rs')
 funcs=fun(sc,'pub fn section_scope(')
 if a.patch: funcs+='\n'+fun(sc,'fn push_scope_part(')+'\n'+fun(sc,'pub fn form_scope(')
 ss=src('src/ui/settings/search.rs'); spot=src('src/ui/settings/spot.rs'); group=src('src/ui/settings/group.rs'); params=src('src/ui/settings/params.rs'); fields=r('src/ui/settings/fields.rs'); view=r('src/ui/settings/mod.rs')
 # Root and nested scopes come from render, not from Finder.
 root=stmt(params,r'^\s+&(format!\("\{slot\}:\{module\}"\)|crate::settings::form_scope\(slot, module, &\[\]\)),\n\s+cx,')
 inner=stmt(group,r'let scope = ([^;]*);'); groupkey=stmt(group,r'let key = (format!\("group:[^;]*);'); advkey=stmt(group,r'let key = (format!\("advanced:[^;]*);')
 # Guard relation to real renderer, settled visibility and selected spot. No GPUI (animation, colors, scrolling not run).
 for s,q in [(spot,'self.open.extend(hit.open.iter().cloned());'),(spot,'self.spot = hit.spot.clone().map'),(spot,'filter(|spot| spot.key == key)'),(spot,'bring_into_view(&scroll, bounds, &settle)'),(fields,'&super::spot::field(path)'),(group,'self.spotted(&super::spot::field(path), header, cx)'),(group,'self.reveal(&key, cx, ||'),(group,'|key| path.child(key)'),(group,'if advanced.len() == 1'),(group,'this.toggle_open(&toggle_key, cx)'),(view,'let open = !self.open.remove(key);'),(view,'self.open.insert(key.to_string());'),(view,'self.open.contains(key)'),(view,'motion::reveal(reveal_key(key), self.is_open(key), cx, content)')]:assert q in s,q
 hit=interval(ss,'const LIMIT:', '/// Russian names')
 dest=interval(spot,'#[derive(Clone, Debug, PartialEq, Eq)]','pub(super) struct Spot {')
 data=Path(__file__).with_name('oracle.rs.in').read_text()
 for k,v in dict(CORE='\n'.join(i for i in co.splitlines() if not i.startswith('//!')),FUNCS=funcs,PATH=path,EDIT=fun(cat,'pub fn editable_field(')+'\n'+fun(cat,'pub fn editable_fields('),HIT=hit,DEST=dest,SPOT=fun(spot,'pub(super) fn field('),SCOPE=fun(ss,"struct Scope<'a>")+'\n'+fun(ss,"impl Scope<'_> {"),ROOT=root,INNER=inner,GRP=groupkey,ADV=advkey).items():data=data.replace('/*'+k+'*/',v)
 (t/'main.rs').write_text(data)
 sp.run([str(a.rustc),'--edition=2024','--cfg',('fixed' if a.patch else 'old'),'-A','dead_code',str(t/'main.rs'),'--extern','serde='+str(a.serde.resolve()),'--extern','serde_json='+str(a.serde_json.resolve()),'-L','dependency='+str(a.serde.resolve().parent),'-o',str(t/'peer')],check=True)
 sp.run([str(t/'peer')],check=True)
