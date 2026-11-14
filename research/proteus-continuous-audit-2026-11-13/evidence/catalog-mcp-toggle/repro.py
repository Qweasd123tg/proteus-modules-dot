#!/usr/bin/env python3
from pathlib import Path
import json,os,subprocess,time,urllib.request,urllib.error,urllib.parse,queue,threading,signal,shutil,hashlib,argparse
R=Path(__file__).resolve().parent
parser=argparse.ArgumentParser()
parser.add_argument('--core',type=Path,default=Path('/workspace/shared/proteus-review-20261112/core'))
parser.add_argument('--core-binary',type=Path,default=Path('/workspace/shared/trace-component-deployment-evidence/run-1794580123588475346/home/.proteus/releases/fixture/proteus'))
a=parser.parse_args();CORE=a.core.resolve();BINARY=a.core_binary.resolve()
PROBE=R/'target/debug/catalog-mcp-toggle-probe'
F=R/f'run-{time.time_ns()}';F.mkdir();(F/'home').mkdir();(F/'workspace').mkdir()
shutil.copy2(R/'workflow.py',F/'workflow.py');shutil.copy2(R/'mcp.py',F/'mcp.py')
profile=F/'profile.toml'
profile.write_text(f'''[modules]
workflow = "audit_tool_driver"
policy = "fixture_allow_all"
[components.workflow]
command = "python3"
args = ["-B", {json.dumps(str(F/'workflow.py'))}, {json.dumps(str(CORE/'examples/modules'))}]
[components.workflow.exports.workflow.audit_tool_driver]
[components.policy]
command = "python3"
args = ["-B", {json.dumps(str(CORE/'crates/proteus-core/tests/fixtures/process_allow_all_policy.py'))}]
[components.policy.exports.policy.fixture_allow_all]
''')
env={**os.environ,'HOME':str(F/'home'),'PROTEUS_HOME':str(F/'home/.proteus'),'PROTEUS_CONFIG_HOME':str(F/'config-home')}
err=(F/'core.stderr').open('w')
p=subprocess.Popen([str(BINARY),'--config',str(profile),'--cwd',str(F/'workspace'),'--new-session','server','http','--host','127.0.0.1','--port','0','--token','fixture-only-local-token','--ready-stdout'],env=env,text=True,stdout=subprocess.PIPE,stderr=err,start_new_session=True)
q=queue.Queue()
def reader():
 for line in p.stdout:
  with (F/'core.stdout').open('a') as f:f.write(line)
  try:q.put(json.loads(line))
  except ValueError:pass
 q.put(None)
threading.Thread(target=reader,daemon=True).start()
try:
 ready=q.get(timeout=45);assert ready and ready['type']=='http_ready',ready;origin=ready['origin'];query=''
 def api(data=None,path='/config/builder'):
  req=urllib.request.Request(origin+path+(query if path=='/config/builder' else ''),headers={'Authorization':'Bearer fixture-only-local-token','Content-Type':'application/json'},data=json.dumps(data).encode() if data is not None else None)
  try:
   with urllib.request.urlopen(req,timeout=30) as resp:return resp.status,json.load(resp)
  except urllib.error.HTTPError as e:return e.code,json.load(e)
 status,new=api({'id':'fixture-session','workspace':str(F/'workspace')},'/new-session');assert status==200 and new.get('ok'),new
 query='?'+urllib.parse.urlencode({'session_dir':new['output']['session_dir']})
 def fetch():
  status,snap=api();assert status==200,(status,snap);(F/'snapshot.json').write_text(json.dumps(snap));return snap
 def probe(mode):return json.loads(subprocess.check_output([str(PROBE),mode,str(F)],text=True,env=env))
 fetch();install_req=probe('prepare');(F/'install-request.json').write_text(json.dumps(install_req,indent=2))
 status,installed=api(install_req);assert status==200,(status,installed);(F/'installed-snapshot.json').write_text(json.dumps(installed,indent=2))
 assert installed['addon_settings']['mcp_servers'][0]['enabled'] is False
 fetch();toggle_req=probe('toggle');(F/'toggle-request.json').write_text(json.dumps(toggle_req,indent=2));status,toggled=api(toggle_req);assert status==200,(status,toggled)
 (F/'toggled-snapshot.json').write_text(json.dumps(toggled,indent=2));assert toggled['addon_settings']['mcp_servers'][0]['enabled'] is True
 fetch();result=probe('check')
 # Verify actual persisted profile has successful toggle, independently of Desktop model.
 assert 'enabled = true' in profile.read_text(),profile.read_text()
 result.update({'initial_catalog_install_status':200,'ordinary_UI_toggle_save_status':200,'persisted_enabled':True,'fixture':str(F),'core_sha256':hashlib.sha256(BINARY.read_bytes()).hexdigest(),'probe_sha256':hashlib.sha256(PROBE.read_bytes()).hexdigest()})
 (F/'results.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');print(json.dumps(result,ensure_ascii=False,indent=2),flush=True)
finally:
 if p.poll() is None:os.killpg(p.pid,signal.SIGTERM)
 try:p.wait(timeout=10)
 except subprocess.TimeoutExpired:os.killpg(p.pid,signal.SIGKILL);p.wait(timeout=5)
 err.close()
