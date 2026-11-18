"""Verify the current proposal package from local pinned Git sources. Runs isolated fixtures only."""
from pathlib import Path
import argparse,hashlib,shutil,subprocess,sys,tempfile
a=argparse.ArgumentParser(description=__doc__)
for n in ['desktop','extensions','deps','markdown']:a.add_argument('--'+n,type=Path,required=True)
a.add_argument('--rustc',default='rustc');o=a.parse_args()
root=Path(__file__).resolve().parent.parent; ck=root/'checks';deps=o.deps.resolve()
for line in (root/'SHA256SUMS').read_text().splitlines():
 sha,name=line.split('  ',1);assert hashlib.sha256((root/name).read_bytes()).hexdigest()==sha,name
libs=list(deps.glob('libserde_json-*.rlib'));assert len(libs)==1;lib=libs[0]; mdlib=o.markdown.resolve()
def run(*args,expected=0,cwd=None):
 r=subprocess.run(args,cwd=cwd)
 if r.returncode!=expected:raise RuntimeError((args,r.returncode,expected))
def py(f,*args,expected=0):run(sys.executable,ck/f,*args,expected=expected)
patches=sorted((root/'patches').glob('*.patch'))
targets={s[6:] for f in patches for s in f.read_text().splitlines() if s.startswith('--- a/')}
sources=targets|{'src/ui/extensions/declarative/layout.rs','src/ui/motion/disclosure.rs','src/ui/motion/mod.rs','crates/tabs/src/size.rs','vendor/gpui-base/src/text/utils.rs','packages/json-render/src/catalog.rs'}
with tempfile.TemporaryDirectory() as td:
 work=Path(td);before=work/'before';after=work/'after'
 for n in sources:
  ext=n.startswith('packages/');r,v=(o.extensions,'ef064381d2194d95faef2b85f6cc3a1c34c6b975') if ext else (o.desktop,'2307e9c67125bbe66f15ced51317a2dfcc437aa4')
  f=before/n;f.parent.mkdir(parents=True,exist_ok=True);f.write_bytes(subprocess.check_output(['git','-C',r,'show',v+':'+n]))
 for out,fs in [(after,patches),(work/'other-order',list(reversed(patches)))]:
  shutil.copytree(before,out)
  for p in fs:
   run('git','apply','--check','--whitespace=error',p,cwd=out);run('git','apply','--whitespace=error',p,cwd=out)
 assert all((after/n).read_bytes()==(work/'other-order'/n).read_bytes() for n in sources)
 undo=work/'undo';shutil.copytree(after,undo)
 for p in reversed(patches):run('git','apply','--reverse','--whitespace=error',p,cwd=undo)
 assert all((undo/n).read_bytes()==(before/n).read_bytes() for n in sources)
 print(f'{len(patches)} patches, {len(targets)} edited blobs. Both apply orders agree, all reverted bytes match.',flush=True)
 py('reset/replay.py','--desktop',o.desktop,'--serde-json',lib,'--patch',root/'patches/preserve-empty-parents.patch','--rustc',o.rustc)
 py('reset/peer.py',before,after,lib,o.rustc)
 py('focus/check.py',before,after,'--rustc',o.rustc)
 py('disclosure/run.py',before,after,'--rustc',o.rustc);py('disclosure/peer.py',before,after,o.rustc)
 n='src/ui/extensions/declarative/render.rs'
 py('bars/peer.py',before/n,after/n,'--rustc',o.rustc)
 py('bars/replay.py',before/n,after/n,before/'packages/json-render/src/catalog.rs',deps,'--rustc',o.rustc)
 for variant,tree in [('base',before),('patched',after)]:
  build=work/(variant+'-focus.rs');exe=work/(variant+'-focus')
  py('focus/assemble.py',tree,build)
  run(o.rustc,'--edition=2024',build,'-o',exe);run(exe,expected=int(variant=='base'))
  py('markdown/replay.py',tree,mdlib,'--rustc',o.rustc,expected=int(variant=='base'))
  py('markdown/peer/replay.py',tree,mdlib,'--rustc',o.rustc,expected=int(variant=='base'))
print('Verified focused fixtures. No application window, real settings, filesystem operation by a module, or upstream build.')
