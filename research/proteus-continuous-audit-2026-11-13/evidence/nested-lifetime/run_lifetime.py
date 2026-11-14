import hashlib,json,os,pathlib,queue,subprocess,tempfile,threading,time,signal
E=pathlib.Path(__file__).resolve().parent
CORE=pathlib.Path('/workspace/shared/background-agent-chain-audit')
BINARY=E/'proteus'
REFERENCE=pathlib.Path('/workspace/shared/proteus-review-20261112/core/target/sources/modules/target/debug/proteus-reference-module')
def git(path,*args):
 r=subprocess.run(['git','-C',str(path),*args],capture_output=True,text=True)
 assert r.returncode==0,repr((args,r.stderr));return r.stdout
for mode in ['clean-background','dirty-background','clean-wait']:
 root=pathlib.Path(tempfile.mkdtemp(prefix='proteus-lifetime-'+mode+'-'));cwd=root/'workspace';cwd.mkdir();configs=root/'configs';configs.mkdir()
 markers=root/'markers.jsonl';release=root/'release';ready=root/'ready';config=configs/'root.toml';parent=configs/'parent.toml';leaf=configs/'leaf.toml'
 for args in [('init','-q','-b','main'),('config','user.email','test@example.com'),('config','user.name','Synthetic Audit')]:git(cwd,*args)
 (cwd/'base.txt').write_text('tracked base remains useful to an active reader\n');git(cwd,'add','.');git(cwd,'commit','-qm','base fixture')
 common=f'''active_provider = "fake"
[providers.fake]
provider = "fake"
model = "fake-tool-model"
[modules]
workflow = "lifetime_probe"
policy = "fixture_allow_all"
[components.workflow]
command = "python3"
args = [{json.dumps(str(E/'lifetime_fixture.py'))}, {json.dumps(str(markers))}, {json.dumps(str(release))}, {json.dumps(str(ready))}]
[components.workflow.exports.workflow.lifetime_probe]
[components.policy]
command = "python3"
args = [{json.dumps(str(CORE/'crates/proteus-core/tests/fixtures/process_allow_all_policy.py'))}]
[components.policy.exports.policy.fixture_allow_all]
[components.test-model]
command = {json.dumps(str(REFERENCE))}
[components.test-model.exports.model.fake]
[module_config.model.fake]
implementation = "fake"
'''
 config.write_text(common+f'''[agent_control]
surface = "task"
max_depth = 3
max_idle_processes = 4
[[agent_control.roles]]
name = "parent"
description = "isolated parent"
config = {json.dumps(str(parent))}
isolation = "worktree"
timeout_ms = 20000
''')
 parent.write_text(common+f'''[agent_control]
surface = "collaboration"
max_depth = 3
max_idle_processes = 4
[[agent_control.roles]]
name = "reader"
description = "read-only background peer"
config = {json.dumps(str(leaf))}
parallel_safe = true
timeout_ms = 20000
''')
 leaf.write_text(common+'[agent_control]\nsurface = "none"\nmax_depth = 0\n')
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
  if mode=='clean-wait' and ready.exists():release.touch()
  try:v=lines.get(timeout=.02)
  except queue.Empty:
   if p.poll() is not None:break
   continue
  if v.get('type')=='response' and v.get('id')=='main':response=v;break
 # At this exact point root's finalization and cleanup have finished. Only now may background reader read.
 released_at=time.time();release.touch()
 deadline=time.monotonic()+4
 while time.monotonic()<deadline:
  if markers.exists() and 'reader_result' in markers.read_text():break
  time.sleep(.02)
 records=[json.loads(x) for x in markers.read_text().splitlines()] if markers.exists() else []
 reader_result=next((r for r in records if r['name']=='reader_result'),None)
 summary={'mode':mode,'root':str(root),'response':response,'release_at':released_at,'reader_result':reader_result,'worktrees':git(cwd,'worktree','list','--porcelain'),'branches':git(cwd,'branch','--list')}
 before_shutdown=list(outputs)
 send({'type':'shutdown','id':'shutdown'})
 try:p.wait(timeout=4)
 except subprocess.TimeoutExpired:os.killpg(p.pid,signal.SIGTERM);p.wait(timeout=4)
 (E/(mode+'-outputs.json')).write_text(json.dumps(before_shutdown,indent=2));(E/(mode+'-markers.jsonl')).write_text(markers.read_text() if markers.exists() else '');(E/(mode+'-stderr.log')).write_text(''.join(errors));(E/(mode+'-summary.json')).write_text(json.dumps(summary,indent=2));print(json.dumps(summary,ensure_ascii=False))
