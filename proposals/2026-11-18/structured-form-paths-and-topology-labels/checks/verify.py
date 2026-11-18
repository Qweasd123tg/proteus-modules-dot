"""Verify source proposals only, on synthetic form values and diagnostic text; no running host, GUI, or live profile."""
from pathlib import Path
import argparse,hashlib,os,re,shutil,subprocess as sp,sys,tempfile
p=argparse.ArgumentParser(description=__doc__)
for k in ['desktop','core','extensions','dot','deps']:p.add_argument('--'+k,type=Path,required=True)
p.add_argument('--proposal-cache',type=Path);p.add_argument('--rustc',default='rustc');a=p.parse_args()
root=Path(__file__).resolve().parents[1];ck=root/'checks';deps=a.deps.resolve();se,=deps.glob('libserde-*.rlib');sj,=deps.glob('libserde_json-*.rlib')
refs={'core':'c2cbadee518788f306ffb2b5271036b2658ea8cc','desktop':'2307e9c67125bbe66f15ced51317a2dfcc437aa4','extensions':'ef064381d2194d95faef2b85f6cc3a1c34c6b975'}
def run(*cmd,cwd=None):sp.run(cmd,cwd=cwd,check=True,env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1'})
def py(f,*args):run(sys.executable,ck/f,*args)
def obj(b):return hashlib.sha1(f'blob {len(b)}\0'.encode()+b).hexdigest()
def put(d,n,b):z=d/n;z.parent.mkdir(parents=True,exist_ok=True);z.write_bytes(b)
def get(r,n):return sp.check_output(['git','-C',getattr(a,r),'show',refs[r]+':'+n])
def names(p):return re.findall(r'^--- a/([^\n]+)',p.read_text(),re.M)
def apply(d,p,rev=False):
 opt=['--reverse'] if rev else [];run('git','apply','--check','--whitespace=error',*opt,p,cwd=d);run('git','apply','--whitespace=error',*opt,p,cwd=d)
def unchanged(x,y,ns):assert all((x/n).read_bytes()==(y/n).read_bytes() for n in ns)
def blob(s):
 v=sp.run(['git','-C',a.dot,'cat-file','blob',s],capture_output=True)
 if v.returncode==0:b=v.stdout
 elif a.proposal_cache:b=(a.proposal_cache/s).read_bytes()
 else:raise RuntimeError('missing dot blob '+s)
 assert obj(b)==s;return b
for l in (root/'SHA256SUMS').read_text().splitlines():
 h,n=l.split('  ',1);assert hashlib.sha256((root/n).read_bytes()).hexdigest()==h,n
change=root/'patches/structured-form-identity.patch';alt=root/'compat/identity-after-raw-search.patch'
assert hashlib.sha256(change.read_bytes()).hexdigest()=='a3c44ed1f38c3a3e5c3b93f03131895116b116ed10cd804137f41143d6fc2b04'
assert hashlib.sha256(alt.read_bytes()).hexdigest()=='c832badb57db5bd4301097c5cd3e50bccfbab28b6f43dadaee7592eeaf51f195'
with tempfile.TemporaryDirectory() as t:
 d=Path(t);B=d/'desktop';T=d/'fixed';X=d/'combined';C=d/'core';E=d/'ext';prev={}
 for l in (ck/'prior.tsv').read_text().splitlines():
  path,sha=l.split('\t');name=Path(path).name;dest=(d/'prior'/name);put(dest.parent,name,blob(sha));prev[name]=dest
 u='src/ui/extensions/declarative/';fields=u+'fields.rs';render=u+'render.rs';inputstate='vendor/gpui-base/src/input/base/state.rs';sdk='sdk/src/ui.rs'
 formschema='crates/proteus-contracts/src/domain/config_schema.rs'
 # Materialize public Core DTOs only. No implementation of validation, host or configuration I/O is compiled or called.
 stop=b'impl ConfigField'
 with sp.Popen(['git','-C',a.core,'show',refs['core']+':'+formschema],stdout=sp.PIPE) as proc:
  chunks=[]
  for line in proc.stdout:
   if line.startswith(stop):chunks.append(stop);break
   chunks.append(line)
  proc.stdout.close()
 assert chunks[-1]==stop;put(C,formschema,b''.join(chunks))
 prior=[prev[n] for n in ['desktop-exact-title.patch','preserve-empty-parents.patch','advanced-section-header.patch','confirm-invalid-form-before-json.patch','multiline-array-editor.patch','raw-settings-search-target.patch']]
 ns={n for pat in [change,alt,*prior] for n in names(pat)}|{fields,render,inputstate,'src/settings/draft.rs','src/settings/catalog.rs','src/ui/settings/fields.rs'}
 for n in ns:put(B,n,get('desktop',n))
 put(E,sdk,get('extensions',sdk));shutil.copytree(B,T);shutil.copytree(B,X);apply(T,change)
 for z in [B,T]:
  py('scopes/replay.py',z,C,deps,'--rustc',a.rustc)
  py('scopes/peer/review.py',a.core,a.desktop,se,sj,a.rustc,*(['--patch',change] if z==T else []))
 py('scopes/encoding/run.py',T/'src/settings/schema.rs','--rustc',a.rustc)
 apply(T,change,True);unchanged(T,B,ns)
 for pat in prior:apply(X,pat)
 # The #206 raw-search hunk shares touching context, so select exactly ONE alternate.
 assert sp.run(['git','apply','--check',change],cwd=X,capture_output=True).returncode!=0
 apply(X,alt);py('scopes/replay.py',X,C,deps,'--rustc',a.rustc)
 py('scopes/encoding/raw206-peer.py',X,d/'prior','--rustc',a.rustc)
 for pat in reversed(prior+[alt]):apply(X,pat,True)
 unchanged(X,B,ns)
 py('input/replay.py','--desktop-fields',B/fields,'--desktop-render',B/render,'--desktop-input-state',B/inputstate,'--sdk-ui',E/sdk,'--serde-json',sj,'--rustc',a.rustc)
 py('input/peer/check.py',B,a.rustc)
 # Terminal representation only; the fixture compiles a complete Rust presenter against UI-free sample structures.
 m=root/'patches/quoted-mermaid-nodes.patch';rel=names(m);assert len(rel)==1;n=rel[0];parent=str(Path(n).parent);helper=parent+'/helpers.rs';z=d/'core-before';y=d/'core-after'
 for k in [n,helper]:put(z,k,get('core',k))
 shutil.copytree(z,y);apply(y,m)
 py('mermaid/replay.py',z/n,y/n,z/helper,a.rustc)
 py('mermaid/peer/replay.py',z/parent,y/parent,m,a.rustc)
 apply(y,m,True);unchanged(z,y,[n,helper])
 print('PASS: focused native checks, independent projections, selected #206 combination and exact rollback. No full GPUI, Mermaid JS engine or runtime.')
