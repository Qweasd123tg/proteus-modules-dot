#!/usr/bin/env python3
from pathlib import Path
import argparse,json,os,subprocess,time,urllib.request,urllib.error,urllib.parse,queue,threading,signal,hashlib
R=Path(__file__).resolve().parent
p=argparse.ArgumentParser();p.add_argument('--core',type=Path,default=Path('/workspace/shared/proteus-review-20261112/core'));p.add_argument('--binary',type=Path,default=Path('/workspace/shared/trace-component-deployment-evidence/run-1794580123588475346/home/.proteus/releases/fixture/proteus'));a=p.parse_args();CORE=a.core.resolve();BINARY=a.binary.resolve();PROBE=R/'target/debug/mcp-rename-probe'
F=R/f'run-{time.time_ns()}';F.mkdir();results={}
for mode in ['direct','stepped','undo']:
 d=F/mode;d.mkdir();(d/'home').mkdir();(d/'workspace').mkdir();cfg=d/'profile.toml';events=d/'mcp-events.log'
 txt=f'''[modules]\nworkflow = "audit_tool_driver"\npolicy = "fixture_allow_all"\n[components.workflow]\ncommand = "python3"\nargs = ["-B", {json.dumps(str(R/'workflow.py'))}, {json.dumps(str(CORE/'examples/modules'))}]\n[components.workflow.exports.workflow.audit_tool_driver]\n[components.policy]\ncommand = "python3"\nargs = ["-B", {json.dumps(str(CORE/'crates/proteus-core/tests/fixtures/process_allow_all_policy.py'))}]\n[components.policy.exports.policy.fixture_allow_all]\n[addons]\ndisabled_mcp_servers=["db"]\n'''
 for name,label in [('db','original_db'),('db2','existing_db2')]:
  txt+='\n[[tools.mcp_servers]]\n'+f'name={json.dumps(name)}\nenabled=true\ncommand="python3"\nargs=["-B",{json.dumps(str(R/"mcp.py"))},{json.dumps(label)},{json.dumps(str(events))}]\ntimeout_ms=2000\n'
 cfg.write_text(txt);env={**os.environ,'HOME':str(d/'home'),'PROTEUS_HOME':str(d/'home/.proteus'),'PROTEUS_CONFIG_HOME':str(d/'config-home')}
 err=(d/'stderr').open('w');proc=subprocess.Popen([str(BINARY),'--config',str(cfg),'--cwd',str(d/'workspace'),'--new-session','server','http','--host','127.0.0.1','--port','0','--token','fixture-only','--ready-stdout'],env=env,text=True,stdout=subprocess.PIPE,stderr=err,start_new_session=True);q=queue.Queue()
 def reader():
  for line in proc.stdout:
   with (d/'stdout').open('a') as f:f.write(line)
   try:q.put(json.loads(line))
   except ValueError:pass
  q.put(None)
 threading.Thread(target=reader,daemon=True).start()
 try:
  ready=q.get(timeout=30);assert ready and ready['type']=='http_ready',ready
  def api(path,data=None):
   req=urllib.request.Request(ready['origin']+path,headers={'Authorization':'Bearer fixture-only','Content-Type':'application/json'},data=json.dumps(data).encode() if data is not None else None)
   try:
    with urllib.request.urlopen(req,timeout=30) as r:return r.status,json.load(r)
   except urllib.error.HTTPError as e:return e.code,json.load(e)
  status,new=api('/new-session',{'id':'fixture','workspace':str(d/'workspace')});assert status==200 and new.get('ok'),new
  query='?'+urllib.parse.urlencode({'session_dir':new['output']['session_dir']})
  status,snapshot=api('/config/builder'+query);assert status==200;(d/'snapshot.json').write_text(json.dumps(snapshot,indent=2))
  events_before=events.read_text().splitlines();assert not any(x.startswith('original_db:') for x in events_before)
  projected=json.loads(subprocess.check_output([str(PROBE),mode,str(d)],text=True));(d/'projection.json').write_text(json.dumps(projected,ensure_ascii=False,indent=2))
  status,saved=api('/config/builder'+query,projected['request']);assert status==200,(status,saved)
  status,addons=api('/addons'+query);assert status==200
  state={s['name']:s['enabled'] for s in addons['mcp_servers']};events_after=events.read_text().splitlines()
  expected={'db20':False,'db2':True} if mode=='direct' else ({'db20':True,'db2':False} if mode=='stepped' else {'db':True,'db2':False})
  assert state==expected,(mode,state);new_spawns=events_after[len(events_before):]
  assert any(x.startswith('original_db:') for x in new_spawns)==(mode!='direct'),new_spawns
  results[mode]={'http_save_status':200,'before':projected['before'],'after':projected['after'],'runtime_enabled':state,'new_process_spawns':new_spawns,'final_validation_errors':projected['final_validation_errors'],'direct_control_preserves_switches':projected['direct_rename_preserves_switches']}
  (d/'addons-after.json').write_text(json.dumps(addons,ensure_ascii=False,indent=2));(d/'config-after.json').write_text(json.dumps(saved,ensure_ascii=False,indent=2))
 finally:
  if proc.poll() is None:os.killpg(proc.pid,signal.SIGTERM)
  try:proc.wait(timeout=8)
  except subprocess.TimeoutExpired:os.killpg(proc.pid,signal.SIGKILL);proc.wait(timeout=5)
  err.close()
results['binary_sha256']=hashlib.sha256(BINARY.read_bytes()).hexdigest();results['probe_sha256']=hashlib.sha256(PROBE.read_bytes()).hexdigest();(F/'results.json').write_text(json.dumps(results,ensure_ascii=False,indent=2)+'\n');print(json.dumps({'evidence':str(F),**results},ensure_ascii=False,indent=2))
