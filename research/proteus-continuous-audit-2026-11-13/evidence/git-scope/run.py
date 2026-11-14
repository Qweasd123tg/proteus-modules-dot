import argparse,hashlib,json,os,pathlib,queue,subprocess,tempfile,threading,time,signal
E=pathlib.Path(__file__).resolve().parent
BINARY=pathlib.Path(os.environ.get('PROTEUS_BINARY','/workspace/shared/nested-lifetime-evidence/proteus'))
REFERENCE=pathlib.Path(os.environ.get('PROTEUS_REFERENCE_MODULE','/workspace/shared/proteus-review-20261112/core/target/sources/modules/target/debug/proteus-reference-module'))
p=argparse.ArgumentParser();p.add_argument('--output',type=pathlib.Path,default=E/'pass1');p.add_argument('--modes',nargs='*',default=['reuse-same','reuse-unique','reuse-noidle','reuse-shared','hook','env-clear','env-same','env-other','env-dironly','env-dironly-commit','env-clear-commit']);args=p.parse_args();O=args.output;O.mkdir(parents=True,exist_ok=True)
GIT_KEYS=['GIT_DIR','GIT_WORK_TREE','GIT_INDEX_FILE','GIT_COMMON_DIR','GIT_PREFIX']
clean_env={k:v for k,v in os.environ.items() if k not in GIT_KEYS}
def git(path,*a):
 r=subprocess.run(['git','-C',str(path),*a],env=clean_env,capture_output=True,text=True)
 return {'code':r.returncode,'stdout':r.stdout,'stderr':r.stderr}
def checked(path,*a):
 r=git(path,*a);assert r['code']==0,(a,r);return r['stdout']
for mode in args.modes:
 root=pathlib.Path(tempfile.mkdtemp(prefix='proteus-gittrace-'+mode+'-'));repo=root/'requested';other=root/'other';configs=root/'configs';configs.mkdir();markers=root/'markers.jsonl'
 for path in [repo,other]:
  path.mkdir()
  for a in [('init','-qb','main'),('config','user.email','synthetic@example.com'),('config','user.name','Synthetic Fixture')]:checked(path,*a)
  (path/'base.py').write_text('SOURCE = "'+path.name+' repository"\n');checked(path,'add','.');checked(path,'commit','-qm','base fixture')
 hook=repo/'.git/hooks/post-checkout'
 if mode=='hook':hook.write_text('#!/bin/sh\necho "synthetic post-checkout dependency unavailable" >&2\nexit 1\n');hook.chmod(0o755)
 common=f'''active_provider = "fake"
[providers.fake]
provider = "fake"
model = "fake-tool-model"
[modules]
workflow = "git_trace"
policy = "fixture_allow_all"
[components.workflow]
command = "python3"
args = [{json.dumps(str(E/'workflow.py'))}, {json.dumps(str(markers))}]
[components.workflow.exports.workflow.git_trace]
[components.policy]
command = "python3"
args = [{json.dumps(str(E/'process_allow_all_policy.py'))}]
[components.policy.exports.policy.fixture_allow_all]
[components.test-model]
command = {json.dumps(str(REFERENCE))}
[components.test-model.exports.model.fake]
[module_config.model.fake]
implementation = "fake"
'''
 child=configs/'child.toml';config=configs/'root.toml'
 config.write_text(common+f'''[agent_control]
surface = "task"
max_depth = 1
max_idle_processes = {0 if mode=='reuse-noidle' else 2}
[[agent_control.roles]]
name = "coder"
description = "coder"
config = {json.dumps(str(child))}
{'' if mode=='reuse-shared' else 'isolation = "worktree"'}
timeout_ms = 20000
''')
 child_text=common+'[agent_control]\nsurface = "none"\nmax_depth = 0\n'
 if mode.startswith('reuse-'):child_text+=f'''[[tools.mcp_servers]]
name = "local_files"
command = "python3"
args = [{json.dumps(str(E/'mcp_files.py'))}]
safety = "ReadOnly"
timeout_ms = 5000
'''
 child.write_text(child_text)
 env=clean_env.copy();env.update(HOME=str(root),XDG_DATA_HOME=str(root/'data'),XDG_CONFIG_HOME=str(root/'config'),PYTHONDONTWRITEBYTECODE='1')
 if mode in ['env-same','env-other','env-dironly','env-dironly-commit']:
  scoped=repo if mode=='env-same' else other;env.update(GIT_DIR=str(scoped/'.git'))
  if not mode.startswith('env-dironly'):env['GIT_WORK_TREE']=str(scoped)
 proc=subprocess.Popen([str(BINARY),'--config',str(config),'--cwd',str(repo),'--new-session','server','stdio'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,env=env,start_new_session=True)
 outputs=[];errors=[];q=queue.Queue()
 def read():
  for line in proc.stdout:
   try:v=json.loads(line)
   except Exception:v={'raw':line}
   outputs.append(v);q.put(v)
 threading.Thread(target=read,daemon=True).start();threading.Thread(target=lambda:errors.extend(proc.stderr.readlines()),daemon=True).start()
 def send(v):proc.stdin.write(json.dumps(v)+'\n');proc.stdin.flush()
 snapshots=[]
 for n in range(3 if mode=='hook' else (2 if mode.startswith('reuse-') else 1)):
  if mode=='hook' and n==1:
   hook.write_text('#!/bin/sh\nexit 0\n')
   send({'type':'new_session','id':'reset'})
   while True:
    reset=q.get(timeout=10)
    if reset.get('type')=='response' and reset.get('id')=='reset':
     assert reset['ok'],reset
     break
  send({'type':'send','id':str(n),'text':'root:'+mode+':'+str(n)})
  deadline=time.monotonic()+30;response=None
  while time.monotonic()<deadline:
   try:v=q.get(timeout=.05)
   except queue.Empty:
    if proc.poll() is not None:break
    continue
   if v.get('type')=='response' and v.get('id')==str(n):response=v;break
  if not response:raise RuntimeError('Missing response '+mode+' '+str(n)+' '+str(outputs)[-1200:])
  records=[json.loads(l) for l in markers.read_text().splitlines()]
  paths={r['cwd'] for r in records if r['name'].startswith('child_') or r['name']=='mcp_result'}
  snapshots.append({'n':n,'response':response,'records':records,'requested_worktrees':git(repo,'worktree','list','--porcelain'),'other_worktrees':git(other,'worktree','list','--porcelain'),'requested_branches':git(repo,'branch','--list'),'other_branches':git(other,'branch','--list'),'requested_status':git(repo,'status','--porcelain'),'other_status':git(other,'status','--porcelain'),'requested_file':(repo/'base.py').read_text(),'other_file':(other/'base.py').read_text(),'requested_head':git(repo,'rev-parse','HEAD'),'other_head':git(other,'rev-parse','HEAD'),'requested_branch_file':git(repo,'show','proteus/coder-call_0:base.py'),'other_branch_file':git(other,'show','proteus/coder-call_0:base.py'),'requested_branch_tip':git(repo,'rev-parse','--verify','refs/heads/proteus/coder-call_0'),'other_branch_tip':git(other,'rev-parse','--verify','refs/heads/proteus/coder-call_0'),'child_paths':{p:{'exists':pathlib.Path(p).exists(),'git_common_dir':git(p,'rev-parse','--git-common-dir') if pathlib.Path(p).exists() else None,'base':(pathlib.Path(p)/'base.py').read_text() if (pathlib.Path(p)/'base.py').exists() else None} for p in paths}})
 before_shutdown=list(outputs);send({'type':'shutdown','id':'shutdown'})
 try:proc.wait(timeout=4)
 except subprocess.TimeoutExpired:os.killpg(proc.pid,signal.SIGTERM);proc.wait(timeout=4)
 summary={'mode':mode,'root':str(root),'requested':str(repo),'other':str(other),'git_environment':{k:env[k] for k in GIT_KEYS if k in env},'snapshots':snapshots}
 (O/(mode+'-summary.json')).write_text(json.dumps(summary,indent=2));(O/(mode+'-outputs.json')).write_text(json.dumps(before_shutdown,indent=2));(O/(mode+'-stderr.log')).write_text(''.join(errors));(O/(mode+'-markers.jsonl')).write_text(markers.read_text())
 print(json.dumps({'mode':mode,'results':[(r['name'],r['prompt'],r['extra']) for r in snapshots[-1]['records'] if r['name'] in ['task_result','mcp_result','child_written']]},ensure_ascii=False),flush=True)
(O/'provenance.txt').write_text('Core HEAD: 89997df995df7c39b713e16aba216ecb19c8f497\n'+str(BINARY)+' sha256='+hashlib.sha256(BINARY.read_bytes()).hexdigest()+'\n'+str(REFERENCE)+' sha256='+hashlib.sha256(REFERENCE.read_bytes()).hexdigest()+'\n'+subprocess.check_output(['git','--version'],text=True))
