import argparse,hashlib,json,os,pathlib,queue,subprocess,tempfile,threading,time,signal
E=pathlib.Path(__file__).resolve().parent
BINARY=pathlib.Path(os.environ.get('PROTEUS_BINARY','/workspace/shared/nested-lifetime-evidence/proteus'))
REFERENCE=pathlib.Path(os.environ.get('PROTEUS_REFERENCE_MODULE','/workspace/shared/proteus-review-20261112/core/target/sources/modules/target/debug/proteus-reference-module'))
POLICY=E/'process_allow_all_policy.py'
def git(path,*args,check=True):
 r=subprocess.run(['git','-C',str(path),*args],capture_output=True,text=True)
 if check:assert r.returncode==0,repr((args,r.stderr))
 return r.stdout if check else {'code':r.returncode,'stdout':r.stdout,'stderr':r.stderr}
p=argparse.ArgumentParser();p.add_argument('--output',type=pathlib.Path,default=E/'run1');p.add_argument('--modes',nargs='*',default=['unstaged','staged','committed','cwd-subdir','cwd-shared','exclude-utf8','exclude-legacy']);args=p.parse_args();O=args.output;O.mkdir(parents=True,exist_ok=True)
for mode in args.modes:
 root=pathlib.Path(tempfile.mkdtemp(prefix='proteus-boundary-'+mode+'-'));repo=root/'workspace';repo.mkdir();configs=root/'configs';configs.mkdir()
 markers=root/'markers.jsonl';config=configs/'root.toml';child=configs/'child.toml'
 for a in [('init','-q','-b','main'),('config','user.email','test@example.com'),('config','user.name','Synthetic Audit')]:git(repo,*a)
 (repo/'base.py').write_text('ROOT = "main application"\n');sub=repo/'service';sub.mkdir();(sub/'base.py').write_text('SERVICE = "subpackage"\n');(repo/'included').mkdir();(repo/'included/base.py').write_text('INCLUDED = True\n');git(repo,'add','.');git(repo,'commit','-qm','base fixture')
 if mode=='index-sparse':git(repo,'sparse-checkout','init','--cone');git(repo,'sparse-checkout','set','included')
 cwd=sub if mode.startswith('cwd-') else repo
 exclude=repo/'.git/info/exclude'
 if mode.startswith('exclude-'):
  exclude.write_bytes(b'# private local ignores; '+ ('caf\xe9'.encode('latin1') if mode=='exclude-legacy' else 'caf\xe9'.encode('utf8')) + b'\nlocal-settings.txt\n')
  (repo/'local-settings.txt').write_text('synthetic private local settings; not a real credential\n')
 before={'exclude_hex':exclude.read_bytes().hex(),'status':git(repo,'status','--porcelain'),'check_ignore':git(repo,'check-ignore','-v','local-settings.txt',check=False)}
 common=f'''active_provider = "fake"
[providers.fake]
provider = "fake"
model = "fake-tool-model"
[modules]
workflow = "worktree_probe"
policy = "fixture_allow_all"
[components.workflow]
command = "python3"
args = [{json.dumps(str(E/'worktree_fixture.py'))}, {json.dumps(str(markers))}]
[components.workflow.exports.workflow.worktree_probe]
[components.policy]
command = "python3"
args = [{json.dumps(str(POLICY))}]
[components.policy.exports.policy.fixture_allow_all]
[components.test-model]
command = {json.dumps(str(REFERENCE))}
[components.test-model.exports.model.fake]
[module_config.model.fake]
implementation = "fake"
'''
 config.write_text(common+f'''[agent_control]
surface = "task"
max_depth = 1
max_idle_processes = 2
[[agent_control.roles]]
name = "coder"
description = "coder"
config = {json.dumps(str(child))}
{'' if mode=='cwd-shared' else 'isolation = "worktree"'}
timeout_ms = 20000
''')
 child.write_text(common+'[agent_control]\nsurface = "none"\nmax_depth = 0\n')
 env=os.environ.copy();env.update(HOME=str(root),XDG_DATA_HOME=str(root/'data'),XDG_CONFIG_HOME=str(root/'config'),PYTHONDONTWRITEBYTECODE='1')
 proc=subprocess.Popen([str(BINARY),'--config',str(config),'--cwd',str(cwd),'--new-session','server','stdio'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,env=env,start_new_session=True)
 outputs=[];errors=[];lines=queue.Queue()
 def read():
  for line in proc.stdout:
   try:v=json.loads(line)
   except Exception:v={'raw':line}
   outputs.append(v);lines.put(v)
 threading.Thread(target=read,daemon=True).start();threading.Thread(target=lambda:errors.extend(proc.stderr.readlines()),daemon=True).start()
 def send(v):proc.stdin.write(json.dumps(v)+'\n');proc.stdin.flush()
 send({'type':'send','id':'main','text':'root-'+mode})
 deadline=time.monotonic()+30;response=None
 while time.monotonic()<deadline:
  try:v=lines.get(timeout=.05)
  except queue.Empty:
   if proc.poll() is not None:break
   continue
  if v.get('type')=='response' and v.get('id')=='main':response=v;break
 records=[json.loads(x) for x in markers.read_text().splitlines()] if markers.exists() else []
 written=next((r for r in records if r['name']=='child_written'),None);target=pathlib.Path(written['extra']['target']) if written else None
 result=next((r['extra'] for r in records if r['name']=='task_result'),None)
 summary={'mode':mode,'root':str(root),'repo':str(repo),'cwd':str(cwd),'response':response,'before':before,'records':records,'task_result':result,'target_exists':target.exists() if target else None,'checkout_exists':pathlib.Path(written['cwd']).exists() if written else None,'root_base_content':(repo/'base.py').read_text(),'worktrees':git(repo,'worktree','list','--porcelain'),'branches':git(repo,'branch','--list'),'exclude_hex_after':exclude.read_bytes().hex(),'status_after':git(repo,'status','--porcelain'),'check_ignore_after':git(repo,'check-ignore','-v','local-settings.txt',check=False)}
 if mode in ['unstaged','staged','committed']:
  summary['suggested_branch_merge']=git(repo,'merge','--ff-only','proteus/coder-call_0',check=False)
  summary['root_file_after_merge']=(repo/'base.py').read_text();summary['checkout_file_after_merge']=target.read_text()
  summary['branch_file']=git(repo,'show','proteus/coder-call_0:base.py')
  if mode in ['unstaged','staged']:
   summary['normal_worktree_remove']=git(repo,'worktree','remove',str(target.parent),check=False)
   summary['checkout_exists_after_normal_remove']=target.parent.exists()
 if mode.startswith('cwd-') and target:
  summary['files']={'root':(repo/'base.py').read_text(),'service':(repo/'service/base.py').read_text(),'child_root':(target.parent/'base.py').read_text(),'child_service':(target.parent/'service/base.py').read_text() if (target.parent/'service/base.py').exists() else None}
 before_shutdown=list(outputs);send({'type':'shutdown','id':'shutdown'})
 try:proc.wait(timeout=4)
 except subprocess.TimeoutExpired:os.killpg(proc.pid,signal.SIGTERM);proc.wait(timeout=4)
 (O/(mode+'-outputs.json')).write_text(json.dumps(before_shutdown,indent=2));(O/(mode+'-markers.jsonl')).write_text(markers.read_text() if markers.exists() else '');(O/(mode+'-stderr.log')).write_text(''.join(errors));(O/(mode+'-summary.json')).write_text(json.dumps(summary,indent=2));print(json.dumps({'mode':mode,'target_exists':summary['target_exists'],'task_result':result,'files':summary.get('files'),'exclude_hex_before':before['exclude_hex'],'exclude_hex_after':summary['exclude_hex_after'],'status_after':summary['status_after'],'merge':summary.get('suggested_branch_merge')},ensure_ascii=False))
(O/'provenance.txt').write_text('Core HEAD: 89997df995df7c39b713e16aba216ecb19c8f497\n'+str(BINARY)+' sha256='+hashlib.sha256(BINARY.read_bytes()).hexdigest()+'\n'+str(REFERENCE)+' sha256='+hashlib.sha256(REFERENCE.read_bytes()).hexdigest()+'\n'+subprocess.check_output(['git','--version'],text=True))
