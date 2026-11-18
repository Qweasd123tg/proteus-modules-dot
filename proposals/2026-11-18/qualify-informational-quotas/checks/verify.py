"""Verify local-only public quota presentation on immutable Git inputs, including the earlier #191 candidate."""
import argparse,hashlib,shutil,sys,subprocess as sp,tempfile
from pathlib import Path
p=argparse.ArgumentParser(description=__doc__)
for k in ['extensions','core','dot','deps']:p.add_argument('--'+k,type=Path,required=True)
p.add_argument('--rustc',default='rustc');a=p.parse_args();root=Path(__file__).resolve().parents[1];dp=a.deps.resolve();se,=dp.glob('libserde-*.rlib');sj,=dp.glob('libserde_json-*.rlib')
def git(r,*x):return sp.check_output(['git','-C',r,*x])
def py(path,*args):sp.run([sys.executable,root/path,*args],check=True)
def put(d,n,b):f=d/n;f.parent.mkdir(parents=True,exist_ok=True);f.write_bytes(b)
def apply(d,p,rev=False):
 q=['--reverse'] if rev else []
 for cmd in (['--check'],[]):sp.run(['git','apply',*cmd,'--whitespace=error',*q,p],cwd=d,check=True)
def content(d):return {x.relative_to(d):x.read_bytes() for x in d.rglob('*') if x.is_file()}
for l in (root/'SHA256SUMS').read_text().splitlines():
 h,n=l.split('  ',1);assert hashlib.sha256((root/n).read_bytes()).hexdigest()==h,n
patch=root/'informational-quota-scope.patch';assert hashlib.sha256(patch.read_bytes()).hexdigest()=='57fadeac6a94f314d1fa4bdb1272026a57222f146baf63b9b7f1ff160bd1c0a6'
with tempfile.TemporaryDirectory() as td:
 t=Path(td);E=t/'ext';C=t/'core';M=t/'candidate';A=t/'191';R=t/'191candidate';X=t/'candidate191';old=t/'quota191.patch';dto='crates/proteus-contracts/src/contracts/model_quota.rs'
 with sp.Popen(['git','-C',a.core,'show','c2cbadee518788f306ffb2b5271036b2658ea8cc:'+dto],stdout=sp.PIPE) as proc:
  lines=[]
  for line in proc.stdout:
   if line.startswith(b'impl ModelQuotaSnapshot'):break
   lines.append(line)
  proc.stdout.close()
 put(C,dto,b''.join(lines))
 for n in ('sdk/src/value.rs','sdk/src/ui.rs','packages/quota/src/view.rs','packages/quota/src/describe.rs'):put(E,n,git(a.extensions,'show','ef064381d2194d95faef2b85f6cc3a1c34c6b975:'+n))
 s='233db3c081e500ea59699b1f8fdc5dc3d4aadbe2';b=git(a.dot,'cat-file','blob',s);assert hashlib.sha1(f'blob {len(b)}\0'.encode()+b).hexdigest()==s;old.write_bytes(b)
 shutil.copytree(E,M);apply(M,patch);shutil.copytree(E,A);apply(A,old);shutil.copytree(A,R);apply(R,patch);shutil.copytree(M,X);apply(X,old);assert content(X)==content(R)
 for before,after in [(E,M),(A,R)]:
  py('checks/replay.py',before,after,E,C,dp,'--rustc',a.rustc)
  py('peer/projection/run.py',C,before,after,a.rustc,dp)
 py('peer/compat/check.py',E,patch,old,se,sj,a.rustc,C)
 for d,p1,p2 in [(R,patch,old),(X,old,patch)]:
  apply(d,p1,True);apply(d,p2,True);assert content(E)==content(d)
 apply(M,patch,True);assert content(M)==content(E)
 print('PASS: isolated current scope, unchanged outputs elsewhere, prior #191 combination both ways and exact rollback. No connectivity, provider, quota lookup, GUI or operating-system clock.')
