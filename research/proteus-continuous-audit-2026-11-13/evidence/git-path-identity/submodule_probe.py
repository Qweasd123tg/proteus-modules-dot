"""Negative-control hypothesis: ignored dirty submodule is not deleted by Git cleanup."""
from pathlib import Path
import subprocess,tempfile,json
r=Path(tempfile.mkdtemp(prefix='git-submodule-cleanup-'));calls=[]
def run(p,*a):
 x=subprocess.run(['git','-C',str(p),*a],capture_output=True,text=True)
 calls.append({'cwd':str(p),'args':a,'code':x.returncode,'stdout':x.stdout,'stderr':x.stderr});return x
for name in ['repo','dep']:
 p=r/name;p.mkdir()
 for a in [('init','-qb','main'),('config','user.email','fixture@example.com'),('config','user.name','Fixture')]:assert run(p,*a).returncode==0
 (p/'base.txt').write_text(name);assert run(p,'add','.').returncode==0;assert run(p,'commit','-qm','base').returncode==0
p=r/'repo';assert run(p,'-c','protocol.file.allow=always','submodule','add','-q',str(r/'dep'),'dep').returncode==0;assert run(p,'commit','-qam','submodule').returncode==0
w=r/'work';assert run(p,'worktree','add','-b','probe',str(w),'HEAD').returncode==0
assert list((w/'dep').iterdir())==[]
assert run(w,'-c','protocol.file.allow=always','submodule','update','--init').returncode==0
(w/'dep'/'base.txt').write_text('uncommitted child result')
assert run(w,'config','submodule.dep.ignore','all').returncode==0
assert run(w,'status','--porcelain').stdout==''
x=run(p,'worktree','remove',str(w));assert x.returncode==128
assert (w/'dep'/'base.txt').read_text()=='uncommitted child result'
print(json.dumps({'scope':'Git-only negative control, not a real TaskTool invocation','fixture_root':str(r),'child_file_retained':True,'calls':calls},indent=2))
