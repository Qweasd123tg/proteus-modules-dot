"""Offline source-slice tests: no application, user profile, repo mutations or network."""
from pathlib import Path
import argparse,hashlib,os,re,shutil,subprocess as sp,sys,tempfile
A=argparse.ArgumentParser(description=__doc__)
for n in ['desktop','extensions','dot','deps']:A.add_argument('--'+n,type=Path,required=True)
A.add_argument('--rustc',default='rustc');a=A.parse_args()
root=Path(__file__).resolve().parents[1];ck=root/'checks';deps=a.deps.resolve();lib,=deps.glob('libserde_json-*.rlib')
env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1'}
refs={'desktop':'2307e9c67125bbe66f15ced51317a2dfcc437aa4','extensions':'ef064381d2194d95faef2b85f6cc3a1c34c6b975','dot':'3bcb47225db2cfdd066a69d9c968026a6e9a597a'}
def run(*args,cwd=None,expected=0):
 rc=sp.run(args,cwd=cwd,env=env).returncode
 if rc!=expected:raise RuntimeError(f'{args[0]} returned {rc}, expected {expected}: {args[1:3]}')
def py(f,*args,expected=0):run(sys.executable,ck/f,*args,expected=expected)
def get(repo,p):return sp.check_output(['git','-C',getattr(a,repo),'show',refs[repo]+':'+p])
def put(d,p,b):f=d/p;f.parent.mkdir(parents=True,exist_ok=True);f.write_bytes(b)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def patch(d,p,reverse=False):
 opt=['--reverse'] if reverse else [];run('git','apply','--check','--whitespace=error',*opt,p,cwd=d);run('git','apply','--whitespace=error',*opt,p,cwd=d)
def paths(p):return set(re.findall(r'^--- a/([^\n]+)',p.read_text(),re.M))
def same(d,x,names):assert all((d/n).read_bytes()==(x/n).read_bytes() for n in names)
for line in (root/'SHA256SUMS').read_text().splitlines():
 h,n=line.split('  ',1);assert sha(root/n)==h,n
ps=sorted((root/'patches').glob('*.patch'));cp=root/'compat/tabs-after-hover.patch';flat=root/'patches/tab-arrangement-per-window.patch'
assert len(ps)==3
dg=sp.check_output(['git','-C',a.desktop,'rev-parse','--absolute-git-dir'],text=True).strip()
with tempfile.TemporaryDirectory() as t:
 d=Path(t);B=d/'base';T=d/'candidate';X=d/'rollback';C=d/'combined'
 hover=d/'hover.patch';hover.write_bytes(get('dot','proposals/2026-11-17/fade-tree-tabs-and-tps/desktop-tab-hover.patch'))
 assert sha(hover)=='b6180aaa5617525fff61b41d97cd7cc028501077cc1e858ade325b78c8b91b33'
 badges=d/'badges.patch';badges.write_bytes(get('dot','proposals/2026-11-17/font-picker-window-badges-and-diff/desktop-window-badge-order.patch'))
 names=set.union(*(paths(p) for p in ps+[cp,hover,badges]))|{'src/declarative/tree.rs','src/ui/extensions/declarative/tree.rs'}
 for n in names:put(B,n,get('desktop',n))
 extfiles=['packages/git/src/panel.rs','packages/git/src/model.rs','packages/git/src/list.rs','sdk/src/ui.rs','sdk/src/value.rs']
 for n in extfiles:put(d/'ext',n,get('extensions',n))
 for z,order in [(T,ps),(X,reversed(ps))]:
  shutil.copytree(B,z)
  for p in order:patch(z,p)
 same(T,X,names)
 for p in reversed(ps):patch(X,p,True)
 same(B,X,names)
 print('Three independent proposal diffs: both orders match byte-for-byte, rollback exact.',flush=True)
 py('focus/focus.py',B,T,'--rustc',a.rustc);py('focus/schema.py',a.desktop,deps,'--rustc',a.rustc)
 py('focus/peer/replay.py',B/'src/ui/reorder.rs',root/'patches/reorder-focus-index.patch',a.rustc)
 for tree in [B,T]:
  py('tabs/run.py',tree,a.rustc,expected=1 if tree==B else 0);py('tabs/peer/peer.py',tree,'--rustc',a.rustc)
 py('settings/replay.py','--desktop',dg,'--rustc',a.rustc,'--serde-json',lib);py('settings/peer/check.py',T,'--rustc',a.rustc)
 py('changes/replay.py',deps,'--rustc',a.rustc,'--extensions',d/'ext','--desktop-tree',B/'src/ui/extensions/declarative/tree.rs','--desktop-schema',B/'src/declarative/tree.rs')
 # #194 alternative rather than stacking the standalone diff on top of #194.
 shutil.copytree(B,C);stack=[hover,cp]
 for p in stack:patch(C,p)
 py('tabs/run.py',C,a.rustc);py('tabs/peer/peer.py',C,'--rustc',a.rustc);py('tabs/prior_hover.py',a.dot,C,'--rustc',a.rustc)
 for p in reversed(stack):patch(C,p,True)
 same(B,C,names)
 # #196 and this proposal also touch Workspace; both full diffs compose in either order.
 for z,order in [(C,[badges,flat]),(X,[flat,badges])]:
  for p in order:patch(z,p)
 same(C,X,names)
 for p in [badges,flat]:patch(X,p,True)
 same(B,X,names)
print('PASS: source proposals and independent native fixture checks. #194 replay; #196 source composition only. No GPUI or real Git action.')
