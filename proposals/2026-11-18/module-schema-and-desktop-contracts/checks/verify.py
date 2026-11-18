"""Offline: patched source projections on synthetic contents, never a running app, profile or user repository."""
from pathlib import Path
import argparse,hashlib,os,re,shutil,subprocess as sp,sys,tempfile
p=argparse.ArgumentParser(description=__doc__)
for k in ['desktop','core','modules','extensions','dot','deps','markdown']:p.add_argument('--'+k,required=True,type=Path)
p.add_argument('--proposal-cache',type=Path);p.add_argument('--rustc',default='rustc');p.add_argument('--rustdoc',default='rustdoc');a=p.parse_args()
root=Path(__file__).resolve().parents[1];ck=root/'checks';deps=a.deps.resolve();sj,=deps.glob('libserde_json-*.rlib');se,=deps.glob('libserde-*.rlib')
refs={'desktop':'2307e9c67125bbe66f15ced51317a2dfcc437aa4','extensions':'ef064381d2194d95faef2b85f6cc3a1c34c6b975','core':'c2cbadee518788f306ffb2b5271036b2658ea8cc'}
def run(*args,cwd=None,expected=0):
 q=sp.run(args,cwd=cwd,env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1'})
 if q.returncode!=expected:raise RuntimeError(f'{args[:2]} returned {q.returncode}, expected {expected}')
def py(f,*args,expected=0):run(sys.executable,ck/f,*args,expected=expected)
def obj(b):return hashlib.sha1(f'blob {len(b)}\0'.encode()+b).hexdigest()
def put(d,n,b):z=d/n;z.parent.mkdir(parents=True,exist_ok=True);z.write_bytes(b)
def get(r,n):return sp.check_output(['git','-C',getattr(a,r),'show',refs[r]+':'+n])
def names(p):return re.findall(r'^--- a/([^\n]+)',p.read_text(),re.M)
def apply(d,p,rev=False):
 opt=['--reverse'] if rev else [];run('git','apply','--check','--whitespace=error',*opt,p,cwd=d);run('git','apply','--whitespace=error',*opt,p,cwd=d)
def same(x,y,ns):assert all((x/n).read_bytes()==(y/n).read_bytes() for n in ns)
def blob(s):
 v=sp.run(['git','-C',a.dot,'cat-file','blob',s],capture_output=True)
 if v.returncode==0:b=v.stdout
 elif a.proposal_cache:b=(a.proposal_cache/s).read_bytes()
 else:raise RuntimeError('missing dot object '+s)
 assert obj(b)==s;return b
for l in (root/'SHA256SUMS').read_text().splitlines():
 h,n=l.split('  ',1);assert hashlib.sha256((root/n).read_bytes()).hexdigest()==h,n
D=sorted((root/'patches/desktop').glob('*.patch'));E,=(root/'patches/extensions').glob('*.patch');assert len(D)==4
dg=sp.check_output(['git','-C',a.desktop,'rev-parse','--absolute-git-dir'],text=True).strip()
m='vendor/gpui-base/src/text/format/markdown.rs';node='vendor/gpui-base/src/text/node.rs';hi='vendor/gpui-base/src/text/range_highlight.rs'
sch='crates/proteus-contracts/src/domain/config_schema.rs';cs=get('core',sch)
# The Desktop-pinned Core contract is exactly current Core's schema, not a local lookalike.
assert obj(cs)=='5c1cb74d5d7afc957c05165c1b916019529a5129' and b'b6f48cdaaec0e97a083ac81c6292c711a10fe65d' in get('desktop','Cargo.toml')
old=sp.run(['git','-C',a.core,'rev-parse','--verify','b6f48cdaaec0e97a083ac81c6292c711a10fe65d:'+sch],text=True,capture_output=True)
if old.returncode==0:assert old.stdout.strip()==obj(cs)
else:print('Previous Core checkout is shallow: using verified published Git tree receipt for the Desktop pin.',flush=True)
with tempfile.TemporaryDirectory() as temp:
 d=Path(temp);B=d/'desktop';T=d/'candidate';X=d/'reverse';eb=d/'ext';et=d/'ext-patched';c=d/'core';put(c,sch,cs);pri=[]
 for row in (ck/'prior.tsv').read_text().splitlines():
  n,sha=row.split('\t');z=d/'prior'/Path(n).name;put(z.parent,z.name,blob(sha));pri.append(z)
 ns={m,node,hi,'src/declarative/lanes.rs','src/ui/extensions/declarative/list.rs','src/ui/extensions/declarative/rows.rs','src/ui/settings/fields.rs','src/ui/settings/editors.rs','vendor/gpui-base/src/input/base/state.rs','src/ui/tabs/tab.rs','src/ui/tabs/bar.rs'}|{'crates/tabs/src/'+n+'.rs' for n in ['tree','pane','layout','pins']}|{n for f in D+pri for n in names(f)}
 for n in ns:put(B,n,get('desktop',n))
 put(eb,'sdk/src/ui.rs',get('extensions','sdk/src/ui.rs'));shutil.copytree(eb,et);apply(et,E)
 for z,order in [(T,D),(X,reversed(D))]:
  shutil.copytree(B,z)
  for f in order:apply(z,f)
 same(T,X,ns)
 for f in reversed(D):apply(X,f,True)
 same(B,X,ns)
 print('Four Desktop source proposals compose identically in both orders; reverse exact. SDK changes docs only.',flush=True)
 for z,phase in [(B,'before'),(T,'after')]:
  py('multiline/check.py',c,z,se,sj,'--rustc',a.rustc,'--expect',phase)
  py('menu/run.py',z,a.rustc);py('menu/peer/review.py',z,'--rustc',a.rustc)
  py('markdown/peer/run.py',z/m,z/node,z/hi,a.markdown,a.rustc,expected=int(z==B))
  py('raw/peer/check.py',z,'--rustc',a.rustc)
  py('sdk/replay.py',eb if z==B else et,z,deps,'--rustc',a.rustc)
 py('markdown/run.py',B/m,T/m,B/node,B/hi,a.markdown,a.rustc)
 py('raw/replay.py','--desktop',dg,'--rustc',a.rustc)
 py('multiline/peer/replay.py',B,root/'patches/desktop/multiline-array-editor.patch',sj,a.rustc)
 py('sdk/peer/review.py','--before-ui',eb/'sdk/src/ui.rs','--after-ui',et/'sdk/src/ui.rs','--deps',deps,'--rustc',a.rustc,'--rustdoc',a.rustdoc)
 apply(et,E,True);same(eb,et,['sdk/src/ui.rs'])
 # Selected, specifically overlapping predecessors: #186, #201, #202 and #205. Not the whole proposal backlog.
 C=d/'combined';shutil.copytree(B,C)
 for f in pri+D:apply(C,f)
 py('multiline/check.py',c,C,se,sj,'--rustc',a.rustc,'--expect','after')
 py('raw/peer/check.py',C,'--rustc',a.rustc)
 py('menu/peer/review.py',C,'--rustc',a.rustc)
 py('markdown/peer/run.py',C/m,C/node,C/hi,a.markdown,a.rustc)
 for f in reversed(pri+D):apply(C,f,True)
 same(B,C,ns)
 print('Selected prior + new proposals: exact rollback and focused combined replays.',flush=True)
args=[]
for r in ['desktop','core','modules','extensions','dot']:args+=['--'+r,getattr(a,r)]
if a.proposal_cache:args+=['--proposal-cache',a.proposal_cache]
run(sys.executable,root/'adoption/check.py',*args)
print('PASS: synthetic native checks, checked documentation example, proposal status. No running GPUI or profile.')
