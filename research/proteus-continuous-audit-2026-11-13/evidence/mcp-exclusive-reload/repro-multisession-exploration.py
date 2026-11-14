#!/usr/bin/env python3
"""No production edits. Real Core HTTP saves and model-free tool invocations."""
from pathlib import Path
import argparse,fcntl,hashlib,json,os,queue,signal,subprocess,threading,time,tomllib,urllib.request,urllib.error,urllib.parse
R=Path(__file__).resolve().parent
p=argparse.ArgumentParser();p.add_argument('--core',type=Path,default=Path('/workspace/shared/proteus-review-20261112/core'));p.add_argument('--binary',type=Path,default=Path('/workspace/shared/trace-component-deployment-evidence/run-1794580123588475346/home/.proteus/releases/fixture/proteus'));a=p.parse_args();CORE=a.core.resolve();BINARY=a.binary.resolve()
F=R/f'run-{time.time_ns()}';F.mkdir();results={}
def run(label,mode,change):
 d=F/label;d.mkdir();(d/'home').mkdir();(d/'workspace').mkdir();cfg=d/'profile.toml'
 cfg.write_text(f'''[modules]\nworkflow="audit_tool_driver"\npolicy="fixture_allow_all"\n[components.workflow]\ncommand="python3"\nargs=["-B",{json.dumps(str(R/'workflow.py'))},{json.dumps(str(CORE/'examples/modules'))}]\n[components.workflow.exports.workflow.audit_tool_driver]\n[components.policy]\ncommand="python3"\nargs=["-B",{json.dumps(str(CORE/'crates/proteus-core/tests/fixtures/process_allow_all_policy.py'))}]\n[components.policy.exports.policy.fixture_allow_all]\n''')
 env={**os.environ,'HOME':str(d/'home'),'PROTEUS_HOME':str(d/'home/.proteus'),'PROTEUS_CONFIG_HOME':str(d/'config-home')}
 err=(d/'stderr').open('w');proc=subprocess.Popen([str(BINARY),'--config',str(cfg),'--cwd',str(d/'workspace'),'--new-session','server','http','--host','127.0.0.1','--port','0','--token','fixture-only','--ready-stdout'],env=env,text=True,stdout=subprocess.PIPE,stderr=err,start_new_session=True);q=queue.Queue()
 def reader():
  for line in proc.stdout:
   with (d/'stdout').open('a') as f:f.write(line)
   try:q.put(json.loads(line))
   except ValueError:pass
  q.put(None)
 t=threading.Thread(target=reader,daemon=True);t.start()
 def lock_free():
  with (d/'fixture.lock').open('a+') as f:
   try:fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB);return True
   except BlockingIOError:return False
 try:
  ready=q.get(timeout=30);assert ready and ready['type']=='http_ready',ready
  def api(path,data=None):
   req=urllib.request.Request(ready['origin']+path,headers={'Authorization':'Bearer fixture-only','Content-Type':'application/json'},data=json.dumps(data).encode() if data is not None else None)
   try:
    with urllib.request.urlopen(req,timeout=30) as r:return r.status,json.load(r)
   except urllib.error.HTTPError as e:return e.code,json.load(e)
  status,new=api('/new-session',{'id':'fixture','workspace':str(d/'workspace')});assert status==200 and new.get('ok'),new
  session=new['output']['session_dir'];query='?'+urllib.parse.urlencode({'session_dir':session})
  def tool(label):
   status,r=api('/send',{'id':label,'session_dir':session,'text':json.dumps({'tool':'fixture__echo','args':{}})});assert status==200,r
   return r
  status,base=api('/addons'+query);assert status==200
  settings=base['settings'];settings['mcp_servers']=[{'name':'fixture','command':'python3','args':['-B',str(R/'mcp.py'),mode,str(d)],'timeout_ms':2000}]
  status,first=api('/addons'+query,settings);assert status==200 and first['mcp_servers'][0]['tools']==['fixture__echo'],first
  time.sleep(1.2)
  before=api('/addons'+query)[1];before_call=tool('before');assert before_call.get('ok') and json.loads(before_call['output']['text'])['ok'],before_call
  settings=before['settings']
  if change:settings['addons']['disabled_skills'].append('unrelated-fixture-skill')
  before_events=(d/'mcp-events.jsonl').read_text().splitlines();status,saved=api('/addons'+query,settings)
  assert status==200,(status,saved)
  time.sleep(1.2)
  after=api('/addons'+query)[1];after_call=tool('after');free=lock_free()
  events=[json.loads(x) for x in (d/'mcp-events.jsonl').read_text().splitlines()]
  status,retried=api('/addons'+query,settings);assert status==200
  retry_call=tool('retry')
  result={'mode':mode,'change_unrelated_disabled_skill':change,'save_status':200,'before':before,'before_call':before_call,'saved':saved,'after':after,'after_call':after_call,'lock_free_after':free,'events_before_retry':events,'second_identical_save':retried,'retry_call':retry_call}
  (d/'results.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');return result
 finally:
  if proc.poll() is None:os.killpg(proc.pid,signal.SIGTERM)
  try:proc.wait(timeout=8)
  except subprocess.TimeoutExpired:os.killpg(proc.pid,signal.SIGKILL);proc.wait(timeout=5)
  t.join(timeout=2);err.close()
for label,mode,change in [('exclusive_unrelated','exclusive',True),('exclusive_noop','exclusive',False),('shared_control','shared',True)]:
 results[label]=run(label,mode,change)
 print(label,json.dumps({'after':results[label]['after']['mcp_servers'],'after_call':results[label]['after_call'],'lock_free':results[label]['lock_free_after'],'retry':results[label]['second_identical_save']['mcp_servers']},ensure_ascii=False),flush=True)
results['binary_sha256']=hashlib.sha256(BINARY.read_bytes()).hexdigest();results['core_head']=subprocess.check_output(['git','-C',str(CORE),'rev-parse','HEAD'],text=True).strip();(F/'results.json').write_text(json.dumps(results,ensure_ascii=False,indent=2)+'\n');print('EVIDENCE',F)
