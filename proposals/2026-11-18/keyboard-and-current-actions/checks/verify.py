"""Offline, in-memory UI tests. Edits only temporary copies of pinned source. Does not launch Git actions or Desktop."""
from pathlib import Path
import hashlib,argparse,subprocess as sp,sys,os,tempfile,shutil
A=argparse.ArgumentParser(description=__doc__)
for n in ['desktop','extensions','dot','deps']:A.add_argument('--'+n,type=Path,required=True)
A.add_argument('--rustc',default='rustc');a=A.parse_args()
root=Path(__file__).resolve().parents[1];ck=root/'checks';deps=a.deps.resolve();lib,=deps.glob('libserde_json-*.rlib')
refs={'desktop':'2307e9c67125bbe66f15ced51317a2dfcc437aa4','extensions':'ef064381d2194d95faef2b85f6cc3a1c34c6b975','dot':'3bcb47225db2cfdd066a69d9c968026a6e9a597a'}
env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1'}
def run(*cmd,cwd=None,expected=0):
 q=sp.run(cmd,cwd=cwd,env=env);assert q.returncode==expected,(cmd,q.returncode)
def py(f,*args,expected=0):run(sys.executable,ck/f,*args,expected=expected)
def get(r,p):return sp.check_output(['git','-C',getattr(a,r),'show',refs[r]+':'+p])
def put(d,p,b):n=d/p;n.parent.mkdir(parents=True,exist_ok=True);n.write_bytes(b)
def patch(d,p,rev=False):
 opt=['--reverse'] if rev else [];run('git','apply','--check','--whitespace=error',*opt,p,cwd=d);run('git','apply','--whitespace=error',*opt,p,cwd=d)
for l in (root/'SHA256SUMS').read_text().splitlines():
 h,n=l.split('  ',1);assert hashlib.sha256((root/n).read_bytes()).hexdigest()==h,n
patches=sorted((root/'patches').glob('*.patch'));u='src/ui/extensions/declarative/'
sources={u+n+'.rs' for n in ['fields','tree','tree_row','rows','graph','list','lanes','render']}|{'src/declarative/'+n+'.rs' for n in ['widget','control','tree','graph','list','lanes']}|{'PROTOCOL.md','sdk/src/ui.rs','sdk/src/value.rs'}
desktop_git=sp.check_output(['git','-C',a.desktop,'rev-parse','--absolute-git-dir'],text=True).strip()
with tempfile.TemporaryDirectory() as tmp:
 d=Path(tmp);B=d/'base';T=d/'candidate';X=d/'reverse';H=d/'headers-only'
 for p in sources:put(B,p,get('extensions' if p.startswith(('sdk/','PROTOCOL')) else 'desktop',p))
 # Only selected presentation/section methods will be compiled by the Changes peer probe.
 for p in ['packages/git/src/model.rs','packages/git/src/panel.rs','packages/git/src/list.rs']:put(B,p,get('extensions',p))
 for tree,order in [(T,patches),(X,reversed(patches))]:
  shutil.copytree(B,tree)
  for p in order:patch(tree,p)
 assert all((T/p).read_bytes()==(X/p).read_bytes() for p in sources)
 for p in reversed(patches):patch(X,p,True)
 assert all((B/p).read_bytes()==(X/p).read_bytes() for p in sources)
 print('Two changes in three patches: forward/reverse orders agree; exact rollback.',flush=True)
 standalone=root/'patches/retain-current-widget-action.patch'
 py('action/replay.py','--desktop',desktop_git,'--rustc',a.rustc,'--serde-json',lib,'--patch',standalone)
 py('action/peer/schema.py',B,a.rustc,deps)
 py('action/peer/schema.py',B,a.rustc,deps,B,expected=1);py('action/peer/schema.py',B,a.rustc,deps,T)
 py('headers/run.py',B,T,'--rustc',a.rustc)
 shutil.copytree(B,H);patch(H,root/'patches/keyboard-section-navigation.patch')
 # Isolate the keyboard proposal for this peer's stand-in of the old row sender.
 for phase,s in [('baseline',B),('final',H)]:
  py('headers/peer/replay.py',s,'--rustc',a.rustc,expected=int(phase=='baseline'))
  py('changes/replay.py',s/(u+'tree.rs'),phase,deps,'--extensions',T,'--desktop-schema',s/'src/declarative/tree.rs','--rustc',a.rustc)
 # Original discarded experiment: actual first candidate only added this keyboard guard.
 n=u+'tree.rs';s=(X/n).read_text();mark='    fn key(&mut self, event: &KeyDownEvent, cx: &mut Context<Self>) {\n';assert s.count(mark)==1
 (X/n).write_text(s.replace(mark,mark+'        if self.rows.get(self.cursor).is_some_and(Row::header) { return; }\n'))
 py('changes/replay.py',X/n,'guard',deps,'--extensions',T,'--desktop-schema',X/'src/declarative/tree.rs','--rustc',a.rustc)
 # Reuse the prior row-reuse gates unchanged for the alternative diff on #199.
 C=d/'compat';shutil.copytree(B,C);prior='proposals/2026-11-18/selection-and-retained-rendering/';orig=d/'shared-row-snapshots.patch';orig.write_bytes(get('dot',prior+'patches/shared-row-snapshots.patch'))
 assert hashlib.sha256(orig.read_bytes()).hexdigest()=='b409c163c8ab72837c1601464097129fd91a97b3e9a5ef8dc7d26fa244c377bb'
 alt=root/'compat/action-after-snapshots.patch'
 stack=[orig,alt,root/'patches/keyboard-section-navigation.patch',root/'patches/keyboard-section-protocol.patch']
 for p in stack:patch(C,p)
 py('action/peer/schema.py',B,a.rustc,deps,C);py('headers/run.py',B,C,'--rustc',a.rustc)
 for n in ['run.py','frame.rs.in','peer.py','peer.rs.in']:put(d/'snapshot-checks',n,get('dot',prior+'checks/rows/'+n))
 run(sys.executable,d/'snapshot-checks/run.py',B,C,'--rustc',a.rustc);run(sys.executable,d/'snapshot-checks/peer.py',C,'--rustc',a.rustc)
 for p in reversed(stack):patch(C,p,True)
 assert all((B/n).read_bytes()==(C/n).read_bytes() for n in sources)
print('Passed: synthetic native checks and source preparation, including combination with #199. No real GUI, repository action or service.')
