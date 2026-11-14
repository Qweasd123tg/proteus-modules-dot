#!/usr/bin/env python3
"""Deployment catalog boundary: exact source projection + real Core API on loopback."""
from pathlib import Path
import os,sys,time,json,subprocess,hashlib,shutil,argparse,urllib.request,urllib.error,urllib.parse,signal,queue,threading
ROOT=Path(__file__).resolve().parent
parser=argparse.ArgumentParser()
parser.add_argument('--core',type=Path,required=True)
parser.add_argument('--modules',type=Path,required=True)
parser.add_argument('--core-binary',type=Path,required=True)
parser.add_argument('--module-binary',type=Path,required=True)
a=parser.parse_args()
CORE=a.core.resolve();BIN=a.core_binary.resolve();MEMORY=a.module_binary.resolve()
EXPORTS=json.loads(subprocess.check_output(['git','show','HEAD:components/memory-pack-module/exports.json'],cwd=a.modules,text=True))
PROBE=ROOT/'target/debug/component-deployment-inventory-probe'
R=ROOT/f'run-{time.time_ns()}';R.mkdir()
HOME=R/'home';HOME.mkdir()
AGENT=HOME/'.proteus';SNAP=AGENT/'releases/fixture';(SNAP/'bin').mkdir(parents=True)
WRAPPER=HOME/'.local/bin/proteus';WRAPPER.parent.mkdir(parents=True)
core_install=subprocess.check_output(['git','show','HEAD:install.sh'],cwd=CORE,text=True)
wrapper=core_install.split("<<'WRAPPER'\n",1)[1].split('\nWRAPPER',1)[0]+'\n'
WRAPPER.write_text(wrapper);WRAPPER.chmod(0o755)
shutil.copy2(BIN,SNAP/'proteus');shutil.copy2(MEMORY,SNAP/'bin/proteus-memory-pack-module')
(AGENT/'current').symlink_to('releases/fixture')
metadata=SNAP/'share/modules/memory-pack/module.json';metadata.parent.mkdir(parents=True)
metadata.write_text(json.dumps({'id':'memory-pack','version':'0.1.0-alpha.3','command':['bin/proteus-memory-pack-module'],'exports':EXPORTS,'sha256':hashlib.sha256(MEMORY.read_bytes()).hexdigest()}))
NEW=AGENT/'modules/memory-pack-upgrade/bin/proteus-memory-pack-module';NEW.parent.mkdir(parents=True);shutil.copy2(MEMORY,NEW)
workspace=R/'workspace';workspace.mkdir()
profile=R/'profile.toml'
shutil.copy2(ROOT/'workflow.py',R/'workflow.py')
profile.write_text(f'''[modules]
workflow = "audit_tool_driver"
policy = "fixture_allow_all"
[components.workflow]
command = "python3"
args = ["-B", {json.dumps(str(R/'workflow.py'))}, {json.dumps(str(CORE/'examples/modules'))}]
[components.workflow.exports.workflow.audit_tool_driver]
[components.policy]
command = "python3"
args = ["-B", {json.dumps(str(CORE/'crates/proteus-core/tests/fixtures/process_allow_all_policy.py'))}]
[components.policy.exports.policy.fixture_allow_all]
[components.memory-pack]
command = "proteus-memory-pack-module"
[components.memory-pack.exports.tool.jsonl_memory]
[module_config.tool.jsonl_memory]
path = {json.dumps(str(workspace/'memory.jsonl'))}
[tools]
enabled = ["remember_fact", "recall_memory"]
''')
env={**os.environ,'HOME':str(HOME),'PROTEUS_HOME':str(AGENT),'PROTEUS_CONFIG_HOME':str(R/'config-home'),'PROTEUS_BIN':str(WRAPPER),'PATH':str(WRAPPER.parent)+os.pathsep+os.environ['PATH']}
for k in ('PROTEUS_MODULES_SOURCE','PROTEUS_EXTENSIONS_DIR'):
    env.pop(k,None)
err=(R/'core.stderr').open('w')
p=subprocess.Popen([str(WRAPPER),'--config',str(profile),'--cwd',str(workspace),'--new-session','server','http','--host','127.0.0.1','--port','0','--token','fixture-only-local-token','--ready-stdout'],env=env,text=True,stdout=subprocess.PIPE,stderr=err,start_new_session=True)
q=queue.Queue()
def reader():
    for line in p.stdout:
        with (R/'core.stdout').open('a') as f:f.write(line)
        try:q.put(json.loads(line))
        except ValueError:pass
    q.put(None)
threading.Thread(target=reader,daemon=True).start()
try:
    ready=q.get(timeout=45);assert ready and ready['type']=='http_ready',ready
    origin=ready['origin']
    query=''
    def api(data=None,path='/config/builder'):
        req=urllib.request.Request(origin+path+(query if path=='/config/builder' else ''),headers={'Authorization':'Bearer fixture-only-local-token','Content-Type':'application/json'},data=json.dumps(data).encode() if data is not None else None)
        try:
            with urllib.request.urlopen(req,timeout=30) as response: return response.status,json.load(response)
        except urllib.error.HTTPError as e:return e.code,json.load(e)
    status,created=api({'id':'fixture-new-session','workspace':str(workspace)},'/new-session')
    (R/'created.json').write_text(json.dumps(created,indent=2))
    assert status==200 and created.get('ok'),(status,created)
    query='?'+urllib.parse.urlencode({'session_dir':created['output']['session_dir']})
    status,snapshot=api();assert status==200,(status,snapshot)
    (R/'snapshot-before.json').write_text(json.dumps(snapshot,indent=2))
    def selection(binary):
        child_env=env.copy()
        if binary is None:child_env.pop('PROTEUS_BIN',None)
        else:child_env['PROTEUS_BIN']=str(binary)
        output=subprocess.check_output([str(PROBE),str(R/'snapshot-before.json'),str(NEW)],env=child_env,text=True)
        return json.loads(output)
    via_wrapper=selection(WRAPPER)
    default_path_backend=selection(None)
    assert default_path_backend==via_wrapper
    via_snapshot=selection(SNAP/'proteus')
    via_current=selection(AGENT/'current/proteus')
    assert via_wrapper['module_inventory_path'] is None,via_wrapper
    assert via_wrapper['replace']==[],via_wrapper
    assert len(via_snapshot['replace'])==1,via_snapshot
    assert via_current==via_snapshot,(via_current,via_snapshot)
    def request(selected):return {'component_packages':[{'id':'memory-pack','command':[str(NEW)],'exports':EXPORTS,'replace':selected['replace']}]}
    before=profile.read_bytes()
    failure=api(request(via_wrapper));assert failure[0]==400,failure
    assert 'component already exists: memory-pack' in json.dumps(failure),failure
    assert profile.read_bytes()==before
    result=api(request(via_snapshot));assert result[0]==200,result
    plugin=next(x for x in result[1]['plugins'] if x['id']=='memory-pack')
    assert plugin['command']==str(NEW),plugin
    (R/'snapshot-after.json').write_text(json.dumps(result[1],indent=2))
    output={'core_sha256':hashlib.sha256(BIN.read_bytes()).hexdigest(),'module_sha256':hashlib.sha256(MEMORY.read_bytes()).hexdigest(),'wrapper_sha256':hashlib.sha256(wrapper.encode()).hexdigest(),'wrapper':via_wrapper,'default_path_backend':default_path_backend,'snapshot_control':via_snapshot,'current_symlink_control':via_current,'wrapper_request':request(via_wrapper),'wrapper_failure':failure,'snapshot_control_request':request(via_snapshot),'snapshot_control_status':result[0],'updated_component':plugin,'failed_update_preserved_profile':True}
    (R/'results.json').write_text(json.dumps(output,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(output,ensure_ascii=False,indent=2),flush=True)
    print('EVIDENCE',R,flush=True)
finally:
    if p.poll() is None:os.killpg(p.pid,signal.SIGTERM)
    try:p.wait(timeout=10)
    except subprocess.TimeoutExpired:os.killpg(p.pid,signal.SIGKILL);p.wait(timeout=5)
    err.close()
