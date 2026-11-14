import json,os,pathlib,queue,subprocess,tempfile,threading,time,signal,hashlib
E=pathlib.Path(__file__).resolve().parent
CORE=pathlib.Path('/workspace/shared/proteus-review-20261112/core')
BINARY=pathlib.Path('/workspace/shared/nested-lifetime-evidence/proteus')
MODS=pathlib.Path('/workspace/shared/disabled-skill-context-target/debug')
REFERENCE=CORE/'target/sources/modules/target/debug/proteus-reference-module'
root=pathlib.Path(tempfile.mkdtemp(prefix='proteus-disabled-skill-'));cwd=root/'workspace';cwd.mkdir()
(cwd/'.git').mkdir()
skills=cwd/'.proteus/skills'
for name in ['review','testing']:(skills/name).mkdir(parents=True)
def valid(name):return f'---\nname: {name}\ndescription: {name} synthetic instructions\n---\nUse the synthetic {name} procedure.\n'
review=skills/'review/SKILL.md';review.write_text(valid('review'));(skills/'testing/SKILL.md').write_text(valid('testing'))
config=root/'profile.toml'
config.write_text(f'''active_provider = "fake"
[providers.fake]
provider = "fake"
model = "fake-tool-model"
[modules]
workflow = "coding.codex_loop"
context = "codex_context"
[components.workflow]
command = {json.dumps(str(MODS/'proteus-coding-workflow-module'))}
[components.workflow.exports.workflow."coding.codex_loop"]
[components.context]
command = {json.dumps(str(MODS/'proteus-context-pack-module'))}
[components.context.exports.context.codex_context]
[module_config.context.codex_context]
providers = ["skills"]
[components.skills]
command = {json.dumps(str(MODS/'proteus-skill-pack-module'))}
[components.skills.exports.context_provider.skills]
[components.skills.exports.tool.skill_tool]
[components.test-model]
command = {json.dumps(str(REFERENCE))}
[components.test-model.exports.model.fake]
[module_config.model.fake]
implementation = "fake"
[tools]
enabled = ["skill"]
[addons]
disabled_skills = ["review"]
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
results={}
try:
 results['valid_disabled']=request('valid-disabled','Say hello in this synthetic context test.')
 review.write_text('---\nname: review\ndescription: [\n---\nCorrupted disabled skill.\n')
 results['malformed_disabled']=request('malformed-disabled','Say hello again; no skill invocation is requested.')
 review.write_text(valid('review'))
 results['restored_disabled']=request('restored-disabled','Say hello after the disabled file is restored.')
finally:
 if p.poll() is None:send({'type':'shutdown','id':'shutdown'})
 try:p.wait(timeout=4)
 except subprocess.TimeoutExpired:os.killpg(p.pid,signal.SIGTERM);p.wait(timeout=4)
(E/'outputs.json').write_text(json.dumps(outputs,indent=2));(E/'stderr.log').write_text(''.join(errors));(E/'results.json').write_text(json.dumps(results,indent=2));(E/'profile.toml').write_text(config.read_text())
for name,v in results.items(): print(name,json.dumps(v['response']))
(E/'provenance.json').write_text(json.dumps({'fixture_root':str(root),'core':'89997df995df7c39b713e16aba216ecb19c8f497','modules':'3270dc0f894eaf4d0360306052b806099b8f5351','binary_sha256':{str(x):hashlib.sha256(x.read_bytes()).hexdigest() for x in [BINARY,REFERENCE,*[MODS/name for name in ['proteus-coding-workflow-module','proteus-context-pack-module','proteus-skill-pack-module']]]}},indent=2))
