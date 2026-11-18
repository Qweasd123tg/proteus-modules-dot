"""Replay small inert projections at four exact Git commits. No application, HTTP client, GUI, provider, profile or tool handler runs."""
import argparse,hashlib,re,shutil,subprocess as sp,sys,tempfile
from pathlib import Path
p=argparse.ArgumentParser(description=__doc__)
for k in ['desktop','core','dot','extensions','modules','deps','markdown-rlib','contracts-rlib','contracts-json-rlib']:p.add_argument('--'+k,required=True,type=Path)
p.add_argument('--rustc',default='rustc');p.add_argument('--proposal-cache',type=Path);a=p.parse_args();root=Path(__file__).resolve().parents[1]
refs={'desktop':'2307e9c67125bbe66f15ced51317a2dfcc437aa4','core':'c2cbadee518788f306ffb2b5271036b2658ea8cc','modules':'0fe8e3b4dfb64ca2e07df8af016d7ccc3a7de45f','extensions':'ef064381d2194d95faef2b85f6cc3a1c34c6b975'}
deps=a.deps.resolve();sj,=deps.glob('libserde_json-*.rlib');se,=deps.glob('libserde-*.rlib');md=a.markdown_rlib.resolve()
def git(r,*args):return sp.check_output(['git','-C',r,*args])
def dst(r,n,b):f=r/n;f.parent.mkdir(parents=True,exist_ok=True);f.write_bytes(b)
def project(r,key,paths):
 for n in paths:dst(r,n,git(getattr(a,key),'show',refs[key]+':'+n))
def run(*cmd,dir=None):sp.run(cmd,cwd=dir,check=True)
def py(path,*argv):run(sys.executable,root/path,*argv)
def pn(p):return re.findall(r'^--- a/([^\n]+)',p.read_text(),re.M)
def apply(tree,patch,reverse=False):
 op=['--reverse'] if reverse else [];run('git','apply','--check','--whitespace=error',*op,patch,dir=tree);run('git','apply','--whitespace=error',*op,patch,dir=tree)
def content(t):return {f.relative_to(t):f.read_bytes() for f in t.rglob('*') if f.is_file()}
def prior(s):
 v=sp.run(['git','-C',a.dot,'cat-file','blob',s],capture_output=True)
 if v.returncode==0:b=v.stdout
 elif a.proposal_cache:b=(a.proposal_cache/s).read_bytes()
 else:raise RuntimeError('missing Git blob '+s)
 assert hashlib.sha1(f'blob {len(b)}\0'.encode()+b).hexdigest()==s;return b
for line in (root/'SHA256SUMS').read_text().splitlines():
 h,n=line.split('  ',1);assert hashlib.sha256((root/n).read_bytes()).hexdigest()==h,n
q=root/'choice/share-checkbox-values.patch';g=root/'gfm/gfm-table-column-alignment.patch';f=root/'tools/tools-word-filter.patch'
dto='crates/proteus-contracts/src/domain/config_schema.rs';ui='src/ui/settings/fields.rs';node='vendor/gpui-base/src/text/node.rs';html='vendor/gpui-base/src/text/format/html.rs'
with tempfile.TemporaryDirectory() as directory:
 t=Path(directory);d=t/'desktop';fixed=t/'fixed';core=t/'core';ext=t/'extensions';modules=t/'modules';adj=t/'with197';before197=t/'before197'
 patch197=t/'selected-table-boundaries.patch';patch197.write_bytes(prior('eaa843244a7f8cd339a4e527182b4a3a6ca27b84'))
 priors=[]
 for i,sha in enumerate(('c6aa4570263b617bba830dfc8a5747bb35e1b6aa','b0387ac28cc242fee807656c967f56d0ac96cbc8')):
  patch=t/f'tool-compat{i}.patch';patch.write_bytes(prior(sha));priors.append(patch)
 paths={*(n for v in priors for n in pn(v)),*pn(f),*pn(q),*pn(g),node,'src/ui/settings/tags.rs','src/settings/schema.rs','src/tool_display/mod.rs','src/ui/chat/tool_row.rs','src/ui/settings/search.rs','src/ui/settings/spot.rs'}
 # Extra read-only source fragments used in the search checks are added below.
 project(d,'desktop',paths);project(ext,'extensions',('sdk/src/ui.rs','packages/markdown-render/src/inlines.rs'))
 with sp.Popen(['git','-C',a.core,'show',refs['core']+':'+dto],stdout=sp.PIPE) as proc:
  first=[]
  for line in proc.stdout:
   if line.startswith(b'impl ConfigField'):break
   first.append(line)
  proc.stdout.close()
 dst(core,dto,b''.join(first))
 shutil.copytree(d,fixed)
 for patch in (q,g,f):apply(fixed,patch)
 py('choice/checks/replay.py',d,core,q,se,sj,'--rustc',a.rustc)
 for tree,label in [(d,'before'),(fixed,'after')]:
  o=sp.check_output([sys.executable,root/'choice/peer/peer.py',tree/ui,core/dto,deps,'--rustc',a.rustc]);print(o.decode(),end='');(t/(label+'.log')).write_bytes(o)
 py('choice/peer/compare.py',t/'before.log',t/'after.log')
 py('gfm/checks/replay.py',d,d/html,fixed/html,a.rustc,md,md.parent)
 py('gfm/peer/run.py',d,fixed,ext,md,deps,a.rustc)
 shutil.copytree(d,before197);apply(before197,patch197);shutil.copytree(before197,adj);apply(adj,g)
 py('gfm/peer/run.py',before197,adj,ext,md,deps,a.rustc,adj/node)
 apply(adj,g,True);assert content(before197)==content(adj);apply(before197,patch197,True);assert content(before197)==content(d)
 py('open/grep/checks/replay.py','--desktop',d,'--rlib',sj,'--rustc',a.rustc)
 # Only published name/description/alias declaration lines are materialized from module implementations.
 def declaration(path,lines):
  wanted=set(lines);out=[]
  with sp.Popen(['git','-C',a.modules,'show',refs['modules']+':'+path],stdout=sp.PIPE) as proc:
   for n,line in enumerate(proc.stdout,1):
    out.append(line if n in wanted else b'\n')
    if n==max(wanted):break
   proc.stdout.close()
  assert len(out)==max(wanted);dst(modules,path,b''.join(out))
 declaration('tool/git-tools/src/lib.rs',[32,33,52,75,76,112]);declaration('tool/rust-lsp/src/lib.rs',[24,100,101,121])
 for args in ([],['--patch',f]):
  py('tools/checks/replay.py',modules,d,a.contracts_json_rlib,a.contracts_rlib,a.rustc,*args)
 py('tools/peer/replay.py',d,fixed,'--rustc',a.rustc)
 # Prior #186 and #206 update Settings search; local matcher must still work with those proposals.
 base_p=t/'previous';stack=t/'stack';other=t/'other'
 shutil.copytree(d,base_p)
 for v in priors:apply(base_p,v)
 py('tools/checks/replay.py',modules,base_p,a.contracts_json_rlib,a.contracts_rlib,a.rustc,'--patch',f)
 shutil.copytree(base_p,stack);apply(stack,f)
 shutil.copytree(d,other)
 for v in [f,*priors]:apply(other,v)
 assert content(stack)==content(other)
 for v in reversed([f,*priors]):apply(other,v,True)
 assert content(other)==content(d)
 for v in reversed([*priors,f]):apply(stack,v,True)
 assert content(stack)==content(d)
 for patch in (f,g,q):apply(fixed,patch,True)
 assert content(d)==content(fixed)
 print('PASS: originals, candidates, independent replay, selected GFM/#197 and search/#186/#206 stacks and exact rollback. No full GUI, actual settings edits, tool calls or system clipboard.')
