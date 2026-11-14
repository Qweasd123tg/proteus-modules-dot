import json,os,pathlib,queue,subprocess,tempfile,threading,time,signal,hashlib
E=pathlib.Path(__file__).resolve().parent
CORE=pathlib.Path('/workspace/shared/proteus-review-20261112/core')
BINARY=pathlib.Path('/workspace/shared/nested-lifetime-evidence/proteus')
MODS=pathlib.Path('/workspace/shared/disabled-skill-context-target/debug')
root=pathlib.Path(tempfile.mkdtemp(prefix='proteus-skills-budget-'));cwd=root/'workspace';cwd.mkdir()
(cwd/'.git').mkdir()
skills=cwd/'.proteus/skills'
def write_skills(count):
 for i in range(count):
  name=f'procedure-{i:03}'
  directory=skills/name;directory.mkdir(parents=True,exist_ok=True)
  description=(f'Procedure {i:03}. Review implementation details, verify affected invariants, run focused checks, inspect regressions, and report observed outcomes. ' * 8)[:900]
  (directory/'SKILL.md').write_text(f'---\nname: {name}\ndescription: {description}\n---\nSynthetic workflow body {i:03}.\n')
write_skills(40)
config=root/'profile.toml'
config.write_text(f'''active_provider = "fake"
[providers.fake]
provider = "fake"
model = "fake-tool-model"
[modules]
workflow = "coding.codex_loop"
context = "codex_context"
policy = "fixture_allow_all"
[components.policy]
command = "python3"
args = ["-B", {json.dumps(str(CORE/'crates/proteus-core/tests/fixtures/process_allow_all_policy.py'))}]
[components.policy.exports.policy.fixture_allow_all]
[components.workflow]
command = {json.dumps(str(MODS/'proteus-coding-workflow-module'))}
[components.workflow.exports.workflow."coding.codex_loop"]
[components.context]
command = {json.dumps(str(MODS/'proteus-context-pack-module'))}
[components.context.exports.context.codex_context]
[module_config.context.codex_context]
providers = ["project_instructions", "skills", "environment"]
[components.skills]
command = {json.dumps(str(MODS/'proteus-skill-pack-module'))}
[components.skills.exports.context_provider.skills]
[components.skills.exports.tool.skill_tool]
[components.test-model]
command = "python3"
args = ["-B", {json.dumps(str(E/"capture_model.py"))}]
[components.test-model.exports.model.fake]
[module_config.model.fake]
capture_path = {json.dumps(str(E/"model-requests.jsonl"))}
[tools]
enabled = ["skill"]
[agent_control]
surface = "none"
max_depth = 0
''')
env=os.environ.copy();env.update(HOME=str(root),PROTEUS_HOME=str(root/'proteus-home'),XDG_DATA_HOME=str(root/'data'),XDG_CONFIG_HOME=str(root/'config'),PROTEUS_CONFIG_HOME=str(root/'config'),PYTHONDONTWRITEBYTECODE='1')
p=subprocess.Popen([str(BINARY),'--config',str(config),'--cwd',str(cwd),'--new-session','server','stdio'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,env=env,start_new_session=True)
outputs=[];errors=[];lines=queue.Queue()
def read():
 for line in p.stdout:
  try:v=json.loads(line)
  except Exception:v={'raw':line}
  outputs.append(v);lines.put(v)
threading.Thread(target=read,daemon=True).start();threading.Thread(target=lambda:errors.extend(p.stderr.readlines()),daemon=True).start()
def send(v):p.stdin.write(json.dumps(v)+'\n');p.stdin.flush()
def request(i,text):
 start=len(outputs);send({'type':'send','id':i,'text':text});deadline=time.monotonic()+40
 while time.monotonic()<deadline:
  try:v=lines.get(timeout=.1)
  except queue.Empty:
   if p.poll() is not None:break
   continue
  if v.get('type')=='response' and v.get('id')==i:return {'response':v,'events':outputs[start:]}
 raise RuntimeError(f'no response: {i}, stderr={errors}')
from catalog import catalog
results={}
catalogs={}
(E/"model-requests.jsonl").write_text("")
try:
 catalogs['forty']=catalog(MODS/'proteus-skill-pack-module',cwd,root)
 results['forty']=request('forty','Inspect the workspace workflows.')
 write_skills(60)
 catalogs['sixty']=catalog(MODS/'proteus-skill-pack-module',cwd,root)
 results['sixty']=request('sixty','Inspect the workspace workflows again.')
 results['sixty_tool']=request('sixty-tool','LOAD procedure-000')
 for i in range(40,60):
  path=skills/f'procedure-{i:03}'/'SKILL.md';path.rename(path.with_name('SKILL.parked'))
 results['restored_forty']=request('restored-forty','Inspect the workspace workflows after restoration.')
 # A normal-sized rules file can also remove an otherwise fitting catalogue.
 (cwd/'AGENTS.md').write_text(('Project rules: report only verified results.\n' * 700)[:20000])
 results['forty_with_rules']=request('forty-with-rules','Inspect workflows with project instructions.')
finally:
 if p.poll() is None:send({'type':'shutdown','id':'shutdown'})
 try:p.wait(timeout=4)
 except subprocess.TimeoutExpired:os.killpg(p.pid,signal.SIGTERM);p.wait(timeout=4)
(E/'outputs.json').write_text(json.dumps(outputs,indent=2));(E/'stderr.log').write_text(''.join(errors));(E/'results.json').write_text(json.dumps(results,indent=2));(E/'profile.toml').write_text(config.read_text())
(E/'catalogs.json').write_text(json.dumps(catalogs,indent=2))
for name,v in results.items(): print(name,json.dumps(v['response']))
(E/'provenance.json').write_text(json.dumps({'fixture_root':str(root),'core':'89997df995df7c39b713e16aba216ecb19c8f497','modules':'3270dc0f894eaf4d0360306052b806099b8f5351','binary_sha256':{str(x):hashlib.sha256(x.read_bytes()).hexdigest() for x in [BINARY,*[MODS/name for name in ['proteus-coding-workflow-module','proteus-context-pack-module','proteus-skill-pack-module']]]}},indent=2))
