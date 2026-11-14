import hashlib,json,os,pathlib,queue,subprocess,tempfile,threading,time,signal
E=pathlib.Path(__file__).resolve().parent
BINARY=pathlib.Path(os.environ.get('PROTEUS_BINARY','/workspace/shared/nested-lifetime-evidence/proteus'))
REFERENCE=pathlib.Path(os.environ.get('PROTEUS_REFERENCE_MODULE','/workspace/shared/proteus-review-20261112/core/target/sources/modules/target/debug/proteus-reference-module'))
POLICY=E/'process_allow_all_policy.py'
def git(path,*args):
 r=subprocess.run(['git','-C',str(path),*args],capture_output=True,text=True)
 assert r.returncode==0,repr((args,r.stderr));return r.stdout
for mode in ['default-untracked','hidden-untracked','hidden-staged','hidden-modified']:
 root=pathlib.Path(tempfile.mkdtemp(prefix='proteus-untracked-'+mode+'-'));cwd=root/'workspace';cwd.mkdir();configs=root/'configs';configs.mkdir()
 markers=root/'markers.jsonl';config=configs/'root.toml';child=configs/'child.toml'
 for args in [('init','-q','-b','main'),('config','user.email','test@example.com'),('config','user.name','Synthetic Audit')]:git(cwd,*args)
 (cwd/'base.py').write_text('BASE = True\n');git(cwd,'add','.');git(cwd,'commit','-qm','base fixture')
 if mode.startswith('hidden'):git(cwd,'config','status.showUntrackedFiles','no')
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
description = "isolated coder"
config = {json.dumps(str(child))}
isolation = "worktree"
timeout_ms = 20000
''')
 child.write_text(common+'[agent_control]\nsurface = "none"\nmax_depth = 0\n')
 env=os.environ.copy();env.update(HOME=str(root),XDG_DATA_HOME=str(root/'data'),XDG_CONFIG_HOME=str(root/'config'),PYTHONDONTWRITEBYTECODE='1')
 p=subprocess.Popen([str(BINARY),'--config',str(config),'--cwd',str(cwd),'--new-session','server','stdio'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,env=env,start_new_session=True)
 outputs=[];errors=[];lines=queue.Queue()
 def read():
  for line in p.stdout:
   try:v=json.loads(line)
   except Exception:v={'raw':line}
   outputs.append(v);lines.put(v)
 threading.Thread(target=read,daemon=True).start();threading.Thread(target=lambda:errors.extend(p.stderr.readlines()),daemon=True).start()
 def send(v):p.stdin.write(json.dumps(v)+'\n');p.stdin.flush()
 send({'type':'send','id':'main','text':'root-'+mode})
 deadline=time.monotonic()+30;response=None
 while time.monotonic()<deadline:
  try:v=lines.get(timeout=.05)
  except queue.Empty:
   if p.poll() is not None:break
   continue
  if v.get('type')=='response' and v.get('id')=='main':response=v;break
 records=[json.loads(x) for x in markers.read_text().splitlines()] if markers.exists() else []
 child_written=next((r for r in records if r['name']=='child_written'),None)
 target=pathlib.Path(child_written['extra']['target']) if child_written else None
 result=next((r['extra'] for r in records if r['name']=='task_result'),None)
 summary={'mode':mode,'root':str(root),'response':response,'child_written':child_written,'task_result':result,'target_exists':target.exists() if target else None,'checkout_exists':target.parent.exists() if target else None,'worktrees':git(cwd,'worktree','list','--porcelain'),'branches':git(cwd,'branch','--list'),'tracked_new_file':git(cwd,'ls-tree','-r','HEAD','--','new_algorithm.py')}
 before_shutdown=list(outputs)
 send({'type':'shutdown','id':'shutdown'})
 try:p.wait(timeout=4)
 except subprocess.TimeoutExpired:os.killpg(p.pid,signal.SIGTERM);p.wait(timeout=4)
 (E/(mode+'-outputs.json')).write_text(json.dumps(before_shutdown,indent=2));(E/(mode+'-markers.jsonl')).write_text(markers.read_text() if markers.exists() else '');(E/(mode+'-stderr.log')).write_text(''.join(errors));(E/(mode+'-summary.json')).write_text(json.dumps(summary,indent=2));print(json.dumps({'mode':mode,'target_exists':summary['target_exists'],'checkout_exists':summary['checkout_exists'],'task_result':result},ensure_ascii=False))
(E/'provenance.txt').write_text('Core HEAD: 89997df995df7c39b713e16aba216ecb19c8f497\n'+str(BINARY)+' sha256='+hashlib.sha256(BINARY.read_bytes()).hexdigest()+'\n'+str(REFERENCE)+' sha256='+hashlib.sha256(REFERENCE.read_bytes()).hexdigest()+'\n'+subprocess.check_output(['git','--version'],text=True))
