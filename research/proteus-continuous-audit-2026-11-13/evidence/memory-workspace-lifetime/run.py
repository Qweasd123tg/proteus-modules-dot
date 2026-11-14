import hashlib,json,os,pathlib,queue,subprocess,tempfile,threading,time,signal
E=pathlib.Path(__file__).resolve().parent
CORE=pathlib.Path('/workspace/shared/proteus-review-20261112/core')
BINARY=pathlib.Path('/workspace/shared/nested-lifetime-evidence/proteus')
REFERENCE=CORE/'target/sources/modules/target/debug/proteus-reference-module'
MEMORIES={'jsonl_memory':pathlib.Path('/workspace/shared/trace-integration-round8-module-target/debug/proteus-memory-pack-module'), 'sqlite_memory': CORE/'target/sources/modules/target/debug/proteus-sqlite-memory-module'}
def git(path,*args):
 r=subprocess.run(['git','-C',str(path),*args],capture_output=True,text=True)
 assert r.returncode==0,repr((args,r.stderr));return r.stdout
for backend,memory_binary in MEMORIES.items():
 for mode in ['worktree-default','worktree-absolute','worktree-dirty','shared-default']:
  root=pathlib.Path(tempfile.mkdtemp(prefix='proteus-memory-lifetime-'));cwd=root/'workspace';cwd.mkdir();configs=root/'configs';configs.mkdir()
  markers=root/'markers.jsonl';config=configs/'root.toml';child=configs/'child.toml'
  for args in [('init','-q','-b','main'),('config','user.email','test@example.com'),('config','user.name','Synthetic Audit')]:git(cwd,*args)
  (cwd/'base.txt').write_text('tracked fixture\n');git(cwd,'add','.');git(cwd,'commit','-qm','base fixture')
  filename='memory.jsonl' if backend=='jsonl_memory' else 'memory.sqlite'
  absolute=str(root/filename) if mode=='worktree-absolute' else ''
  common=f'''active_provider = "fake"
[providers.fake]
provider = "fake"
model = "fake-tool-model"
[modules]
workflow = "memory_lifetime_probe"
policy = "fixture_allow_all"
[components.workflow]
command = "python3"
args = ["-B", {json.dumps(str(E/'workflow.py'))}, {json.dumps(str(markers))}]
[components.workflow.exports.workflow.memory_lifetime_probe]
[components.policy]
command = "python3"
args = ["-B", {json.dumps(str(CORE/'crates/proteus-core/tests/fixtures/process_allow_all_policy.py'))}]
[components.policy.exports.policy.fixture_allow_all]
[components.test-model]
command = {json.dumps(str(REFERENCE))}
[components.test-model.exports.model.fake]
[module_config.model.fake]
implementation = "fake"
[components.memory]
command = {json.dumps(str(memory_binary))}
[components.memory.exports.tool.{backend}]
[tools]
enabled = ["remember_fact", "recall_memory"]
'''
  if absolute:common+=f'[module_config.tool.{backend}]\npath = {json.dumps(absolute)}\n'
  isolation_line='' if mode=='shared-default' else 'isolation = "worktree"'
  config.write_text(common+f'''[agent_control]
surface = "task"
max_depth = 1
max_idle_processes = 2
[[agent_control.roles]]
name = "rememberer"
description = "synthetic authorized memory writer"
config = {json.dumps(str(child))}
{isolation_line}
timeout_ms = 20000
''')
  child.write_text(common+'[agent_control]\nsurface = "none"\nmax_depth = 0\n')
  env=os.environ.copy();env.update(HOME=str(root),XDG_DATA_HOME=str(root/'data'),XDG_CONFIG_HOME=str(root/'config'),PROTEUS_CONFIG_HOME=str(root/'config'),PYTHONDONTWRITEBYTECODE='1')
  p=subprocess.Popen([str(BINARY),'--config',str(config),'--cwd',str(cwd),'--new-session','server','stdio'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,env=env,start_new_session=True)
  outputs=[];errors=[];lines=queue.Queue()
  def read():
   for line in p.stdout:
    try:v=json.loads(line)
    except Exception:v={'raw':line}
    outputs.append(v);lines.put(v)
  threading.Thread(target=read,daemon=True).start();threading.Thread(target=lambda:errors.extend(p.stderr.readlines()),daemon=True).start()
  def send(v):p.stdin.write(json.dumps(v)+'\n');p.stdin.flush()
  request={'phase':'root','dirty':mode=='worktree-dirty','absolute_path':absolute,'filename':filename,'fact':'unique factual memory '+backend+' '+mode}
  send({'type':'send','id':'main','text':json.dumps(request)})
  deadline=time.monotonic()+40;response=None
  while time.monotonic()<deadline:
   try:v=lines.get(timeout=.1)
   except queue.Empty:
    if p.poll() is not None:break
    continue
   if v.get('type')=='response' and v.get('id')=='main':response=v;break
  records=[json.loads(x) for x in markers.read_text().splitlines()] if markers.exists() else []
  before=next((r for r in records if r['name']=='before_return'),None)
  path=pathlib.Path(before['value']['memory_path']) if before else None
  summary={'backend':backend,'mode':mode,'fixture_root':str(root),'response':response,'before_return':before,'after_memory_exists':path.exists() if path else None,'after_child_cwd_exists':pathlib.Path(before['cwd']).exists() if before else None,'worktrees':git(cwd,'worktree','list','--porcelain'),'branches':git(cwd,'branch','--list')}
  if before and pathlib.Path(before['cwd']).exists():summary['git_status']=git(pathlib.Path(before['cwd']),'status','--porcelain','--ignored')
  before_shutdown=list(outputs)
  if p.poll() is None:send({'type':'shutdown','id':'shutdown'})
  try:p.wait(timeout=4)
  except subprocess.TimeoutExpired:os.killpg(p.pid,signal.SIGTERM);p.wait(timeout=4)
  stem=backend+'-'+mode
  (E/(stem+'-outputs.json')).write_text(json.dumps(before_shutdown,indent=2));(E/(stem+'-markers.jsonl')).write_text(markers.read_text() if markers.exists() else '');(E/(stem+'-stderr.log')).write_text(''.join(errors));(E/(stem+'-summary.json')).write_text(json.dumps(summary,indent=2));print(json.dumps(summary,ensure_ascii=False),flush=True)
