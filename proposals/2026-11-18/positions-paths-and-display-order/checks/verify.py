"""Verify proposals against pinned, read-only Git inputs without launching any application or tool."""
from pathlib import Path
import argparse,hashlib,re,shutil,subprocess as sp,sys,tempfile
p=argparse.ArgumentParser(description=__doc__)
for n in ('core','desktop','modules','extensions','dot','deps'):p.add_argument('--'+n,type=Path,required=True)
p.add_argument('--contracts-rlib',required=True,type=Path);p.add_argument('--contracts-json-rlib',required=True,type=Path)
p.add_argument('--rustc',default='rustc')
a=p.parse_args();root=Path(__file__).resolve().parents[1];deps=a.deps.resolve();sj,=deps.glob('libserde_json-*.rlib');se,=deps.glob('libserde-*.rlib')
refs={'core':'c2cbadee518788f306ffb2b5271036b2658ea8cc','desktop':'2307e9c67125bbe66f15ced51317a2dfcc437aa4','extensions':'ef064381d2194d95faef2b85f6cc3a1c34c6b975','modules':'0fe8e3b4dfb64ca2e07df8af016d7ccc3a7de45f'}
def git(repo,*args):return sp.check_output(['git','-C',repo,*args])
def get(repo,path):return git(getattr(a,repo),'show',refs[repo]+':'+path)
def write(tree,path,b):f=tree/path;f.parent.mkdir(parents=True,exist_ok=True);f.write_bytes(b)
def project(tree,repo,paths):
 for n in paths:write(tree,n,get(repo,n))
def run(*cmd,cwd=None):sp.run(cmd,cwd=cwd,check=True)
def py(f,*args):run(sys.executable,root/f,*args)
def names(p):return re.findall(r'^--- a/([^\n]+)',p.read_text(),re.M)
def apply(tree,patch,reverse=False):
 opt=['--reverse'] if reverse else [];run('git','apply','--check','--whitespace=error',*opt,patch,cwd=tree);run('git','apply','--whitespace=error',*opt,patch,cwd=tree)
def content(tree):return {p.relative_to(tree):p.read_bytes() for p in tree.rglob('*') if p.is_file()}
def fromto(base,after,pat,*rest):
 shutil.copytree(base,after)
 for x in [pat,*rest]:apply(after,x)
def back(base,after,*pats):
 for x in reversed(pats):apply(after,x,True)
 assert content(base)==content(after)
for line in (root/'SHA256SUMS').read_text().splitlines():
 h,n=line.split('  ',1);assert hashlib.sha256((root/n).read_bytes()).hexdigest()==h,n
core=root/'slot-order/slot-display-order.patch';alt=root/'slot-order/peer/slot-display-order-after-streamed-table.patch'
steps=root/'steps/steps-current-options.patch';paths=root/'batch-paths/path-list-preview.patch'
u='src/ui/extensions/declarative/';s=u+'steps.rs';v=u+'view.rs';dto='crates/proteus-contracts/src/app_protocol/topology.rs';m='crates/proteus-core/src/core/topology_render/'
# Existing proposal from #192: independent of this package and verified by its immutable Git object ID.
blob='51c946c915dd37d28b886a5072a41731a5ed2079'
with tempfile.TemporaryDirectory() as td:
 t=Path(td);C=t/'core';CA=t/'core-fixed';C1=t/'streamed';C2=t/'streamed-fixed';D=t/'desktop';DA=t/'desktop-fixed';E=t/'ext';M=t/'modules';prior=t/'plain-topology-table.patch'
 b=git(a.dot,'cat-file','blob',blob);assert hashlib.sha1(f'blob {len(b)}\0'.encode()+b).hexdigest()==blob;prior.write_bytes(b)
 project(C,'core',{dto,m+'map.rs',m+'helpers.rs',*names(core)})
 fromto(C,CA,core);py('slot-order/checks/replay.py',C,core,se,sj,a.rustc);py('slot-order/peer/run.py',C,CA,a.rustc,deps);back(C,CA,core)
 fromto(C,C1,prior);assert sp.run(['git','apply','--check',core],cwd=C1,capture_output=True).returncode!=0
 fromto(C1,C2,alt);py('slot-order/peer/run.py',C1,C2,a.rustc,deps);back(C1,C2,alt);back(C,C1,prior)
 project(D,'desktop',{*names(steps),*names(paths)})
 project(E,'extensions',('sdk/src/value.rs',*['packages/model/src/'+file+'.rs' for file in ('settings','popup','main')]))
 fromto(D,DA,steps,paths)
 py('steps/checks/replay.py',D,DA,E,a.rustc,deps)
 for x in (D,DA):py('steps/peer/peer.py',x/s,x/v,E,sj,'--rustc',a.rustc)
 # The batch-path check needs only the static public tool declaration and public DTO declaration.
 # Do not materialize tool handlers or invoke them. Stop copying at the close of the declaration.
 def fragment(repo,tree,path,start,stop):
  with sp.Popen(['git','-C',getattr(a,repo),'show',refs[repo]+':'+path],stdout=sp.PIPE) as proc:
   seq=[];found=False
   for l in proc.stdout:
    if not found:found=start in l
    if found:
     seq.append(l)
     if stop in l:break
   proc.stdout.close()
  assert seq and stop in seq[-1];write(tree,path,b''.join(seq))
 assert git(a.modules,'rev-parse',refs['modules']+':tool/file-tools/src/read_many.rs').decode().strip()=='a43f14f8d7ba1585a6a35948d2bc8cd1e734eef4'
 assert git(a.core,'rev-parse',refs['core']+':crates/proteus-contracts/src/domain/tool.rs').decode().strip()=='438e620298bcee1725e8dde6338c69451f3c46a4'
 fragment('modules',M,'tool/file-tools/src/read_many.rs',b'let spec = json!({',b'});')
 fragment('core',C,'crates/proteus-contracts/src/domain/tool.rs',b'pub struct ToolSpec {',b'}')
 mod='src/tool_display/mod.rs';details='src/ui/chat/tool_row.rs'
 for x in (D,DA):
  py('batch-paths/checks/replay.py',M,C,x,a.contracts_json_rlib,a.contracts_rlib,a.rustc,'--expect','before' if x==D else 'after')
 py('batch-paths/peer/check.py','--display',D/mod,'--details',D/details,'--rlib',sj,'--rustc',a.rustc)
 py('batch-paths/peer/candidate.py',DA,'--base-details',D/details,'--rlib',sj,'--rustc',a.rustc)
 back(D,DA,steps,paths)
 print('PASS: pinned proposals, focused native and independent fixtures, exact rollback including newly added tests. No live GUI, provider, file tool or CLI run.')
