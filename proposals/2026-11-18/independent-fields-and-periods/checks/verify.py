"""Offline aggregate. Reads pinned Git blobs, applies proposals only inside a temporary directory."""
from pathlib import Path
import argparse,hashlib,os,shutil,subprocess as sp,sys,tempfile
A=argparse.ArgumentParser(description=__doc__)
for n in ['desktop','core','extensions','dot','deps','markdown']: A.add_argument('--'+n,type=Path,required=True)
A.add_argument('--rustc',default='rustc');A.add_argument('--cargo',default='cargo');a=A.parse_args()
base=Path(__file__).resolve().parents[1];ck=base/'checks';patch=base/'patches';deps=a.deps.resolve();rlib,=deps.glob('libserde_json-*.rlib');md=a.markdown.resolve()
refs={'desktop':'2307e9c67125bbe66f15ced51317a2dfcc437aa4','core':'c2cbadee518788f306ffb2b5271036b2658ea8cc','extensions':'ef064381d2194d95faef2b85f6cc3a1c34c6b975','dot':'3bcb47225db2cfdd066a69d9c968026a6e9a597a'}
def read(r,p):return sp.check_output(['git','-C',getattr(a,r),'show',refs[r]+':'+p])
def run(*args,cwd=None):sp.run(args,check=True,cwd=cwd,env={**os.environ,'RUSTC':a.rustc})
def py(n,*args):run(sys.executable,ck/n,*args)
def put(d,p,b):f=d/p;f.parent.mkdir(parents=True,exist_ok=True);f.write_bytes(b)
def apply(d,p,reverse=False):
 opts=['--reverse'] if reverse else []
 run('git','apply','--check','--whitespace=error',*opts,p,cwd=d);run('git','apply','--whitespace=error',*opts,p,cwd=d)
for line in (base/'SHA256SUMS').read_text().splitlines():
 s,n=line.split('  ',1);assert hashlib.sha256((base/n).read_bytes()).hexdigest()==s,n
pa=sorted(patch.glob('*.patch'));targets={s[6:] for p in pa for s in p.read_text().splitlines() if s.startswith('--- a/')}
sources=targets|{'src/ui/extensions/declarative/'+n+'.rs' for n in ['view','render']}|{'src/declarative/'+n+'.rs' for n in ['widget','graph','lanes','list','tree','control']}|{'src/ui/format.rs','src/settings/catalog.rs','src/settings/schema.rs','packages/usage/src/entry.rs','packages/usage/src/view.rs','sdk/src/value.rs'}
with tempfile.TemporaryDirectory() as tmp:
 d=Path(tmp);B=d/'before';F=d/'after';other=d/'other'
 for p in sources:put(B,p,read('extensions' if p.startswith(('packages/','sdk/')) else 'core' if p.startswith('crates/proteus-core/') else 'desktop',p))
 for path,order in [(F,pa),(other,reversed(pa))]:
  shutil.copytree(B,path)
  for p in order:apply(path,p)
 assert all((F/p).read_bytes()==(other/p).read_bytes() for p in sources)
 for p in reversed(pa):apply(other,p,True)
 assert all((B/p).read_bytes()==(other/p).read_bytes() for p in sources)
 print(f'{len(pa)} independent patches; {len(targets)} changed upstream blobs. Both apply orders agree; reverse restores all source bytes.',flush=True)
 for tag,tree in [('before',B),('after',F)]:
  py('preview/probe.py',tree,deps,'--expect',tag);py('preview/peer.py',tree,'--rustc',a.rustc,'--expect',tag)
  py('markdown/check.py',tree,'--markdown-rlib',md,'--rustc',a.rustc)
 py('markdown/unit.py',B,F,'--rustc',a.rustc)
 py('settings/replay.py','--desktop',a.desktop,'--patch',patch/'advanced-section-header.patch','--rustc',a.rustc,'--serde-json',rlib)
 py('settings/peer/check.py',B,F,deps,'--rustc',a.rustc)
 py('markdown/peer/peer.py','--core',a.core,'--patch',patch/'markdown-cell-line-endings.patch','--markdown-rlib',md,'--rustc',a.rustc)
 for s in ['replay','ux']:py('usage/'+s+'.py',B,F,deps,'--rustc',a.rustc)
 r='packages/usage/src/report.rs';py('usage/peer/replay.py',B/r,F/r,B/'sdk/src/value.rs',B/r,'--cargo',a.cargo)
 # The standalone and #201 input patches overlap. Exercise the qualified alternate,
 # then compile both the new gate and #201's existing full input-arm fixture.
 D=d/'combined';shutil.copytree(B,D);prior='proposals/2026-11-18/retained-input-and-honest-presentation/'
 orig=d/'201.patch';orig.write_bytes(read('dot',prior+'patches/retained-input-bindings.patch'))
 assert hashlib.sha256(orig.read_bytes()).hexdigest()=='55780e49813c627c13f5960d36ebc3762f8551c9a98bd4309c3a4808c9391a0d'
 apply(D,orig);alternate=base/'compat/preview-after-bindings.patch';apply(D,alternate)
 py('preview/probe.py',D,deps,'--expect','after');py('preview/peer.py',D,'--rustc',a.rustc,'--expect','after')
 replay=d/'replay.py';frame=d/'frame.rs.in';replay.write_bytes(read('dot',prior+'checks/bindings/replay.py'));frame.write_bytes(read('dot',prior+'checks/bindings/frame.rs.in'))
 fs=(D/'src/ui/extensions/declarative/fields.rs').read_text();i=fs.index('impl Fields {');helper=fs[i:fs.index('\n}\n',i)+2]
 (d/'stimulus.rs').write_bytes(read('dot',prior+'checks/bindings/stimulus.rs'))
 # Old recording toolkit has no new helper. Before cfg keeps the old model intact.
 hook='#[derive(Default)] struct DeclarativeView';t=frame.read_text();assert t.count(hook)==1
 frame.write_text(t.replace(hook,'#[cfg(any(after,candidate))]\n'+helper+'\n'+hook))
 run(sys.executable,replay,B,D,'--rustc',a.rustc,'--serde-json',rlib)
 apply(D,alternate,True);apply(D,orig,True);assert all((D/p).read_bytes()==(B/p).read_bytes() for p in sources)
 print('Verified 4 standalone proposals and the #201 alternate. No GPUI window, server, real data or upstream build.',flush=True)
