"""Verify the exact published diffs against today's named repo refs. Does not apply anything to a checkout."""
import argparse,csv,hashlib,subprocess as sp,tempfile,re
from pathlib import Path
p=argparse.ArgumentParser()
for r in ('dot','core','modules','desktop','extensions'):p.add_argument('--'+r,required=True,type=Path)
p.add_argument('--proposal-cache',type=Path,help='optional verified Git blobs named by SHA for shallow dot clones');a=p.parse_args();here=Path(__file__).resolve().parent
refs={'dot':'36473954b15f518654909ea8d78a298cdb4a29be','core':'c2cbadee518788f306ffb2b5271036b2658ea8cc','desktop':'2307e9c67125bbe66f15ced51317a2dfcc437aa4','modules':'0fe8e3b4dfb64ca2e07df8af016d7ccc3a7de45f','extensions':'ef064381d2194d95faef2b85f6cc3a1c34c6b975'}
def obj(b):return hashlib.sha1(f'blob {len(b)}\0'.encode()+b).hexdigest()
def get(r,s):return sp.check_output(['git','-C',getattr(a,r),'show',s])
# PR merge metadata was recorded from GitHub. This offline step checks consistency only.
rows=list(csv.DictReader((here/'prs.tsv').open(),delimiter='\t'))
assert sorted(int(z['pr']) for z in rows)==list(range(184,206))
assert all(z['repo']=='Qweasd123tg/proteus-modules-dot' and z['base']=='main' for z in rows)
count=0
for row in csv.DictReader((here/'samples.tsv').open(),delimiter='\t'):
 n,r,path,sha=[row[k] for k in ['pr','repo','path','published_blob']]
 src=sp.run(['git','-C',a.dot,'cat-file','blob',sha],capture_output=True)
 if src.returncode==0:b=src.stdout
 elif a.proposal_cache:b=(a.proposal_cache/sha).read_bytes()
 else:raise RuntimeError('missing published dot blob '+sha+'; full dot clone or --proposal-cache required')
 assert obj(b)==sha
 with tempfile.TemporaryDirectory() as tmp:
  d=Path(tmp);f=d/'proposal.diff';f.write_bytes(b);files=re.findall(r'^--- a/([^\n]+)',b.decode(),re.M);assert files
  old={}
  for name in files:
   raw=get(r,refs[r]+':'+name);old[name]=obj(raw);y=d/name;y.parent.mkdir(exist_ok=True,parents=True);y.write_bytes(raw)
  def apply(*opts):return sp.run(['git','apply',*opts,f],cwd=d,stderr=sp.DEVNULL,stdout=sp.DEVNULL).returncode
  fwd=apply('--check');rev=apply('--reverse','--check')
  assert (fwd,rev)==(0,1),(n,fwd,rev)
  assert apply()==0
  for name,h in old.items():assert obj((d/name).read_bytes())!=h
  assert apply('--reverse')==0 and all(obj((d/name).read_bytes())==h for name,h in old.items())
  print(f'#{n} {r} {len(files)} file(s): exact diff applies forward; reverse rejected on upstream; exact rollback.')
  count+=1
print(f'{len(rows)} PRs target dot/main; sample of {count} unintegrated exact diffs across 4 upstreams (not an exhaustive semantic audit).')
